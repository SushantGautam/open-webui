import pytest
from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.retrieval import instrument_embedding, instrument_reranker, traced_retrieval
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


@pytest.mark.asyncio
async def test_embedding_vectors_and_document_content_are_capped_when_enabled():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(
        provider.get_tracer('retrieval-content-test'),
        GenAIConfig(capture_embedding_vectors=True, capture_retrieval_documents=True, content_max_length=8),
    )

    async def embedding(query, prefix=None):
        return [[0.1, 0.2, 0.3, 0.4]]

    @traced_retrieval(tracer)
    async def retrieve(items, queries, k, hybrid_search=False, embedding_function=None):
        await instrument_embedding(tracer, embedding_function)('query')
        return items

    await retrieve(
        items=[{'metadata': {'document_id': 'doc-1'}, 'document': ['document-content-too-long']}],
        queries=['query'],
        k=1,
        embedding_function=embedding,
    )
    spans = exporter.get_finished_spans()
    embedding_span = next(span for span in spans if span.name == 'embedding')
    retrieval_span = next(span for span in spans if span.name == 'retrieval')
    assert len(embedding_span.attributes['gen_ai.embeddings']) <= 8
    assert '"content": "document"' in retrieval_span.attributes['gen_ai.retrieval.documents'][0]
    assert 'document-content-too-long' not in retrieval_span.attributes['gen_ai.retrieval.documents'][0]
