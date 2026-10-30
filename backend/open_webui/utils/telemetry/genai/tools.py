from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai import extractors, semconv
from open_webui.utils.telemetry.genai.tracer import GenAITracer

# OpenTelemetry GenAI tool types: "function" is a client-side function, "extension" is an
# agent-side tool that calls an external API, "datastore" is retrieval.
_OFFICIAL_TOOL_TYPES = {
    'function': 'function',
    'builtin': 'function',
    'mcp': 'extension',
    'openapi': 'extension',
    'external': 'extension',
    'action': 'extension',
    'terminal': 'extension',
}


def classify_tool(tool_type: str | None, direct: bool = False) -> str:
    """Map an Open WebUI tool type onto the GenAI ``gen_ai.tool.type`` values."""
    return _OFFICIAL_TOOL_TYPES.get((tool_type or '').lower(), 'function')


def _retrieval_documents(result) -> list[dict] | None:
    """The documents of a knowledge tool result, or None for any other result.

    Open WebUI's retrieval result is a JSON list of dicts, each with a ``source`` name.
    Matched by shape, so every knowledge tool is covered without naming them.
    """
    docs = result
    if isinstance(result, str):
        import json

        try:
            docs = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(docs, list) and docs and all(isinstance(d, dict) and d.get('source') for d in docs):
        return docs
    return None


async def traced_tool(
    tracer: GenAITracer,
    *,
    name: str,
    call_id: str | None,
    tool_type: str | None,
    arguments,
    direct: bool,
    call: Callable[[], Awaitable],
):
    """Run one tool call inside a GenAI ``execute_tool`` span.

    Span name is ``execute_tool {gen_ai.tool.name}``. Arguments and results are
    ``gen_ai.tool.call.arguments`` and ``gen_ai.tool.call.result``, each recorded only
    when its capture flag is on. A failing call sets ``error.type`` and an ERROR status.
    """
    with tracer.tool(
        f'execute_tool {name}',
        operation_name='execute_tool',
        tool_name=name,
        tool_call_id=call_id,
        tool_type=classify_tool(tool_type, direct),
        tool_arguments=arguments,
    ) as span:
        try:
            result = await call()
        except Exception as exc:
            if span.is_recording():
                span.set_attribute('error.type', type(exc).__name__)
            raise
        if span.is_recording():
            config = tracer.config
            value = extractors.capture(result, enabled=config.capture_tool_results, config=config)
            if value is not None:
                span.set_attribute(semconv.GEN_AI_TOOL_CALL_RESULT, value)
            docs = _retrieval_documents(result)
            if docs:
                # Documents (with their source names) are gen_ai.retrieval.documents content.
                documents = extractors.capture(
                    docs, enabled=config.capture_retrieval_documents, config=config
                )
                if documents is not None:
                    span.set_attribute(semconv.GEN_AI_RETRIEVAL_DOCUMENTS, documents)
        return result
