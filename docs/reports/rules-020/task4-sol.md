# Task4B Sol — integrated rules, templates, images and safe lifecycle

Status: **production source/tests frozen for independent review**. Final owned
focused gate: **88 passed in 11.24s, exit 0**. Worktree:
`C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`, branch
`feature/filehub-rules-020`, dispatch HEAD `f46fdbd25e77f7783013d7e5a9cf3bc55d600d3f`.

## Ownership and constraints

Owned changes: `ui/main_window.py`, `ui/app.py`, `ui/coordinator.py`, new
`ui/automation_controller.py` and `ui/compact_message.py`; bounded integrated
layout/cancel/copy changes in `rules_page.py`, `templates_page.py`,
`conversion_page.py`; new `tests/test_automation_ui.py` and the narrow asynchronous
demo expectation in `tests/test_app_runtime.py`; this report. The capture helper
and screenshots live only under owned `sandbox/task4b-render/`. Task5/root
packaging, documentation and evidence edits visible concurrently are not mine.

No backend/model/codec/publication/journal/packaging edits, agent spawning,
stage/commit, full suite, pip/install/uninstall, Explorer, live app/user state,
real watch/sync folders, registry edits, user-process operations or external
publication. Existing `.venv` junction was read-only. All test/capture state is
new worktree sandbox data; the capture helper uses a fresh UUID state each run.
Original `F:/Hazel Windows` was not modified.

## Wiring and APIs

- Existing main navigation indices 0–3 remain 整理/收件箱/记录/设置. Indices 4/5
  add 自动规则/图片转换. Rules and subordinate 项目模板 share a `QTabWidget`.
  Existing home scroll, footer, history chips and icon/theme implementation stay
  in place. First-run/home/settings/background copy distinguishes ordinary rules
  from the legacy unmatched 3-day inbox fallback and project sync requirements.
- `AutomationController(QObject)` owns immutable loaded rules/library revisions,
  saved selected-rule snapshots, request bindings, job handles and Qt delivery.
  `PreviewToken(service, state_generation, effective_generation,
  page_generation, preview, images)` carries the exact backend-issued preview;
  tokens and incoming request generations are checked before execution/delivery.
  No UI types are imported by the backend and no new runner/publication layer is
  introduced.
- Initial rules/library/project discovery and lazy `service.conversions` creation
  run on `Coordinator`. Complete watch roots are injected with
  `RulesPage.set_watch_roots`; discovered project snapshots populate templates.
  `RuleStore.save`/`import_document` and `TemplateStore.save` receive the loaded
  full `expected_revision`. Success alone acknowledges forms. Save failures and
  stale external revisions preserve dirty drafts. A later programmatic draft is
  not overwritten by an older successful save; persisted revision still advances.
- Rule import uses `checked_path`, stat size, a bounded `MAX_DOCUMENT_BYTES+1`
  binary read, UTF-8 decoding, duplicate-key rejecting `_unique_object` parsing,
  and store schema/import validation. Imported IDs and disabled state remain
  store-owned. Export writes definitions only on the ordinary worker.
- Saved rules without `image_convert` use
  `service.automation.preview(..., cancel_event=Event)` and
  `.execute(..., cancel_event=Event, progress=...)` on the ordinary worker.
  Image-bearing rule preview/execution use the frozen executor's
  `submit_rule_preview`/`submit_rule`. Standalone images use
  `submit_image_preview`/`submit_images`, with exact mode/output-directory args.
  Full decode and encode stay on the dedicated serial image worker.
- Dedicated submission is itself queued briefly on `Coordinator`, so a Future
  that finishes before callback registration cannot call `Future.result()` on
  GUI. Ordinary `Coordinator` actions emit their captured result/failure directly
  from the worker, avoiding the same immediate-Future callback hazard. Codec work
  never occupies the ordinary worker. UI callbacks/progress are Qt signals.
- Direct cancellation sets the bound Event under a short adapter lock; it never
  waits behind codec work. A cancellation before handle registration transfers to
  the actual handle Event. Rules have explicit job cancel/pending controls;
  cancellation is unavailable during store load/save because those are not
  cancellable jobs. Standalone cancel covers both preview and conversion.
