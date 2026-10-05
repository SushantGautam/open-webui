# Execution State

Agent-updated. Do not hand-edit except to fix a factual error. One entry per milestone attempt —
append, don't overwrite history (if a milestone is retried, add a new entry below the old one).

Format per entry:

```
## M<N> — <milestone title>
Status: NOT_STARTED | IN_PROGRESS | COMPLETE | BLOCKED
Requirements completed: <list checklist lines from IMPLEMENTATION_PLAN.md with [x]/[ ]>
Files changed: <paths>
Tests run: <exact command(s)>
Test results: <pass/fail summary, paste key output lines>
Deviations: NONE | <explicit deviation + reason>
Next milestone: M<N+1> | NONE (plan complete)
```

If BLOCKED, also include:

```
Blocked reason: <precise statement>
Evidence: <exact command run + exact error output>
```

---

## M1 — OTLP transport hygiene
Status: NOT_STARTED
Requirements completed: (none yet)
Files changed: (none yet)
Tests run: (none yet)
Test results: (none yet)
Deviations: NONE
Next milestone: M1

## M1 — OTLP transport hygiene
Status: BLOCKED
Requirements completed: [ ] All M1 checklist lines remain unverified because the required test command cannot execute in the current environment.
Files changed: backend/open_webui/utils/telemetry/setup.py; backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py
Tests run: `pytest backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py -v`
Test results: FAIL — 3 failed. Importing OTel fails with `ImportError: cannot import name '_ExtendedAttributes' from 'opentelemetry.util.types'`; importing `open_webui.env` also fails with `SystemExit: WEBUI_SECRET_KEY is not set`.
Deviations: NONE
Next milestone: M1
Blocked reason: The required M1 verification command cannot pass because the execution environment has incompatible installed OTel versions (`opentelemetry-api==1.45.0`, `opentelemetry-sdk==1.39.1`, `opentelemetry-exporter-otlp==1.39.1`, while `backend/requirements.txt` pins the OTel core packages to `1.42.1`) and lacks `WEBUI_SECRET_KEY` for importing the application environment. Satisfying the checklist requires changing the environment or receiving human direction; no code workaround is permitted by the plan.
Evidence: `python -m pip show opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp opentelemetry-semantic-conventions` reported versions `1.45.0`, `1.39.1`, `1.39.1`, and `0.60b1`, respectively. `pytest backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py -v` reported `ImportError: cannot import name '_ExtendedAttributes' from 'opentelemetry.util.types'` and `SystemExit: WEBUI_SECRET_KEY is not set`.

## M1 — OTLP transport hygiene
Status: COMPLETE
Requirements completed: [x] Basic-auth Authorization header preserved; [x] unset basic-auth passes `headers=None`; [x] `OTEL_EXPORTER_OTLP_HEADERS=foo=bar` is honored; [x] HTTP and default gRPC exporter paths covered; [x] gRPC `OTEL_EXPORTER_OTLP_INSECURE` preserved; [x] required test file created; [x] required pytest command passes.
Files changed: backend/open_webui/utils/telemetry/setup.py; backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py
Tests run: `uv sync`; `uv pip install --python .venv/bin/python -r backend/requirements.txt`; `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/tests/test_env.py -v`; `uv run ruff check backend/open_webui/utils/telemetry/setup.py backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py`; `git diff --check`
Test results: PASS — required telemetry test: `3 passed, 1 warning in 2.19s`; existing environment test: `1 passed`; Ruff: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M2

## M2 — Wheel packaging for observability deps
Status: COMPLETE
Requirements completed: [x] Added `observability` optional dependency extra listing every `opentelemetry-*` package from `backend/requirements.txt` at its pinned version; [x] clean-venv editable install succeeded; [x] gRPC OTLP exporter import succeeded without a separate package install.
Files changed: pyproject.toml; uv.lock
Tests run: `uv sync`; `uv lock`; `clean_env_dir=$(mktemp -d) && uv venv "$clean_env_dir" && uv pip install --python "$clean_env_dir/bin/python" -e '.[observability]' && "$clean_env_dir/bin/python" -c "import opentelemetry.exporter.otlp.proto.grpc.trace_exporter; print('grpc exporter import ok')"`; `uv sync --extra observability && uv run python -c "import opentelemetry.exporter.otlp.proto.grpc.trace_exporter; print('project grpc exporter import ok')"`; `uv run ruff check backend/open_webui/utils/telemetry/setup.py backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py`; `git diff --check`
Test results: PASS — clean venv installed `open-webui==0.11.4` with OTel dependencies and printed `grpc exporter import ok`; project extra sync printed `project grpc exporter import ok`; Ruff: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M3

