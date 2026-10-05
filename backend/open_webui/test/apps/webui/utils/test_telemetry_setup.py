import importlib


class _Instrumentor:
    def instrument(self):
        pass


def _reload_exporter_modules(monkeypatch, exporter_headers):
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_HEADERS', 'foo=bar')
    monkeypatch.delenv('OTEL_BASIC_AUTH_USERNAME', raising=False)
    monkeypatch.delenv('OTEL_BASIC_AUTH_PASSWORD', raising=False)

    import opentelemetry.exporter.otlp.proto.grpc.trace_exporter as grpc_exporter
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as http_exporter

    importlib.reload(grpc_exporter)
    importlib.reload(http_exporter)

    grpc = grpc_exporter.OTLPSpanExporter(endpoint='http://localhost:4317')
    http = http_exporter.OTLPSpanExporter(endpoint='http://localhost:4318/v1/traces')
    exporter_headers.append((grpc._headers, http._headers))


def test_sdk_otlp_headers_are_used_when_basic_auth_is_unset(monkeypatch):
    headers = []
    _reload_exporter_modules(monkeypatch, headers)

    grpc_headers, http_headers = headers[0]
    assert ('foo', 'bar') in grpc_headers
    assert http_headers.get('foo') == 'bar'


def test_setup_passes_none_headers_without_basic_auth(monkeypatch):
    import open_webui.utils.telemetry.setup as telemetry_setup

    captured = []

    class Exporter:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    class Provider:
        def add_span_processor(self, processor):
            pass

    monkeypatch.setattr(telemetry_setup, 'HttpOTLPSpanExporter', Exporter)
    monkeypatch.setattr(telemetry_setup, 'OTLPSpanExporter', Exporter)
    monkeypatch.setattr(telemetry_setup.trace, 'set_tracer_provider', lambda provider: None)
    monkeypatch.setattr(telemetry_setup.trace, 'get_tracer_provider', lambda: Provider())
    monkeypatch.setattr(telemetry_setup, 'Instrumentor', lambda **kwargs: _Instrumentor())
    monkeypatch.setattr(telemetry_setup, 'ENABLE_OTEL_TRACES', True)
    monkeypatch.setattr(telemetry_setup, 'OTEL_BASIC_AUTH_USERNAME', '')
    monkeypatch.setattr(telemetry_setup, 'OTEL_BASIC_AUTH_PASSWORD', '')
    monkeypatch.setattr(telemetry_setup, 'OTEL_OTLP_SPAN_EXPORTER', 'grpc')
    telemetry_setup.setup(None, None)
    assert captured[-1]['headers'] is None

    monkeypatch.setattr(telemetry_setup, 'OTEL_OTLP_SPAN_EXPORTER', 'http')
    telemetry_setup.setup(None, None)
    assert captured[-1]['headers'] is None


def test_setup_preserves_basic_auth_and_grpc_insecure(monkeypatch):
    import open_webui.utils.telemetry.setup as telemetry_setup

    captured = []

    class Exporter:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    class Provider:
        def add_span_processor(self, processor):
            pass

    monkeypatch.setattr(telemetry_setup, 'OTLPSpanExporter', Exporter)
    monkeypatch.setattr(telemetry_setup.trace, 'set_tracer_provider', lambda provider: None)
    monkeypatch.setattr(telemetry_setup.trace, 'get_tracer_provider', lambda: Provider())
    monkeypatch.setattr(telemetry_setup, 'Instrumentor', lambda **kwargs: _Instrumentor())
    monkeypatch.setattr(telemetry_setup, 'ENABLE_OTEL_TRACES', True)
    monkeypatch.setattr(telemetry_setup, 'OTEL_BASIC_AUTH_USERNAME', 'user')
    monkeypatch.setattr(telemetry_setup, 'OTEL_BASIC_AUTH_PASSWORD', 'pass')
    monkeypatch.setattr(telemetry_setup, 'OTEL_OTLP_SPAN_EXPORTER', 'grpc')
    monkeypatch.setattr(telemetry_setup, 'OTEL_EXPORTER_OTLP_INSECURE', True)
    telemetry_setup.setup(None, None)

    assert captured[-1]['headers'] == [('authorization', 'Basic dXNlcjpwYXNz')]
    assert captured[-1]['insecure'] is True
