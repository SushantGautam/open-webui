from open_webui.utils.telemetry.genai import semconv

_KINDS = {
    'rerank': 'RERANKER',
    'tool': 'TOOL',
    'embedding': 'EMBEDDING',
    'retrieval': 'RETRIEVER',
    'inference': 'LLM',
    'workflow': 'CHAIN',
}


def attributes_for(kind: str) -> dict:
    value = _KINDS.get(kind)
    return {semconv.OPENINFERENCE_SPAN_KIND: value} if value else {}
