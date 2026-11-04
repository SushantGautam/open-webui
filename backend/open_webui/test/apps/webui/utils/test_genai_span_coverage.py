"""Every way Open WebUI reads content, runs a tool or calls a model emits a GenAI span."""

import inspect
import json

import pytest
from open_webui.utils.telemetry.genai import compact
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.retrieval import _tool_documents, traced_knowledge_tool
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Built-in tools that return stored or web content, and where it comes from.
CONTENT_TOOLS = {
    'query_knowledge_files': 'knowledge',
    'view_knowledge_file': 'knowledge',
    'grep_knowledge_files': 'knowledge',
    'query_chat_files': 'chat_files',
    'grep_chat_files': 'chat_files',
    'view_file': 'files',
    'search_notes': 'notes',
    'view_note': 'notes',
    'search_chats': 'chats',
    'view_chat': 'chats',
    'search_channel_messages': 'channels',
    'view_channel_message': 'channels',
    'view_channel_thread': 'channels',
    'search_memories': 'memories',
    'read_memory_path': 'memories',
    'search_web': 'web',
    'fetch_url': 'web',
}
LIMIT = 10000


def _tracer():
    compact.REGISTRY.clear()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    config = GenAIConfig(capture_retrieval_documents=True, capture_retrieval_query=True)
    return GenAITracer(provider.get_tracer('coverage'), config), exporter


# --- which tools are wrapped -------------------------------------------------------------


def test_every_content_reading_builtin_is_a_retrieval():
    from open_webui.tools import builtin
    from open_webui.tools.knowledge_fs import kb_exec

    for name in CONTENT_TOOLS:
        function = getattr(builtin, name)
        assert hasattr(function, '__wrapped__'), f'{name} emits no retrieval span'
        # The tool spec Open WebUI builds still sees the real signature.
        assert '__request__' in inspect.signature(function).parameters or name in ('search_web', 'fetch_url')
    assert hasattr(kb_exec, '__wrapped__')


def test_inventory_and_write_tools_are_not_retrievals():
    from open_webui.tools import builtin

    for name in (
        'list_knowledge',
        'list_knowledge_bases',
        'list_chat_files',
        'search_knowledge_files',
        'query_knowledge_bases',
        'write_note',
        'add_memory',
    ):
        assert not hasattr(getattr(builtin, name), '__wrapped__'), name


# --- result shapes -----------------------------------------------------------------------


def test_list_of_chunks():
    result = json.dumps(
        [{'content': 'Electronics: 15 days.', 'source': 'refunds.md', 'file_id': 'f1', 'distance': 0.2}]
    )
    assert _tool_documents(result, 10, LIMIT) == [
        {'source': 'refunds.md', 'file_id': 'f1', 'content': 'Electronics: 15 days.'}
    ]


def test_single_file_view():
    """view_knowledge_file / view_file: one object with the whole file."""
    result = json.dumps(
        {'id': 'fac7', 'filename': 'customer_faq.md', 'content': '# FAQ', 'knowledge_id': 'k1', 'knowledge_name': 'KB'}
    )
    assert _tool_documents(result, 10, LIMIT) == [{'id': 'fac7', 'source': 'customer_faq.md', 'content': '# FAQ'}]


def test_web_results_keep_title_and_link():
    result = json.dumps([{'title': 'Returns', 'link': 'https://acme.test/returns', 'snippet': '30 days'}])
    assert _tool_documents(result, 10, LIMIT) == [
        {'source': 'Returns', 'url': 'https://acme.test/returns', 'content': '30 days'}
    ]


def test_fetched_page_text_takes_its_url_as_source():
    assert _tool_documents('Page body', 10, LIMIT, source='https://acme.test') == [
        {'content': 'Page body', 'source': 'https://acme.test'}
    ]


