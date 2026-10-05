import logging
from contextlib import contextmanager

from open_webui.utils.telemetry.genai import context, extractors, semconv
from open_webui.utils.telemetry.genai import openinference as oi
from open_webui.utils.telemetry.genai.config import GenAIConfig
from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)


def _record_exception(span, exc, limit):
    if not span.is_recording():
        return
    span.add_event(
        'exception',
        {
            'exception.type': type(exc).__name__,
            'exception.message': str(exc)[:limit],
        },
    )


class GenAITracer:
    def __init__(self, tracer=None, config: GenAIConfig | None = None):
        self.tracer = tracer or trace.get_tracer(__name__)
        self.config = config or GenAIConfig.from_env()

    def workflow(self, name='invoke_workflow', **attrs):
        return self._span('workflow', name, **attrs)

    def inference(self, name='inference', **attrs):
        return self._span('inference', name, **attrs)

    def embedding(self, name='embedding', **attrs):
        return self._span('embedding', name, **attrs)

    def retrieval(self, name='retrieval', **attrs):
        return self._span('retrieval', name, **attrs)

    def rerank(self, name='rerank', **attrs):
        return self._span('rerank', name, **attrs)

    def tool(self, name='execute_tool', **attrs):
        return self._span('tool', name, **attrs)

    def finish_inference(self, span, response):
        try:
            if span.is_recording() and isinstance(response, dict):
                usage = response.get('usage') or {}
                attributes = {
                    semconv.GEN_AI_RESPONSE_MODEL: response.get('model'),
                    semconv.GEN_AI_RESPONSE_ID: response.get('id'),
                    semconv.GEN_AI_USAGE_INPUT_TOKENS: usage.get('prompt_tokens', usage.get('input_tokens')),
                    semconv.GEN_AI_USAGE_OUTPUT_TOKENS: usage.get('completion_tokens', usage.get('output_tokens')),
                    semconv.GEN_AI_RESPONSE_FINISH_REASONS: [
                        choice.get('finish_reason')
                        for choice in response.get('choices', [])
                        if isinstance(choice, dict) and choice.get('finish_reason') is not None
                    ],
                }
                span.set_attributes({key: value for key, value in attributes.items() if value is not None})
            span.end()
        except Exception:
            logger.exception('Unable to finish GenAI inference span')

    @contextmanager
    # The lifecycle guard intentionally handles independent failure points.
    def _span(self, kind, name, **attrs):  # noqa: C901
        if not self.config.enabled:
            yield trace.INVALID_SPAN
            return
        defer_end = attrs.pop('_defer_end', False)
        span = None
        token = None
        failed = False
        try:
            try:
                span = self.tracer.start_span(name)
            except Exception:
                logger.exception('Unable to start GenAI span')
                yield trace.INVALID_SPAN
                return

            try:
                token = trace.use_span(span, end_on_exit=False)
                token.__enter__()
                if span.is_recording():
                    safe_attrs = extractors.capture_attributes(attrs, self.config)
                    resolved = {
                        semconv.attribute_key(key): value
                        for key, value in safe_attrs.items()
                        if value is not None
                    }
                    resolved.update(oi.attributes_for(kind))
                    if resolved:
                        span.set_attributes(resolved)
                    if kind == 'workflow':
                        context.apply_context(span, attrs)
                        context.set_context(
                            chat_id=attrs.get('chat_id'),
                            message_id=attrs.get('message_id'),
                            conversation_id=attrs.get('conversation_id'),
                            purpose=attrs.get('purpose', 'primary'),
                        )
            except Exception:
                logger.exception('Unable to initialize GenAI span')

            try:
                yield span
            except BaseException as exc:
                failed = True
                try:
                    _record_exception(span, exc, self.config.exception_max_length)
                    span.set_status(StatusCode.ERROR)
                except Exception:
                    logger.exception('Unable to record GenAI span exception')
                raise
        finally:
            if token is not None:
                try:
                    token.__exit__(None, None, None)
                except Exception:
                    logger.exception('Unable to detach GenAI span context')
            if span is not None and (not defer_end or failed):
                try:
                    span.end()
                except Exception:
                    logger.exception('Unable to end GenAI span')
