import asyncio

from open_webui.utils.telemetry.propagation import (
    TraceContextMiddleware,
    install_propagator,
)

# A fixed W3C traceparent used to assert adoption end-to-end.
_TRACEPARENT = '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'
_EXPECTED_TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_install_propagator_enables_traceparent_extraction(monkeypatch):
    monkeypatch.delenv('OTEL_TRACES_EXPORTER', raising=False)
    install_propagator()

    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.propagate import extract

    ctx = extract({'traceparent': _TRACEPARENT}, otel_context.get_current())
    span_context = trace.get_current_span(ctx).get_span_context()
    assert format(span_context.trace_id, '032x') == _EXPECTED_TRACE_ID
    assert span_context.is_valid


def test_middleware_adopts_incoming_trace_id_for_child_spans():
    install_propagator()

    from opentelemetry import trace

    captured = {}

    async def inner(scope, receive, send):
        tracer = trace.get_tracer('test')
        with tracer.start_as_current_span('child'):
            span_context = trace.get_current_span().get_span_context()
            captured['trace_id'] = format(span_context.trace_id, '032x')

    middleware = TraceContextMiddleware(inner)
    scope = {
        'type': 'http',
        'headers': [(b'traceparent', _TRACEPARENT.encode('latin-1'))],
    }
    _run_async(middleware(scope, None, None))

    # The child span must inherit the propagated trace id. With no
    # TracerProvider registered in this bare unit context, start_as_current_span
    # still resolves the parent from the attached context, so the trace id
    # matches even though the span itself is non-recording.
    assert captured['trace_id'] == _EXPECTED_TRACE_ID


def test_middleware_is_noop_without_traceparent():
    install_propagator()

    from opentelemetry import trace

    called = {'inner': False}

    async def inner(scope, receive, send):
        called['inner'] = True

    middleware = TraceContextMiddleware(inner)
    scope = {'type': 'http', 'headers': []}
    _run_async(middleware(scope, None, None))

    assert called['inner'] is True


def test_middleware_passes_non_http_scopes_through():
    called = {'inner': False}

    async def inner(scope, receive, send):
        called['inner'] = True

    middleware = TraceContextMiddleware(inner)
    scope = {'type': 'websocket', 'headers': []}
    _run_async(middleware(scope, None, None))

    assert called['inner'] is True
