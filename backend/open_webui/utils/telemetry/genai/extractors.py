"""Schema-aware GenAI content conversion for OTLP span attributes."""

from open_webui.utils.telemetry.genai import content
from open_webui.utils.telemetry.genai.config import GenAIConfig


def capture(value, *, enabled: bool, config: GenAIConfig):
    if not enabled or value is None:
        return None
    if isinstance(value, str):
        return value[: config.content_max_length]
    return content.json_attribute(value, config.content_max_length)


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
        if value is None:
            continue
        if name in flags:
            if not flags[name]:
                continue
            if name == 'inputs':
                value = content.input_messages(value, config.content_max_length)
            elif name == 'outputs':
                value = content.output_messages(value, config.content_max_length)
            elif name == 'system_instructions':
                value = content.system_instructions(value, config.content_max_length)
            elif name in ('tool_arguments', 'tool_result'):
                value = content.as_object(value, result=(name == 'tool_result'))
            elif name == 'retrieval_documents' and not isinstance(value, list):
                continue
            if name in (
                'inputs',
                'outputs',
                'system_instructions',
                'tool_arguments',
                'tool_result',
                'retrieval_documents',
            ):
                if value is None:
                    continue
                value = content.json_attribute(value, config.content_max_length)
            else:
                value = capture(value, enabled=True, config=config)
        if value is not None:
            captured[name] = value
    return captured
