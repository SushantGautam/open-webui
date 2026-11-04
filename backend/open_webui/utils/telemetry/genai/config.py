"""GenAI content capture configuration (privacy-preserving defaults)."""
import os
from dataclasses import dataclass

def _as_bool(value):
    return (value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

def _flag(key, default):
    value = os.getenv(key)
    return default if value is None else _as_bool(value)

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
        master = _as_bool(os.getenv('OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT', 'true'))
        return cls(
            enabled=os.getenv('OTEL_GENAI_ENABLED', 'true').strip().lower() not in {'0', 'false', 'no', 'off'},
            capture_inputs=_flag('OTEL_GENAI_CAPTURE_INPUTS', master),
            capture_outputs=_flag('OTEL_GENAI_CAPTURE_OUTPUTS', master),
            capture_system_instructions=_flag('OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS', master),
            capture_tool_arguments=_flag('OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS', master),
            capture_tool_results=_flag('OTEL_GENAI_CAPTURE_TOOL_RESULTS', master),
            capture_retrieval_query=_flag('OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY', master),
            capture_retrieval_documents=_flag('OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS', master),
            capture_embedding_text=_flag('OTEL_GENAI_CAPTURE_EMBEDDING_TEXT', master),
            capture_embedding_vectors=_flag('OTEL_GENAI_CAPTURE_EMBEDDING_VECTORS', False),
            content_max_length=max_length,
        )
