# FileHub 0.3.0 external rules design

Status: Phase A design for root review; no engineering work started. Baseline `29f1170e59757e2a198a079492c6e225c5cc950e`; branch `codex/filehub-external-rules` in the existing managed worktree. The user authorized implementation by GPT-6.1 Sol, with Astra direction/review. This document records technical decisions without repeating user authorization.

## Outcome and boundaries

FileHub is a local rule executor. An external AI or a person writes a versioned JSON file using the published, downloadable guide. FileHub imports, validates, stores, replaces, exports, binds folders, enables/disables, previews and executes those definitions. It does not author rules, maintain a built-in scenario/template catalogue, call AI, accept API keys or automatically fetch/reload external files.

Reuse the tested operation engine, generated-content publication, journal/undo, rule ledger, image codecs, source fingerprints and preview authority. Keep standalone image conversion, true same-path replacement, collision version numbering, drag/drop and history. No arbitrary scripts/expressions, OCR, video conversion, cloud marketplace, recursive watch expansion or new dependencies.

All implementation/verification uses owned sandbox state. Do not change the original F checkout, shared junction runtime, installed app, live registry, real settings/files/watches or old installers. Do not push, merge, release or shut down in this phase. Target version is 0.3.0; root owns the final publication decision. Director alone stages/commits.

## Existing coupling and selected approach

`automation/models.py` already supplies strict finite conditions/actions, semantic rule revisions and atomic v1 internal storage. Its importer currently regenerates IDs, and destinations/scopes contain absolute paths. `runner.py`/`ledger.py` bind revisions and suppress repeat execution by stable `(rule id, semantic revision)` plus exact source provenance.

`scheduler.py` runs a legacy unmatched-file inbox fallback and optional cleanup. `MainWindow`/`ArchiveDialog` assume project tags; `service.py`/`planner.py` reload a default template library even for ordinary rules. `rules.py` discovers projects using a fixed tree. These are the coupling points to isolate, not reasons to rewrite safe file operations.

Considered: (1) expose current RuleSet JSON unchanged—small but leaks paths and lacks replacement identity; (2) rewrite the engine around a new workflow language—too broad and discards verified safety; (3) **selected: portable package + local catalogue compiler over current models**, with an explicit legacy compatibility profile. One atomic catalogue is the authority; no dual-writing of catalogue and old rule/template files.

## Portable protocol: `filehub.rules`, version 1

Use UTF-8 JSON, maximum 2,000,000 bytes, duplicate object keys rejected, no NaN/infinity, unknown keys/types/versions/actions rejected at every object. Top-level required fields: `format`, `version`, `id`, `name`, `bindings`, `variables`, `rules`. `format` is exactly `filehub.rules`; `version` is integer 1, not boolean. Only optional top-level field is `compatibility`, defined below. Package/rule/binding/variable IDs use `[A-Za-z0-9_-]{1,128}`; package/rule names are nonblank, at most 256 characters. Descriptions in binding declarations are at most 512 characters. Total installed rules remain at most 1000 and installed packages at most 100; installed catalogue size is bounded at 16,000,000 bytes.

`bindings` is an object from symbolic ID to `{ "label": "Input folder" }`, maximum 100. It contains no path or default path. A path reference is exactly `{ "binding": "input", "relative": "" }`; `relative` is empty or a validated slash-separated Windows-safe relative path. Reject drive/UNC/device anchors, `..`, empty internal segments, ADS, reserved names, illegal characters, symlink/junction escapes and overlap with application state. Resolve under the explicitly selected local binding and verify containment again at preview/execution. Binding a folder does not create it, add a watch root, enable rules or execute anything. Output subdirectories may be created only by an approved execution through the existing engine.

`variables` is an object of at most 100 literal text values, each at most 256 characters. `${NAME}` is permitted only in `rename.pattern`, `subfolder.path`, and a path reference's `relative`. Expand once; do not expand inside variable values or read environment variables. Values are filename-component text: no slash, backslash, colon, Windows-invalid characters, braces or `$`; validate the complete expanded component/path with current naming validators. Existing runtime naming tokens `{stem}`, `{ext}`, `{date}`, `{date_long}`, `{period}`, `{sequence}`, `{original}` remain unchanged. Do not invent capture groups or promise tokens unavailable in an ordinary rule.