## M3 — Semantic core: config, semconv, context, tracer
Status: COMPLETE
Requirements completed: [x] Official/fallback semantic constants centralized in `semconv.py`; [x] no semantic-key literals outside `semconv.py`; [x] workflow/inference/embedding/retrieval/rerank/tool context managers with child spans, exception recording, ERROR status, re-raising user exceptions, and fail-open telemetry handling; [x] recording checks precede extraction; [x] capture flags and truncation implemented; [x] streaming wrapper closes on exhaustion, error, and cancellation; [x] InMemorySpanExporter tests cover kinds, errors, privacy, truncation, and cancellation; [x] required pytest command passes.
Files changed: backend/open_webui/utils/telemetry/genai/__init__.py; backend/open_webui/utils/telemetry/genai/config.py; backend/open_webui/utils/telemetry/genai/semconv.py; backend/open_webui/utils/telemetry/genai/context.py; backend/open_webui/utils/telemetry/genai/tracer.py; backend/open_webui/utils/telemetry/genai/extractors.py; backend/open_webui/utils/telemetry/genai/streaming.py; backend/open_webui/utils/telemetry/genai/openinference.py; backend/open_webui/test/apps/webui/utils/test_genai_tracer.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_tracer.py -v`; `uv run ruff check backend/open_webui/utils/telemetry/genai backend/open_webui/test/apps/webui/utils/test_genai_tracer.py`; semantic-key grep; `git diff --check`
Test results: PASS — `5 passed in 0.06s`; Ruff: `All checks passed!`; literal-key grep: `literal-key grep passed`; diff check: passed.
Deviations: NONE
Next milestone: M4

## M4 — Workflow root span + context propagation
Status: COMPLETE
Requirements completed: [x] Chat orchestration call path now wraps `_process_chat`/`process_chat_payload()` in `ai_tracer.workflow(...)`; [x] workflow name is exactly `invoke_workflow open-webui.chat` and contains no IDs; [x] conversation/message/purpose attributes are set and propagated through `context.py`; [x] deferred workflow span remains open until streaming iterator exhaustion/cancellation; [x] background workflow purpose can be non-primary; [x] InMemorySpanExporter tests added; [x] required pytest command passes.
Files changed: backend/open_webui/main.py; backend/open_webui/utils/telemetry/genai/tracer.py; backend/open_webui/test/apps/webui/utils/test_genai_workflow_context.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_workflow_context.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run python -c "import open_webui.main; print('main import ok')"`; `uv run ruff check --select I backend/open_webui/main.py backend/open_webui/test/apps/webui/utils/test_genai_workflow_context.py`; `git diff --check`
Test results: PASS — workflow tests: `3 passed`; main import: `main import ok`; import lint: `All checks passed!`; diff check: passed. Full-file Ruff reports pre-existing unrelated violations in `main.py`.
Deviations: NONE
Next milestone: M5

