import functools
import inspect
import json

from open_webui.utils.telemetry.genai import semconv
from open_webui.utils.telemetry.genai.openinference import attributes_for
from open_webui.utils.telemetry.genai.tracer import GenAITracer


def instrument_embedding(tracer: GenAITracer, embedding_function):
    if embedding_function is None:
        return None

    async def wrapped(query, *args, **kwargs):
        with tracer.embedding('embedding', embedding_text=query) as span:
            result = await embedding_function(query, *args, **kwargs)
            if span.is_recording() and tracer.config.capture_embedding_vectors and result is not None:
                span.set_attribute(semconv.GEN_AI_EMBEDDINGS, result)
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


def traced_retrieval(tracer: GenAITracer):
    def decorator(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            bound = inspect.signature(function).bind_partial(*args, **kwargs)
            values = bound.arguments
            queries = values.get('queries') or []
            query = queries[0] if isinstance(queries, list) and queries else queries
            with tracer.retrieval(
                'retrieval',
                operation_name='retrieval',
                retrieval_query=query,
                top_k=values.get('k'),
                candidate_count=len(values.get('items') or []),
                retrieval_mode='hybrid' if values.get('hybrid_search') else 'vector',
                data_source=[
                    item.get('collection_name') for item in values.get('items') or [] if item.get('collection_name')
                ],
            ) as span:
                if 'embedding_function' in values:
                    values['embedding_function'] = instrument_embedding(tracer, values['embedding_function'])
                result = await function(*bound.args, **bound.kwargs)
                if span.is_recording() and isinstance(result, list):
                    documents = []
                    for rank, source in enumerate(result[: tracer.config.retrieval_max_documents], 1):
                        metadata = source.get('metadata') or {}
                        distances = source.get('distances') or []
                        entry = {
                            'document_id': metadata.get('document_id') or metadata.get('id'),
                            'file_id': metadata.get('file_id'),
                            'chunk_id': metadata.get('chunk_id'),
                            'rank': rank,
                            'score': distances[rank - 1] if len(distances) >= rank else metadata.get('score'),
                        }
                        if tracer.config.capture_retrieval_documents:
                            entry['content'] = (source.get('document') or [''])[0]
                        documents.append(json.dumps(entry, ensure_ascii=False, default=str))
                    span.set_attribute(semconv.GEN_AI_RETRIEVAL_DOCUMENTS, documents)
                    span.set_attribute(semconv.OPENWEBUI_RETRIEVAL_SELECTED_COUNT, len(result))
                return result

        return wrapped

    return decorator
