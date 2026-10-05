import os
from dataclasses import dataclass


def _as_bool(value: str | None) -> bool:
    return (value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class GenAIConfig:
    capture_inputs: bool = False
    capture_outputs: bool = False
    capture_system_instructions: bool = False
    capture_tool_arguments: bool = False
    capture_tool_results: bool = False
    capture_retrieval_query: bool = False
    capture_retrieval_documents: bool = False
    capture_embedding_text: bool = False
    capture_embedding_vectors: bool = False
    content_max_length: int = 2000

    @classmethod
    def from_env(cls) -> 'GenAIConfig':
        try:
            max_length = max(int(os.getenv('OTEL_GENAI_CONTENT_MAX_LENGTH', '2000')), 0)
        except (TypeError, ValueError):
            max_length = 2000
        return cls(
            capture_inputs=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_INPUTS')),
            capture_outputs=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_OUTPUTS')),
            capture_system_instructions=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS')),
            capture_tool_arguments=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS')),
            capture_tool_results=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_TOOL_RESULTS')),
            capture_retrieval_query=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY')),
            capture_retrieval_documents=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS')),
            capture_embedding_text=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_EMBEDDING_TEXT')),
            capture_embedding_vectors=_as_bool(os.getenv('OTEL_GENAI_CAPTURE_EMBEDDING_VECTORS')),
            content_max_length=max_length,
        )
