from types import SimpleNamespace

import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.inference import traced_inference
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.mark.asyncio
async def test_two_round_tool_loop_creates_independent_inference_spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('inference-test'), GenAIConfig())
    responses = [
        {
            'id': 'one',
            'model': 'requested',
            'usage': {'prompt_tokens': 3, 'completion_tokens': 4},
            'choices': [{'finish_reason': 'tool_calls'}],
        },
        {
            'id': 'two',
            'model': 'actual',
            'usage': {'prompt_tokens': 5, 'completion_tokens': 6},
            'choices': [{'finish_reason': 'stop'}],
        },
    ]

    async def call():
        return responses.pop(0)

    await traced_inference(tracer, provider='openai-compatible', request_payload={'model': 'requested'}, call=call)
    await traced_inference(tracer, provider='ollama', request_payload={'model': 'requested'}, call=call)
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert [span.attributes['gen_ai.usage.input_tokens'] for span in spans] == [3, 5]
    assert [span.attributes['gen_ai.usage.output_tokens'] for span in spans] == [4, 6]
    assert [span.attributes['gen_ai.response.id'] for span in spans] == ['one', 'two']


@pytest.mark.asyncio
async def test_content_is_absent_for_openai_and_ollama_when_disabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('privacy-test'), GenAIConfig())

    async def call():
        return {'id': 'response', 'model': 'model', 'choices': [{'finish_reason': 'stop'}]}

    payload = {'model': 'model', 'messages': [{'role': 'user', 'content': 'secret'}]}
    await traced_inference(tracer, provider='openai-compatible', request_payload=payload, call=call)
    await traced_inference(tracer, provider='ollama', request_payload=payload, call=call)
    for span in exporter.get_finished_spans():
        assert 'gen_ai.input.messages' not in span.attributes
        assert 'gen_ai.output.messages' not in span.attributes


@pytest.mark.asyncio
async def test_buffered_output_is_captured_when_enabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(
        provider.get_tracer('output-content-test'),
        GenAIConfig(capture_outputs=True, content_max_length=12),
    )

    async def call():
        return {
            'id': 'response',
            'model': 'model',
            'choices': [{'message': {'role': 'assistant', 'content': 'output is longer'}}],
        }

    await traced_inference(tracer, provider='openai-compatible', request_payload={'model': 'model'}, call=call)
    output = exporter.get_finished_spans()[0].attributes['gen_ai.output.messages']
    assert len(output) == 12
    assert output.startswith('[{"role": "a')


@pytest.mark.asyncio
async def test_streaming_inference_span_closes_after_body_iterator():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('stream-test'), GenAIConfig())

    async def body():
        yield 'chunk'

    response = SimpleNamespace(body_iterator=body())
    result = await traced_inference(
        tracer,
        provider='ollama',
        request_payload={'model': 'model', 'stream': True},
        call=lambda: _return(response),
    )
    assert exporter.get_finished_spans() == ()
    assert [item async for item in result.body_iterator] == ['chunk']
    assert len(exporter.get_finished_spans()) == 1


@pytest.mark.asyncio
async def test_streaming_output_is_captured_after_body_iteration():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(
        provider.get_tracer('stream-output-test'),
        GenAIConfig(capture_outputs=True),
    )

    async def body():
        yield 'chunk-one'
        yield 'chunk-two'

    response = SimpleNamespace(body_iterator=body())
    result = await traced_inference(
        tracer,
        provider='ollama',
        request_payload={'model': 'model', 'stream': True},
        call=lambda: _return(response),
    )
    assert [item async for item in result.body_iterator] == ['chunk-one', 'chunk-two']
    assert exporter.get_finished_spans()[0].attributes['gen_ai.output.messages'] == 'chunk-onechunk-two'


async def _return(value):
    return value
