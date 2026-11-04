"""Open WebUI emits canonical GenAI spans consumed by SimpleAudit Studio."""
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from open_webui.utils.telemetry.genai.config import GenAIConfig
from open_webui.utils.telemetry.genai.tracer import GenAITracer


def test_genai_trace_has_workflow_inference_retrieval_and_tool():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GenAITracer(tracer=provider.get_tracer(__name__), config=GenAIConfig())

    with tracer.workflow("invoke_workflow open-webui.chat", operation_name="invoke_workflow") as workflow:
        with tracer.inference(
            "chat qwen3",
            operation_name="chat",
            request_model="qwen3",
        ) as llm:
            with tracer.tool(
                "execute_tool acme_get_order",
                operation_name="execute_tool",
                tool_name="acme_get_order",
                tool_call_id="tool-call-1",
            ):
                pass
        with tracer.retrieval("retrieval", operation_name="retrieval"):
            pass
        with tracer.embedding("embeddings qwen3-embedding", operation_name="embeddings"):
            pass

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert len(spans) == 5
    expected = {
        "invoke_workflow open-webui.chat": "invoke_workflow",
        "chat qwen3": "chat",
        "execute_tool acme_get_order": "execute_tool",
        "retrieval": "retrieval",
        "embeddings qwen3-embedding": "embeddings",
    }
    for name, operation in expected.items():
        assert spans[name].attributes["gen_ai.operation.name"] == operation
        assert not any(key.startswith("openinference.") for key in spans[name].attributes)

    assert spans["chat qwen3"].attributes["gen_ai.request.model"] == "qwen3"
    assert spans["execute_tool acme_get_order"].attributes["gen_ai.tool.name"] == "acme_get_order"
    assert spans["execute_tool acme_get_order"].attributes["gen_ai.tool.call.id"] == "tool-call-1"
    assert spans["chat qwen3"].parent.span_id == workflow.get_span_context().span_id
    assert spans["execute_tool acme_get_order"].parent.span_id == llm.get_span_context().span_id