- Rule preview displays the backend's complete `preview.matching` evaluation
  tree and `plan.explanation`, including nested groups, actual values, thresholds,
  unavailable information and nonmatches. GUI never reevaluates conditions.
  Ordered action labels come from the saved rule's `action_index`; conversion
  replacement/backup versus keep behavior appears beside exact plans. Test never
  executes. 明确执行 consumes the exact token once. Manual check executes enabled
  rules through Scheduler; ordinary generic rules work without sync_root.
- Progress binds item index and service/generations. Rule progress includes action
  name/index and current subject. Codec/commit progress never marks final success;
  only final `RunOutcome` sets completed rows. Late cancellation after a critical
  commit reports that row completed, with remaining rows canceled. Rule final
  states are Chinese, including skipped/partial/failed/canceled.
- `RunOutcome` is resolved by batch_id through `service.history()` on a worker;
  it is never passed as a `BatchResult`. Actual batches feed existing history,
  undo and notifications. History labels `convert` as 图片转换/替换, and worker
  snapshots of `journal.generated(operation_id)` preserve original backup,
  swap/undo-stage locations and backend conflict messages for display.
- `Scheduler(..., automatic_completion=...)` uses the adapter completion hook.
  Runtime refreshes a captured hook on each tick, marshals asynchronous image
  successes/failures into GUI history and notifications, and handles mixed
  ordinary `RunOutcome`/legacy `BatchResult` tick output. Old service/state/effective
  callbacks do not update new state; revoked effective callbacks refresh durable
  history without delivering obsolete result UI.

## Authority, demo and exit

Settings and pause persistence plus effective `service.config` assignment run
inside `service.engine.locked()` on the ordinary worker. Direct cancellation is
requested before queuing that change. Structural settings cancel all image jobs;
pause cancels automatic jobs and conservative manually selected rule work;
explicit standalone images continue through paused-only changes. Theme-only
changes do not revoke execution authority or cancel jobs. Preview invalidation
and changed watch/project snapshots are applied without hiding configured roots.
Queued zero-intent claim release remains exclusively backend-owned.

`AutomationController.retire(callback)` stops accepting work, directly cancels
owned jobs and uses `service.close_conversions(callback)`; no GUI native wait,
Future.result/join or synchronous codec shutdown exists. `Coordinator.begin_wait`
/`end_wait` account for asynchronous settlement in the existing busy ownership
gate. Effective demo/state replacement occurs only after settlement. Runtime
quit retains its lease/marker until both image settlement and ordinary worker
operations finish. Event-loop-finally cleanup also settles conversions before
releasing ownership after the loop ends.

A demo creation exception or `None` result reconstructs a **new** same-state
service after old settlement, rebinds forms and Runtime Scheduler/service, and
retains the original runtime lease/state. The old closed executor is never reset.
The user receives “未进入演示，原状态已恢复”. If reopening itself fails, the UI
states that prior jobs safely ended and requests a safe exit/reopen, leaves new
image/automatic submissions disabled, and never claims demo success. No partial
new-demo scheduler constructor failure leaks its acquired lease.

## Focused RED / GREEN evidence

All commands used the existing runtime, worktree cwd and fresh owned basetemp.

1. `tests/test_automation_ui.py --basetemp=sandbox/task4b-red-nav`:
   **1 failed /0.33s**: the two new navigation entries were absent (assertion RED).
2. First nav + existing UI gate: **1 failed,10 passed /2.07s**. Old demo test's
   settle helper returned before the new asynchronous settlement callback; busy
   settlement accounting fixed that behavior.
3. Existing UI/app compatibility gate exposed the old slow-demo test blocking GUI
   with `entered.wait(2)` before the settlement signal could dispatch. It now
   processes events while waiting for the worker checkpoint. A bounded diagnostic
   run was interrupted via its owned session after that assertion failure left
   incomplete fixture cleanup; no user process was touched. Corrected gate
   `sandbox/task4b-green-runtime3`: **30 passed /5.63s**.
4. New integration regression gate `sandbox/task4b-ui-new1`:
   **1 failed,11 passed /2.57s**: planner engine `move` kind was incorrectly shown
   as the source rename action. Rendering saved action_index fixed the label.
5. `sandbox/task4b-ui-new2`: **19 passed /4.59s**, including critical transaction,
   actual replace/undo, independent decode/encode, automatic completion and leases.
6. `sandbox/task4b-integration-gate1`: **84 passed /12.26s**;
   `sandbox/task4b-integration-gate2`: **84 passed /11.40s** (JUnit retained).
