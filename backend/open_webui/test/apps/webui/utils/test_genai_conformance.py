import asyncio
import json
from pathlib import Path

import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.inference import traced_inference
from open_webui.utils.telemetry.genai.retrieval import instrument_embedding, instrument_reranker
from open_webui.utils.telemetry.genai.tools import traced_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

GOLDEN_DIR = Path(__file__).parent / 'telemetry' / 'golden'


def setup(config=None):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('conformance'), config or GenAIConfig()), exporter


def topology(spans):
    by_id = {span.context.span_id: span.name for span in spans}
    return [
        {
            'name': span.name,
            'parent': by_id.get(span.parent.span_id) if span.parent else None,
            'attributes': sorted(span.attributes),
        }
        for span in spans
    ]


async def successful_response():
    return {
        'id': 'response-id',
        'model': 'actual-model',
        'usage': {'prompt_tokens': 2, 'completion_tokens': 3},
        'choices': [{'finish_reason': 'stop'}],
    }


async def build_scenario(name, tracer):
    with tracer.workflow('invoke_workflow open-webui.chat', operation_name='invoke_workflow', purpose='primary'):
        if name in {'simple_chat', 'openai', 'ollama', 'no_chat_id', 'background_title', 'followup'}:
            task = None
            if name == 'background_title':
                task = 'title_generation'
            elif name == 'followup':
                task = 'follow_up_generation'
            await traced_inference(
                tracer,
                provider='ollama' if name == 'ollama' else 'openai-compatible',
                request_payload={'model': 'requested-model', 'metadata': {'task': task} if task else {}},
                call=successful_response,
            )
        elif name == 'streaming':

            async def stream():
                yield 'first'
                yield 'final'

            async def response():
                return type('Response', (), {'body_iterator': stream()})()

            result = await traced_inference(
                tracer,
                provider='openai-compatible',
                request_payload={'model': 'model', 'stream': True},
                call=response,
            )
            [item async for item in result.body_iterator]
        elif name == 'cancelled':
            span = tracer.tracer.start_span('chat_completion')

            async def stream():
                yield 'first'
                await asyncio.sleep(10)

            from open_webui.utils.telemetry.genai.streaming import wrap_stream

            wrapped = wrap_stream(span, stream())
            await wrapped.__anext__()
            await wrapped.aclose()
        elif name in {'one_tool', 'multiple_tools', 'mcp_tool'}:
            with tracer.inference('chat_completion'):
                count = 1 if name != 'multiple_tools' else 2
                for index in range(count):

                    async def call(index=index):
                        return {'result': index}

                    await traced_tool(
                        tracer,
                        name='mcp' if name == 'mcp_tool' else f'tool-{index}',
                        call_id=f'call-{index}',
                        tool_type='mcp' if name == 'mcp_tool' else 'function',
                        arguments={'index': index},
                        direct=False,
                        call=call,
                    )
            if name == 'one_tool':
                await traced_inference(
                    tracer,
                    provider='openai-compatible',
                    request_payload={'model': 'model'},
                    call=successful_response,
                )
        elif name == 'multi_round':
            await traced_inference(
                tracer, provider='openai-compatible', request_payload={'model': 'model'}, call=successful_response
            )
            await traced_inference(
                tracer, provider='openai-compatible', request_payload={'model': 'model'}, call=successful_response
            )
        elif name in {'knowledge', 'hybrid', 'rerank', 'embedding', 'retrieval_failure'}:
            with tracer.retrieval('retrieval', operation_name='retrieval', retrieval_query='query', top_k=3):

                async def embedding(query, prefix=None):
                    return [[0.1, 0.2]]

                await instrument_embedding(tracer, embedding)('query')
                if name in {'hybrid', 'rerank'}:
                    with tracer.tracer.start_as_current_span('bm25_search' if name == 'hybrid' else 'vector_search'):
                        pass
                if name == 'rerank':
                    instrument_reranker(tracer, lambda query, docs: [0.9])('query', ['doc'])
                    await traced_tool(
                        tracer,
                        name='retrieval-tool',
                        call_id='retrieval-call',
                        tool_type='function',
                        arguments={'query': 'query'},
                        direct=False,
                        call=lambda: successful_response(),
                    )
                if name == 'retrieval_failure':
                    with pytest.raises(RuntimeError):
                        raise RuntimeError('retrieval failed')
                if name in {'knowledge', 'hybrid', 'rerank'}:
                    current = trace.get_current_span()
                    current.set_attribute(
                        'gen_ai.retrieval.documents', ['{"document_id":"doc-1","rank":1,"score":0.9}']
                    )
        elif name == 'llm_failure':

            async def fail():
                raise ValueError('llm failed')

            with pytest.raises(ValueError):
                await traced_inference(
                    tracer, provider='openai-compatible', request_payload={'model': 'model'}, call=fail
                )
        elif name == 'no_content':
            await traced_inference(
                tracer,
                provider='openai-compatible',
                request_payload={'model': 'model', 'messages': [{'content': 'secret'}]},
                call=successful_response,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'scenario',
    [
        'simple_chat',
        'streaming',
        'cancelled',
        'openai',
        'ollama',
        'one_tool',
        'multiple_tools',
        'multi_round',
        'knowledge',
        'hybrid',
        'rerank',
        'embedding',
        'mcp_tool',
        'background_title',
        'followup',
        'no_chat_id',
        'llm_failure',
        'retrieval_failure',
        'no_content',
    ],
)
async def test_conformance_scenarios(scenario):
    tracer, exporter = setup()
    await build_scenario(scenario, tracer)
    spans = exporter.get_finished_spans()
    assert spans
    if scenario == 'llm_failure':
        assert any(span.status.status_code is StatusCode.ERROR for span in spans)
    if scenario == 'no_content':
        assert all('gen_ai.input.messages' not in span.attributes for span in spans)
    if scenario == 'background_title':
        assert any(span.attributes.get('openwebui.operation.purpose') == 'title_generation' for span in spans)
    if scenario == 'followup':
        assert any(span.attributes.get('openwebui.operation.purpose') == 'followup_generation' for span in spans)


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['simple_chat', 'knowledge', 'multi_round', 'rerank'])
async def test_golden_topology(scenario):
    tracer, exporter = setup()
    await build_scenario(scenario, tracer)
    actual = topology(exporter.get_finished_spans())
    golden_name = {
        'knowledge': 'rag_chat',
        'multi_round': 'tool_loop',
        'rerank': 'rag_rerank_tool',
    }.get(scenario, scenario)
    expected = json.loads((GOLDEN_DIR / f'{golden_name}.json').read_text())
    assert actual == expected


def test_tracing_suppressed_produces_no_semantic_spans():
    exporter = InMemorySpanExporter()
    tracer = GenAITracer(trace.get_tracer('suppressed'), GenAIConfig())
    with tracer.workflow('invoke_workflow open-webui.chat'):
        pass
    assert exporter.get_finished_spans() == ()
