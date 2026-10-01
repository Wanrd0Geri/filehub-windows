# Task 1 brief — safety engine

Implement **Task 1 only** from `docs/superpowers/plans/2026-09-30-filehub-v1.md`, including its Global Constraints. Read spec and Task 1 before work. No UI/rules work yet. Report in `docs/reports/task-1-sol.md`.

Controller is Astra, implementation model explicitly GPT-6.1 Sol. Do not spawn agents. Use project `.venv` (Python `py -3.12`), install pytest/dev dependencies there; avoid global installs. Branch `feature/filehub-windows-v1`, base `bc06c01`. Commit only your scoped files and report, controller docs may change concurrently.

Follow TDD; read superpowers test-driven-development skill. Crucial safety: destination publication never overwrites, all destructive source transitions require matching fingerprint and write-ahead record. SQLite durable state must distinguish copied target pending source removal from committed move; recover never treats an incomplete copy as a successful target. Keep rollback conservative. File IDs + size/mtime + SHA256 should distinguish replacement and content changes. Do not touch real user files; tests in pytest tmp within workspace or explicit sandbox.

One engine lock shared by all same-app-state instances must cover operations, undo, recovery and (later) service reallocation. Expose a context or callable allocation interface if necessary so Task 3 can atomically allocate semantic versions and execute under the lock without deadlock. Source/target path overlap must be rejected.

Windows recycle adapter must never fall back to unlink; save sufficient recycle identity when available, or mark restore as manual/conflict with explanatory result. Aim to support programmatic safe restore using returned identity; do not pretend generic send2trash is automatically undoable. A failure or unknown recycle result must retain truthful state.

Use injectable platform for deterministic fault tests, but test actual exclusive Windows writes and process lock. Include concurrent second-process test if practical. Directories may explicitly reject in this task with no changes; Task 4 will implement full support. Summarize design questions early through collaboration if blocked. Do not execute any reference Mac script.

Return <=15 lines: status, commit SHA, tests, concerns, report path. Report exact public interfaces and TDD RED/GREEN evidence. Read diff in self-review; controller performs independent review.
