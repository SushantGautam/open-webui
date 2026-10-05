import logging
from contextlib import contextmanager

from open_webui.utils.telemetry.genai import context, extractors, semconv
from open_webui.utils.telemetry.genai import openinference as oi
from open_webui.utils.telemetry.genai.config import GenAIConfig
from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)


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

    @contextmanager
    # The lifecycle guard intentionally handles independent failure points.
    def _span(self, kind, name, **attrs):  # noqa: C901
        span = None
        token = None
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
            except Exception:
                logger.exception('Unable to initialize GenAI span')

            try:
                yield span
            except BaseException as exc:
                try:
                    span.record_exception(exc)
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
            if span is not None:
                try:
                    span.end()
                except Exception:
                    logger.exception('Unable to end GenAI span')
