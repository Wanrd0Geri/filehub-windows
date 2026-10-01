# Task3B — durable rules and serial image jobs

Implementation is frozen for director review. Work stayed in the authorized
`feature/filehub-rules-020` worktree, starting at `ab7e406`. No staging, commit,
full suite, pip/install, app/watch/registry/live-state operation or child agent.
Task1/Task2 models/planner and image backend remain unchanged. Owned changes:
`automation/ledger.py`, `runner.py`, `executor.py`, narrow `service.py` and
`scheduler.py`, `tests/test_automation_runtime.py`, this report, and the explicitly
authorized narrow generated-publication tunneling fix plus two generated tests.
The director's separate directory safety fix (`caf2335`) is consumed and tested;
its operations/trees/directory-test files were not edited by Task3B.

## Integration APIs

`FileHubService.rules` is the state-local `RuleStore`. Lazy, synchronized
`service.automation -> AutomationRunner` and `service.conversions ->
ConversionExecutor` use the existing engine/state. Constructors and all preview,
scan and execution filesystem work belong on a worker, never the GUI thread.

```python
runner.preview(paths, rule_id=None, *, inspect_images=False, now=None,
               automatic=False, watch_root=None, cancel_event=None) -> RulePreview
runner.execute(preview, *, cancel_event=None, progress=None,
               automatic=False, claims=None) -> tuple[RunOutcome, ...]
runner.ledger.history() -> tuple[dict, ...]

executor.submit_rule_preview(paths, rule_id=None, *, completion=None, progress=None)
executor.submit_rule(preview, *, completion=None, progress=None,
                     automatic=False, claims=None)
executor.submit_image_preview(paths, spec, *, mode='keep', output_dir=None,
                              completion=None, progress=None)
executor.submit_images(preview, *, completion=None, progress=None)
executor.cancel(job_id=None)
executor.cancel_automatic()
executor.when_idle(callback)
executor.close(callback=None) -> threading.Event
executor.state_change(callback=None) -> threading.Event
service.close_conversions(callback=None) -> threading.Event
```

Every submit returns `JobHandle(id, cancel_event, future, automatic)`. Cancel is
direct and thread safe; it bypasses the serial queue. Completion receives the
completed Future on a worker/callback thread; marshal into Qt before touching
widgets. `future.result()` returns the preview or outcomes, or raises validation/
cancellation. Completion and idle callbacks are not GUI signals.

`RulePreview` contains `plans`, complete first-match `matching`, `errors`, full
ruleset/template/config diagnostic revisions, `image_capabilities`, and separate
`authority_config_revision`. The exact issued object is bound to its runner and
engine/state; copied, forged or foreign-service previews are rejected before
decode or promotion. Weak ownership records retain queued automatic previews
while a new manual sample invalidates older manual tokens. Plain runner preview
does no image decode. Use `submit_rule_preview` for image-bearing manual rules;
image-bearing execution refuses an ordinary worker before any material step.

`ImagePreview(items, mode, config_revision, authority_config_revision)` contains
`ImagePreviewItem(source, target, conversion_plan, error)` per selected row.
Keep requires `output_dir`; replace requires no folder and rejects a supplied
one. Every selected source, case alias and exact destination is reserved before
execution. Errors remain per item and remaining good items can continue.
Preview and execution never reallocate an occupied destination. The exact issued
ImagePreview object is executor-bound.

`RunOutcome(source, batch_id, status, error, steps, run_id)` has `.ok` for success.
Rule steps retain committed operation IDs/source/target/state; standalone steps
contain the actual ItemResult. A rule failure stops later steps and keeps prior
successes with partial status. History uses the rule display name as the engine
batch label, with all steps in one batch. `service.history()/undo()` remain the
sole operation history/inverse path; undo reconciles verified restored IDs into
automation ancestry.

Progress mappings carry `index` (zero-based item row), `source`, `phase`,
`percent`; rules also carry `step_index`. Codec complete100 is translated to
`committing`/99. Whole-item `complete`/100/success follows publication and ledger
commit. Final outcomes also report errors/skips. External progress callback
exceptions are logged and cannot change a transaction's actual result.

## Watch, claims and authority

`Scheduler(service, *, automatic_completion=None).tick(aware_now)` matches basic
rules before the legacy 3-day gate and works without sync_root/project tag.
Only unmatched legacy fallback needs sync_root. Empty rule documents retain
existing no-sync diagnostics, hidden/reparse/temp/Office filtering, pause, expiry
and the existing 600-second timer behavior. The first matching enabled rule
claims even an invalid plan, prior failure or visited lineage; no later rule or
legacy fallback executes. Observations are saved before matching; manual missing
ages remain unavailable. Pausing clears observation clocks, retaining claims and
ancestry. Generic video project routing reuses the existing width probe only
when actual planned naming needs it; keep-name routes do not probe.

Ordinary rules return `RunOutcome` entries from tick; old fallback/global jobs
return existing `BatchResult` entries. Both expose batch_id/ok/status. Image rules
are claimed/enqueued and tick returns promptly; their results arrive through
`automatic_completion(future)` for AppRuntime's GUI marshaling/history refresh.
Initialize lazy runtime/executor before acquiring the engine authority lock;
the scheduler follows this lock order.

Full ruleset/template digests, semantic rule revision, original full fingerprint,
exact destinations, current subject fingerprint, scope and config are checked
again at material boundaries and after encoding. Future subjects are never
pretended to exist. Original bytes can be inspected for eligibility after a
planned rename/copy; each actual later converted subject is independently
inspected and fingerprint-bound before generation. Terminal project-route branch
copy honors `advances_subject=False`.