Each rule has exactly `id`, `name`, `scope`, `condition`, `actions`; no portable `enabled` field. `scope` contains 0–100 distinct path references. A nonempty scope restricts both explicit/manual and automatic sources to the exact referenced top-level folders. Manual scope does not require those folders to be configured watches. Empty scope permits explicitly selected manual sources and, only when locally enabled, the already-configured watch roots. The UI describes empty scope as “所有已配置观察目录；手动可选择文件”. No scope adds watches or implies recursion.

Conditions retain current fields/operators/types, all/any/none groups, maximum 4 group levels and 100 leaves. Actions retain 1–20 ordered operations: `rename`, `move`, `copy`, `subfolder`, `image_convert`; absolute `destination` strings become path-reference objects in the portable form. Conversion defaults/ranges remain `ConversionSpec`; keep requires destination, replace rejects it. Normal move/copy/rename retain their current collision rules; only image conversion has the verified automatic number allocator. `project_route` is accepted only in a package with the explicit compatibility profile below. No generic recycle/delete action is introduced.

Example, complete and directly importable but initially unbound/disabled:

```json
{
  "format": "filehub.rules", "version": 1,
  "id": "image-delivery", "name": "PNG delivery",
  "bindings": {"input": {"label": "Input"}, "output": {"label": "Output"}},
  "variables": {"folder": "PNG"},
  "rules": [{
    "id": "jpeg-to-png", "name": "JPEG to PNG",
    "scope": [{"binding": "input", "relative": ""}],
    "condition": {"field": "extension", "operator": "glob", "value": ".jp*g"},
    "actions": [{"kind": "image_convert", "options": {
      "output_format": "png", "mode": "keep",
      "destination": {"binding": "output", "relative": "${folder}"}
    }}]
  }]
}
```

Ship `schemas/filehub-rules-v1.schema.json` using JSON Schema 2020-12 and `additionalProperties: false` throughout. The schema expresses structural/range constraints; shared runtime semantic validation remains authoritative for paths, naming tokens, leaf count and cross-references. A dependency-free CLI `python -m filehub.rulefiles validate FILE` uses that same parser, emits bounded JSON diagnostics with field paths and exits 0/1. It does not open app state or mutate files. Do not add a second permissive importer.

## Catalogue, IDs and transaction contract

Create `state/rule-catalog.json`, a strict versioned local document containing canonical package documents, their original source-file provenance (local only), binding values, local enable states, package order, stable runtime-ID mappings, selected compatibility profile/permissions, and a generation token. This is the sole active authority after adoption. `automation-rules.json` and `templates.json` become read-only migration inputs, never secondary active stores.

`RuleCatalogStore.load()` returns an immutable `CatalogSnapshot`; its `compiled` member exposes `.rules` and `.revision` to the existing runner. Rule IDs for new packages are deterministic `ext_` plus SHA256(package ID + NUL + rule ID), within the existing 128-character bound. Replacement of the same package ID preserves runtime mappings for unchanged rule IDs; migrated mappings preserve the old internal rule IDs. New rules are disabled. Preserve ledger, provenance and file history when a rule/package is removed or replaced.

Compile conditions/actions/scopes into the existing validated `Rule` objects. Their semantic revision continues to exclude name, enabled and order. Resolved destinations/scopes affect semantics. Catalogue authority revision includes canonical installed content, local bindings, enable/order/profile state and generation. Any accepted import/replace/restore/bind/toggle/order change invalidates old previews, even if execution semantics are unchanged. Name-only edits, enable/disable, ordering or unchanged replacement must not replay an already-visited same rule revision. Semantic replacement may produce a new revision, but replacement leaves the package disabled until explicit re-enabling.

Operations:

| Operation | Contract |
| --- | --- |
| Import | Validate entire input before writes. Reject duplicate package ID with “use replace”. Install canonical snapshot, no bindings, all rules/profile permissions disabled. Do not watch the external file. |
| Replace | Explicitly select installed package and incoming file; IDs must match. Show added/changed/removed rules and binding declarations before commit. Preserve matching local binding values and stable IDs; prune removed bindings, require new ones; disable all package rules and compatibility permissions. |
| Reload | Explicit action reads a selected source file, performs exactly the replace review, and cannot silently activate changed content. Missing source affects reload only, not the installed snapshot. |
| Export | Export portable canonical definitions only. No local absolute paths, enabled/watch settings, source provenance, catalogue IDs, ledger or backups. Export per package; compatibility projects also use path references. |
| Bind/toggle/order | CAS against expected catalogue authority revision. Bind does not auto-enable. Package-order moves preserve rule order inside each file; external editing changes rule order. Enabling requires resolved used bindings and a valid scope, and still does not execute immediately. |
| Remove | Explicit removal with summary; keep historical runs and catalogue backups. Does not delete source files or undo file operations. |
| Restore | Explicitly restore a selected validated catalogue backup through a new transaction. Disable all restored rules/compatibility permissions, assign a new generation, require preview. Restores definitions/local controls only, never reverses executed files. |

