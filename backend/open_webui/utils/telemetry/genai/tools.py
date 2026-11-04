"""GenAI tool-execution spans. Knowledge listings are not retrieval spans."""
from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai import content, semconv
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
            span.set_attribute(
                semconv.GEN_AI_TOOL_CALL_RESULT,
                content.json_attribute(
                    content.as_object(result, result=True),
                    tracer.config.content_max_length,
                ),
            )
        # Do not attach gen_ai.retrieval.documents to arbitrary tool outputs.
        # list_knowledge inventories aren't documents returned by retrieval.
        return result
