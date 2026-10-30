import functools
import inspect
import json

from open_webui.utils.telemetry.genai import semconv
from open_webui.utils.telemetry.genai.extractors import capture
from open_webui.utils.telemetry.genai.openinference import attributes_for
from open_webui.utils.telemetry.genai.tracer import GenAITracer


def instrument_embedding(tracer: GenAITracer, embedding_function, model: str | None = None):
    if embedding_function is None:
        return None

    async def wrapped(query, *args, **kwargs):
        # Standard span name `embeddings {gen_ai.request.model}`.
        with tracer.embedding(
            f'embeddings {model}' if model else 'embeddings',
            operation_name='embeddings',
            request_model=model,
            embedding_text=query,
        ) as span:
            result = await embedding_function(query, *args, **kwargs)
            if span.is_recording() and tracer.config.capture_embedding_vectors and result is not None:
                value = capture(result, enabled=True, config=tracer.config)
                if value is not None:
                    span.set_attribute(semconv.GEN_AI_EMBEDDINGS, value)
            return result

    return wrapped


def instrument_reranker(tracer: GenAITracer, reranking_function):
    if reranking_function is None:
        return None

    def wrapped(query, documents, *args, **kwargs):
        with tracer.rerank('rerank', retrieval_query=query, **attributes_for('rerank')) as span:
            result = reranking_function(query, documents, *args, **kwargs)
            if span.is_recording():
                span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_CANDIDATE_COUNT, len(documents))
            return result

    return wrapped


def _embedding_model(request) -> str | None:
    """The configured embedding model name, from the request's app state."""
    config = getattr(getattr(getattr(request, 'app', None), 'state', None), 'config', None)
    return getattr(config, 'RAG_EMBEDDING_MODEL', None) or None


def traced_retrieval(tracer: GenAITracer):
    def decorator(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            bound = inspect.signature(function).bind_partial(*args, **kwargs)
            values = bound.arguments
            queries = values.get('queries') or []
            query = queries[0] if isinstance(queries, list) and queries else queries
            # One data source id per span (the standard's gen_ai.data_source.id): the knowledge
            # collections searched, joined when there are several.
            collections = sorted({item.get('collection_name') for item in values.get('items') or [] if item.get('collection_name')})
            data_source_id = ','.join(collections) or None
            with tracer.retrieval(
                f'retrieval {data_source_id}' if data_source_id else 'retrieval',
                operation_name='retrieval',
                retrieval_query=query,
                retrieval_top_k=values.get('k'),
                data_source_id=data_source_id,
                candidate_count=len(values.get('items') or []),
                retrieval_mode='hybrid' if values.get('hybrid_search') else 'vector',
            ) as span:
                if 'embedding_function' in values:
                    values['embedding_function'] = instrument_embedding(
                        tracer, values['embedding_function'], model=_embedding_model(values.get('request'))
                    )
                result = await function(*bound.args, **bound.kwargs)
                if span.is_recording() and isinstance(result, list):
                    documents = []
                    for rank, source in enumerate(result[: tracer.config.retrieval_max_documents], 1):
                        if not isinstance(source, dict):
                            continue
                        metadata = source.get('metadata') or {}
                        if not isinstance(metadata, dict):
                            metadata = {}
                        distances = source.get('distances') or []
                        entry = {
                            'document_id': metadata.get('document_id') or metadata.get('id'),
                            'file_id': metadata.get('file_id'),
                            'chunk_id': metadata.get('chunk_id'),
                            'rank': rank,
                            'score': distances[rank - 1] if len(distances) >= rank else metadata.get('score'),
                        }
                        if tracer.config.capture_retrieval_documents:
                            entry['content'] = capture(
                                (source.get('document') or [''])[0],
                                enabled=True,
                                config=tracer.config,
                            )
                        documents.append(entry)
                    # gen_ai.retrieval.documents is opt-in: nothing is recorded unless enabled.
                    if tracer.config.capture_retrieval_documents:
                        span.set_attribute(semconv.GEN_AI_RETRIEVAL_DOCUMENTS, json.dumps(documents, ensure_ascii=False, default=str))
                    span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_SELECTED_COUNT, len(result))
                return result

        return wrapped

    return decorator