All mutations use the existing process/engine lock and are admitted only when owned work has settled; do not mutate the catalogue while an image worker is committing. Recheck expected revision under the lock. Before replacing an existing active catalogue, write an immutable UUID-named full previous-catalogue backup under `rule-catalog-backups`, flush/fsync and verify its bytes, then atomically replace a flushed active temporary file. Backup failure prevents replacement. An interrupted write leaves the complete old or complete new catalogue, never a mixture; orphan temporary files are ignored, not adopted. Raw legacy migration inputs live under a separate `legacy-migration-backups/<UUID>/` manifest and are never catalogue restore candidates. No automatic pruning in 0.3.0.

If an active catalogue is malformed or missing while backups exist, fail closed and present recovery choices; never activate a guessed backup, empty rules or old v1 definitions. Initial no-catalogue/no-backup state means no active rules. Strictly validate local catalogue files too; arbitrary manual editing is not a bypass. No executable jobs are restored or replayed by definition recovery.

## Legacy migration and compatibility

An old state may contain config aliases, v1 rules, template assignments, tag history, observations and running/partial history. Continue accepting existing Config aliases and dataclass validation. Invalid legacy config/rules/templates remain untouched and cannot activate anything; report the precise invalid file rather than overwriting defaults. New local settings are defaulted without breaking old valid config files. Existing file-operation and automation databases remain authoritative and are not rewritten by migration.

On first read in the upgraded process, if no catalogue exists, build a read-only migration candidate from valid existing state and show a visible pending-migration notice. No implicit import, enable, fallback cleanup or file movement. Accepting migration is an explicit app management operation, performed only by the user in a future running app—not against their live state during this engineering task. Recheck all source file digests at acceptance. Store their complete original bytes in the migration backup and create the new catalogue atomically; retain the original files in place. Reopening the app after committed migration must not offer or execute a duplicate migration.

Ordinary old rules migrate into a portable package: extract each distinct absolute scope/destination as a symbolic binding, seed matching local binding values, preserve original runtime IDs and unchanged semantic revisions. They are disabled. Old empty scopes retain their existing explicitly-configured-watch meaning. Do not duplicate/run all existing rules as fresh IDs.

For personal project/tag archive, retain an **optional, explicitly selected** `filehub.archive.v1` compatibility dialect, not a normal generic requirement. Its external profile contains: a root path reference; an explicit project-code → path-reference map; full project template records/assignments and selected default-template ID; a configured general-test destination; and explicit legacy inbox/cleanup policies. Snapshot discovered old projects during migration; new project folders later require explicit external configuration update, not hidden discovery. Project paths can be arbitrarily named/located under the bound root—no numbered area, `项目` directory, dated project-folder name or Baidu location required after migration. Preserve legacy tag grammar, shot rules, resolution naming and dedup/undo as documented compatibility behavior.

Profile records must be complete: no injected built-in template catalogue or fixed fallback destinations at runtime. Existing default-template constants may remain solely for recognizing/exporting historical state. `rules.py`/`service.py` receive explicit project/profile context; generic rule execution must not fail because an unrelated old template file is corrupt or missing. There is at most one selected compatibility package at a time; a `project_route` rule cannot accidentally run against another package's selected profile.

Compatibility policies carry explicit `inbox_root`, image/video/other category names, observed-arrival delay, inbox-expiry delay, exact disposable filenames and name-sanitization roots. Migration translates the old configured values, including previous defaults, into these data fields. Keep the old readiness/transaction safety logic, but call it only under separate local permissions `manual_archive`, `unmatched_inbox`, `cleanup`, all false after import/migration/replace/restore. Selecting a profile alone grants no permission. No-match generic scheduling always does nothing unless `unmatched_inbox` is explicitly allowed; expiry/sanitization additionally require `cleanup`. Preserve the old observation time gates and do not backdate files to trigger immediate cleanup.

This is the chosen bounded compatibility tradeoff: keep the known tag dialect for existing personal users, externalize every directory/project/template/policy choice, and remove it from the normal workflow. Do not build a new arbitrary parser language or silently discard personal archive/cleanup.

