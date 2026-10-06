# OpenTelemetry GenAI telemetry

This package emits vendor-neutral OpenTelemetry GenAI spans. Structural
attributes are emitted by default; content capture is opt-in and each content
value is truncated to `OTEL_GENAI_CONTENT_MAX_LENGTH` (default `2000`).

## Environment variables

The following `OTEL_GENAI_*` variables are read by the semantic layer. Boolean
values accept `1`, `true`, `yes`, or `on` (case-insensitive).

| Variable | Default | Captures |
| --- | --- | --- |
| `OTEL_GENAI_ENABLED` | `true` | Enables semantic span creation |
| `OTEL_GENAI_CAPTURE_INPUTS` | `false` | Model input messages |
| `OTEL_GENAI_CAPTURE_OUTPUTS` | `false` | Model output messages |
| `OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS` | `false` | System instructions |
| `OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS` | `false` | Tool arguments |
| `OTEL_GENAI_CAPTURE_TOOL_RESULTS` | `false` | Tool results |
| `OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY` | `false` | Retrieval queries |
| `OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS` | `false` | Retrieved document content |
| `OTEL_GENAI_CAPTURE_EMBEDDING_TEXT` | `false` | Text sent to embedding providers |
| `OTEL_GENAI_CAPTURE_EMBEDDING_VECTORS` | `false` | Embedding vectors |
| `OTEL_GENAI_CONTENT_MAX_LENGTH` | `2000` | Maximum characters for captured content |

The OTLP destination is configured with the standard OpenTelemetry variables,
including `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, and
`OTEL_EXPORTER_OTLP_INSECURE`. No vendor-specific exporter or attribute is
required.

## Protected content-capture verification

Content capture is disabled by default. For a protected local receiver only,
enable the fields needed by the test and keep the length cap in place:

```bash
OTEL_GENAI_CAPTURE_INPUTS=true \
OTEL_GENAI_CAPTURE_OUTPUTS=true \
OTEL_GENAI_CAPTURE_TOOL_ARGUMENTS=true \
OTEL_GENAI_CAPTURE_TOOL_RESULTS=true \
OTEL_GENAI_CAPTURE_RETRIEVAL_QUERY=true \
OTEL_GENAI_CAPTURE_RETRIEVAL_DOCUMENTS=true \
OTEL_GENAI_CONTENT_MAX_LENGTH=2000
```

Buffered and streamed model outputs are emitted on `gen_ai.output.messages`.
Tool arguments/results, retrieval query/document content, embedding text, and
embedding vectors each remain independently controlled by their corresponding
flag. Do not enable these flags for an untrusted or production telemetry
destination without an explicit data-handling review.

## M10 interoperability procedure

Use the M9 `rag_rerank_tool` scenario as the representative trace: a chat
workflow with retrieval, reranking, and tool execution. Run it with the same
Open WebUI build and change only `OTEL_EXPORTER_OTLP_ENDPOINT` between
backends. Keep content capture disabled unless the destination is a protected
local test system.

1. Start one of the following OTLP-compatible destinations and record its OTLP
   HTTP endpoint:

   - Local Phoenix: `http://localhost:6006/v1/traces`.
   - Local or hosted Langfuse: use the project's OTLP HTTP endpoint, commonly
     `https://<host>/api/public/otel/v1/traces`, together with its documented
     `OTEL_EXPORTER_OTLP_HEADERS` authentication value.
   - Generic Jaeger or Tempo: use the instance's OTLP HTTP `/v1/traces`
     endpoint.

2. Run Open WebUI with the endpoint override, for example:

   ```bash
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces \
   WEBUI_SECRET_KEY=test-secret-key \
   uv run open-webui serve
   ```

   For gRPC-only receivers, use the receiver's OTLP endpoint and set
   `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`; otherwise the HTTP exporter is used.

3. Exercise the `rag_rerank_tool` flow: submit a chat using a knowledge source,
   allow reranking, and invoke a tool. Verify one trace contains the workflow,
   inference, retrieval, rerank, and tool spans. Repeat step 2 for Phoenix,
   Langfuse, and Jaeger/Tempo by changing only
   `OTEL_EXPORTER_OTLP_ENDPOINT` (and, where required, the receiver's standard
   OTLP headers).

### Known differences

- Backend UIs use different names and nesting displays for the same OTLP
  spans. The conformance contract is the span topology and standard semantic
  attributes, not a particular vendor's screen layout.
- Phoenix, Langfuse, Jaeger, and Tempo may omit or flatten attributes they do
  not index or render. This is a presentation/indexing difference; no
  backend-specific code belongs in this repository.
- Langfuse may require authentication headers and may display GenAI spans in
  its generation view only after recognizing the standard GenAI attributes.
- Jaeger and Tempo generally show the generic trace tree and attributes but do
  not provide vendor-specific GenAI generation summaries.
