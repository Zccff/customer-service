# Full local startup implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement and review task-by-task.

**Goal:** Run the existing knowledge, admin jobs, monitoring, evaluation, review and classifier modules on this Windows machine.
**Architecture:** Keep existing API contracts and frontend. Use the project's Python environment, local databases and local Langfuse. Adapt Windows execution without changing task identifiers. Preserve existing data and distinguish archived reports from fresh results.
**Tech Stack:** Python 3.12, FastAPI, MySQL, Milvus, Docker, Langfuse, PyTorch/ONNX.
**Spec:** User-approved six-item completion checklist in this conversation (2026-09-12).

## Global constraints
- No deletion of existing knowledge or conversations; back up reports before regeneration.
- Never print model secrets. Existing configured model calls are authorized, including knowledge embedding and training corpus generation.
- Keep frontend and API contracts. No real refund or external customer communication.
- This directory has no Git repository; use file backups and review diffs instead of commits/worktrees.

### Task 1: Windows background jobs
Files: app/core/jobs.py; a focused scripts Windows task runner and classifier lifecycle helper if needed; tests/test_jobs.py and focused new tests.
- [ ] Back up changed files under log/full-start/before.
- [ ] Write failing tests for Windows fixed-allowlist dispatch, UTF-8 environment, duplicate start protection and stopping the process tree.
- [ ] Preserve Unix make behavior; on Windows dispatch fixed commands with sys.executable, no caller-provided shell text. Cover all registered jobs including SQL stdin and classifier lifecycle.
- [ ] Run focused tests and a real safe kb-preview job; record report and diff under log/full-start.

### Task 2: Knowledge embeddings
Files: app/core/embeddings.py, tests/test_embeddings.py.
- [ ] Reproduce provider batch limit: current provider rejects batches above 10.
- [ ] Test more than 10 inputs with a fake provider that rejects oversized batches, preserving order, and test empty input.
- [ ] Batch sequentially in groups of 10, validate output cardinality, preserve existing single-query behavior.
- [ ] Run tests, vectorize pending chunks, verify MySQL/Milvus counts and actual retrieval.

### Task 3: Local monitoring
Files: docker-compose.langfuse.local.yml, .env (private), startup scripts/documentation.
- [ ] Start existing Langfuse compose with localhost-only exposed UI ports and isolated project name; avoid other project ports.
- [ ] Configure local project keys without printing secrets, restart app and verify fresh traces.
- [ ] Generate fresh cost report, report missing pricing honestly rather than inventing costs.

### Task 4: Evaluation and review loop
Files: existing scripts/eval_ch04.py, scripts/eval_flywheel.py, scripts/calibrate_confidence.py, scripts/flywheel_pipeline.py; fixes only if actual failures.
- [ ] Back up data/ch04 and data/ch09 reports.
- [ ] Validate evaluation dataset against current KB; run fresh evaluation and threshold calibration, preserving provenance and actual scores.
- [ ] Use an explicitly marked synthetic question with verified answer to test collection, review, writeback and retrieval, no fake business policy.

### Task 5: Topic classifier
Files: existing scripts/ch10 pipeline, data/ch10, Windows service helper.
- [ ] Inspect GPU and disk; install compatible ML dependencies into project-local environment.
- [ ] Back up historical reports, validate golden prompt, generate corpus and split without data leakage.
- [ ] Train, evaluate, export ONNX, start :8110 and verify predictions and pool classification. Never alter acceptance thresholds to force passing.

### Task 6: Integration and handoff
- [ ] Review implementation diffs and resolve findings.
- [ ] Run applicable/full tests once changes stabilize; verify admin module states and service restart behavior.
- [ ] Update 本机启动说明.md with actual completed states, monitoring access and any remaining blockers.
