# FileHub External Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. GPT-6.1 Sol implements; Astra directs/reviews. Root must release the Phase A engineering gate first. Steps use checkboxes; director alone stages/commits.

**Goal:** Deliver FileHub 0.3.0 as a portable external-rule executor with safe local management and an explicit personal-archive compatibility path.

**Architecture:** A strict portable package compiler feeds existing Rule/Planner/Executor contracts. One atomic local catalogue stores definitions, bindings and local permissions; old files are read-only migration sources. Generic scheduling/UI no longer require project tags or legacy fallback.

**Tech Stack:** Python 3.12.10, existing PySide6 6.11.2, current Windows operation engine/SQLite ledger and pinned packaging toolchain; no dependency changes.

**Spec:** `docs/superpowers/specs/2026-10-02-filehub-external-rules-design.md`.

## Global constraints

- Baseline `29f1170e59757e2a198a079492c6e225c5cc950e`; use the existing worktree on `codex/filehub-external-rules`; original F checkout and junction runtime remain read-only.
- No live state/files/watch/registry mutation, install, process stops, pip, push/merge/release or shutdown. Preserve prior installers. Only owned UUID sandbox fixtures.
- Target 0.3.0. External protocol `filehub.rules` integer version 1; 2,000,000-byte input, max 100 packages/1000 installed rules, 16,000,000-byte catalogue; strict unknown-key/type handling.
- Existing operation/journal/undo and image publication safety are not weakened. Definitions never restore executable jobs.
- Non-pytest Python commands: explicit worktree `PYTHONPATH=.../src`, `PYTHONDONTWRITEBYTECODE=1`, `.venv/Scripts/python.exe -B -X utf8`. Pytest also uses this source path and a fresh `--basetemp=sandbox/<task>-<UUID>`.
- Root owns one final full suite after all source/metadata freeze. Each implementer runs focused tests, records RED/GREEN, reports files/results, then stops writing. Director reviews and commits serially.

## Review focus

- A manually selected rule must still reject an out-of-scope source while accepting its bound folder without adding a watch (Task 3).
- A same-ID replacement with only display/order changes must not become a new ledger identity, even after backup restore (Tasks 2/3).
- An absent/corrupt catalogue with surviving backups or old v1 files must never silently re-enable legacy fallback (Tasks 2/3).
- Portable exports, compatibility projects and variables must not smuggle machine paths or create path traversal after expansion (Tasks 1/3).
- An old `--send` request during lifecycle transitions must remain claimed/released/acknowledged correctly with the new generic dialog (Task 4).

## Shared interfaces and file ownership

New package `src/filehub/rulefiles/`:

- `protocol.py`: immutable `RulePackage`, `PathReference`, `RuleDefinition`; strict `parse_package(data: bytes) -> RulePackage`, `encode_package(package: RulePackage) -> bytes`; diagnostics carry JSON field paths.
- `compiler.py`: `compile_package(package, bindings: Mapping[str, Path], runtime_ids: Mapping[str, str], enabled_ids: frozenset[str], *, state_dir: Path) -> PackageCompilation`; compilation contains validated Rule objects plus unresolved/error diagnostics. The catalogue/service passes its actual owned state directory for overlap checks. It never writes/creates folders. Normal IDs are deterministic; migration may supply checked pre-existing IDs.
- `catalog.py`: `CatalogSnapshot(revision, packages, compiled, bindings, enabled, order, compatibility_selection, compatibility_permissions)`; `CompiledRules(rules: tuple[Rule, ...], revision: str)` is read-only and meets runner `.rules/.revision` use. `RuleCatalogStore.load() -> CatalogSnapshot`, `.runtime_snapshot() -> CompiledRules`.
- `migration.py`: `MigrationCandidate(source_digests, packages, bindings, runtime_ids, compatibility, warnings)` and `inspect_legacy(state_dir, config) -> MigrationCandidate | None`; no mutations.
- `compatibility.py`: validated `ArchiveProfile`/`ResolvedArchiveContext`; `resolve_archive_profile(package, bindings) -> ResolvedArchiveContext` and migration translation of existing templates/project mappings/policies. No implicit default library during execution.
- `__main__.py`: standalone validate command; no normal app bootstrap.

