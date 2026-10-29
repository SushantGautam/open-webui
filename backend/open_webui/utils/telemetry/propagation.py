"""W3C trace-context propagation for inbound requests.

Open WebUI exports OTLP spans for its GenAI workflow (see
``open_webui.utils.telemetry.genai``), but by default it starts every request
on a fresh, self-generated trace id: the OpenTelemetry ``TracerProvider`` is
created without a global text-map propagator and no middleware extracts an
incoming W3C ``traceparent`` header.

SimpleAudit Studio propagates a per-turn W3C ``traceparent`` on every request
it sends to the OpenAI-compatible chat endpoint so that the spans the target
exports can be correlated back to the exact scenario/turn that produced them.
Without this module those headers are ignored and Studio falls back to a
coarse wall-clock window to attribute spans, which misattributes spans across
back-to-back scenarios sharing one OTLP credential.

This module wires up the standard W3C TraceContext propagator and provides an
ASGI middleware that extracts the incoming ``traceparent`` into the active
OpenTelemetry context for the duration of the request. Because GenAI spans are
started with ``tracer.start_span(...)`` (which parents off the *current*
context), the whole span tree for a request then nests under the propagated
trace id — making precise per-request correlation possible.

The change is entirely additive and inert when tracing is disabled or no
``traceparent`` is present: extraction simply yields the unchanged context.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Header names (lower-cased) we look for on inbound requests. The W3C
#: standard is case-insensitive; ASGI scope headers arrive lower-cased.
_TRACEPARENT_KEY = b'traceparent'


def install_propagator() -> None:
    """Register the W3C TraceContext text-map propagator globally.

    Idempotent and safe to call multiple times. Must run before any span is
    started so that ``opentelemetry.propagate.extract`` knows how to parse the
    incoming ``traceparent`` header.
    """
    try:
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        set_global_textmap(TraceContextTextMapPropagator())
    except Exception:  # pragma: no cover - telemetry is best-effort
        logger.exception('Unable to install W3C trace-context propagator')


class TraceContextMiddleware:
    """Pure-ASGI middleware that extracts inbound W3C trace context.

    Reads the ``traceparent`` / ``tracestate`` headers from the ASGI scope and
    applies the global propagator's ``extract`` so downstream code (including
    GenAI span creation) inherits the caller's trace/span ids. When no valid
    header is present the context is left untouched, so normal browser traffic
    is unaffected.

    Implemented as a raw ASGI middleware (not ``BaseHTTPMiddleware``) to match
    the rest of the app's middleware stack and avoid anyio cancel-scope issues.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return

        try:
            from opentelemetry import context as otel_context
            from opentelemetry.propagate import extract

            raw_headers = scope.get('headers') or []
            # Only pay the extraction cost when a traceparent is actually sent.
            if any(k == _TRACEPARENT_KEY for k, _ in raw_headers):
                # ASGI headers are (bytes, bytes); the W3C propagator's default
                # getter expects str keys/values, so decode them.
                carrier = {k.decode('latin-1'): v.decode('latin-1') for k, v in raw_headers}
                # ``extract`` takes the header carrier first; pass the current
                # context so any already-active span is preserved as parent.
                ctx = extract(carrier, otel_context.get_current())
                token = otel_context.attach(ctx)
                try:
                    await self.app(scope, receive, send)
                finally:
                    otel_context.detach(token)
                return
        except Exception:  # pragma: no cover - never break the request path
            logger.exception('Trace-context extraction failed; continuing')

        await self.app(scope, receive, send)
