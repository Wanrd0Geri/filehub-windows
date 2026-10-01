# SDD ledger — plan: docs/superpowers/plans/2026-09-30-filehub-v1.md

## Identity and decisions
- Controller: GPT-6 Astra (`/root/astra_director`); implementers: GPT-6.1 Sol fresh per phase. Root owns goal and user communication.
- Ruling: use PySide6 Widgets instead of QML — custom QSS meets approved visual direction with less IPC/model complexity — cost if wrong: UI refactor.
- Ruling: dedicated supplied workspace + feature branch is isolation; no extra worktree — user-authorized — cost if wrong: worktree move only.
- Ruling: source ZIP fixed under reference and read-only by convention; never execute Mac entry points — preserve rule evidence — no product cost.
- Ruling: in-session Astra controller performs stage spec/quality review under explicit user delegation, independent Astra whole-branch review at end — cost if wrong: later defect correction.
- Ruling: controller preserves durable briefs/reports under docs instead of deleting evidence — user requires auditable delivery — cost: small repository size.

## Preflight consistency
| Pair/task | Produced and consumed | Finding |
|---|---|---|
| 1 | operations + journal, safety tests | internally consistent; directory support may finish in 4 |
| 2 | deterministic rule targets | internally consistent, source now available |
| 3 | service previews and execution | internally consistent |
| 4 | scheduler and integration | internally consistent, no real folders in tests |
| 5 | GUI/tray/CLI | internally consistent |
| 6 | package + integration verification | internally consistent |
| 1→3,4 | engine/fingerprint used by service/sweep | report pins final signatures |
| 2→3 | rule destinations used in locked execute | reallocate under lock required |
| 3→4,5 | service/config shared | all mutations centralized |
| 4→5 | timer/IPC integration ownership | scheduler logic separate from UI timer |
| 5→6 | CLI/GUI packaged entry | isolated state flags needed |
| 1–5→6 | acceptance + offline binary | repeat package validation if fixes |

## Progress
- Source recovered at original path after user restored it; copied/extracted safely under reference. Original scripts not executed.
- Plan self-review complete; ready for Task 1.
- Task 1: dispatched GPT-6.1 Sol `/root/astra_director/sol_safety`, brief `docs/briefs/task-1.md`, base bc06c01; initial baseline has no product/tests.