Theme is excluded from execution authority but retained in the captured full
diagnostic digest. Explicit standalone images also exclude only `paused`, so
pausing automation cannot cancel an explicit image job. Automatic jobs require
the full remaining settings, enabled definition, configured top-level watch and
unpaused state. Manual selected-rule execution permits a disabled rule through
distinct Execute and retains conservative pause snapshot binding.

New manual claims happen only after harmless stale/occupied-preview rejection,
so correcting an obstruction and re-previewing does not poison unchanged work.
Automatic claims are durable before enqueue/mutation and are passed back into
the job rather than claimed twice. Paused/obsolete jobs proven still queued can
release only AFTER their Future settles, with **zero engine journal intents** and
the unchanged original full fingerprint. Audit status becomes
`canceled_before_start`; only that claim's visited marker and unique key are
released. Running/failed/partial/unknown/material-intent jobs retain suppression.
There is no generic retry/reset UI or automatic phase replay.

## Ledger, publication and lifecycle

`automation.sqlite` uses the same reentrant process lock and SQLite synchronous
FULL. It stores original path/full fingerprint, stable/first-seen observations,
semantic/full revisions, rule display name, linked engine batch, intended exact
steps/spec/mode, progress and queued/running/success/partial/failed/review-required
states. Exact normalized path/full-fingerprint ancestry carries inherited visited
(rule id, semantic revision) pairs. Each committed output and retained input is
registered. This stops actual PNG→JPG→PNG replacement after A and B complete,
including restart, while external path/content changes and semantic edits remain
eligible. Enable/name/order changes do not reset semantic ancestry.

Startup calls conservative engine recovery before ledger reconciliation when no
same-state job is live. Interrupted queued/running claims become review-required.
Journal commits reconstruct output ancestry only from matching actual full
fingerprints and trustworthy terminal states. Ambiguous existing targets are
blocked, including generated rename before durable fingerprint rebind. Verified
journal undo_fingerprint identities propagate to restored originals, including
new Windows file IDs; no arbitrary hash-based inverse suppression is used.

Generation uses only frozen `generate_owned(engine,...expected_source,
expected_capability_digest)` tickets; publication uses only
`engine.publish_generated(..., staging=ticket, mode=..., batch_id=..., cancel_event=...)`.
Cleanup uses only `discard_owned` and tolerates an already consumed ticket. No
duplicate publication, backup or undo implementation exists. The Task3A journal
migration and inverse lineage remain unchanged except the separately reviewed
directory safety integration consumed above.

Close/state_change stops submissions, cancels current/queued jobs immediately,
and returns without native-codec joining on the caller. A separate settlement
thread joins the owned worker. The returned Event/callback fires **after** every
old file mutation and completion callback settles. Service close latches retirement
even before lazy executor creation. Task4B must only make demo/service generation
replacement effective from this settled callback; discarding an old UI callback
alone is insufficient. Native codec calls may return before cancellation is
observed. Cancellation after critical replace intent safely settles a committed
item, reports it as completed, stops remaining items, and then permits the switch.

## Authorized generated safety delta

Actual cycle RED proved A PNG→JPG succeeded but B returning to the recently
vacated PNG path hit NTFS creation-time tunneling, leaving a conflict. Root and
director authorized one narrow `generated.py` change: after exclusive rename,
rebind creation time from the continuously held owned output for cross-extension
as well as same-path publication. Device/file ID/size/hash/mtime/ADS remain exact;
the actual published fingerprint is journaled before source removal. Ordinary
transfer checks are untouched. A real returning-name roundtrip and a child-process
crash before rebind verify success versus conservative survivor/conflict behavior.

## Evidence and remaining integration

Initial RED was the missing runtime module collection error. Later meaningful
REDs covered vacated-name tunneling and the directory chain safety gap; both were
resolved through the expressly authorized ownership boundaries. One stale-copy
fixture sets an obstruction's creation time equal to its source to isolate claim
semantics from the unchanged ordinary engine's conservative NTFS tunneling check.
The core safety is not weakened to make that fixture pass.

Final focused command (no full suite):

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_runtime.py tests/test_generated.py tests/test_scheduler.py tests/test_service.py -q --basetemp=sandbox/task3b-final-owner --junitxml=sandbox/task3b-final-owner-results.xml
```

Final result: **179 passed in 21.93s**, exit 0, no failures/skips. The runtime file
alone passed **48 tests in 9.27s** after the final owner-boundary hardening. The
preceding combined gate passed **177 tests in 21.13s** before the two owner
regressions were added. Focused diff-check produced no whitespace errors.

Coverage uses real Qt images and real Windows owned sandbox artifacts. Three
runtime `os._exit(77)` child-process fixtures exercise both publication/provenance
gaps and same-path prebind crash; the generated extension has another actual
cross-extension prebind crash. Tests include ordered copy/rename/move, directories,
real keep/replace/image chains/multiple conversions/undo/restart/cycles, invalid
first-match claims, stale/foreign/forged previews, exact reservations, concurrent
manual/automatic claims, decode/encode responsiveness, queued authority changes,
pause/resume release, theme-only continuity, codec cancellation, and asynchronous
switch exactly inside critical publication before final commit.

Native codec cancellation remains stage-boundary based. Backups have no automatic
cleanup. Unjournaled generated staging after process death is preserved, as in
Task3A. Unresolved owned targets require history review; there is no unsafe reset.
UI/Coordinator/AppRuntime generation wiring and packaging/final full suite remain
Task4B/root work; this backend does not claim those gates.
