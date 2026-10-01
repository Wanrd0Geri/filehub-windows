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
- Ruling: merged-shot primary participates in project dedup; only newly generated supplemental copy bypasses dedup — original requirement says only the copy is exempt, root confirms no contrary accepted behavior — cost if wrong: users wanting same content linked to new shots must copy/manually associate separately. Duplicate 2/3-shot requests recycle source and create no further copies.
- Task 1 interim evidence (implementer-reported, pre-final): `.venv\Scripts\python.exe -X utf8 -m pytest -q` RED 19 failed; GREEN 19 passed in 1.40s; native recycle and extra guard/fault tests still in progress, not accepted yet.
- Task 1 pre-review Important: undo(copy) can remove sole surviving original content when source is absent/edited or paired move undo conflicts. Requested protected matching-content survivor before deleting copy, with regression tests. Also assessing atomic staging publication to avoid incomplete final filenames during copy/crash.
- Ruling: require verified sibling staging + atomic no-overwrite rename for forward transfer and undo restore before Task1 acceptance — parent confirms avoiding cloud-visible partial final files is load-bearing safety — cost if wrong: additional state handling/test complexity. Sol estimated existing Guard.rename supports a small scoped change.
- Task 1 interim evidence update: Sol reported GREEN 38 (native write/delete/rename locks, reparse/state/download protection, recycle failure/unknown/manual restore, undo/copy faults), then 42 passed/1 deselected after undo guard-lifetime regression; latest pre-review-fix full run 44 passed. Native IFileOperation recycled a workspace sandbox file and Shell.Application Namespace(10) exact-name check found its restorable recycle item. An initial PowerShell verification script failed due to `$args` shadowing; checker corrected, native operation itself succeeded. Not accepted yet: sole-survivor copy undo and atomic staging publication fixes pending. Implementer final report will contain exact final commands and counts.
- Task 1 baseline committed e6a729c (59 passed in 3.45s). Astra stage review Needs fixes: creation/mtime and ADS silently dropped by byte-copy move; original copy-undo survivor and atomic-publication findings are addressed. Fix round 1 dispatched same GPT-6.1 Sol; root confirms NTFS Zone.Identifier/custom streams need safe preservation, not broad rejection. Review: docs/reports/task-1-astra-review.md.
