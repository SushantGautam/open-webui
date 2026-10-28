from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai import semconv
from open_webui.utils.telemetry.genai.tracer import GenAITracer


def classify_tool(tool_type: str | None, direct: bool = False) -> str:
    normalized = (tool_type or '').lower()
    if normalized in {'mcp', 'openapi', 'external', 'action', 'terminal', 'builtin', 'function'}:
        return normalized
    return 'builtin' if direct else 'function'


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
        name,
        operation_name='execute_tool',
        tool_name=name,
        tool_call_id=call_id,
        tool_type=classify_tool(tool_type, direct),
        inputs=arguments,
    ) as span:
        result = await call()
        if span.is_recording() and tracer.config.capture_outputs and result is not None:
            from open_webui.utils.telemetry.genai.extractors import capture

            value = capture(result, enabled=True, config=tracer.config)
            if value is not None:
                span.set_attribute('gen_ai.output.messages', value)
        return result
