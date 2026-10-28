"""Application-level query generation spans for web search and RAG."""

import functools
import json

from open_webui.utils.telemetry.genai import semconv
from open_webui.utils.telemetry.genai.extractors import capture
from opentelemetry.trace import StatusCode


def _original_query(messages):
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get('role') == 'user':
            content = message.get('content')
            return content if isinstance(content, str) else None
    return None


def _generated_content(response):
    # Model providers generally return a Chat Completions dict. Cached queries
    # may instead be a list or a response with a "queries" field.
    if hasattr(response, 'body') and getattr(response, 'media_type', None) == 'application/json':
        try:
            response = json.loads(response.body)
        except (TypeError, ValueError):
            return None

    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        choices = response.get('choices') or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get('message') or {}
            if isinstance(message, dict):
                return message.get('content')
            return choices[0].get('text')
        queries = response.get('queries')
        if isinstance(queries, list):
            return queries
    return None


def _parse_queries(content):
    """Extract query candidates from the native task-model response format.

    The default Open WebUI prompt returns {"queries": [...]}, optionally
    wrapped in surrounding prose; cached values are already lists.
    """
    if isinstance(content, list):
        return [query for query in content if isinstance(query, str)]
    if isinstance(content, str):
        try:
            value = json.loads(content)
        except ValueError:
            start, end = content.rfind('{'), content.rfind('}')
            if start >= 0 and end > start:
                try:
                    value = json.loads(content[start : end + 1])
                except ValueError:
                    return [content] if content.strip() else []
            else:
                return [content] if content.strip() else []
        if isinstance(value, dict):
            value = value.get('queries')
        if isinstance(value, list):
            return [query for query in value if isinstance(query, str)]
    return None



def traced_query_generation(tracer):
    """Add a task span around query generation, retaining the existing LLM span.

    Query text is opt-in and length-limited. No new GenAI operation name is
    invented for a single model call, and the original response is unchanged.
    """

    def decorator(function):
        @functools.wraps(function)
        async def wrapped(request, form_data, *args, **kwargs):
            metadata = getattr(request.state, 'metadata', None) or {}
            cached = bool(getattr(request.state, 'cached_queries', None))
            chat_id = form_data.get('chat_id') or metadata.get('chat_id')
            with tracer.task(
                'query_generation',
                purpose='retrieval_query',
                conversation_id=chat_id,
                **{
                    semconv.OPENWEBUI_QUERY_TYPE: str(form_data.get('type') or 'unknown'),
                    semconv.OPENWEBUI_QUERY_CACHED: cached,
                },
            ) as span:
                if span.is_recording():
                    original = capture(
                        _original_query(form_data.get('messages')),
                        enabled=tracer.config.capture_retrieval_query,
                        config=tracer.config,
                    )
                    if original is not None:
                        span.set_attribute(semconv.OPENWEBUI_QUERY_ORIGINAL, original)

                result = await function(request, form_data, *args, **kwargs)

                if span.is_recording():
                    if getattr(result, 'status_code', 200) >= 400:
                        span.set_status(StatusCode.ERROR)
                    generated = _generated_content(result)
                    queries = _parse_queries(generated)
                    if queries is not None:
                        span.set_attribute(semconv.OPENWEBUI_QUERY_GENERATED_COUNT, len(queries))
                    output = capture(
                        queries if queries is not None else generated,
                        enabled=tracer.config.capture_outputs,
                        config=tracer.config,
                    )
                    if output is not None:
                        span.set_attribute(semconv.OPENWEBUI_QUERY_GENERATED, output)
                return result

        return wrapped

    return decorator


def traced_rag_retrieval(tracer):
    """Group RAG query generation and subsequent retrieval in one internal span."""

    def decorator(function):
        @functools.wraps(function)
        async def wrapped(request, body, extra_params, user, *args, **kwargs):
            metadata = body.get('metadata') or {}
            files = [
                item
                for item in metadata.get('files') or []
                if isinstance(item, dict) and item.get('type') != 'filesystem'
            ]
            if not files:
                return await function(request, body, extra_params, user, *args, **kwargs)
            with tracer.task(
                'rag.retrieval',
                purpose='rag_retrieval',
                conversation_id=metadata.get('chat_id'),
            ):
                return await function(request, body, extra_params, user, *args, **kwargs)

        return wrapped

    return decorator
