"""Query generation should be a distinct task with nested standard inference."""

from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.inference import traced_inference
from open_webui.utils.telemetry.genai.query import traced_query_generation, traced_rag_retrieval
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode


def setup_tracer(config=None):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('query-test'), config or GenAIConfig()), exporter


def request(*, cached=None, metadata=None):
    return SimpleNamespace(state=SimpleNamespace(cached_queries=cached, metadata=metadata or {}))


def form_data(query='secret original search'):
    return {
        'type': 'web_search',
        'chat_id': 'chat-123',
        'messages': [{'role': 'user', 'content': query}],
        'model': 'test-model',
    }


@pytest.mark.asyncio
async def test_query_generation_contains_standard_llm_span_without_leaking_content():
    tracer, exporter = setup_tracer()

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        async def call():
            return {
                'model': 'test-model',
                'usage': {'prompt_tokens': 10, 'completion_tokens': 6},
                'choices': [{'message': {'role': 'assistant', 'content': '["rewritten search"]'}}],
            }

        return await traced_inference(
            tracer,
            provider='openai-compatible',
            request_payload={
                'model': form_data['model'],
                'metadata': {'task': 'query_generation'},
                'messages': form_data['messages'],
            },
            call=call,
        )

    result = await generate_queries(request(), form_data())
    assert result['choices'][0]['message']['content'] == '["rewritten search"]'

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    task = next(s for s in spans if s.name == 'query_generation')
    llm = next(s for s in spans if s.name == 'chat test-model')
    assert llm.parent.span_id == task.context.span_id
    assert llm.attributes['gen_ai.operation.name'] == 'chat'
    assert llm.attributes['openwebui.operation.purpose'] == 'retrieval_query'
    assert llm.attributes['gen_ai.usage.input_tokens'] == 10
    assert task.attributes['gen_ai.conversation.id'] == 'chat-123'
    assert task.attributes['openwebui.query.type'] == 'web_search'
    assert task.attributes['openwebui.query.cached'] is False
    assert task.attributes['openwebui.query.generated_count'] == 1
    assert 'gen_ai.operation.name' not in task.attributes
    assert 'openwebui.query.original' not in task.attributes
    assert 'openwebui.query.generated' not in task.attributes


@pytest.mark.asyncio
async def test_content_capture_requires_each_independent_opt_in_and_is_bounded():
    tracer, exporter = setup_tracer(
        GenAIConfig(
            capture_retrieval_query=True,
            capture_outputs=True,
            content_max_length=8,
        )
    )

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return {'choices': [{'message': {'content': 'rewritten query'}}]}

    await generate_queries(request(), form_data())
    span = exporter.get_finished_spans()[0]
    assert span.attributes['openwebui.query.original'] == 'secret o'
    assert span.attributes['openwebui.query.generated'] == '["rewrit'

    tracer, exporter = setup_tracer(GenAIConfig(capture_outputs=True))

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return {'choices': [{'message': {'content': 'rewritten query'}}]}

    await generate_queries(request(), form_data())
    span = exporter.get_finished_spans()[0]
    assert 'openwebui.query.original' not in span.attributes
    assert span.attributes['openwebui.query.generated'] == '["rewritten query"]'


@pytest.mark.asyncio
async def test_cached_query_has_no_model_span_and_keeps_cached_response():
    tracer, exporter = setup_tracer()
    response = ['cached query one', 'cached query two']

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return request.state.cached_queries

    result = await generate_queries(request(cached=response), form_data())
    assert result is response
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes['openwebui.query.cached'] is True
    assert spans[0].attributes['openwebui.query.generated_count'] == 2
    assert 'openwebui.query.generated' not in spans[0].attributes


@pytest.mark.asyncio
async def test_errors_are_recorded_without_changing_return_or_exception():
    tracer, exporter = setup_tracer()

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return JSONResponse(status_code=400, content={'detail': 'failed'})

    response = await generate_queries(request(), form_data())
    assert response.status_code == 400
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.ERROR

    exporter.clear()

    @traced_query_generation(tracer)
    async def raise_error(request, form_data):
        raise RuntimeError('failed')

    with pytest.raises(RuntimeError, match='failed'):
        await raise_error(request(), form_data())
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
async def test_disabled_telemetry_is_transparent():
    tracer, exporter = setup_tracer(GenAIConfig(enabled=False))

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return ['query']

    assert await generate_queries(request(), form_data()) == ['query']
    assert exporter.get_finished_spans() == ()


@pytest.mark.asyncio
async def test_json_response_and_retrieval_type_are_supported():
    tracer, exporter = setup_tracer(GenAIConfig(capture_outputs=True))

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return JSONResponse({'queries': ['alpha', 'beta']})

    data = form_data()
    data['type'] = 'retrieval'
    response = await generate_queries(request(), data)
    assert response.status_code == 200
    span = exporter.get_finished_spans()[0]
    assert span.attributes['openwebui.query.type'] == 'retrieval'
    assert span.attributes['openwebui.query.generated_count'] == 2
    assert 'alpha' in span.attributes['openwebui.query.generated']


@pytest.mark.asyncio
async def test_default_prompt_json_object_tracks_real_query_count():
    tracer, exporter = setup_tracer(GenAIConfig(capture_outputs=True))

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return {
            'choices': [{
                'message': {
                    'content': '{"queries": ["first rewritten query", "second rewritten query"]}'
                }
            }]
        }

    await generate_queries(request(), form_data())
    span = exporter.get_finished_spans()[0]
    assert span.attributes['openwebui.query.generated_count'] == 2
    assert 'first rewritten query' in span.attributes['openwebui.query.generated']
    assert 'second rewritten query' in span.attributes['openwebui.query.generated']


@pytest.mark.asyncio
async def test_rag_parent_groups_query_generation_and_vector_retrieval():
    tracer, exporter = setup_tracer()

    @traced_query_generation(tracer)
    async def generate_queries(request, form_data):
        return {'choices': [{'message': {'content': '{"queries": ["rewritten"]}'}}]}

    @traced_rag_retrieval(tracer)
    async def retrieval_flow(request, body, extra_params, user):
        await generate_queries(request, form_data())
        with tracer.retrieval('retrieval', operation_name='retrieval', retrieval_query='rewritten'):
            pass
        return body, {'sources': []}

    body = {'metadata': {'files': [{'type': 'file', 'id': 'one'}], 'chat_id': 'chat-123'}}
    result = await retrieval_flow(request(), body, {}, None)
    assert result[0] is body
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ['query_generation', 'retrieval', 'rag.retrieval']
    parent = spans[-1]
    assert parent.attributes['gen_ai.conversation.id'] == 'chat-123'
    assert 'gen_ai.operation.name' not in parent.attributes
    assert spans[0].parent.span_id == parent.context.span_id
    assert spans[1].parent.span_id == parent.context.span_id


@pytest.mark.asyncio
async def test_rag_parent_skips_empty_file_context():
    tracer, exporter = setup_tracer()

    @traced_rag_retrieval(tracer)
    async def retrieval_flow(request, body, extra_params, user):
        return body, {'sources': []}

    body = {'metadata': {'files': []}}
    result = await retrieval_flow(request(), body, {}, None)
    assert result[0] is body
    assert exporter.get_finished_spans() == ()