7. `sandbox/task4b-final-owner`: **87 passed /11.48s** after stale-request,
   all-Future-results-off-GUI and demo-reopen-failure coverage. Log/JUnit retained.
8. Final exact command:

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_ui.py tests/test_ui.py tests/test_app_runtime.py tests/test_automation_forms.py -q --basetemp=sandbox/task4b-final-owner2 --junitxml=sandbox/task4b-final-owner2.xml | Tee-Object -FilePath sandbox/task4b-final-owner2.txt
```

Result **88 passed in11.24s, exit0**: 27 new integrated UI cases, 10 existing UI,
19 existing app/runtime,32 pure-form cases (forms were rechecked because bounded
layout/cancel/copy changes occurred). Focused `git diff --check -- src/filehub/ui
tests/test_automation_ui.py tests/test_app_runtime.py` returned exit0, no whitespace
errors; Git emitted only standard LF→CRLF notices. No subsequent production or
test edit after this final gate.

New coverage includes nav/store acknowledgement/CRUD/import bounds+duplicate keys,
dirty external revision failure and newer draft retention, template save failure,
manual ordinary and image rule preview versus execute, exact nested match and
unavailable reasons, stale request/page/service generations, real standalone
replace/backup/history/undo, per-row commit truthfulness, direct preview/encode
cancellation while actual ordinary archive proceeds, theme continuity/pause
automatic-only behavior, actual critical commit before demo/settings/quit,
owned runtime lease+fake marker retention, automatic success/failure notices,
demo failure/None recovery and reopen failure state, and small template column
geometry. All are isolated artifacts; no full backend gate was repeated.

## Native combined-window visual evidence

Exact native capture command (last run exit0):

```powershell
$env:PYTHONPATH='src'
$env:QT_QPA_PLATFORM='windows'
& .venv/Scripts/python.exe -X utf8 sandbox/task4b-render/render.py
```

The helper shows actual MainWindow objects backed by a fresh UUID sandbox service,
with long Chinese rule names, nested all/any conditions, ordered replace/rename/
move actions, custom template maps/project assignment, image batch states and a
multi-line whole-window footer. Synthetic image row progress/conflict text is a
**visual fixture**, not a claimed live conversion result. Real conversion behavior
is covered separately by the focused tests above.

32 PNG captures cover dark/light × logical1000×700/800×620 × rules top,
rules-conditions, rules-actions, templates top, templates-maps, images top,
images-results and home. This machine's scaling makes physical captures
1500×1050 and1200×930 respectively. Files use
`sandbox/task4b-render/{dark|light}-{1000x700|800x620}-{view}.png`.

Representative inspected outputs (director/root also reviewed800px variants):

- `dark-800x620-rules.png`, `dark-800x620-rules-conditions.png`,
  `dark-1000x700-rules-actions.png`: persistent action controls, nested editor
  scroll and footer remain separate and usable.
- `dark-800x620-templates-maps.png`,
  `light-1000x700-templates-maps.png`: both essential mapping columns fit.
- `dark-800x620-images-results.png`, `light-800x620-images-results.png`: all three
  completed/committing/conflict rows visible with normal wrapped filenames and
  messages, exact absolute paths retained as full tooltips.
- `dark-1000x700-home.png`, `light-800x620-home.png`: prior home cards/recent area
  and whole-width footer boundary preserved.

Concrete capture fixes only: capped rule list82px and hidden empty feedback regain
editor space; long project/template combos no longer force editor horizontal
overflow; capped90px source basename list retains full-path tooltips; result table
shows compact exact basename + full-path tooltips and reflows row heights when
columns resize. No broad theme/redesign changes. Final result-table screenshot
was accepted by director; final recapture retains the same readable geometry.

## Remaining boundary / limitations

Native Qt codec cancellation remains stage-boundary based; pending copy explains
that a current native call or critical replacement will safely finish/restore
before cancellation settles. Backups have no cleanup/reset UI. Image formats and
metadata/limits remain the frozen JPEG/PNG/WebP contract; no video conversion.
The source gate and captures are not installer acceptance. Root owns independent
whole-branch review/full suite; Task5 owns packaging and clean packaged image
roundtrip. All owned sessions completed and capture windows/worker queues were
closed before freeze.
