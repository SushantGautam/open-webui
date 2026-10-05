import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.tools import traced_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.mark.asyncio
async def test_two_tools_are_independent_children_of_inference():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('tools-test'), GenAIConfig())

    async def first():
        return 'first-result'

    async def second():
        return 'second-result'

    with tracer.inference('chat_completion') as parent:
        await traced_tool(
            tracer,
            name='first',
            call_id='call-1',
            tool_type='function',
            arguments={'x': 1},
            direct=False,
            call=first,
        )
        await traced_tool(
            tracer,
            name='second',
            call_id='call-2',
            tool_type='mcp',
            arguments={'x': 2},
            direct=False,
            call=second,
        )

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ['execute_tool', 'execute_tool', 'chat_completion']
    tool_spans = spans[:2]
    assert [span.attributes['gen_ai.tool.name'] for span in tool_spans] == ['first', 'second']
    assert [span.attributes['gen_ai.tool.call.id'] for span in tool_spans] == ['call-1', 'call-2']
    assert [span.attributes['gen_ai.tool.type'] for span in tool_spans] == ['function', 'mcp']
    assert all(span.parent.span_id == parent.get_span_context().span_id for span in tool_spans)


@pytest.mark.asyncio
async def test_tool_payloads_are_absent_when_capture_is_disabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('tools-privacy-test'), GenAIConfig())

    async def call():
        return {'secret': 'result'}

    await traced_tool(
        tracer,
        name='private',
        call_id='call-private',
        tool_type='builtin',
        arguments={'secret': 'argument'},
        direct=False,
        call=call,
    )
    attributes = exporter.get_finished_spans()[0].attributes
    assert 'gen_ai.tool.call.arguments' not in attributes
    assert 'gen_ai.tool.call.result' not in attributes


@pytest.mark.asyncio
async def test_tool_payloads_are_captured_when_enabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(
        provider.get_tracer('tools-content-test'),
        GenAIConfig(capture_tool_arguments=True, capture_tool_results=True),
    )

    async def call():
        return {'result': 'ok'}

    await traced_tool(
        tracer,
        name='captured',
        call_id='call-captured',
        tool_type='openapi',
        arguments={'argument': 'value'},
        direct=False,
        call=call,
    )
    attributes = exporter.get_finished_spans()[0].attributes
    assert 'value' in attributes['gen_ai.tool.call.arguments']
    assert 'ok' in attributes['gen_ai.tool.call.result']
