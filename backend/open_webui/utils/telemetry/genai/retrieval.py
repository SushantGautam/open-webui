"""GenAI retrieval and embedding instrumentation."""

import functools
import inspect
import json
import re
import logging

from open_webui.utils.telemetry.genai import compact, content, semconv
from open_webui.utils.telemetry.genai.extractors import capture
from open_webui.utils.telemetry.genai.tracer import GenAITracer

logger = logging.getLogger(__name__)


def instrument_embedding(tracer: GenAITracer, embedding_function, model: str | None = None):
    if embedding_function is None:
        return None

    async def wrapped(query, *args, **kwargs):
        with tracer.embedding(
            f'embeddings {model}' if model else 'embeddings',
            operation_name='embeddings',
            request_model=model,
            embedding_text=query,
        ) as span:
            result = await embedding_function(query, *args, **kwargs)
            if span.is_recording() and result is not None:
                try:
                    # Only record the dimension count, not the vectors themselves.
                    sample = result[0] if len(result) and not isinstance(result[0], (int, float)) else result
                    if len(sample):
                        span.set_attribute(semconv.GEN_AI_EMBEDDINGS_DIMENSION_COUNT, len(sample))
                except (TypeError, IndexError, KeyError):
                    pass
                if tracer.config.capture_embedding_vectors:
                    value = capture(result, enabled=True, config=tracer.config)
                    if value is not None:
                        # No standard gen_ai.embeddings attribute for raw vectors.
                        span.set_attribute(semconv.OPENWEBUI_EMBEDDING_VECTORS, value)
            return result

    return wrapped


def instrument_reranker(tracer: GenAITracer, reranking_function):
    if reranking_function is None:
        return None

    def wrapped(query, documents, *args, **kwargs):
        # Rerank isn't a standardized gen_ai.operation.name; use an internal
        # application span and preserve the retrieval pipeline parent.
        with tracer.rerank('rerank', retrieval_query=query) as span:
            result = reranking_function(query, documents, *args, **kwargs)
            if span.is_recording():
                span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_CANDIDATE_COUNT, len(documents))
            return result

    return wrapped


def _embedding_model(request) -> str | None:
    config = getattr(getattr(getattr(request, 'app', None), 'state', None), 'config', None)
    return getattr(config, 'RAG_EMBEDDING_MODEL', None) or None


def _retrieved_documents(sources, maximum, limit):
    """Flatten Open WebUI sources into the official retrieval document schema.

    A source has parallel document[] and metadata[] arrays. Vector distances
    are NOT relevance scores; do not emit them as gen_ai score.
    """
    documents = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        snippets = source.get('document') or []
        metadatas = source.get('metadata') or []
        if isinstance(snippets, str):
            snippets = [snippets]
        if isinstance(metadatas, dict):
            metadatas = [metadatas]
        parent = source.get('source') or {}
        parent = parent if isinstance(parent, dict) else {}
        for index, text in enumerate(snippets):
            if len(documents) >= maximum:
                return documents
            meta = metadatas[index] if index < len(metadatas) else {}
            meta = meta if isinstance(meta, dict) else {}
            doc = {}
            doc_id = meta.get('document_id') or meta.get('chunk_id') or meta.get('id')
            if doc_id is not None:
                doc['id'] = str(doc_id)
            score = meta.get('score')
            if isinstance(score, (float, int)) and not isinstance(score, bool):
                doc['score'] = float(score)
            filename = meta.get('name') or meta.get('source') or meta.get('file_name') or parent.get('name')
            if isinstance(filename, str):
                doc['source'] = filename[:limit]
            file_id = meta.get('file_id') or parent.get('id')
            if file_id is not None:
                doc['file_id'] = str(file_id)
            if isinstance(text, str):
                doc['content'] = text[:limit]
            documents.append(doc)
    return documents


