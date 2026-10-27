# Release notes · 0.5.0-rc1

Added a local project/review/evidence/compare workbench over the previously accepted CSV deterministic core. Added manual draft baseline and OpenAI-compatible JSON adapter, explicit outbound confirmation, bounded retries/cost reservations, persistent jobs, optimistic approval versions, immutable run snapshots, corrected batches, CSV/Point GeoJSON input and API/CLI.

Added offline template/injected-defect evaluation, a frozen public USGS point case, lifecycle/security tests, DOM check, startup scripts, container/CI definitions, source packaging and release scan.

Fixed SQLite connection lifetime and original text-reader resource lifetime. Document source hashes now use raw bytes; CRLF does not silently change the evidence hash. No prior frozen verdict expectations were relaxed.

Not verified: real LLM service/quality/cost, normal-browser attachment save, Docker build/run, remote CI, multi-agent benefit or user time savings. This is a source release candidate, not a completed independent acceptance of all original Stage 2–5 goals. See docs/RELEASE_STATUS.md.

Continuation 2026-10-27: DeepSeek Flash preset, CNY estimates, official-host restriction, hidden key launcher, live 12-case preparation/runner, 23 application tests, mobile project switching, real Chromium workflow assertions and authentic 182-second recording. No live provider call made without a key.

Qwen continuation: Beijing qwen-plus profile, dedicated-key precedence, enable_thinking=false, pricing-tier input bound, hidden key startup, 24 application tests passing. Real Qwen call remains pending the user key.

First Qwen HTTP smoke attempted with a user-configured in-process key; failed without usage. Preserve safe HTTP status/error category and stop retrying non-retryable 4xx errors. 25 application tests pass; live authentication and quality remain unverified pending restart/recheck.

User-requested credential entry: Qwen/DeepSeek Python launchers now read work/private/<provider>.env literally, without an interactive prompt. Runtime-only files remain excluded from Git, Docker and source ZIP.
