try:
    from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as _gen_ai
except ImportError:  # pragma: no cover - supports older OTel installations
    _gen_ai = None


def _official(name: str, fallback: str) -> str:
    return getattr(_gen_ai, name, fallback) if _gen_ai is not None else fallback


GEN_AI_OPERATION_NAME = _official('GEN_AI_OPERATION_NAME', 'gen_ai.operation.name')
GEN_AI_PROVIDER_NAME = _official('GEN_AI_PROVIDER_NAME', 'gen_ai.provider.name')
GEN_AI_REQUEST_MODEL = _official('GEN_AI_REQUEST_MODEL', 'gen_ai.request.model')
GEN_AI_RESPONSE_MODEL = _official('GEN_AI_RESPONSE_MODEL', 'gen_ai.response.model')
GEN_AI_RESPONSE_ID = _official('GEN_AI_RESPONSE_ID', 'gen_ai.response.id')
GEN_AI_CONVERSATION_ID = _official('GEN_AI_CONVERSATION_ID', 'gen_ai.conversation.id')
GEN_AI_USAGE_INPUT_TOKENS = _official('GEN_AI_USAGE_INPUT_TOKENS', 'gen_ai.usage.input_tokens')
GEN_AI_USAGE_OUTPUT_TOKENS = _official('GEN_AI_USAGE_OUTPUT_TOKENS', 'gen_ai.usage.output_tokens')
GEN_AI_TOOL_NAME = _official('GEN_AI_TOOL_NAME', 'gen_ai.tool.name')
GEN_AI_TOOL_CALL_ID = _official('GEN_AI_TOOL_CALL_ID', 'gen_ai.tool.call.id')
GEN_AI_TOOL_CALL_ARGUMENTS = _official('GEN_AI_TOOL_CALL_ARGUMENTS', 'gen_ai.tool.call.arguments')
GEN_AI_TOOL_CALL_RESULT = _official('GEN_AI_TOOL_CALL_RESULT', 'gen_ai.tool.call.result')
GEN_AI_TOOL_TYPE = _official('GEN_AI_TOOL_TYPE', 'gen_ai.tool.type')
GEN_AI_RETRIEVAL_QUERY_TEXT = _official('GEN_AI_RETRIEVAL_QUERY_TEXT', 'gen_ai.retrieval.query.text')
GEN_AI_RETRIEVAL_DOCUMENTS = _official('GEN_AI_RETRIEVAL_DOCUMENTS', 'gen_ai.retrieval.documents')
GEN_AI_INPUT_MESSAGES = _official('GEN_AI_INPUT_MESSAGES', 'gen_ai.input.messages')
GEN_AI_OUTPUT_MESSAGES = _official('GEN_AI_OUTPUT_MESSAGES', 'gen_ai.output.messages')
GEN_AI_SYSTEM_INSTRUCTIONS = _official('GEN_AI_SYSTEM_INSTRUCTIONS', 'gen_ai.system.instructions')
GEN_AI_RESPONSE_FINISH_REASONS = _official('GEN_AI_RESPONSE_FINISH_REASONS', 'gen_ai.response.finish_reasons')
GEN_AI_REQUEST_TEMPERATURE = _official('GEN_AI_REQUEST_TEMPERATURE', 'gen_ai.request.temperature')
GEN_AI_REQUEST_TOP_P = _official('GEN_AI_REQUEST_TOP_P', 'gen_ai.request.top_p')
GEN_AI_REQUEST_MAX_TOKENS = _official('GEN_AI_REQUEST_MAX_TOKENS', 'gen_ai.request.max_tokens')
GEN_AI_REQUEST_SEED = _official('GEN_AI_REQUEST_SEED', 'gen_ai.request.seed')
GEN_AI_EMBEDDINGS = _official('GEN_AI_EMBEDDINGS', 'gen_ai.embeddings')

OPENWEBUI_MESSAGE_ID = 'openwebui.message.id'
OPENWEBUI_OPERATION_PURPOSE = 'openwebui.operation.purpose'
OPENWEBUI_TOOL_TYPE = 'openwebui.tool.type'
OPENWEBUI_RETRIEVAL_MODE = 'openwebui.retrieval.mode'
OPENWEBUI_RETRIEVAL_TOP_K = 'openwebui.retrieval.top_k'
OPENWEBUI_RETRIEVAL_THRESHOLD = 'openwebui.retrieval.threshold'
OPENWEBUI_RETRIEVAL_CANDIDATE_COUNT = 'openwebui.retrieval.candidate_count'
OPENWEBUI_RETRIEVAL_SELECTED_COUNT = 'openwebui.retrieval.selected_count'
OPENWEBUI_RETRIEVAL_DATA_SOURCE = 'openwebui.retrieval.data_source'
OPENINFERENCE_SPAN_KIND = 'openinference.span.kind'

ALIASES = {
    'operation_name': GEN_AI_OPERATION_NAME,
    'provider': GEN_AI_PROVIDER_NAME,
    'request_model': GEN_AI_REQUEST_MODEL,
    'response_model': GEN_AI_RESPONSE_MODEL,
    'response_id': GEN_AI_RESPONSE_ID,
    'conversation_id': GEN_AI_CONVERSATION_ID,
    'input_tokens': GEN_AI_USAGE_INPUT_TOKENS,
    'output_tokens': GEN_AI_USAGE_OUTPUT_TOKENS,
    'tool_name': GEN_AI_TOOL_NAME,
    'tool_call_id': GEN_AI_TOOL_CALL_ID,
    'tool_arguments': GEN_AI_TOOL_CALL_ARGUMENTS,
    'tool_result': GEN_AI_TOOL_CALL_RESULT,
    'retrieval_query': GEN_AI_RETRIEVAL_QUERY_TEXT,
    'retrieval_documents': GEN_AI_RETRIEVAL_DOCUMENTS,
    'inputs': GEN_AI_INPUT_MESSAGES,
    'outputs': GEN_AI_OUTPUT_MESSAGES,
    'system_instructions': GEN_AI_SYSTEM_INSTRUCTIONS,
    'finish_reasons': GEN_AI_RESPONSE_FINISH_REASONS,
    'temperature': GEN_AI_REQUEST_TEMPERATURE,
    'top_p': GEN_AI_REQUEST_TOP_P,
    'max_tokens': GEN_AI_REQUEST_MAX_TOKENS,
    'seed': GEN_AI_REQUEST_SEED,
    'embedding_vectors': GEN_AI_EMBEDDINGS,
    'message_id': OPENWEBUI_MESSAGE_ID,
    'purpose': OPENWEBUI_OPERATION_PURPOSE,
    'tool_type': GEN_AI_TOOL_TYPE,
    'retrieval_mode': OPENWEBUI_RETRIEVAL_MODE,
    'top_k': OPENWEBUI_RETRIEVAL_TOP_K,
    'threshold': OPENWEBUI_RETRIEVAL_THRESHOLD,
    'candidate_count': OPENWEBUI_RETRIEVAL_CANDIDATE_COUNT,
    'selected_count': OPENWEBUI_RETRIEVAL_SELECTED_COUNT,
    'data_source': OPENWEBUI_RETRIEVAL_DATA_SOURCE,
}


def attribute_key(name: str) -> str:
    return ALIASES.get(name, name)
