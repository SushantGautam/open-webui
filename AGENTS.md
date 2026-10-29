# Plan-driven implementation

For work governed by `IMPLEMENTATION_PLAN.md`:

1. `IMPLEMENTATION_PLAN.md` is authoritative. Do not edit it.
2. Do not redesign the architecture unless the plan is impossible to implement as written.
3. Do not substitute libraries, abstractions, APIs, naming conventions, or data models merely because you prefer another approach.
4. Work on exactly one milestone at a time, in order. Do not skip ahead.
5. Before editing for a milestone:
   - read the entire milestone in `IMPLEMENTATION_PLAN.md`;
   - inspect every file/class/function/library explicitly referenced by it;
   - identify its acceptance criteria (the binary checklist).
6. Implement the smallest change that satisfies the milestone.
7. Run every verification command the milestone specifies.
8. Fix failures before progressing. Never weaken a test to make it pass.
9. Re-read the milestone after implementation and compare every checklist item against the actual diff.
10. Update `EXECUTION_STATE.md` (see format there) before moving on.
11. Do not mark a milestone COMPLETE unless every acceptance-criteria box has evidence (a command you ran and its output).
12. Never silently omit a requirement.
13. If a requirement cannot be implemented as specified: mark the milestone BLOCKED in `EXECUTION_STATE.md` with exact evidence (command, error, file/line). Do not invent a workaround that contradicts the plan.
14. Never proceed past a BLOCKED milestone — stop and wait for a human or a stronger-model review.

## Repo-wide rules for this fork (apply to every milestone)

- This is a downstream fork of Open WebUI (see `FORK.md`). Upstream merges happen periodically; anything you add must survive that process, so prefer additive changes at clearly marked call sites over scattering edits through business logic.
- Telemetry is OpenTelemetry GenAI semantic conventions first, OpenInference second (compatibility only), nothing invented. Never emit `simpleaudit.*` attributes. `openwebui.*` attributes only for information with no standard equivalent.
- Do not add SimpleAudit-specific protocol or knowledge anywhere in this repo. The fork must not know SimpleAudit exists — it just emits standard OTLP.
- Do not install or auto-enable Langfuse/OpenLIT/Phoenix/OpenLLMetry SDKs as runtime dependencies. They are reference material only (read their source, don't vendor it).
- Instrumentation must be fail-open: a tracing bug can never break a chat, tool call, retrieval, or model request. Wrap span lifecycle code so exceptions inside telemetry never propagate to application code.
- Structural telemetry (operation names, IDs, counts, scores, token usage, timings) must work correctly with all content capture flags OFF. Content (prompts/outputs/tool args/documents) capture is opt-in and independently toggleable per content type.
- Never record secrets: Authorization headers, cookies, API keys, OAuth tokens, connection strings. Never use raw email as a trace identity — use existing internal IDs.
- Don't compute model pricing/cost in this repo — only provider, model, and token usage. Cost is derived externally.
- Before any expensive attribute extraction/serialization, check `span.is_recording()` first.
- Derive OTel package versions for `pyproject.toml` from what's already pinned in `backend/requirements.txt` — don't pick new versions independently.

## Environment failures are NOT implementation blockers

This repo is `uv`-managed (`uv.lock` at root). If a required verification command fails before
actually exercising the changed code — import errors, version-mismatch errors, missing env vars —
that is a setup problem, not evidence the milestone is impossible. Do not mark BLOCKED on this
basis alone.

1. Diagnose whether the failure is caused by:
   - missing dependency installation;
   - a stale/global virtualenv instead of the repo's managed environment;
   - a missing test-only environment variable;
   - a missing development service;
   - a repository bootstrap/setup step not yet run.
2. Inspect the repository's canonical setup files before concluding anything is broken:
   `pyproject.toml`, `uv.lock`, `backend/requirements.txt`, any `.env.example`, `FORK.md`,
   `.github/workflows/*.yaml`.
3. Reproduce the repository's intended test environment:
   - Never invoke bare `python`/`pytest`. Always use `uv run pytest ...` (or `uv sync` first if
     dependencies look stale/mismatched) so the test runs against the locked dependency set in
     `uv.lock`, not whatever global interpreter happens to resolve.
   - If import of `open_webui.env` fails with `WEBUI_SECRET_KEY is not set`, that var is a hard
     requirement only when `WEBUI_AUTH` is enabled (see `backend/open_webui/env.py`); set it for
     the test invocation only, e.g. `WEBUI_SECRET_KEY=test-secret-key uv run pytest ...`. Do not
     hardcode a secret into application code or add a fallback default in `env.py` — this is a
     test-invocation environment variable, not a code change.
4. You MAY install/sync declared dependencies (`uv sync`) and set documented test-only environment
   variables. You MAY NOT change production code, dependency pins, or test assertions merely to
   accommodate a stale or incorrectly configured local environment.
5. Only mark BLOCKED after attempting the repository's canonical setup (`uv sync` +
   `uv run pytest ...` + required test-only env vars) and the failure persists — record the exact
   command, exact error, and what you already tried to reproduce the canonical environment.