def traced_retrieval(tracer: GenAITracer):
    def decorator(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            bound = inspect.signature(function).bind_partial(*args, **kwargs)
            values = bound.arguments
            queries = values.get('queries') or []
            query = queries[0] if isinstance(queries, list) and queries else queries
            collections = sorted(
                {
                    item['collection_name']
                    for item in values.get('items') or []
                    if isinstance(item, dict) and isinstance(item.get('collection_name'), str)
                }
            )
            data_source_id = collections[0] if len(collections) == 1 else None
            with tracer.retrieval(
                f'retrieval {data_source_id}' if data_source_id else 'retrieval',
                operation_name='retrieval',
                retrieval_query=query,
                retrieval_top_k=values.get('k'),
                data_source_id=data_source_id,
                candidate_count=len(values.get('items') or []),
                retrieval_mode='hybrid' if values.get('hybrid_search') else 'vector',
            ) as span:
                if span.is_recording() and len(collections) > 1:
                    span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_COLLECTION_NAMES, collections)
                if 'embedding_function' in values:
                    values['embedding_function'] = instrument_embedding(
                        tracer, values['embedding_function'], model=_embedding_model(values.get('request'))
                    )
                result = await function(*bound.args, **bound.kwargs)
                if span.is_recording() and isinstance(result, list):
                    if tracer.config.capture_retrieval_documents:
                        documents = _retrieved_documents(
                            result,
                            tracer.config.retrieval_max_documents,
                            tracer.config.content_max_length,
                        )
                        if documents:
                            span.set_attribute(
                                semconv.GEN_AI_RETRIEVAL_DOCUMENTS,
                                content.json_attribute(documents, tracer.config.content_max_length),
                            )
                    span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_SELECTED_COUNT, len(result))
                return result

        return wrapped

    return decorator


_TEXT_KEYS = ('content', 'snippet', 'text', 'body')
# A chunk's file_id names its file, not the chunk: it is kept as file_id, never as id.
_ID_KEYS = ('document_id', 'chunk_id', 'id', 'note_id', 'chat_id', 'message_id')
_SOURCE_KEYS = ('source', 'filename', 'title', 'name', 'link', 'url', 'path')
_CONTAINER_KEYS = ('messages', 'replies', 'results', 'items', 'documents')
_QUERY_ARGS = ('query', 'pattern', 'url', 'command', 'path', 'file_id', 'note_id', 'chat_id', 'message_id')
# A grep line: "<file id>  <filename>:<line>: <text>".
_GREP_LINE = re.compile(r'^(?P<id>\S+)\s{2}(?P<file>[^:\n]+):(?P<line>\d+): (?P<text>.*)$')
_NO_RESULT_PREFIXES = ('No matches for', 'Error:', 'Error -', 'No accessible files', 'No files')


def _document(item, limit, source=None):
    """One retrieval document from a result object that carries text, else None."""
    if not isinstance(item, dict):
        return None
    text = next((item[key] for key in _TEXT_KEYS if isinstance(item.get(key), str) and item[key]), None)
    if text is None:
        return None
    doc = {}
    for key in _ID_KEYS:
        if item.get(key) is not None and not isinstance(item[key], (dict, list)):
            doc['id'] = str(item[key])
            break
    score = item.get('score')
    if isinstance(score, (float, int)) and not isinstance(score, bool):
        doc['score'] = float(score)
    name = next((item[key] for key in _SOURCE_KEYS if isinstance(item.get(key), str) and item[key]), source)
    if isinstance(name, str) and name:
        doc['source'] = name[:limit]
    for key in ('link', 'url'):
        if isinstance(item.get(key), str) and item[key]:
            doc['url'] = item[key][:limit]
            break
    if item.get('file_id'):
        doc['file_id'] = str(item['file_id'])
    doc['content'] = text[:limit]
    return doc


def _text_documents(text, limit, source=None):
    """Documents from a plain-text tool result: grep lines grouped by file, else the text itself."""
    stripped = text.strip()
    if not stripped or stripped.startswith(_NO_RESULT_PREFIXES):
        return []
    files = {}
    for line in stripped.splitlines():
        match = _GREP_LINE.match(line)
        if match:
            entry = files.setdefault(match['id'], {'file_id': match['id'], 'source': match['file'], 'lines': []})
            entry['lines'].append(f'{match["line"]}: {match["text"]}')
    if files:
        return [
            {'file_id': f['file_id'], 'source': f['source'][:limit], 'content': '\n'.join(f['lines'])[:limit]}
            for f in files.values()
        ]
    doc = {'content': stripped[:limit]}
    if source:
        doc['source'] = str(source)[:limit]
    return [doc]


