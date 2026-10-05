import asyncio

import pytest
from open_webui.utils.telemetry.genai.streaming import wrap_stream
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def tracer_setup():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('workflow-test')), exporter


@pytest.mark.asyncio
async def test_workflow_name_context_and_stream_lifetime(tracer_setup):
    tracer, exporter = tracer_setup
    span = tracer.tracer.start_span('invoke_workflow open-webui.chat')
    stream_started = asyncio.Event()

    async def source():
        stream_started.set()
        yield 'chunk'
        await asyncio.sleep(0)
        yield 'done'

    wrapped = wrap_stream(span, source())
    assert await wrapped.__anext__() == 'chunk'
    await stream_started.wait()
    assert exporter.get_finished_spans() == ()
    assert await wrapped.__anext__() == 'done'
    with pytest.raises(StopAsyncIteration):
        await wrapped.__anext__()
    assert exporter.get_finished_spans()[0].name == 'invoke_workflow open-webui.chat'


def test_workflow_context_attributes_are_ids_only(tracer_setup):
    tracer, exporter = tracer_setup
    with tracer.workflow(
        'invoke_workflow open-webui.chat',
        operation_name='invoke_workflow',
        conversation_id='chat-123',
        message_id='message-456',
        purpose='primary',
    ):
        pass
    span = exporter.get_finished_spans()[0]
    assert span.name == 'invoke_workflow open-webui.chat'
    assert span.attributes['gen_ai.conversation.id'] == 'chat-123'
    assert span.attributes['openwebui.message.id'] == 'message-456'
    assert span.attributes['openwebui.operation.purpose'] == 'primary'
    assert 'chat-123' not in span.name


def test_background_workflow_can_set_non_primary_purpose(tracer_setup):
    tracer, exporter = tracer_setup
    with tracer.workflow(
        'invoke_workflow open-webui.chat',
        operation_name='invoke_workflow',
        conversation_id='chat-123',
        purpose='title_generation',
    ):
        pass
    assert exporter.get_finished_spans()[0].attributes['openwebui.operation.purpose'] == 'title_generation'