## UI and integration

Normal navigation: `文件处理`, `规则文件`, `图片转换`, `记录`, `设置`. Home accepts file/folder selection and drag/drop; choose an installed rule (or enabled-rule matching), show preview, then execute. No project code/sync-root prompt. Scope mismatches are errors even for a manually selected rule. Empty-rule new users see import/guide actions and can still use independent image conversion/history.

Rules page shows installed files with version/name/status, bound/unbound folders, contained rules and read-only human-readable condition/action summary. Controls: import, review replacement/reload, export, bind folders, rule enable/disable, package order, remove, restore backup, choose sample files, preview/execute. Remove new-rule/duplicate-rule/condition editor/action editor/template-authoring controls from normal navigation. Keep `ConversionFields` for independent image conversion; do not remove it merely because it lives in `action_editor.py`.

Settings keep explicit watches, pause and appearance. Legacy sync root/day/cleanup controls live only in the optional compatibility section. Compatibility users get a clearly named personal-archive entry/dialog with tag history and the existing preview/execute safety. Generic no-profile users never see project-code requirements.

Keep existing `--send` command and durable queue/lease/ack lifecycle. It opens a generic file-processing dialog by default; an explicitly permitted compatibility profile offers the personal archive choice without swallowing queued files. Cancel acknowledges explicit dismissal; execution acknowledges only durable result as before. Retain old Explorer verb ownership/key/command identities and accept old “送进项目…” invocations. New installation/settings registration uses a neutral FileHub label and safe removal recognizes both owned labels. No live registry exercise in this work.

The repository is private. Ship a self-contained `docs/AI规则编写指南.md`, versioned schema, complete portable examples, and a guide-bundle ZIP next to the proposed 0.3.0 artifacts; a friend can attach these files to their AI without access to a private URL. Bundle the static guide/schema/examples as Help content in the installer, but never import them automatically or present a scenario/template library. Help may open/copy the guide; it must not generate rules or call the network. Examples cover move/copy/rename, ordered image conversion and a separately labelled compatibility profile. The guide states unsupported capabilities and instructs the AI to preserve IDs when updating a file.

## Verification contracts

1. Invalid/duplicate-key/unknown-action/unknown-version/oversize input changes neither active catalogue nor old files, enable state, watches or history. Schema/CLI/runtime accept the same documented examples; semantic-only validation differences are documented.
2. Round-trip export from machine A contains no A paths; machine B independently binds folders; neither binding nor import authorizes automatic processing. Missing/unused bindings are distinguished; only referenced bindings block execution.
3. Same-package replacement preserves identity, invalidates old preview, defaults disabled and keeps recoverable prior bytes. Failure injected before/after backup and atomic swap yields only valid old/new authority. Missing/corrupt active state never falls back into legacy jobs.
4. Toggling, ordering, metadata-only/unchanged replacement and restore do not replay a visited semantic rule version. Existing interrupted jobs remain review-required, never resumed. All source/rule/config/profile/binding authority changes reject stale preview.
5. Scoped manual source outside the allowed folder fails; in-scope manual execution works without watch configuration. Automatic work remains top-level, configured-watch-only and explicitly enabled/unpaused. No rules/no match means no source mutation, including legacy junk files.
6. Migration is read-only until accepted, supports valid aliases and missing optional old files, preserves raw backups and legacy IDs, rejects changed candidate digests, is idempotent after restart, and leaves old ledger/history recoverable. No implicit profile permission. Old project grammar/dual-shot/1920-width routing/undo parity is tested using an explicit migrated fixture, not hardcoded normal-app defaults.
7. Owned native UI covers first-run import/bind/preview/run, replacement review, no-template normal navigation, explicit compatibility access and right-click queue dispatch; dark/light and representative actual DPR only. Preserve file/image drag/drop, keyboard/wheel/thumb behavior and worker shutdown/settlement.
8. Keep existing image keep/same-path replace/cross-extension numbered replacement/undo/late-occupancy tests. Add a bounded actual-EXE external-package import/bind/preview/execute/undo and fail-closed-import acceptance fixture. The existing 23 acceptance behaviors continue through explicit owned compatibility fixtures where necessary; do not fake their previous defaults as new-user behavior.

Run focused tests per coherent task; no repeated 733-test baseline. After source + 0.3.0 metadata freeze, root runs one full suite while Sol builds/does isolated EXE acceptance. Root independently checks PYZ/source, versions, manifest/materials and retained old installers. Final publication remains separate.
