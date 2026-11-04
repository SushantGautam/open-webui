import logging
from contextlib import contextmanager

from open_webui.utils.telemetry.genai import compact, content, context, extractors, semconv
from open_webui.utils.telemetry.genai.config import GenAIConfig
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

logger = logging.getLogger(__name__)


def _record_exception(span, exc, limit):
    if not span.is_recording():
        return
    span.set_attribute('error.type', type(exc).__name__)
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

    def task(self, name, **attrs):
        """Trace an application-level task without labeling it a GenAI workflow."""
        return self._span('task', name, **attrs)

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

    def finish_inference(self, span, response, *, end=True):
        """Annotate an inference span; streaming callers end after iteration."""
        try:
            if span.is_recording() and isinstance(response, dict):
                usage = response.get('usage') or {}
                if not isinstance(usage, dict):
                    usage = {}
                attrs = {
                    semconv.GEN_AI_RESPONSE_MODEL: response.get('model'),
                    semconv.GEN_AI_RESPONSE_ID: response.get('id'),
                    semconv.GEN_AI_USAGE_INPUT_TOKENS: usage.get(
                        'prompt_tokens', usage.get('input_tokens', response.get('prompt_eval_count'))
                    ),
                    semconv.GEN_AI_USAGE_OUTPUT_TOKENS: usage.get(
                        'completion_tokens', usage.get('output_tokens', response.get('eval_count'))
                    ),
                    semconv.GEN_AI_RESPONSE_FINISH_REASONS: content.normalized_finish_reasons(response),
                }
                span.set_attributes({key: val for key, val in attrs.items() if val is not None})
                if self.config.capture_outputs:
                    messages = content.output_messages(response, self.config.content_max_length)
                    if messages:
                        if self.config.content_mode == 'compact':
                            compact.remember_messages(span, semconv.GEN_AI_OUTPUT_MESSAGES, messages)
                        span.set_attribute(
                            semconv.GEN_AI_OUTPUT_MESSAGES,
                            content.json_attribute(messages, self.config.content_max_length),
                        )
        except Exception:
            logger.exception('Unable to finish GenAI inference span')
        finally:
            if end:
                span.end()

    def finish_stream(self, span, stream_capture):
        """Streaming metadata can arrive in the final SSE/NDJSON chunk."""
        try:
            self.finish_inference(span, stream_capture.finish(), end=False)
        except Exception:
            logger.exception('Unable to capture streaming GenAI output')

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
                kinds = {
                    'workflow': SpanKind.INTERNAL,
                    'task': SpanKind.INTERNAL,
                    'inference': SpanKind.CLIENT,
                    'embedding': SpanKind.CLIENT,
                    'retrieval': SpanKind.INTERNAL,
                    'rerank': SpanKind.INTERNAL,
                    'tool': SpanKind.INTERNAL,
                }
                operation = attrs.get('operation_name') or {
                    'workflow': 'invoke_workflow',
                    'inference': 'chat',
                    'embedding': 'embeddings',
                    'retrieval': 'retrieval',
                    'tool': 'execute_tool',
                }.get(kind)
                initial = {semconv.GEN_AI_OPERATION_NAME: operation} if operation else {}
                if attrs.get('request_model'):
                    initial[semconv.GEN_AI_REQUEST_MODEL] = attrs['request_model']
                if attrs.get('tool_name'):
                    initial[semconv.GEN_AI_TOOL_NAME] = attrs['tool_name']
                span = self.tracer.start_span(name, kind=kinds.get(kind, SpanKind.INTERNAL), attributes=initial)
            except Exception:
                logger.exception('Unable to start GenAI span')
                yield trace.INVALID_SPAN
                return

            try:
                token = trace.use_span(span, end_on_exit=False)
                token.__enter__()
                if span.is_recording():
                    attrs.setdefault('operation_name', operation)
                    # Workflow wrappers repeat the turn's input; content is kept on model/tool spans.
                    safe_attrs = extractors.capture_attributes(
                        attrs, self.config, span=None if kind == 'workflow' else span
                    )
                    resolved = {
                        semconv.attribute_key(key): value for key, value in safe_attrs.items() if value is not None
                    }
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