## M5 — Inference spans (model gateway)
Status: COMPLETE
Requirements completed: [x] OpenAI-compatible and Ollama chat-completions outbound boundaries wrapped in `ai_tracer.inference`; [x] provider/request model/response model/response ID/usage/finish reason and request sampling attributes supported; [x] streaming spans close only after body iteration; [x] input capture remains flag-controlled through extractors; [x] two-round tool-loop and independent usage test; [x] privacy test for both provider paths; [x] required pytest command passes.
Files changed: backend/open_webui/routers/openai.py; backend/open_webui/routers/ollama.py; backend/open_webui/utils/telemetry/genai/tracer.py; backend/open_webui/utils/telemetry/genai/inference.py; backend/open_webui/test/apps/webui/utils/test_genai_inference.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_inference.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run python -c "import open_webui.routers.openai; import open_webui.routers.ollama; print('gateway imports ok')"`; `uv run ruff check --select I --fix backend/open_webui/routers/openai.py backend/open_webui/routers/ollama.py backend/open_webui/utils/telemetry/genai/inference.py backend/open_webui/test/apps/webui/utils/test_genai_inference.py`; `git diff --check`
Test results: PASS — inference tests: `3 passed`; gateway imports: `gateway imports ok`; import lint: `All checks passed!`; diff check: passed. Full-file Ruff reports pre-existing unrelated violations in the gateway modules.
Deviations: NONE
Next milestone: M6

## M6 — Tool execution spans
Status: COMPLETE
Requirements completed: [x] Legacy, approved/resumed, and Responses API tool execution paths call the shared tool tracer; [x] tool spans carry `execute_tool`, name, call ID, and official tool type classification; [x] arguments/results honor independent capture flags; [x] active OTel context preserves HTTP auto-instrumentation as a child span; [x] two-tool parent/child topology test; [x] privacy/content tests; [x] required pytest command passes.
Files changed: backend/open_webui/utils/middleware.py; backend/open_webui/utils/telemetry/genai/semconv.py; backend/open_webui/utils/telemetry/genai/tools.py; backend/open_webui/test/apps/webui/utils/test_genai_tools.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_tools.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run python -c "import open_webui.utils.middleware; print('middleware import ok')"`; `uv run ruff check --select I --fix backend/open_webui/utils/middleware.py backend/open_webui/test/apps/webui/utils/test_genai_tools.py`; `git diff --check`
Test results: PASS — tool tests: `3 passed`; middleware import: `middleware import ok`; import lint: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M7

## M7 — Retrieval, embedding, rerank spans
Status: COMPLETE
Requirements completed: [x] `get_sources_from_items()` call path is decorated with a retrieval span; [x] retrieval mode, top-k, candidate/selected counts, and data-source metadata are emitted, with query capture gated; [x] result document IDs/file/chunk/rank/score metadata is emitted independently of content capture; [x] embedding callbacks get child spans with independently gated text/vectors; [x] configured rerank callbacks get child RERANKER spans; [x] span-tree and privacy tests added; [x] required pytest command passes.
Files changed: backend/open_webui/retrieval/utils.py; backend/open_webui/utils/telemetry/genai/semconv.py; backend/open_webui/utils/telemetry/genai/retrieval.py; backend/open_webui/test/apps/webui/utils/test_genai_retrieval.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_retrieval.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run python -c "import open_webui.retrieval.utils; print('retrieval import ok')"`; `uv run ruff check --select I --fix backend/open_webui/retrieval/utils.py backend/open_webui/utils/telemetry/genai/retrieval.py backend/open_webui/test/apps/webui/utils/test_genai_retrieval.py`; `git diff --check`
Test results: PASS — retrieval tests: `2 passed`; retrieval import: `retrieval import ok`; import lint: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M8

## M8 — Background vs. primary classification
Status: COMPLETE
Requirements completed: [x] Existing task metadata values are mapped to `title_generation`, `followup_generation`, `tags_generation`, and `retrieval_query`; [x] primary inference/workflow defaults remain `primary`; [x] title/background versus primary test coverage added; [x] required pytest command passes.
Files changed: backend/open_webui/utils/telemetry/genai/purpose.py; backend/open_webui/utils/telemetry/genai/inference.py; backend/open_webui/test/apps/webui/utils/test_genai_purpose.py
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_purpose.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run python -c "import open_webui.routers.tasks; print('tasks import ok')"`; `uv run ruff check --select I --fix backend/open_webui/utils/telemetry/genai/inference.py backend/open_webui/test/apps/webui/utils/test_genai_purpose.py`; `git diff --check`
Test results: PASS — purpose tests: `2 passed`; tasks import: `tasks import ok`; import lint: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M9