Store write APIs all return `CatalogSnapshot` and accept keyword-only `expected_revision: str`: `import_package(data: bytes, source: str | None)`, `replace_package(package_id: str, data: bytes, source: str | None)`, `bind(package_id: str, values: Mapping[str, Path])`, `set_enabled(package_id: str, rule_id: str, enabled: bool)`, `reorder(package_ids: tuple[str, ...])`, `remove(package_id: str)`, `restore(backup_id: str)`, `adopt_legacy(candidate: MigrationCandidate)`, `set_compatibility(package_id: str | None, permissions: frozenset[str])`. `export_package(package_id: str) -> bytes` is read-only. Replace inspection is pure `compare_packages(old, new) -> PackageDelta(added, changed, removed, binding_changes)`; the UI commits only after the user reviews that concrete delta. `list_backups() -> tuple[BackupInfo, ...]` never activates a backup. Selected backup IDs are opaque, not caller-supplied paths.

`FileHubService.catalog` owns the store; `service.rules.load()` becomes a read-only adapter to `.runtime_snapshot()` for existing runner/scheduler consumers. Remove normal GUI use of v1 RuleStore mutation APIs. Existing internal models remain usable for tests and legacy parsing. `service.archive_context()` returns the explicitly selected/permitted context or raises a clear unavailable error. Generic `reload_templates()` returns a validated empty routing context when no compatibility profile applies, not an injected template catalogue; project actions require their owning selected package.

## Task 1 — Portable protocol, compiler and authoritative validator (Sol A)

**Files:** Create `rulefiles/__init__.py`, `protocol.py`, `compiler.py`, `__main__.py`, `schemas/filehub-rules-v1.schema.json`; tests `test_rulefiles_protocol.py`, `test_rulefiles_compiler.py`. Read `automation/models.py`, `naming.py`, `conversion/models.py`; do not modify runtime/UI yet.

**Consumes:** Existing immutable condition/action/rule classes and current validation limits. **Produces:** Package/parser/compiler/CLI interfaces above, closed JSON Schema, runtime-ID algorithm. Compatibility object parsing may delegate to Task 3's profile validator via one explicit integration hook; until integrated, reject it rather than allow arbitrary objects.

- [ ] Add failing tests for the complete spec example, round-trip canonical encoding, duplicate keys, bool version, unknown fields/actions, 2,000,001 bytes, excessive groups/leaves/actions, undeclared references, variable traversal/recursive substitution, and 255 UTF-16 naming limits. Assert invalid parsing performs no filesystem mutations.
- [ ] Add compiler tests for two machines binding the same package to different roots, no exported machine path, stable runtime IDs and semantic revisions, missing-used versus missing-unused bindings, case aliases and checked-path/state overlap. Preserve original path/source style while normalizing authority.
- [ ] Run only those files in a fresh UUID sandbox; record substantive RED before implementation.
- [ ] Implement the strict protocol/compiler, schema and CLI. Use existing validation for finite operation semantics; prohibit env lookup, scripts and hidden directory creation. Keep schema structural constraints in parity with examples and parser tests; document semantic-only constraints.
- [ ] Run focused protocol/compiler tests and CLI against valid/invalid owned files (expected exit 0/1, JSON diagnostics). Hand source/interface freeze to director for review and scoped commit.

## Task 2 — Atomic installed catalogue, bindings and recoverable replacement (Sol B, after Task 1 interfaces)

**Files:** Create `rulefiles/catalog.py`; tests `test_rulefiles_catalog.py`. Minimal `protocol/compiler` fixes require explicit ownership transfer from Sol A. Do not edit service/runtime/UI.

**Consumes:** `parse_package`, `encode_package`, `compile_package`, current `checked_path` and process lock. **Produces:** Catalogue, `PackageDelta`, backup and write APIs above; deterministic local generation/authority revision.