def _tool_documents(result, maximum, limit, source=None):
    """What a content-reading tool returned, in the retrieval document schema.

    Handles every shape the built-in tools return: a JSON list of chunks or
    results, one JSON object with text (a file, note or message), an object
    holding a list of messages or replies, and plain text (grep lines, command
    output, a fetched page). Error objects, "no matches" text and metadata-only
    listings yield no documents. Distances are not reported as scores.
    """
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError):
            return _text_documents(result, limit, source)[:maximum]
        if isinstance(parsed, str):
            return _text_documents(parsed, limit, source)[:maximum]
        result = parsed
    items = []
    if isinstance(result, dict):
        if result.get('error'):
            return []
        title = next((result[k] for k in ('title', 'filename', 'name') if isinstance(result.get(k), str)), source)
        own = _document(result, limit, source)
        if own:
            items.append(own)
        for key in _CONTAINER_KEYS:
            for item in result.get(key) or [] if isinstance(result.get(key), list) else []:
                doc = _document(item, limit, title)
                if doc:
                    items.append(doc)
        for key in ('parent_message', 'message'):
            doc = _document(result.get(key), limit, title)
            if doc:
                items.append(doc)
    elif isinstance(result, list):
        items = [doc for doc in (_document(item, limit, source) for item in result) if doc]
    return items[:maximum]


def _tool_chunks(result, maximum, limit):
    """Backwards-compatible name: the documents of a knowledge-search result."""
    return _tool_documents(result, maximum, limit)


def _first_argument(values, names):
    return next((values[name] for name in names if isinstance(values.get(name), (str, int)) and values[name]), None)


def traced_knowledge_tool(tracer: GenAITracer, data_source: str | None = None):
    """Trace a content-reading tool as a GenAI ``retrieval`` span with its documents.

    Built-in tools that read stored or web content (knowledge files, chat files,
    notes, chats, channel messages, memories, web pages) bypass the RAG pipeline
    traced by ``traced_retrieval``, so without this what they return exists only
    in the parent ``execute_tool`` span's result. The retrieval span is a child of
    that tool span; ``data_source`` names where the content came from
    (``gen_ai.data_source.id``). Inventory listings and write tools are not wrapped.
    """

    def decorator(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            values = signature.bind_partial(*args, **kwargs).arguments
            query = _first_argument(values, _QUERY_ARGS)
            with tracer.retrieval(
                f'retrieval {data_source}' if data_source else 'retrieval',
                operation_name='retrieval',
                retrieval_query=None if query is None else str(query),
                retrieval_top_k=values.get('count') if isinstance(values.get('count'), int) else None,
                data_source_id=data_source,
            ) as span:
                result = await function(*args, **kwargs)
                # Fail-open: a telemetry error must never break the tool.
                try:
                    if span.is_recording() and tracer.config.capture_retrieval_documents:
                        source = _first_argument(values, ('url', 'path', 'file_id', 'note_id', 'chat_id'))
                        documents = _tool_documents(
                            result,
                            tracer.config.retrieval_max_documents,
                            tracer.config.content_max_length,
                            None if source is None else str(source),
                        )
                        if documents:
                            span.set_attribute(
                                semconv.GEN_AI_RETRIEVAL_DOCUMENTS,
                                content.json_attribute(documents, tracer.config.content_max_length),
                            )
                            parsed = content.parse_json(result)
                            if tracer.config.content_mode == 'compact' and isinstance(parsed, list):
                                # A list of chunks: the tool's result and the later tool
                                # response carry these same chunks and refer back to them.
                                compact.remember_value(span, semconv.GEN_AI_RETRIEVAL_DOCUMENTS, parsed)
                except Exception:
                    logger.exception('Unable to record GenAI retrieval documents for a tool')
                return result

        return wrapped

    return decorator
