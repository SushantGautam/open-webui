import contextvars
import logging

from open_webui.utils.telemetry.genai import semconv
from opentelemetry.trace import Span

logger = logging.getLogger(__name__)
_context = contextvars.ContextVar('openwebui_genai_context', default={})


def set_context(*, chat_id=None, message_id=None, conversation_id=None, purpose='primary'):
    values = {
        'chat_id': chat_id,
        'message_id': message_id,
        'conversation_id': conversation_id,
        'purpose': purpose,
    }
    _context.set(values)
    return values


def get_context():
    return dict(_context.get())


def apply_context(span: Span, values=None):
    values = values or get_context()
    attributes = {
        semconv.GEN_AI_CONVERSATION_ID: values.get('conversation_id') or values.get('chat_id'),
        semconv.OPENWEBUI_MESSAGE_ID: values.get('message_id'),
        semconv.OPENWEBUI_OPERATION_PURPOSE: values.get('purpose', 'primary'),
    }
    try:
        span.set_attributes({key: value for key, value in attributes.items() if value is not None})
    except Exception:
        logger.exception('Unable to apply GenAI span context')