- [ ] Add failing import/duplicate-ID/explicit-replace tests. Assert all imports and replacement rules are disabled, bindings alone do not add watches, same-ID maps persist, removed IDs do not erase ledger/history, and exports strip every local field.
- [ ] Add transaction fault tests before backup, during temporary write and before/after active swap; assert active bytes are a complete old/new snapshot, valid prior backup bytes remain, unknown/corrupt local fields fail closed. Missing active plus backups must require restore, while pristine absent active returns empty catalogue.
- [ ] Add CAS, restore-disabled, invalid backup ID, unbound-enable refusal, package reorder and replace-delta tests. New generation invalidates preview authority even for identical replacement; compiled Rule semantic revisions remain stable for only enable/name/order changes.
- [ ] Run the focused catalogue tests for RED; implement bounded strict catalogue serialization, complete backup verification, fsync/atomic replace, expected-revision lock recheck and ignored-orphan policy. No dual writes to old definition files.
- [ ] Run focused GREEN including failure injection and report exact persisted paths/format to director. Director reviews/commits; no full suite.

## Task 3 — Generic runtime/scheduler and explicit legacy compatibility/migration (Sol A, after Tasks 1/2)

**Files:** Create `rulefiles/migration.py`, `rulefiles/compatibility.py`, `legacy_scheduler.py`; modify `service.py`, `config.py`, `scheduler.py`, `automation/runner.py`, `automation/planner.py`, `automation/conditions.py`, narrowly `rules.py`/`templates.py`; tests `test_rulefiles_migration.py`, `test_rulefiles_runtime.py`, affected scheduler/planner/runtime tests. Own all runtime integration; coordinate any catalogue additions with director.

**Consumes:** Catalogue/compiler APIs. **Produces:** service catalogue/read-only rule adapter, resolved compatibility context, `inspect_legacy`, compiled preview authority and gated legacy scheduler. `LegacyScheduler.tick(now, context, permissions)` reuses old observation/file-operation safety only when explicitly selected permissions permit it.

- [ ] Add RED for empty/no-match rules with configured sync/watch roots and old cleanup flags: zero file mutations, no inbox creation or junk deletion. Add in-scope manual/no-watch success and out-of-scope manual rejection; preserve automatic configured top-level scope checks.
- [ ] Add read-only migration candidate tests for valid aliases, no optional old files, bad/unknown legacy data, changed source digests, old stable rule ID/revision mapping, complete backup bytes and restart idempotence. Verify migration remains disabled and old JSON/SQLite history untouched. Raw inputs go to `legacy-migration-backups/<UUID>/`, never `rule-catalog-backups`; interrupt first adoption and prove raw JSON cannot be offered as an active-catalogue restore.
- [ ] Add explicit compatibility profile tests with arbitrarily named project directories/bindings, serialized complete default/custom templates, selected-profile mismatch rejection, dynamic-project-update limitation, manual archive gating, unmatched fallback gating and separate cleanup gating. Preserve old `_ready` timing and no automatic backlog flush.
- [ ] Implement service/runtime adapter and catalogue authority checks without altering OperationEngine/generated publication/journal schemas. Separate generic matching from optional legacy scheduler; remove generic sync/template dependency. Enforce selected-rule scope in manual preview/execution; automatic authority remains configured-watch-only.
- [ ] Implement legacy migration/profile compilation. Extract all fixed directories/project discovery results/category/cleanup settings into the explicit profile. Keep known tag grammar as a labelled compatibility dialect; no default profile is silently created/selected. Reuse old tests by creating explicit fixture profiles, not by reenabling new-user fallback.
- [ ] Run focused migration/runtime/scheduler/planner/image and interrupted-job regressions. Test same-ID metadata replace, enable/order toggles and restore against real ledger suppression; stale source/rule/binding/profile preview must fail. Director reviews/commits this coherent runtime boundary.

## Task 4 — Rules-file management and generic file-processing UI (Sol B, after Task 2; final integration after Task 3)

**Files:** Replace normal `ui/rules_page.py`; create `ui/file_process_dialog.py`, `ui/rulefile_dialogs.py`; modify `ui/main_window.py`, `ui/automation_controller.py`, `ui/rule_requests.py`, `ui/app.py`, narrowly `integration.py` and installer neutral-label text. Keep `archive_dialog.py` for explicit compatibility and `action_editor.py`'s `ConversionFields`; remove condition/template authoring from navigation, not required reusable conversion widgets. Tests `test_rulefiles_ui.py`, relevant `test_app_runtime.py`, `test_automation_ui.py`, `test_conversion_ui021.py`, `test_integration.py`.

