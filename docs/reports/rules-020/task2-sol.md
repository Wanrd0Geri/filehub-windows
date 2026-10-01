# Task 2 Sol report — immutable rules, explanations and ordered plans

Status: implemented, focused verification GREEN, source frozen for director review. Worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`, branch `feature/filehub-rules-020`, dispatched base `03c4b85`. No staging, commits, installs, shared-venv writes, live watches/state/registry/app operations or F checkout writes. No full suite; director/root owns combined gates.

## Owned changes

- New `src/filehub/automation/__init__.py`, `models.py`, `conditions.py`, `planner.py`.
- New `tests/test_automation_models.py`, `test_automation_conditions.py`, `test_automation_planner.py` and this report.
- No existing service, rules, templates, naming, engine, journal, scheduler, UI, image backend or packaging files changed. Concurrent Task3A/director changes visible in status are not this implementer's work.

## Rule models and JSON store API

All definitions are frozen dataclasses. Import public types from their modules; package `__init__` deliberately has no eager execution facade.

`Predicate(field, operator, value)` supports `kind`, `extension`, `name`, `size_bytes`, `created`, `modified`, `first_seen_age_seconds`, `stable_age_seconds`. Text operations are equals/contains/starts_with/ends_with/glob; kind specifically requires equals against file/folder/image/video/audio/document/other. Number/date operations are eq/lt/le/gt/ge. Kind=file includes all nonfolder kinds. Case comparisons use casefold; extension exact/prefix comparisons normalize an omitted leading dot, substring/suffix preserve substring meaning, and glob supports both PNG and *.PNG. Dates normalize to aware ISO8601. Bool numbers, negative/nonfinite/huge thresholds, naive dates, unsupported fields/operators and malformed field types raise ValueError. No scripts, regex, expressions or attribute access.

`ConditionGroup(mode, children)` supports all/any/none, freezes children into a tuple and validates nonempty trees, at most four group levels with root counted as one, and at most 100 leaves across the entire tree. `condition_from_document(data)` validates bounded dictionaries before descending.

`Action(kind, options={})` freezes a copied mapping. Exact finite option schema:

| kind | options |
| --- | --- |
| rename | pattern; Task1 finite naming tokens and strict single Windows component |
| move/copy | destination; validated explicit absolute Windows folder |
| subfolder | path; safe relative folder, slash-normalized |
| project_route | tag; nonempty project command, must be final action |
| image_convert | output_format plus ConversionSpec fields; mode defaults keep; keep requires destination; replace rejects destination |

Image actions reuse the frozen public `ConversionSpec`, not a separate preset validator. `.conversion_spec` returns the backend object with kind=image, output_format=jpeg/png/webp, quality=90, background=#FFFFFF, lossless=False, timeout_seconds=60, max_pixels=40000000 defaults. Complete normalized preset fields are stored in the immutable action options. `.extension` comes from backend spec (.jpg/.png/.webp). Unknown fields, including backup/staging/swap paths, are rejected. There is no video conversion action. Normal local and UNC absolute paths validate every component; device/extended namespaces, malformed server/share, traversal, invalid names and relative destinations fail visibly.

`Rule(id=<fresh UUID hex>, name='新规则', condition=None, actions=(), enabled=False, scope=())` requires an actual validated condition and 1–20 Actions. Scope is an immutable tuple of absolute watch-root strings, with duplicate and size validation. New definitions are disabled by default; explicitly loading/updating enabled rules preserves their enabled value. Rule `.revision` hashes condition/actions/scope only: ID, name, enabled and position are excluded. Scope list ordering is canonicalized for the semantic digest. Condition/action/scope edits change semantic revision; changing display name/enable/order does not.

`RuleSet(rules=())` freezes the ordered list and exposes a full `.revision` covering IDs/name/enabled/order and all definitions. `.with_rule(rule)` replaces same ID or appends; `.duplicate(id,name=None)` appends a fresh disabled independent ID; `.delete(id)` only removes definition; `.reorder(ids)` requires each existing ID exactly once. `.to_document()` / `RuleSet.from_document(data)` use version 1. Document shape:

```json
{"version":1,"rules":[{"id":"stable-id","name":"规则","enabled":false,"scope":[],"condition":{"field":"extension","operator":"equals","value":".png"},"actions":[{"kind":"image_convert","options":{"output_format":"webp","mode":"replace"}}]}]}
```

Group document replaces leaf with `{"mode":"all","children":[...]}`. Unsupported schema fields/version and duplicate rule IDs fail. In addition to the spec's per-rule limits, anti-abuse hard limits are **1000 rules** and **2,000,000 encoded document bytes** (including saved formatting). These are explicit Chinese validation errors, never truncation; UI must show them. Strings/scopes also have explicit bounded validation.

`RuleStore(state_dir)` exposes `.state_dir`, `.path` (`automation-rules.json`), `.load() -> RuleSet`, `.save(ruleset, expected_revision=None) -> RuleSet`, `.import_document(data, expected_revision=None) -> RuleSet`, `.export_document() -> dict`. Missing load creates neither state directory nor lock. Existing load/save use the same per-state reentrant process lock as engine/template store, and reject reparse state/definition/lock components. Save fully validates and bounds data before writes, rechecks the current valid document under lock, rejects stale expected revision, writes a state-local temporary, flushes/fsyncs, and atomically replaces. Malformed/oversize existing JSON blocks save; duplicate JSON object keys are rejected instead of being silently last-wins. Replace failure preserves the saved file and cleans only the owned temporary.

Import validates the whole document before settings writes, assigns every imported rule a new UUID and disabled state, and **appends** them atomically to the existing ordered RuleSet. Bad later definitions cannot partially import good earlier entries. Import never loads run history, backup paths or code. Export includes definitions only. Rule deletion never erases ledger/journal records.

## Facts, explanations and first match API

`FileFacts(path, fingerprint, kind='other', size_bytes=None, created=None, modified=None, first_seen=None, stable_since=None, video_width=None)` is frozen. `.name` and `.extension` derive from path; folder extension is empty rather than a filename-suffix media type. `.capture(path, first_seen=None, stable_since=None, video_width=None)` captures the existing Fingerprint/TreeFingerprint and aware UTC timestamps, classifies by extension, sums tree regular bytes via TreeFingerprint, and performs **no codec decode or observation persistence**. Supplied first_seen/stable_since are aware times from Task3 ledger, not computed ages or zero fallbacks.

`evaluate(condition, facts, now) -> MatchExplanation` requires one aware snapshot clock. Explanation fields: `.status` true/false/unavailable, `.matched` (only true), `.reason` Chinese, `.children` complete nested explanations, `.field`, `.actual`, `.threshold`. All children are explained, even when known children already determine the outcome. Missing facts yield unavailable. all is false if any known false, otherwise unknown propagates; any is true if any known true, otherwise unknown propagates; none is false if any known true, otherwise unknown propagates. In particular unavailable ages cannot turn a negative none group into a match.

First-seen age is now minus first_seen; future observations are unavailable. Stable age is capped by the latest of stable_since, root creation/modification, and every captured tree entry/directory creation/modification. Missing root times or any future latest time are unavailable. Root created/modified date predicates still compare their root dates, not child dates.

`first_match(ruleset, facts, now, rule_id=None, watch_root=None, configured_watch_roots=None) -> FirstMatch` exposes `.rule`, `.evaluations`, `.ruleset_revision`, `.captured_at`, `.explicit_selection`. Each RuleEvaluation has rule_id/name/status/reason/explanation. First enabled matching rule wins; later rules are marked not_evaluated with Chinese explanation. Disabled rules are marked disabled. Automatic callers supply configured_watch_roots (and observed watch_root), enforcing configured top-level scope; scoped roots cannot silently add watches. Explicit selected-rule tests allow disabled rules and samples outside the watch-root parent while retaining validation that scoped roots belong to configured watches. This flag never enables a rule or authorizes material execution.

## Pure planner API and integration requirements

`PlanReservations(selected_sources=(), targets=set())` is a mutable **batch-local planning** object. Seed selected_sources with ALL selected input paths before any plan. Reuse it across inputs. Targets use casefold Windows collision keys and conservative overlap checks. Intermediate output paths remain reserved even when later moved. Reservations commit only after a complete valid plan; an invalid later action leaves all tentative reservations unconsumed. Duplicate same-path/case-variant selected input is rejected, including replacement exceptions.

`plan_rule(rule, facts, service, occupied=None, ruleset_revision='', templates=None, now=None, conversion_plans=None) -> RulePlan` reads only; no mkdir/notify/journal/job/codec/material operations. Inject one loaded TemplateLibrary and one aware clock for the whole preview. Omitted templates call `service.reload_templates()`; omitted clock captures one UTC time for this individual diagnostic plan. `service` consumes engine.state_dir, config.watch_roots/sync_root, reload_templates; no `_notify`, engine execute or service preview is called. Basic actions need neither sync_root nor tag. Only project_route requires sync_root and source created time.

RulePlan is frozen: original_path/original_fingerprint, rule_id/rule_revision, ruleset_revision/template_revision, captured_at, steps/explanation/errors/warnings, `.ok` (steps and no errors). **Task3 preview must supply the FULL RuleSet.revision**; empty ruleset_revision is an unbound standalone diagnostic plan and must not execute. Planning accepts disabled selected rules for explicit preview only. It checks the predicate; unmatched or unknown sample produces an error rather than executable steps. If a later action fails, earlier tentative steps remain visible for explanation, but errors disqualify the whole plan and no reservations commit. Runner must reject any errors/unbound snapshots.

PlannedStep fields: kind/source/target, source_fingerprint, subject_version, action_index, conversion_spec/conversion_plan, generates_content, replaces_original, requires_backup, requires_conversion_validation, explanation, **advances_subject**. Rename/subfolder become move operations. Normal copy/move/rename advance the ordered subject; after every such action expected fingerprint becomes unknown until execution recaptures actual subject. Converted outputs have the planned new suffix/preset and unknown resulting fingerprint. A runner must never reuse the original fingerprint for them.

Terminal project_route expands using frozen Task1 template APIs/default naming. Virtual directory subjects are handled explicitly so an earlier rename/move cannot make nonexistent-yet directory paths look like files; directory names remain unchanged by template naming. Multi-target route emits a secondary-target copy with **advances_subject=False**, then a primary-target move from the same subject. This explicit branch exception differs from ordinary copy; source_version and source binding remain equal for the branch and final move. Generic project plans do not implicitly recycle duplicates.

Image keep selects destination/stem+spec.extension and preserves original. Replace selects **current subject parent/stem+extension**, explicitly marks generated-content replacement and required internal recoverable backup, and accepts same-path/case-variant recompression only for this bound subject. It cannot overwrite an unrelated existing target, another selected source or another plan's reservation. A prior virtual rename/copy may become the replacement subject; its binding must be captured at execution. No imported backup/staging field is accepted and planner creates none.

`conversion_plans` optionally maps action index to a previously inspected public ConversionPlan; source path/spec/fingerprint must agree with this step. For a virtual subject after prior actions there is no known fingerprint yet, so an injected initial-source inspection cannot pretend to validate it. Without injection the step sets requires_conversion_validation=True; Task3 dedicated conversion worker performs actual input/capability validation after ledger suppression and before publication. Ordinary matching/planning does not call backend inspect.

Target checks reject occupied/current no-op, case collisions, selected-source overlap/containment, directory recursion, state overlap, reparse components and invalid Windows output names. `{sequence}` allocation sees existing names and batch reservations; plain patterns collide visibly. Planning creates no missing target directory and changes no source/target bytes. Runtime must revalidate source, exact targets, full rules/templates/service snapshot, input capability/options and fresh subject identity before each protected material action. Material publication/replacement/undo belongs to Tasks3A/3B; Task2 makes no execution claim.

## RED/GREEN evidence

Commands ran from this worktree using existing read-only `.venv/Scripts/python.exe -X utf8 -m pytest`; pytest already sets src pythonpath. No full-suite or Task1 rerun because no frozen shared API was edited.

1. Initial RED: three owned test files, `-q --basetemp=sandbox/rules020-task2-red` → 3 expected collection errors, missing `filehub.automation`. This was import RED, not an assertion failure.
2. First GREEN: same three files, basetemp `sandbox/rules020-task2-green1` → **61 passed in 0.39s**.
3. Assertion RED2: same three files, basetemp `sandbox/rules020-task2-red2` → **5 failed, 74 passed in 0.72s**. Four malformed condition cases leaked TypeError/OverflowError rather than validation ValueError; folder masquerading as image was accepted. Tests named `test_malformed_field_types_are_validation_errors[definition0..3]`, `test_folder_cannot_masquerade_as_file_conversion`.
4. Assertion RED3: conditions/planner only, basetemp `sandbox/rules020-task2-red3` → **9 failed, 44 passed in 0.41s**. Directed cases: selected disabled sample outside scope, recent/future creation (2), latest tree child/directory timestamps (4), still-pending folder type and terminal branch advances_subject flag. Fixed all, plus RED2 type errors. GREEN2 all three files → **87 passed in 0.57s**.
5. Assertion RED4: all three files, basetemp `sandbox/rules020-task2-red4` → **5 failed, 88 passed in 0.71s**: extension glob/substring/suffix (3), automatic unscoped configured/top-level bounds, duplicate selected-source replacement. GREEN3 → **93 passed in 0.60s**.
6. Assertion RED5: models only, basetemp `sandbox/rules020-task2-red5` → **3 failed, 35 passed in 0.37s**, device/extended destination namespaces and malformed UNC server were accepted. Fixed validation of the entire UNC anchor.
7. Final GREEN: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_models.py tests/test_automation_conditions.py tests/test_automation_planner.py -q --basetemp=sandbox/rules020-task2` → **96 passed in 0.44s**, exit 0. Exact output `sandbox/rules020-task2-green.txt`. `py_compile` on the four modules passed. Scoped `git diff --check` exited 0 (these new files are untracked until director staging, so this check does not by itself inspect untracked content).

Coverage includes immutable semantic vs full revision, enable/order/duplicate/import identity, limits/malformed/oversized schema, atomic failure and unrelated-history retention, reparse lock guards, timezone/size/kind boundaries, full tri-state trees and Chinese evidence, durable-observation timestamp semantics, selected vs automatic scope, ordered copy/move/rename and virtual folders, default/custom/multi-target route, case reservations and rejected no-op/state/source/recursive hazards, keep/cross-extension/same-path/virtual-subject replace, injected conversion validation and read-only bytes/directories.
