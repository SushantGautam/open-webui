"""GenAI tool-execution spans. Knowledge listings are not retrieval spans."""

from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai import compact, content, semconv
from open_webui.utils.telemetry.genai.tracer import GenAITracer

_TOOL_TYPES = {
    'function': 'function',
    'builtin': 'function',
    'mcp': 'extension',
    'openapi': 'extension',
    'external': 'extension',
    'action': 'extension',
    'terminal': 'extension',
    'datastore': 'datastore',
}


def classify_tool(tool_type: str | None, direct: bool = False) -> str:
    return _TOOL_TYPES.get((tool_type or '').lower(), 'function')


def _compact_result(span, result, value):
    """The result object, or a reference when the trace already recorded it.

    The raw result is what a later model call receives as the tool response, and
    a knowledge tool's retrieval span records it first as its documents.
    """
    raw = content.parse_json(result)
    for candidate in (raw, value):
        reference = compact.reference_for(span, candidate)
        if reference is not None:
            return reference
    compact.remember_value(span, semconv.GEN_AI_TOOL_CALL_RESULT, value)
    compact.remember_value(span, semconv.GEN_AI_TOOL_CALL_RESULT, raw)
    return value


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
    with tracer.tool(
        f'execute_tool {name}',
        operation_name='execute_tool',
        tool_name=name,
        tool_call_id=call_id or None,
        tool_type=classify_tool(tool_type, direct),
        tool_arguments=arguments,
    ) as span:
        # Exceptions are recorded and typed by GenAITracer._span.
        result = await call()
        if span.is_recording() and tracer.config.capture_tool_results:
            value = content.as_object(result, result=True)
            if tracer.config.content_mode == 'compact':
                value = _compact_result(span, result, value)
            span.set_attribute(
                semconv.GEN_AI_TOOL_CALL_RESULT,
                content.json_attribute(value, tracer.config.content_max_length),
            )
        # Do not attach gen_ai.retrieval.documents to arbitrary tool outputs.
        # list_knowledge inventories aren't documents returned by retrieval.
        return result
