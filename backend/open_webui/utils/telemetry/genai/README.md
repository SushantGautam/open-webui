# OpenTelemetry GenAI tracing (Open WebUI)

This instrumentation emits vendor-neutral **OTLP** spans using the
[OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai).
The schema contract was reviewed against upstream revision
[`633cbb060b16b1487ea2dcd23c4307edc1a03f01`](https://github.com/open-telemetry/semantic-conventions-genai/tree/633cbb060b16b1487ea2dcd23c4307edc1a03f01).
The GenAI conventions are still in **Development**; updating the schema requires tests.

## Span structure

| Operation | Span kind | Name |
| --- | --- | --- |
| Chat workflow | `INTERNAL` | `invoke_workflow open-webui.chat` |
| Inference via HTTP API | `CLIENT` | `chat {model}` |
| Tool invocation | `INTERNAL` | `execute_tool {name}` |
| RAG document retrieval | `INTERNAL` | `retrieval {source}` or `retrieval` |
| Embedding request | `CLIENT` | `embeddings {model}` or `embeddings` |
| Reranking stage | `INTERNAL` | `rerank` (custom task, not a standard GenAI operation) |

Each span exposes `gen_ai.operation.name` when a standard operation exists.
LLM spans also carry model/provider, response identifiers, finish reasons and token usage
when supplied by the provider. W3C `traceparent` continues to connect inbound
audit requests to their Open WebUI spans.

## Structured content

Python's OTel span attributes don't support nested maps. We emit JSON strings,
validated by construction against the official message and document shapes:

- `gen_ai.input.messages`: full ordered role/parts history, including tool-call
  requests and tool-call responses. System messages in history stay in this field.
- `gen_ai.output.messages`: one assistant message per generated choice;
  streaming SSE and native Ollama NDJSON are accumulated before export.
- `gen_ai.system_instructions`: only system instructions supplied *separately*
  from the chat history.
- `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`: JSON objects.
  Plain-text results are wrapped as `{"content": "..."}`.
- `gen_ai.retrieval.documents`: **actual returned chunks**, flattened from
  Open WebUI's document/metadata arrays. Records use standard `id` and
  `score` only when known; document `source` and `file_id` are additional
  metadata permitted by the official schema. Vector *distance* is **not**
  misreported as relevance `score`.

A tool such as `list_knowledge` enumerates a knowledge-base inventory.
Its files therefore remain in `gen_ai.tool.call.result`; this does **not**
produce fake `gen_ai.retrieval.documents`.

JSON is always serialized **after** clipping textual fields. Content truncation
does not turn a valid JSON object into malformed JSON. `OTEL_GENAI_CONTENT_MAX_LENGTH`
caps individual string fields (not the total serialized attribute length);
arrays and objects are also capped to 100 entries per nesting level. At most
`GenAIConfig.retrieval_max_documents` retrieved documents are captured.

## Capture configuration — changed default

**Content capture is opt-in** (previously most fields were enabled by default).
Structural telemetry remains enabled.

```bash
OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT=true
OTEL_GENAI_CONTENT_MAX_LENGTH=10000
```

The standard `OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT` flag enables content
capture. Existing field-level switches still override it individually:

`OTEL_GENAI_CAPTURE_INPUTS`, `OTEL_GENAI_CAPTURE_OUTPUTS`,
`OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS`,
`OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS`, `OTEL_GENAI_CAPTURE_TOOL_RESULTS`,
`OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY`,
`OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS`, and
`OTEL_GENAI_CAPTURE_EMBEDDING_TEXT`.

Embeddings *vectors* remain **disabled**, even with the master switch enabled;
`OTEL_GENAI_CAPTURE_EMBEDDING_VECTORS=true` explicitly enables the custom
`openwebui.embedding.vectors` field. There is no standard
`gen_ai.embeddings` vector attribute; `gen_ai.embeddings.dimension.count`
is used for dimensions.

Avoid enabling content capture for untrusted OTLP receivers. Tool outputs,
queries and documents can contain sensitive data. Transport settings are
controlled by the existing `OTEL_EXPORTER_OTLP_*` configuration.

## Application extensions

Use standardized `gen_ai.*` attributes whenever possible.
Only Open WebUI-specific details use `openwebui.*` attributes (such as
`openwebui.message.id`, `openwebui.operation.purpose`,
`openwebui.retrieval.collection_names`, and
`openwebui.embedding.input`). No `studio.*` or `simpleaudit.*`
attributes are required by the emitter.

Known limits: provider `openai-compatible` describes the API adapter and does
not assert the actual upstream model vendor; streaming responses may omit
usage/finish reasons when the provider does not send them; vector search can
supply distances without providing a relevance score.

## Testing

Run:

```bash
cd backend
pytest -q open_webui/test/apps/webui/utils/test_genai_semconv_migration.py
pytest -q open_webui/test/apps/webui/utils/test_genai_{tracer,inference,tools,retrieval,conformance,performance}.py
```

Official schema source:
[model/gen-ai JSON schemas](https://github.com/open-telemetry/semantic-conventions-genai/tree/633cbb060b16b1487ea2dcd23c4307edc1a03f01/model/gen-ai).