## M9 — Conformance test suite + golden topology snapshots
Status: COMPLETE
Requirements completed: [x] Conformance coverage exists for all 20 scenario rows with graph/attribute assertions; [x] four golden topology JSON snapshots exist and are diffed by tests; [x] required conformance pytest command passes.
Files changed: backend/open_webui/test/apps/webui/utils/test_genai_conformance.py; backend/open_webui/test/apps/webui/utils/telemetry/golden/simple_chat.json; backend/open_webui/test/apps/webui/utils/telemetry/golden/rag_chat.json; backend/open_webui/test/apps/webui/utils/telemetry/golden/tool_loop.json; backend/open_webui/test/apps/webui/utils/telemetry/golden/rag_rerank_tool.json
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_conformance.py -v`; `uv run ruff check --select I --fix backend/open_webui/test/apps/webui/utils/test_genai_conformance.py`; `git diff --check`
Test results: PASS — `24 passed in 0.08s`; import lint: `All checks passed!`; diff check: passed.
Deviations: NONE
Next milestone: M10

## M10 — Cross-backend interoperability check
Status: COMPLETE
Requirements completed: [x] Documented export of the M9 `rag_rerank_tool` representative trace to local Phoenix, local/hosted Langfuse, and generic Jaeger/Tempo using standard `OTEL_EXPORTER_OTLP_ENDPOINT` changes; [x] documented backend-specific rendering differences as known differences with no backend-specific code.
Files changed: backend/open_webui/utils/telemetry/genai/README.md; EXECUTION_STATE.md
Tests run: `test -s backend/open_webui/utils/telemetry/genai/README.md && rg -n "OTEL_GENAI_|Phoenix|Langfuse|Jaeger|Tempo|rag_rerank_tool|known differences" backend/open_webui/utils/telemetry/genai/README.md`; `git diff --check`
Test results: PASS — README contains all required destinations, fixture, environment procedure, and known-differences section; diff check passed.
Deviations: NONE
Next milestone: M11

## M11 — Performance gates
Status: COMPLETE
Requirements completed: [x] Disabled tracing benchmark stays within the agreed 20 ms total overhead for 20,000 spans; [x] disabled capture and non-recording paths prove extractor JSON serialization is not called; [x] explicit caps tested for tool arguments, tool results, message content, retrieval document count, and exception payload size; [x] required performance test file added; [x] required pytest command passes.
Files changed: backend/open_webui/utils/telemetry/genai/config.py; backend/open_webui/utils/telemetry/genai/tracer.py; backend/open_webui/utils/telemetry/genai/retrieval.py; backend/open_webui/utils/telemetry/genai/streaming.py; backend/open_webui/utils/telemetry/genai/README.md; backend/open_webui/test/apps/webui/utils/test_genai_performance.py; EXECUTION_STATE.md
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_performance.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_tracer.py backend/open_webui/test/apps/webui/utils/test_genai_retrieval.py backend/open_webui/test/apps/webui/utils/test_genai_conformance.py -q`; `uv run ruff check backend/open_webui/utils/telemetry/genai backend/open_webui/test/apps/webui/utils/test_genai_performance.py`; `git diff --check`
Test results: PASS — performance tests `3 passed in 0.12s`; regression/conformance tests `31 passed in 0.08s`; Ruff: `All checks passed!`; diff check passed.
Deviations: NONE
Next milestone: M12

## M12 — Fork maintenance documentation
Status: COMPLETE
Requirements completed: [x] `FORK.md` documents the downstream semantic telemetry patch, all M4–M8 hook-point files, and the M9 conformance acceptance command; [x] `backend/open_webui/utils/telemetry/genai/README.md` documents every `OTEL_GENAI_*` variable and the M10 interoperability procedure.
Files changed: FORK.md; backend/open_webui/utils/telemetry/genai/README.md; EXECUTION_STATE.md
Tests run: `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_conformance.py -v`; `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_genai_performance.py -q`; `WEBUI_SECRET_KEY=test-secret-key uv run pytest backend/open_webui/test/apps/webui/utils/test_telemetry_setup.py -v`; `uv run ruff check --select I backend/open_webui/test/apps/webui/utils/test_genai_conformance.py backend/open_webui/test/apps/webui/utils/test_genai_performance.py backend/open_webui/utils/telemetry/genai`; `git diff --check`; full-plan audit: `sed -n '1,430p' IMPLEMENTATION_PLAN.md`
Test results: PASS — conformance `24 passed in 0.10s`; performance `3 passed in 0.10s`; locked telemetry setup `3 passed, 1 warning in 3.32s`; import lint `All checks passed!`; diff check passed; full-plan audit completed with M1–M12 checklist coverage.
Deviations: NONE
Next milestone: NONE (plan complete)
