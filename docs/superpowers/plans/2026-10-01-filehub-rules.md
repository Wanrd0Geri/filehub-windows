# FileHub 0.2.0 Rules and Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver editable project templates and safe, explainable ordered automation rules in a reviewed Windows 0.2.0 installer.

**Architecture:** Keep the existing OperationEngine and default route implementation. Add state-local template definitions, a focused automation package for rule validation/matching/planning/execution/ledger, and independent Qt editor modules; connect all I/O through the existing serial worker.

**Tech Stack:** Existing Python 3.12+, PySide6 6.11.2, SQLite, pytest and PyInstaller/Inno; image conversion uses reviewed Qt WebP plugin/source materials per conversion addendum; no video encoder dependency.

**Spec:** `docs/superpowers/specs/2026-10-01-filehub-rules-design.md`.

## Global Constraints

- Worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`; original `F:/Hazel Windows` is read-only dependency source.
- Version target 0.2.0; empty rules/default template preserve 0.1.1 behavior. No automatic enabling/migration side effects.
- Include image conversion and image rule actions per `docs/superpowers/specs/2026-10-01-filehub-conversion-addendum.md`; exclude video conversion/OCR/scripts/upload/permanent-delete/recursive scan. No live install, registry, real watch/sync/process operations; no push/merge.
- New, copied and imported rules default disabled. Top-level scan, first enabled match, ordered actions, copy changes subject, failure stops following actions.
- Conditions max 4 group levels/100 leaves; actions max 20. Finite non-evaluating naming tokens. Full source/template/rule revisions bind previews.
- Shared worker/process lock; state-local JSON definitions and SQLite automation ledger; existing engine is sole material mutation authority.
- Fresh GPT-6.1 Sol implementers at coherent boundaries; director reviews and commits serially. Root owns baseline/final independent gate. Do not spawn worker reviewers.
- Runtime junction points at existing .venv: no pip changes. Non-pytest source commands must set PYTHONPATH to this worktree/src. All new test outputs in this worktree/sandbox.

## Review Focus

1. An old preview after template/rule edit or demo/service switch must perform no mutation (Tasks 1, 3, 4).
2. A malicious imported pattern/path or junction parent must fail without partial settings replacement or writes outside chosen scope (Tasks 1, 2, 3).
3. Copy→rename/move, folder chains and partial failures must have correct subject lineage, history and conservative undo (Task 3).
4. Restart after success/partial/crash must not repeat copy or let legacy fallback move the source (Task 3).
5. New UI controls under small windows/long Chinese paths must be reachable without GUI-thread I/O or stale-state callbacks (Task 4).

## File responsibilities

- `templates.py`: template/library validation, built-in defaults, atomic store and revision; `naming.py`: finite token validation/rendering.
- Existing `rules.py`/`service.py`: narrow optional template routing/naming and stale-revision checks, legacy default unchanged.
- `automation/models.py`: rule document schema/store/digest; `conditions.py`: facts/tree evaluation/explanations; `planner.py`: pure ordered target planning; `ledger.py`: observations/run claims/progress; `runner.py`: service facade and engine execution.
- Existing `scheduler.py`: narrow first-match-before-legacy integration, existing timer/pause preserved.
- `ui/rules_page.py`, `ui/condition_editor.py`, `ui/action_editor.py`, `ui/templates_page.py`: novice form editors. Existing `ui/main_window.py`/`ui/app.py`: wiring and invalidation only.
- `tests/test_templates.py`, `test_automation_models.py`, `test_automation_conditions.py`, `test_automation_planner.py`, `test_automation_runner.py`, `test_automation_ui.py`: focused behavior coverage. Existing regressions stay authoritative.

### Task 1: Editable template model and compatible project routing

**Files:** Create `src/filehub/templates.py`, `src/filehub/naming.py`, `tests/test_templates.py`; modify `rules.py`, `service.py` narrowly. No UI/scheduler/engine/packaging edits.

**Interfaces:** `TemplateStore(state_dir).load() -> TemplateLibrary`, `.save(library, expected_revision=None) -> TemplateLibrary`; library exposes `templates`, `assignments`, `revision`, and `.for_project(code) -> ProjectTemplate`. `ProjectTemplate` contains fields specified in spec; built-in default is always available. `validate_pattern(pattern, allowed_tokens)` and `render_pattern(pattern, values) -> str` use no evaluation. Extend `parse_tag(..., templates=None)` and RouteSpec with optional naming context; `build_targets` honors it while no-argument defaults remain byte-compatible. FileHubService owns `templates` store, preview batches expose template revision (default-compatible field), execute rejects stale revision before material mutation. Provide `service.reload_templates()` or equivalent explicit method for UI/runner, documented in report.

- [ ] Write tests: absent store leaves disk untouched/default routing exact; round-trip custom mappings/asset category/per-project assignment; unsupported version/duplicate IDs/unknown assignment rejected; assigned template deletion blocked; invalid relative paths/tokens/Windows devices rejected atomically; custom naming sequence and collision; legacy source naming fixtures unchanged; old preview after saved template edit produces no material mutation; normal/demo independence.
- [ ] Run new tests RED and record failing assertions.
- [ ] Implement schema/store, safe finite renderer and narrow routing integration. Default template uses old naming logic, custom modes override only explicit patterns. Preserve all existing service outcome/history semantics.
- [ ] Run `pytest tests/test_templates.py tests/test_rules.py tests/test_service.py -q --basetemp=sandbox/rules020-task1` using workspace venv. Record command/output and interface examples.
- [ ] Self-review, report `docs/reports/rules-020/task1-sol.md`, freeze. Director reviews then commits scoped files.

### Task 2: Rule schema, condition explanations and read-only action plans

**Files:** Create automation package models/conditions/planner and three corresponding test files. Consume Task 1 naming/template APIs. No scheduler/UI/material execution edits.

**Interfaces:** `RuleStore(state_dir).load() -> RuleSet` / `.save(ruleset, expected_revision=None)`, `.import_document(data) -> RuleSet` / `.export_document() -> dict`; RuleSet ordered `.rules`, `.revision`. Rule immutable content `.revision` excludes enabled/order. `FileFacts` includes path/fingerprint/kind/size/timestamps/optional observations. `evaluate(condition, facts, now) -> MatchExplanation` with `.matched` and child/reason detail. `plan_rule(rule, facts, service, occupied=None) -> RulePlan`: original path/fingerprint, rule id/revision, template revision, ordered steps, explanations/errors. Each step has kind/source/target; terminal project route may have multiple operations. No mutation during planning.

- [ ] Write tests asserting nested all/any/none, missing age false+explanation, text/glob case rules, boundary size/date/timezone, nesting/leaf/action limits, unknown fields/operators, disabled import/new IDs, duplicate/update/reorder stable revision, atomic malformed import, path/token rejection.
- [ ] Write planner tests for rename→copy→move subject transition, subfolder containment, terminal project route/default/custom template, directory keep-name, target collision/no-op/source overlap, reservations across selected inputs, preview source/destinations unchanged.
- [ ] Run tests RED, implement focused modules, run those new test files GREEN plus Task 1 tests only if its shared API changes.
- [ ] Report exact interfaces in `docs/reports/rules-020/task2-sol.md`, freeze for director review/scoped commit.

### Task 3: Durable execution, undo and scheduler integration

**Files:** Create `automation/ledger.py`, `automation/runner.py`, runner tests; modify scheduler/service as necessary, existing operations/journal only for demonstrated lineage need.

**Interfaces:** `AutomationService(service)` uses same engine/config/state and exposes `preview(paths, now, rule_id=None) -> AutomationPreview`, `execute(preview) -> tuple[BatchResult,...]`, `process_observed(path, fingerprint, now, watch_root) -> AutomationDecision` (`claimed`, `results`, `errors`), `.rules` store. Preview is bound to rule/template revisions/source fingerprint. `AutomationLedger` has durable observation age and per-rule-revision/fingerprint run claim/progress/status. Scheduler creates/reuses AutomationService and consults it before legacy fallback; empty rules preserve baseline.

- [ ] Write tests: exact planned target executes through engine and history; stale rule/template/source/target rejected; all chain subject/undo cases, directory chain and injected second-step failure; original survives copy; no unguarded source/state/reparse overlap; failed later action not called.
- [ ] Write restart tests for completed copy source, final moved output, durable running crash marker, partial failure; enabling/reordering does not reset history; edited source/rule eligible; first match claims even already done/failed, later rule/legacy fallback skipped; unmatched uses old behavior; paused/temp/reparse/hidden and first_seen/stable observations persist/reset correctly; disabled migration creates no jobs.
- [ ] Implement durable claim before mutation, one engine batch with sequential steps, failure stop, conservative recovery messages. Do not silently retry uncertain runs.
- [ ] Run focused automation runner + scheduler + operations/directory/service tests appropriate to actual changed files. No full suite duplication. Report `task3-sol.md`, freeze for review/commit.

### Task 4: Chinese form editors and preview workflow

**Files:** Create four UI modules above and `tests/test_automation_ui.py`; narrow main_window/app wiring, theme additions; isolated native renderer/evidence under docs/evidence/rules-020.

**Interfaces:** RulesPage/TemplatePage accept shared window service+Coordinator or a small state controller; they expose invalidate/switch_state rather than reading disk in constructors. All stores/service I/O on worker, immutable callback generation and service identity guards. Rule Save/Enable and template changes invalidate main/dialog/generic previews; demo rebind clears old state. Existing home/history/footer behavior retained.

- [ ] Write UI tests for create/edit/save/duplicate/reorder/enable/delete/import/export; all conditions/action fields accessible through structured controls; disabled by default; useful error retains dirty values; default template copy+assignment; preview explanations/exact destinations; explicit execute only; stale callback ignored after edit/demo/service switch; worker I/O assertions.
- [ ] Implement scrollable editors and Chinese copy/token help; folder chooser, sample selection, priority controls, first-match and copy-subject explanation. Avoid JSON-only normal workflow.
- [ ] Run new UI tests plus existing UI/history/runtime focused tests once; isolated Windows Qt dark/light 1000×700 and 800×620 screenshots with long paths and nested groups/actions. Fix actual clipping only. No real app/registry.
- [ ] Report `task4-sol.md`, freeze; director UI/source review and scoped commit.

### Task 5: Reviewed 0.2.0 release

**Files:** Version/docs/packaging inputs, release evidence/report; narrow packaged smoke in isolated state if needed.

- [ ] Director/root perform whole-branch review; one combined fix dispatch for concrete findings, scoped rerun/re-review.
- [ ] Root runs final full pytest once after product freeze. Fresh packaging Sol updates 0.2.0 version, concise Chinese instructions/limitations and fixed input manifests; preserves old installers outside this worktree.
- [ ] Build with existing `packaging/build.ps1 -ISCC 'F:/Hazel Windows/sandbox/tools/inno-6.7.3/{app}/ISCC.exe'`. Existing venv is read-only; no dependency downloads. Run isolated portable ten-check selftest and packaged rule/template smoke, verify icon/version/hash/PYZ includes new modules.
- [ ] Root independently audits final source/artifact correspondence and hashes. Director commits scoped docs/evidence. No installation, registry operation or remote publication. Deliver installer link, upgrade instruction, what's configurable and explicit unsupported scope.

## Preflight and execution record

Root baseline: 276 passed in 21.10s; pinned inputs verified; evidence `sandbox/rules-baseline-pytest.txt`. User already supplied execution method and explicitly authorized start; no redundant plan approval request. Director performs task reviews per user-directed Astra/Sol arrangement rather than additional review agents. Record rulings/progress in `docs/implementation-ledger.md`; tracked briefs/reports persist across context compaction. Managed worktree is retained for delivery, not deleted by generic skill cleanup.

## Current image-conversion scope extension

User explicitly removed video conversion and retained all other work. Read current `docs/superpowers/specs/2026-10-01-filehub-conversion-addendum.md`. Task1 unchanged. Parallel Task M (fresh Sol) implements IMAGE-only backend/plugin provenance per `docs/briefs/rules-020/media-core.md`; no shared engine/UI/rule files, no new FFmpeg/OpenH264 build or deliverable.

Task M steps: [ ] image-only API; [ ] image/cancel/validation RED; [ ] Qt JPEG/PNG/WebP implementation and actual output verification; [ ] exact plugin/runtime QtImageFormats/libwebp provenance; [ ] focused GREEN; [ ] report/freeze. Director reviews before integration.

Task2 includes declarative image_convert action using ConversionSpec, no video_convert. Task3 consumes generate API, adds explicit generated-publication/convert journal migration/undo and addendum tests. Add one dedicated ConversionExecutor(max_workers=1): scheduler claims/enqueues conversion-bearing rules promptly; no global lock during codec work, short locked publication only. Test ordinary archive responsiveness, cancellation and obsolete/demo/queued snapshots never publish. Task4 creates ui/conversion_page.py for standalone IMAGE batch preset/preview/start/cancel, rule image action editor and lifecycle. Task5 includes qwebp and exact notices/source, real packaged image roundtrip. Existing ffprobe/video archive remains unchanged. No video conversion code/UI/encoder material in payload. Goal completion requires templates+rules+images+installer.
`Latest mandatory replacement feature`: image conversion must offer real in-place replacement plus keep-original save-as in standalone and rule action. Current addendum replacement contract is binding: trusted UUID backup, source/target guard-bound transactions, same-path swap, cross-ext publish-before-remove, cancel/crash/recovery/undo conflict tests. TaskM generator unchanged; Task2 declares mode and exact target, Task3 owns safe replacement/undo, Task4 exposes mode and backup explanation without folder choice for replace.
`Task3 split approved by root`: 3A (docs/briefs/rules-020/task3a.md) provides explicit generated image publication/replacement, old journal migration and inverse lineage after image backend freeze; may run parallel to Task2 with disjoint files. 3B consumes frozen3A+Task2 to implement automation ledger/runner/dedicated image executor/scheduler. Separate focused reviews are required at this load-bearing safety boundary; no repeated full suites. UI remains after backend gates.
`Task4 split approved by root`: after Task2 schema freeze, phase4A pure forms/signals (brief task4a.md) can run beside3A/3B on disjoint newUI files; no main/app/Coordinator binding. After3Bfreeze,phase4B integrates worker/runtime/state/lifecycle and finalnativeUI. This reduces waiting without overlapping writers or skipping review.
