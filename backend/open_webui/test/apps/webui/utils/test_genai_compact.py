"""Compact GenAI content: each piece of content is recorded once per trace."""

import json

import pytest
from open_webui.utils.telemetry.genai import compact
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.retrieval import traced_knowledge_tool
from open_webui.utils.telemetry.genai.tools import traced_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SYSTEM = {'role': 'system', 'content': 'You are the Acme Retail Support Refund Assistant. ' * 3}
QUESTION = {'role': 'user', 'content': 'Which document sets the electronics return window, and how long is it?'}
CHUNKS = [
    {'content': 'Electronics keep the 15-day refund window from the Refunds & Returns Policy.', 'source': 'a.md'},
    {'content': 'A defective electronic device is covered by section 2 instead, up to 90 days.', 'source': 'b.md'},
]


def _tracer(mode='compact'):
    compact.REGISTRY.clear()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    config = GenAIConfig(
        capture_inputs=True,
        capture_outputs=True,
        capture_tool_arguments=True,
        capture_tool_results=True,
        capture_retrieval_documents=True,
        content_mode=mode,
    )
    return GenAITracer(provider.get_tracer('compact-test'), config), exporter


def _hex(span):
    return format(span.context.span_id, '016x')


def _attr(span, key):
    return json.loads(span.attributes[key])


def _chat(tracer, messages, reply):
    with tracer.inference('chat agent', inputs=messages) as span:
        tracer.finish_inference(span, {'choices': [{'message': reply, 'finish_reason': 'stop'}]}, end=False)
    return span


async def _tool_loop(tracer):
    """One turn: model asks for a tool, the knowledge tool runs, the model answers."""
    call = {
        'role': 'assistant',
        'content': '',
        'tool_calls': [
            {'id': 'call-1', 'function': {'name': 'query_knowledge_files', 'arguments': '{"query": "electronics"}'}}
        ],
    }

    @traced_knowledge_tool(tracer)
    async def query_knowledge_files(query: str, count: int = 5):
        return json.dumps(CHUNKS)

    with tracer.workflow('invoke_workflow open-webui.chat'):
        _chat(tracer, [SYSTEM, QUESTION], call)
        await traced_tool(
            tracer,
            name='query_knowledge_files',
            call_id='call-1',
            tool_type='builtin',
            arguments={'query': 'electronics'},
            direct=False,
            call=lambda: query_knowledge_files('electronics'),
        )
        tool_message = {'role': 'tool', 'tool_call_id': 'call-1', 'content': json.dumps(CHUNKS)}
        answer = {'role': 'assistant', 'content': 'Electronics have a 15-day window (a.md, section 4).'}
        _chat(tracer, [SYSTEM, QUESTION, call, tool_message], answer)
    return answer


def _spans(exporter):
    return {span.name: span for span in exporter.get_finished_spans()}, exporter.get_finished_spans()


@pytest.mark.asyncio
async def test_tool_loop_records_each_piece_of_content_once():
    tracer, exporter = _tracer()
    await _tool_loop(tracer)
    named, spans = _spans(exporter)
    first, second = [span for span in spans if span.name == 'chat agent']
    retrieval, tool = named['retrieval'], named['execute_tool query_knowledge_files']

    assert len(_attr(first, 'gen_ai.input.messages')) == 2  # first call: everything is new
    system, question, call, response = _attr(second, 'gen_ai.input.messages')
    assert system == {
        'role': 'system',
        'parts': [{'type': 'reference', 'span_id': _hex(first), 'attribute': 'gen_ai.input.messages', 'index': 0}],
    }
    assert question['parts'][0]['index'] == 1
    # The assistant tool call is the first call's generated output.
    assert call['parts'] == [
        {'type': 'reference', 'span_id': _hex(first), 'attribute': 'gen_ai.output.messages', 'index': 0}
    ]
    # The chunks are recorded once, as the retrieval documents.
    assert json.loads(retrieval.attributes['gen_ai.retrieval.documents'])[0]['source'] == 'a.md'
    documents_ref = {'type': 'reference', 'span_id': _hex(retrieval), 'attribute': 'gen_ai.retrieval.documents'}
    assert _attr(tool, 'gen_ai.tool.call.result') == documents_ref
    assert response['role'] == 'tool' and response['parts'][0]['response'] == documents_ref
    assert response['parts'][0]['id'] == 'call-1'


@pytest.mark.asyncio
async def test_next_turn_refers_to_the_whole_previous_turn():
    """The caller propagates one trace across turns (W3C traceparent), as Studio does."""
    tracer, exporter = _tracer()
    follow_up = {'role': 'user', 'content': 'And if the device arrived broken, how long do I have to return it?'}
    with tracer.tracer.start_as_current_span('scenario'):
        answer = await _tool_loop(tracer)
        with tracer.workflow('invoke_workflow open-webui.chat'):
            turn2 = _chat(
                tracer, [SYSTEM, QUESTION, answer, follow_up], {'role': 'assistant', 'content': 'Up to 90 days.'}
            )
    first = next(span for span in exporter.get_finished_spans() if span.name == 'chat agent')
    messages = _attr(turn2, 'gen_ai.input.messages')
    assert [m['parts'][0]['type'] for m in messages] == ['reference', 'reference', 'reference', 'text']
    assert messages[0]['parts'][0]['span_id'] == _hex(first)
    assert messages[2]['parts'][0]['attribute'] == 'gen_ai.output.messages'  # turn 1's final answer
    assert messages[3]['parts'][0]['content'].startswith('And if the device')


@pytest.mark.asyncio
async def test_full_mode_keeps_self_contained_spans():
    tracer, exporter = _tracer(mode='full')
    await _tool_loop(tracer)
    named, spans = _spans(exporter)
    second = [span for span in spans if span.name == 'chat agent'][1]
    assert 'reference' not in second.attributes['gen_ai.input.messages']
    assert _attr(named['execute_tool query_knowledge_files'], 'gen_ai.tool.call.result') == {'content': CHUNKS}


@pytest.mark.asyncio
async def test_other_traces_and_short_content_are_not_referenced():
    tracer, exporter = _tracer()
    await _tool_loop(tracer)
    exporter.clear()
    with tracer.workflow('invoke_workflow other-trace'):  # a new root span: a new trace
        span = _chat(tracer, [SYSTEM, {'role': 'user', 'content': 'hi'}], {'role': 'assistant', 'content': 'hello'})
    assert 'reference' not in span.attributes['gen_ai.input.messages']


def test_registry_is_bounded_and_expires():
    registry = compact.ContentRegistry(max_traces=2, max_entries=1, ttl=60)
    location = {'span_id': 'a' * 16, 'attribute': 'gen_ai.input.messages'}
    registry.remember('t1', 'k1', location)
    registry.remember('t1', 'k2', location)  # over the per-trace limit: not stored
    assert registry.lookup('t1', 'k1') == location and registry.lookup('t1', 'k2') is None
    registry.remember('t2', 'k', location)
    registry.remember('t3', 'k', location)  # evicts the least recently used trace
    assert registry.lookup('t2', 'k') == location and registry.lookup('t1', 'k1') is None
