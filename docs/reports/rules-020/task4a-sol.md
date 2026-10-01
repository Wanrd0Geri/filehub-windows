# Task4A Sol — pure automation, template and image forms

Status: phaseA implemented and frozen for director review / phaseB ownership transfer. Final owned gate **32 passed in 0.44s**, exit0. Dispatch base `dc23d9fdcfa7371734fdc9bab233db226c183ae2`, worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`, branch `feature/filehub-rules-020`.

## Ownership and boundaries

New files only: `src/filehub/ui/condition_editor.py`, `action_editor.py`, `rules_page.py`, `templates_page.py`, `conversion_page.py`, `rule_requests.py`, `tests/test_automation_forms.py` and this report. One permitted isolated capture/script lives under owned `sandbox/forms020-render/`; pytest artifacts/logs under owned `sandbox/forms020-*`.

No main_window/app/Coordinator/theme/backend files edited. Concurrent Task3 backend/brief changes visible in status are not this implementer's work. No agents, stage/commit, install/pip/shared-venv updates, full suite, live user app, real images/watch folders/state/registry operations. The existing `.venv` junction was used read-only. Original F checkout was not modified. This is pure forms delivery, not an integrated-runtime or installer acceptance claim.

## Exact final interfaces

All widgets accept `parent=None`. All use immutable passed model snapshots and signals; none calls a store, service, codec inspect/generate or discovery. Native file/folder/color dialogs only select values; controllers own reads/writes/jobs. Exceptions from `value()` are validation `ValueError`; Save/Test UI catches them and shows actionable text without discarding input.

### ConditionEditor

- `changed: Signal()`; `value() -> Predicate | ConditionGroup`; `set_value(condition)`.
- `node(path=())` exposes structured node controls; `add_condition(path=(), condition=None)`, `add_group(path=(), mode='all')`, `remove_node(path)`, `wrap_group()`.
- Nested all/any/none groups, supported leaf fields/operators, finite model validation of four group levels /100 predicates. Root starts with type=image; wrapping/add/remove are explicit UI operations. No JSON normal workflow.
- Numeric decimal text + unit selection (bytes/KB/MB/GB or seconds/minutes/hours/days) retains full imported integer/float values rather than clamping/spinbox rounding. Invalid/nonfinite/negative/huge values surface validation errors.
- `QDateTimeEdit` with calendar popup displays UTC explicitly. Untouched loaded aware ISO string retains original timezone and microsecond precision; calendar edits emit UTC aware ISO. Conversion to UTC for display uses the actual aware timestamp.

### ActionEditor and shared ConversionFields

- `ActionEditor.changed: Signal()`; `value() -> tuple[Action,...]`; `set_value(actions)`; `add_action(kind='rename')`; `remove_action(index)`; `move_action(index, delta)`; `rows` exposes individual structured rows.
- Ordered rename/move/copy/subfolder/image_convert/project_route controls, explicit destination choosers, finite naming-token help, max20 actions; project_route validated last. Help says ordinary copy advances to its copy, image conversion advances to the generated subject.
- `ConversionFields.changed: Signal()`; `set_value(spec, mode='keep', destination=None)`; `value() -> (ConversionSpec, mode, destination_or_None)`.
- Default keep; explicit replace hides/disables directory and rejects external directory in request/model. JPG/JPEG, PNG, WebP; quality, WebP lossless, JPEG white/black/custom background with QColorDialog and hex field. Imported timeout/max_pixels preserved in spec; dimensions/40M/metadata and pending-cancel limitations explained nearby. No video choices.
- Final small-window visibility review: PNG hides quality/lossless/JPEG background/custom background entire rows; JPEG shows quality+background and custom picker only when custom selected; WebP shows quality+lossless. Hidden parameter values remain intact in spec. Help uses existing muted styling; duplicated static cancel help removed.

### Immutable request DTOs

- `RulePreviewRequest(rule_id: str, paths: tuple[str,...], ruleset_revision: str, generation: int)`.
- `ConversionRequest(paths: tuple[str,...], spec: ConversionSpec, mode='keep', output_dir=None, generation=0)`.
- Both are frozen, detach mutable paths input to tuple strings, reject empty paths. ConversionRequest validates spec/mode, normalizes keep output directory with the model helper and rejects any replace output directory. No backup/swap/staging paths from UI.

### RulesPage

- Signals: `saveRequested(object: RuleSet)`, `importRequested(str: path)`, `exportRequested(str: path)`, `previewRequested(object: RulePreviewRequest)`, `executeRequested(object: opaque_token)`, `checkRequested()`, `changed()`.
- `set_ruleset(snapshot: RuleSet)`, `value() -> RuleSet`, read-only `dirty`, `selected_id`, `generation`.
- `set_watch_roots(paths)`: passed configured-root checklist, no discovery. Empty checked scope=all configured roots. Unknown saved roots stay visible and selected with warning; Save/Test rejects unknown scope until corrected. Untouched scope ordering and case are retained.
- `new_rule()`, `duplicate_rule()`, `delete_rule()`, `move_rule(delta)`; new/duplicate disabled via frozen model helpers. Existing enabled definitions preserved. Invalid current draft blocks switching rules rather than discarding edits.
- `set_sample_paths(paths)` accepts files/folders, always invalidates even identical replacement. File multiselect and additional folder chooser available.
- `invalidate_preview()` increments generation, clears token/output, disables Execute.
- `set_preview(text, token=None, can_execute=False)`, `set_busy(busy)`, `show_error(message)`.
- Dirty draft must be saved before Test; Save emits full validated RuleSet and remains dirty until controller acknowledges success with `set_ruleset(saved)`. `show_error` preserves draft. Import/export choose paths only; dirty draft first requires save. Controller import must use RuleStore's fully validated fresh-disabled-ID import API.
- Execute is explicit and consumes token once before signal. There is no preview-triggered execution/autosave/auto-enable. Manual check button explicitly labels that it executes enabled rules. Copy explains existing/new matching top-level items, explicit enable/unpause, each rule's age criteria, approximately10-minute checks and generic rules not needing sync_root.

### TemplatesPage

- Signals `saveRequested(object: TemplateLibrary)`, `changed()`.
- `set_library(library)`, `set_projects(mapping)`, `value() -> TemplateLibrary`; read-only `dirty`, `selected_id`.
- `copy_template(name=None)`, `delete_template()`, `assign_project(code, identifier_or_None)`, `set_busy(busy)`, `show_error(message)`.
- Built-in default readable/copyable/read-only; custom name/directories/category+keep-name mapping tables/naming fields with add-remove and token examples. Example rendering is pure finite naming, never reads files. No seventh main navigation is added here; parent places it under rule tooling in phaseB.
- Full library/assignments retained, including codes absent from currently passed project list. Invalid rows/naming preserve dirty draft and block save/switch. Assigned deletion explains removal first. Previously saved assignment must be removed **and acknowledged with set_library(saved)** before deletion, matching TemplateStore's saved-assignment guard. Failed save keeps dirty input.

### ConversionPage

- Signals `previewRequested(object: ConversionRequest)`, `executeRequested(object: opaque_token)`, `cancelRequested()`, `changed()`.
- `set_paths(paths)`, `value() -> ConversionRequest`; read-only `paths`, `generation`, `cancel_pending`.
- `invalidate_preview()`, `set_preview(rows, token=None, can_execute=True)`, `set_progress(status)`, `set_busy(busy)`, `set_cancel_pending(pending=True)`, `show_error(message)`.
- Rows are mappings with optional `source`, `target`, `status` (default ready), `message`; exact paths shown with wrapping and full-path tooltips. Controller passes `can_execute=False` for wholly invalid preview. No fabricated target computation or decode happens in widget.
- Progress mapping: `index: int` (zero-based row), `phase` and optional `percent`, or final `status` and optional `message`. Unknown/out-of-range row ignored. Phases start/decoded/encoded/verified are preparation/read/encode/verify; **complete=100, saving, replacing, committing all display 正在保存/替换**, omit percentages and never success. Final status enum: ready, pending, running, success, error, canceled (cancelled alias), conflict. Only explicit status=success marks 已完成. Late-cancel display supports already-successful row plus remaining canceled rows.
- Busy applies to settings/source selection and preview/start; progress table remains enabled/scrollable. Cancel button is active during both preview and run; first click immediately sets cancel_pending and emits once. Busy=false clears pending; owned rows remain. It never blocks ordinary archive controls.
- Explicit Execute consumes token once. Edits/new same-path selection invalidate it. Busy consumes previous token. Keep requires explicitly selected directory; replace doesn't.

## PhaseB adapter obligations

Both request-generating pages expose public monotonic `generation`. `set_preview` does not itself infer callback source: adapter **must compare captured request.generation + service/state identity** before setting preview/progress/error, and marshal all worker callbacks to GUI thread. On service/demo/template/rule/source switch call invalidation and cancel obsolete jobs; never install old callback tokens. Save must use captured expected persisted revision; acknowledge only successful saves. Forms don't implement cancellation events: connect cancelRequested to dedicated executor's direct cancellation API. Preview/inspect as well as execution must go on dedicated executor. Backend final outcomes—not codec complete100—drive final row statuses. Parent main-window/nav/runtime/close wiring remains phaseB.

## RED / GREEN evidence

All commands from this worktree, existing `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_forms.py -q`, only owned basetemp:

1. `--basetemp=sandbox/forms020-red1`: expected missing new module collection error,1error. This was import RED, not assertion failure.
2. `--basetemp=sandbox/forms020-green1`:14passed in0.38s.
3. `--basetemp=sandbox/forms020-red2`:7failed,12passed in0.55s: absent calendar/root API, numeric clamp/rounding, duplicate execute, assignment-removal sequencing. Calendar fixture was later made explicitly UTC (a naive QDateTime is local and was correctly converted, causing an intermediate1failed/18passed run); template fixture explicitly acknowledges saved assignment before testing the persistent deletion guard.
4. `--basetemp=sandbox/forms020-red3`:2failed,18passed in0.60s: scope order/case rewritten without user edits; result table disabled while busy. `forms020-green3`:20passed in0.52s.
5. `--basetemp=sandbox/forms020-final`:1failed,24passed in0.64s: QColorDialog custom color didn't re-enable its hex control. This failure log retained as `sandbox/forms020-final.txt` (not final green evidence).
6. `--basetemp=sandbox/forms020-red4`:2failed,28passed in0.70s: same color bug + Decimal overflow escaping ValueError. Log `sandbox/forms020-red4.txt`. `forms020-final2`:30passed in0.56s, log `sandbox/forms020-final2.txt`.
7. `--basetemp=sandbox/forms020-red5`:1failed,30passed in0.56s: frozen DTO retained caller's mutable list. Log `sandbox/forms020-red5.txt`.
8. `forms020-final3`:31passed in0.51s. Director/root final scoped visibility review RED6:1failed,31passed in0.62s (PNG irrelevant rows visible); GREEN4:32passed in0.55s. Same isolated capture regenerated for final row visibility and inspected.
9. Adapter phase alignment RED7:1failed,31passed in0.68s (`committing` displayed generic99% rather than publication phase). Log `sandbox/forms020-red7.txt`.
10. Final exact command: `& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_forms.py -q --basetemp=sandbox/forms020-final5 | Tee-Object -FilePath sandbox/forms020-final5.txt` → **32passed in0.44s, exit0**, full owned log retained. No later production edits after this gate.

Coverage: nested logic/limits/field values+units/date precision, all action kinds and CRUD/reorder/validation, keep/replace/no-directory, format-dependent settings/background picker, disabled new/duplicate, draft save failure and save-before-preview, import/export path-only intents, folder samples, configured/unknown scopes preserving untouched snapshots, immutable request input detachment, single-use tokens/same-value selection edits, independent busy/pending cancel, final-vs-staging progress and late-cancel rows, template full fields/mapping/naming/assignment/copy/read-only/delete/save-error. Store/codec methods monkeypatched forbidden prove constructors/value don't invoke runtime IO.

## Isolated visual evidence

One permitted small dark conversion-widget render only (no native combined matrix):

`$env:PYTHONPATH = 'src'; & .venv/Scripts/python.exe -X utf8 sandbox/forms020-render/render.py`

Exit0; logical620×620 widget (display scaling produces930×930 capture), `sandbox/forms020-render/conversion-dark-620x620.png`. Inspected pixels: settings/help scroll, long Chinese row paths wrap/truncate with full tooltips, 正在保存/替换 visible, bottom action row remains outside scroll. Synthetic row only; no source image read. Full integrated dark/light800×620/1000×700 matrix, ordinary archive responsiveness, generation/service callback and installer evidence are explicitly reserved to phaseB/root.

All owned phaseA deliverables frozen; no ongoing process remains.