def test_grep_lines_are_grouped_by_file():
    text = (
        'f1  faq.md:3: refund in 30 days\nf1  faq.md:9: refund card\nf2  policy.md:4: refund window\n[3 total matches]'
    )
    assert _tool_documents(text, 10, LIMIT) == [
        {'file_id': 'f1', 'source': 'faq.md', 'content': '3: refund in 30 days\n9: refund card'},
        {'file_id': 'f2', 'source': 'policy.md', 'content': '4: refund window'},
    ]


def test_chat_and_thread_messages_are_documents():
    chat = json.dumps({'id': 'c1', 'title': 'Order help', 'messages': [{'role': 'user', 'content': 'Where is it?'}]})
    assert _tool_documents(chat, 10, LIMIT) == [{'source': 'Order help', 'content': 'Where is it?'}]
    thread = json.dumps(
        {'parent_message': {'id': 'm1', 'content': 'Q'}, 'replies': [{'id': 'm2', 'content': 'A'}], 'title': 'Ch'}
    )
    assert [d['content'] for d in _tool_documents(thread, 10, LIMIT)] == ['A', 'Q']


@pytest.mark.parametrize(
    'result',
    [
        json.dumps({'error': 'File not found'}),
        'No matches for "refund"',
        'Error: Request context not available',
        json.dumps([{'id': 'k1', 'name': 'KB', 'description': 'inventory row'}]),
        json.dumps([]),
    ],
)
def test_errors_empty_results_and_listings_yield_no_documents(result):
    assert _tool_documents(result, 10, LIMIT) == []


# --- the span itself ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_span_names_its_data_source_and_query():
    tracer, exporter = _tracer()

    @traced_knowledge_tool(tracer, 'knowledge')
    async def view_knowledge_file(file_id: str, __request__=None):
        return json.dumps({'id': file_id, 'filename': 'customer_faq.md', 'content': '# FAQ'})

    await view_knowledge_file('fac7')
    (span,) = exporter.get_finished_spans()
    assert span.name == 'retrieval knowledge'
    assert span.attributes['gen_ai.operation.name'] == 'retrieval'
    assert span.attributes['gen_ai.data_source.id'] == 'knowledge'
    assert span.attributes['gen_ai.retrieval.query.text'] == 'fac7'
    assert json.loads(span.attributes['gen_ai.retrieval.documents'])[0]['source'] == 'customer_faq.md'


@pytest.mark.asyncio
async def test_a_failing_normalizer_never_breaks_the_tool(monkeypatch):
    from open_webui.utils.telemetry.genai import retrieval

    tracer, _ = _tracer()
    monkeypatch.setattr(retrieval, '_tool_documents', lambda *a, **k: 1 / 0)

    @traced_knowledge_tool(tracer, 'web')
    async def fetch_url(url: str):
        return 'body'

    assert await fetch_url('https://acme.test') == 'body'


# --- other paths -------------------------------------------------------------------------


def test_recalled_memories_become_retrieval_documents(monkeypatch):
    from types import SimpleNamespace

    from open_webui.utils import memory

    tracer, exporter = _tracer()
    monkeypatch.setattr(memory, '_genai_tracer', tracer)
    results = SimpleNamespace(
        documents=[['prefers email', '']], ids=[['m1', 'm2']], metadatas=[[{'path': 'contact'}, {}]]
    )
    with tracer.retrieval('retrieval memories', operation_name='retrieval') as span:
        memory._record_memory_documents(span, results)
    (span,) = exporter.get_finished_spans()
    assert json.loads(span.attributes['gen_ai.retrieval.documents']) == [
        {'content': 'prefers email', 'id': 'm1', 'source': 'contact'}
    ]


def test_default_function_calling_traces_its_tools():
    """chat_completion_tools_handler (non-native mode) runs tools through traced_tool."""
    from open_webui.utils import middleware

    source = inspect.getsource(middleware.chat_completion_tools_handler)
    assert 'traced_tool(' in source and "tool['callable'](**tool_function_params)" in source


def test_pipe_models_are_traced_as_model_calls():
    from open_webui.utils import chat

    source = inspect.getsource(chat.generate_chat_completion)
    assert "provider='open-webui.function'" in source and 'traced_inference(' in source