## Continuous execution — do not stop between milestones

Completing a milestone is not a stopping point. After you commit a milestone and update
`EXECUTION_STATE.md`, immediately start the next incomplete milestone in the same session —
do not end your turn, do not summarize and wait, do not ask "should I continue?". Keep going,
milestone after milestone, until either:

- every milestone in `IMPLEMENTATION_PLAN.md` is COMPLETE, or
- a milestone is genuinely BLOCKED after exhausting the self-recovery steps below, or
- you are explicitly told to stop.

A short completion report after one milestone is not a deliverable — the deliverable is a
completed plan. Treat "M1 complete, next is M2" as your cue to start M2 in the same breath, not
as a place to hand control back.

## Self-recovery from blockers

This is a git repository — nearly every failure mode here is recoverable, so exhaust these before
writing BLOCKED:

1. Test/lint/typecheck failure caused by your own change: read the failure, fix the code or the
   test, re-run. This is normal iteration, not a blocker.
2. Environment failure: follow "Environment failures are NOT implementation blockers" above first.
3. You made an edit that turned out wrong mid-milestone: use `git diff`/`git stash`/`git checkout
-- <file>` to back out just that edit and retry differently. You do not need to ask permission
   to revert your own uncommitted work.
4. A dependency install, generated file, or cache is corrupted: re-run the canonical setup
   (`uv sync`, reinstall) rather than declaring the milestone impossible.
5. Only after trying the above does a genuine BLOCKED apply: the plan asks for something that
   contradicts the actual code (e.g. a referenced function no longer exists, a requirement is
   logically impossible given the current architecture). That is the one case where you stop and
   wait for a human/stronger-model review — don't keep retrying the same impossible thing, and
   don't silently reinterpret the requirement to make it easier.

## Execution algorithm (for a fresh executor session)

1. Read, in order: `AGENTS.md` (this file) → `IMPLEMENTATION_PLAN.md` → `EXECUTION_STATE.md` → the repo code relevant to the next incomplete milestone.
2. Determine the first milestone in `IMPLEMENTATION_PLAN.md` not marked COMPLETE in `EXECUTION_STATE.md`.
3. Work ONLY on that milestone. Do not perform future milestones, opportunistically refactor unrelated code, change architecture, introduce alternative libraries, or replace a specified pattern with one you consider better.
4. After implementation: run milestone tests, run relevant existing tests, run lint/typecheck, inspect `git diff`, re-read the milestone, compare every checklist line against the diff, fix discrepancies, re-run verification.
5. Update `EXECUTION_STATE.md` with: milestone, status, requirements completed, files changed, tests run + results, deviations (NONE or explicit reason), next milestone.
6. Commit with a message naming the milestone (e.g. `feat(otel): M3 — tool execution spans`).
7. Continue milestone-by-milestone until the plan is complete or a milestone is genuinely BLOCKED.
8. At full completion, do one final audit: read `IMPLEMENTATION_PLAN.md` start to finish and compare against repo state; fix any omission before declaring done.