**Consumes:** Catalogue snapshots/write APIs/PackageDelta, existing opaque preview tokens and lifecycle worker. **Produces:** normal generic UI, file-manager intents, explicit migration/recovery/compatibility controls and stable queue protocol.

- [ ] Add RED for first-run normal nav with no project-code/sync/template prompt, import all-disabled, unresolved binding indication, read-only rule summaries, concrete replacement delta/cancel, binding without watch/enable, stale async response and lifecycle busy gating.
- [ ] Add generic manual file/folder/drop previews and scope mismatch feedback; image-page drop must retain its current route. Keep exact preview token binding; no start-on-import/drop. Backup restore clearly restores definitions only and leaves disabled.
- [ ] Add owned/fake-registry `--send` queue tests: generic dialog by default, explicit legacy option with permitted profile, cancel/durable-result acknowledgment, lease renewal, state switch and shutdown settlement. Recognize both old/new owned menu labels without removing foreign registry values. Do not exercise real registration.
- [ ] Implement source-file management controls and generic navigation. Optional compatibility section has no embedded template authoring; explicit migration review summarizes retained features and disabled permissions. Guide button opens bundled static help, not a private-only URL.
- [ ] Run focused UI/integration tests, then a small owned qwindows walkthrough in dark/light at representative actual DPR: import/bind/preview/execute/replace/recover and conversion/drop controls. Capture a few meaningful screenshots and assertion results. Director reviews/commits; no full suite.

## Task 5 — External authoring guide, examples and release acceptance (reuse a completed Sol)

**Files:** Create `docs/AI规则编写指南.md`, `examples/rules-v1/*.json`, `packaging/create-rule-guide.py`, bounded `selftest030.py` plus acceptance tests; update `README.md`, `docs/使用说明.md`, current delivery notes and packaging inputs/spec for 0.3.0/help bundle. Preserve all historical installers/evidence. Root owns final independent artifact audit.

**Consumes:** Frozen protocol/schema/catalogue/UI/runtime. **Produces:** standalone guide/schema/example ZIP, packaged Help files and concrete proposed 0.3.0 installer/portable artifacts.

- [ ] Write standalone Chinese guide: exact format/version/limits, complete operation examples, allowed tokens/operators, portable bindings versus local watch permission, preserving IDs for replacement, no scripts/AI keys/network/OCR/video conversion, explicit compatibility limitations. A private GitHub URL is optional context, never required to use the files.
- [ ] Validate every complete example through the shared CLI/parser; ensure no personal/machine paths. Add a schema/example parity check and guide-bundle inventory/hash test. Bundling examples must not register/import/enable them.
- [ ] Add meaningful owned acceptance for external import/bind/manual preview/real move or conversion/undo, invalid replacement preserving catalogue and default no-match/no-legacy behavior. Existing 23 checks continue using explicit compatibility fixtures where old behavior is under test. No giant new test framework or live install hooks.
- [ ] Run targeted acceptance/schema/help tests, then freeze all source + 0.3.0 metadata. Director reviews/commits and sends root the SHA. Root runs the single full suite; Sol builds in parallel with existing Inno path and preserves old installer hashes.
- [ ] Run actual packaged EXE acceptance in clean hidden UUID child; verify helper docs/schema/examples exist without activating rules. Record exact check count, logs, SHA/version and limitations. Root independently audits source/PYZ/materials/installer and decides delivery/publication; do not push/release from implementation tasks.

## Dispatch and completion order

Do not dispatch engineering before root reviews Phase A. Recommended two coherent Sol workers: A owns protocol then runtime/migration; B owns catalogue then UI. Task 2 begins only after Task 1's interface freeze; Task 4 UI can prepare against frozen APIs while A integrates Task 3, with disjoint files and final integration after runtime freeze. Reuse either completed worker for Task 5. Director performs targeted diff reviews and serial commits, not repeat full tests per layer. Root performs the final independent review/full-suite/artifact gate.

Phase A self-review: protocol, local permissions, stable identities, failure recovery, source scope, migration, compatibility, default no-op scheduling, user flows, offline AI guide and release verification each map to a task and checkable assertions. No engineering code or dependency changes are authorized by this document until root releases the gate.
