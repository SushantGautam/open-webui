"""GenAI instrumentation must not synthesize OpenInference attributes."""
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.tracer import GenAITracer


def test_genai_tool_span_without_openinference_kind():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(tracer=provider.get_tracer(__name__), config=GenAIConfig())

    with tracer.tool(
        "execute_tool acme_get_order",
        operation_name="execute_tool",
        tool_name="acme_get_order",
    ):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["gen_ai.operation.name"] == "execute_tool"
    assert attrs["gen_ai.tool.name"] == "acme_get_order"
    assert "openinference.span.kind" not in attrs
