import json

from open_webui.utils.telemetry.genai.config import GenAIConfig


def _truncate(value, limit: int):
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return value[:limit]


def capture(value, *, enabled: bool, config: GenAIConfig):
    if not enabled:
        return None
    return _truncate(value, config.content_max_length)


def capture_attributes(attributes: dict, config: GenAIConfig) -> dict:
    flags = {
        'inputs': config.capture_inputs,
        'outputs': config.capture_outputs,
        'system_instructions': config.capture_system_instructions,
        'tool_arguments': config.capture_tool_arguments,
        'tool_result': config.capture_tool_results,
        'retrieval_query': config.capture_retrieval_query,
        'retrieval_documents': config.capture_retrieval_documents,
        'embedding_text': config.capture_embedding_text,
        'embedding_vectors': config.capture_embedding_vectors,
    }
    captured = {}
    for name, value in attributes.items():
        if name in flags:
            value = capture(value, enabled=flags[name], config=config)
        if value is not None:
            captured[name] = value
    return captured
