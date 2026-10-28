import os
from dataclasses import dataclass


def _as_bool(value: str | None) -> bool:
    return (value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class GenAIConfig:
    enabled: bool = True
    capture_inputs: bool = False
    capture_outputs: bool = False
    capture_system_instructions: bool = False
    capture_tool_arguments: bool = False
    capture_tool_results: bool = False
    capture_retrieval_query: bool = False
    capture_retrieval_documents: bool = False
    capture_embedding_text: bool = False
    capture_embedding_vectors: bool = False
    content_max_length: int = 10000
    retrieval_max_documents: int = 100
    exception_max_length: int = 2000

    @classmethod
    def from_env(cls) -> 'GenAIConfig':
        try:
            max_length = max(int(os.getenv('OTEL_GENAI_CONTENT_MAX_LENGTH', '10000')), 0)
        except (TypeError, ValueError):
            max_length = 10000
        return cls(
            enabled=os.getenv('OTEL_GENAI_ENABLED', 'true').strip().lower() not in {'0', 'false', 'no', 'off'},
            capture_inputs=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_INPUTS', 'true')),
            capture_outputs=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_OUTPUTS', 'true')),
            capture_system_instructions=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS', 'true')),
            capture_tool_arguments=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS', 'true')),
            capture_tool_results=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_TOOL_RESULTS', 'true')),
            capture_retrieval_query=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY', 'true')),
            capture_retrieval_documents=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS', 'true')),
            capture_embedding_text=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_EMBEDDING_TEXT', 'true')),
            capture_embedding_vectors=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_EMBEDDING_VECTORS', 'false')),
            content_max_length=max_length,
        )
