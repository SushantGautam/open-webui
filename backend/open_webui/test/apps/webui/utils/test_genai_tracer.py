import asyncio

import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.streaming import wrap_stream
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode


@pytest.fixture
def span_setup():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('test'), GenAIConfig()), exporter


def test_span_kind_and_structural_attributes(span_setup):
    tracer, exporter = span_setup
    with tracer.inference(operation_name='chat', provider='test', request_model='model'):
        pass
    span = exporter.get_finished_spans()[0]
    assert span.attributes['gen_ai.operation.name'] == 'chat'
    assert span.attributes['gen_ai.provider.name'] == 'test'
    assert span.attributes['openinference.span.kind'] == 'LLM'


def test_exception_is_recorded_and_status_is_error(span_setup):
    tracer, exporter = span_setup
    with pytest.raises(ValueError):
        with tracer.inference():
            raise ValueError('boom')
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert any(event.name == 'exception' for event in span.events)


def test_content_is_absent_when_capture_is_disabled(span_setup):
    tracer, exporter = span_setup
    with tracer.inference(inputs='secret prompt', outputs='secret output', tool_arguments='secret args'):
        pass
    assert not any(
        'input' in key or 'output' in key or 'tool' in key for key in exporter.get_finished_spans()[0].attributes
    )


def test_content_is_truncated_when_capture_is_enabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    config = GenAIConfig(capture_inputs=True, capture_outputs=True, content_max_length=5)
    with GenAITracer(provider.get_tracer('test'), config).inference(inputs='123456789', outputs='abcdefgh'):
        pass
    span = exporter.get_finished_spans()[0]
    assert span.attributes['gen_ai.input.messages'] == '12345'
    assert span.attributes['gen_ai.output.messages'] == 'abcde'


@pytest.mark.asyncio
async def test_streaming_cancellation_closes_span(span_setup):
    tracer, exporter = span_setup
    span = tracer.tracer.start_span('stream')

    async def source():
        yield 'first'
        await asyncio.sleep(10)

    wrapped = wrap_stream(span, source())
    assert await wrapped.__anext__() == 'first'
    await wrapped.aclose()
    assert len(exporter.get_finished_spans()) == 1
