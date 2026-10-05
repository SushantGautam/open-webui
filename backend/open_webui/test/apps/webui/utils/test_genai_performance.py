import timeit

import pytest
from open_webui.utils.telemetry.genai import extractors
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.retrieval import traced_retrieval
from open_webui.utils.telemetry.genai.tools import traced_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _tracer(config):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('performance-test'), config), exporter


def test_disabled_tracing_stays_within_agreed_overhead():
    tracer, _ = _tracer(GenAIConfig(enabled=False))

    def baseline():
        return None

    def disabled_trace():
        with tracer.inference():
            pass

    baseline_time = min(timeit.repeat(baseline, number=20_000, repeat=5))
    disabled_time = min(timeit.repeat(disabled_trace, number=20_000, repeat=5))
    # Agreed tolerance: at most 20 ms total for 20,000 disabled spans.
    assert disabled_time - baseline_time <= 0.02


def test_disabled_capture_does_not_serialize(monkeypatch):
    def unexpected_serialization(*args, **kwargs):
        raise AssertionError('content was serialized while capture was disabled')

    monkeypatch.setattr(extractors.json, 'dumps', unexpected_serialization)
    tracer, _ = _tracer(GenAIConfig())
    with tracer.inference(inputs={'secret': 'prompt'}, tool_arguments={'secret': 'args'}):
        pass

    disabled_tracer, _ = _tracer(GenAIConfig(enabled=False, capture_inputs=True))
    with disabled_tracer.inference(inputs={'secret': 'prompt'}):
        pass


@pytest.mark.asyncio
async def test_explicit_content_and_topology_caps():
    config = GenAIConfig(
        capture_inputs=True,
        capture_outputs=True,
        capture_tool_arguments=True,
        capture_tool_results=True,
        capture_retrieval_documents=True,
        content_max_length=5,
        retrieval_max_documents=2,
        exception_max_length=7,
    )
    tracer, exporter = _tracer(config)

    async def tool_call():
        return 'result-too-long'

    await traced_tool(
        tracer,
        name='limited-tool',
        call_id='call-1',
        tool_type='function',
        arguments='arguments-too-long',
        direct=False,
        call=tool_call,
    )

    with pytest.raises(ValueError):
        with tracer.inference(inputs='message-too-long'):
            raise ValueError('exception-message-too-long')

    @traced_retrieval(tracer)
    async def retrieve(items, queries, k, hybrid_search=False, embedding_function=None):
        return items

    items = [
        {'metadata': {'document_id': f'doc-{index}'}, 'document': [f'content-{index}'], 'distances': [0.1]}
        for index in range(4)
    ]
    await retrieve(items=items, queries=['query'], k=4)

    spans = exporter.get_finished_spans()
    tool_span = next(span for span in spans if span.name == 'execute_tool')
    assert tool_span.attributes['gen_ai.tool.call.arguments'] == 'argum'
    assert tool_span.attributes['gen_ai.tool.call.result'] == 'resul'
    inference_span = next(span for span in spans if span.name == 'inference')
    assert inference_span.attributes['gen_ai.input.messages'] == 'messa'
    exception_event = next(event for event in inference_span.events if event.name == 'exception')
    assert exception_event.attributes['exception.message'] == 'excepti'
    retrieval_span = next(span for span in spans if span.name == 'retrieval')
    assert len(retrieval_span.attributes['gen_ai.retrieval.documents']) == 2
