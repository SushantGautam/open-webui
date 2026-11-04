"""GenAI retrieval and embedding instrumentation."""

import functools
import inspect

from open_webui.utils.telemetry.genai import content, semconv
from open_webui.utils.telemetry.genai.extractors import capture
from open_webui.utils.telemetry.genai.tracer import GenAITracer


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
            collections = sorted({
                item['collection_name']
                for item in values.get('items') or []
                if isinstance(item, dict) and isinstance(item.get('collection_name'), str)
            })
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
