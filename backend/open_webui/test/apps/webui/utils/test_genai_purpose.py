import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.inference import traced_inference
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.mark.asyncio
async def test_task_metadata_maps_background_purpose_and_primary_defaults():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('purpose-test'), GenAIConfig())

    async def call():
        return {'id': 'response', 'model': 'model', 'choices': [{'finish_reason': 'stop'}]}

    await traced_inference(
        tracer,
        provider='openai-compatible',
        request_payload={'model': 'model', 'metadata': {'task': 'title_generation'}},
        call=call,
    )
    await traced_inference(tracer, provider='openai-compatible', request_payload={'model': 'model'}, call=call)
    spans = exporter.get_finished_spans()
    assert spans[0].attributes['openwebui.operation.purpose'] == 'title_generation'
    assert spans[1].attributes['openwebui.operation.purpose'] == 'primary'


def test_primary_workflow_purpose_is_explicit():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('workflow-purpose-test'), GenAIConfig())
    with tracer.workflow('invoke_workflow open-webui.chat', operation_name='invoke_workflow', purpose='primary'):
        pass
    assert exporter.get_finished_spans()[0].attributes['openwebui.operation.purpose'] == 'primary'
