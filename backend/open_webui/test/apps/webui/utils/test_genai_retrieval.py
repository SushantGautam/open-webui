import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.retrieval import instrument_embedding, instrument_reranker
from open_webui.utils.telemetry.genai.tracer import GenAITracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.mark.asyncio
async def test_retrieval_tree_has_embedding_and_rerank_children():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('retrieval-test'), GenAIConfig())

    async def embedding(query, prefix=None):
        return [[0.1, 0.2]]

    def rerank(query, documents):
        return [0.9 for _ in documents]

    with tracer.retrieval('retrieval') as parent:
        await instrument_embedding(tracer, embedding)('query')
        instrument_reranker(tracer, rerank)('query', ['document'])
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ['embedding', 'rerank', 'retrieval']
    assert all(span.parent.span_id == parent.get_span_context().span_id for span in spans[:2])
    assert spans[1].attributes['openinference.span.kind'] == 'RERANKER'


@pytest.mark.asyncio
async def test_embedding_and_retrieval_content_are_private_by_default():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(provider.get_tracer('retrieval-privacy-test'), GenAIConfig())

    async def embedding(query, prefix=None):
        return [[0.1, 0.2]]

    with tracer.retrieval('retrieval') as parent:
        await instrument_embedding(tracer, embedding)('secret query')
        parent.set_attribute('gen_ai.retrieval.documents', ['{"document_id": "doc-1", "rank": 1, "score": 0.9}'])
    spans = exporter.get_finished_spans()
    assert 'gen_ai.retrieval.query.text' not in spans[0].attributes
    assert 'gen_ai.embeddings' not in spans[0].attributes
    assert spans[-1].attributes['gen_ai.retrieval.documents']
