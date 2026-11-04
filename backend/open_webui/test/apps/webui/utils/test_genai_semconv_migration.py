"""Regression tests for OTel GenAI schema-shaped trace emission.

Reference: open-telemetry/semantic-conventions-genai at
633cbb060b16b1487ea2dcd23c4307edc1a03f01.
"""

import json

import pytest
from open_webui.utils.telemetry.genai import content
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.inference import traced_inference
from open_webui.utils.telemetry.genai.retrieval import _retrieved_documents
from open_webui.utils.telemetry.genai.tools import traced_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode


def tracer_with_spans(config=None):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return GenAITracer(provider.get_tracer('semconv-test'), config or GenAIConfig()), exporter


def test_content_capture_is_opt_in_and_legacy_flags_override(monkeypatch):
    monkeypatch.delenv('OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT', raising=False)
    monkeypatch.delenv('OTEL_GENAI_CAPTURE_TOOL_RESULTS', raising=False)
    assert not GenAIConfig.from_env().capture_outputs
    assert not GenAIConfig.from_env().capture_tool_results
    monkeypatch.setenv('OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT', 'true')
    assert GenAIConfig.from_env().capture_inputs
    assert GenAIConfig.from_env().capture_tool_results
    monkeypatch.setenv('OTEL_GENAI_CAPTURE_TOOL_RESULTS', 'false')
    assert not GenAIConfig.from_env().capture_tool_results
    assert not GenAIConfig.from_env().capture_embedding_vectors


def test_input_and_output_contain_standard_role_parts_and_tool_calls():
    messages = [
        {'role': 'system', 'content': 'Follow the policy'},
        {'role': 'user', 'content': 'When is my refund?'},
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call-42', 'function': {'name': 'query_knowledge', 'arguments': '{"q":"refund"}'}}
        ]},
        {'role': 'tool', 'tool_call_id': 'call-42', 'content': '{"status": "ok"}'},
    ]
    rendered = content.input_messages(messages, 100)
    assert [entry['role'] for entry in rendered] == ['system', 'user', 'assistant', 'tool']
    assert rendered[2]['parts'] == [
        {'type': 'tool_call', 'name': 'query_knowledge', 'id': 'call-42', 'arguments': {'q': 'refund'}}
    ]
    assert rendered[3]['parts'] == [
        {'type': 'tool_call_response', 'id': 'call-42', 'response': {'status': 'ok'}}
    ]
    response = {'choices': [
        {'message': {'role': 'assistant', 'content': 'first'}},
        {'message': {'role': 'assistant', 'content': 'second'}},
    ]}
    assert len(content.output_messages(response, 100)) == 2
    assert content.output_messages(response, 100)[1]['parts'][0]['content'] == 'second'
    assert json.loads(content.json_attribute(rendered, 3))[1]['parts'][0]['content'] == 'Whe'


@pytest.mark.asyncio
async def test_streamed_tool_calls_are_parts_and_usage_is_recorded():
    tracer, exporter = tracer_with_spans(GenAIConfig(capture_outputs=True))
    chunks = [
        'data: {"id":"resp-1","model":"qwen","choices":[{"index":0,"delta":{"content":"Hello "}}]}\n\n',
        'data: {"choices":[{"index":0,"delta":{"content":"world","tool_calls":[{"index":0,"id":"call-42","function":{"name":"list_","arguments":"{\\"knowledge"}}]}}]}\n\n',
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"knowledge","arguments":"_id\\": 1}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":9,"completion_tokens":7}}\n\n',
    ]

    class Streaming:
        async def body(self):
            for chunk in chunks:
                mid = len(chunk) // 2
                yield chunk[:mid]
                yield chunk[mid:]

    async def call():
        return type('Response', (), {'body_iterator': Streaming().body()})()

    response = await traced_inference(
        tracer, provider='openai-compatible', request_payload={'model': 'qwen', 'stream': True}, call=call,
    )
    assert not exporter.get_finished_spans()
    [chunk async for chunk in response.body_iterator]
    span = exporter.get_finished_spans()[0]
    assert span.kind == SpanKind.CLIENT
    assert span.attributes['gen_ai.response.id'] == 'resp-1'
    assert span.attributes['gen_ai.usage.input_tokens'] == 9
    assert span.attributes['gen_ai.response.finish_reasons'] == ('tool_call',)
    parts = json.loads(span.attributes['gen_ai.output.messages'])[0]['parts']
    assert parts[0] == {'type': 'text', 'content': 'Hello world'}
    assert parts[1]['type'] == 'tool_call'
    assert parts[1]['name'] == 'list_knowledge'
    assert parts[1]['id'] == 'call-42'
    assert parts[1]['arguments'] == {'knowledge_id': 1}


@pytest.mark.asyncio
async def test_knowledge_inventory_stays_a_tool_result_not_retrieval_documents():
    tracer, exporter = tracer_with_spans(GenAIConfig(capture_tool_results=True))

    async def call():
        return {'knowledge_bases': [{'files': [{'id': 'file-1', 'filename': 'policy.md'}]}]}

    await traced_tool(
        tracer, name='list_knowledge', call_id='call-1', tool_type='builtin',
        arguments={'knowledge_id': 'kb-1'}, direct=False, call=call,
    )
    span = exporter.get_finished_spans()[0]
    assert 'gen_ai.retrieval.documents' not in span.attributes
    payload = json.loads(span.attributes['gen_ai.tool.call.result'])
    assert payload['knowledge_bases'][0]['files'][0]['filename'] == 'policy.md'


def test_retrieval_documents_are_flattened_and_never_use_distance_as_score():
    sources = [{
        'source': {'id': 'file-1', 'name': 'policy.md'},
        'document': ['content-1', 'content-2'],
        'metadata': [
            {'file_id': 'file-1', 'document_id': 'chunk-1', 'name': 'policy.md'},
            {'file_id': 'file-1', 'document_id': 'chunk-2', 'score': 0.91},
        ],
        'distances': [0.2, 0.5],
    }]
    docs = _retrieved_documents(sources, 100, 100)
    assert len(docs) == 2
    assert docs[0] == {'id': 'chunk-1', 'source': 'policy.md', 'file_id': 'file-1', 'content': 'content-1'}
    assert docs[1]['id'] == 'chunk-2'
    assert docs[1]['score'] == 0.91
    assert 'score' not in docs[0]
    assert docs[1]['source'] == 'policy.md'


def test_genai_spans_have_standard_kinds_and_error_types():
    tracer, exporter = tracer_with_spans()
    with tracer.workflow('invoke_workflow open-webui.chat', workflow_name='open-webui.chat'):
        with pytest.raises(ValueError):
            with tracer.inference('chat model', request_model='model'):
                raise ValueError('invalid request')
    spans = exporter.get_finished_spans()
    assert spans[0].kind == SpanKind.CLIENT
    assert spans[0].status.status_code == StatusCode.ERROR
    assert spans[0].attributes['error.type'] == 'ValueError'
    assert spans[1].kind == SpanKind.INTERNAL
    assert spans[1].attributes['gen_ai.workflow.name'] == 'open-webui.chat'
