# Independent final UI/runtime review — FileHub 0.2.0

Frozen target: `244895d` against `d5b6f88`. Reviewed the UI/controller/Coordinator/runtime/forms/test integration, Task4B brief, task4-astra-review.md, task4-sol.md, frozen task3-sol.md backend APIs and resolved root-core-final-astra.md. App source was read through `git show 244895d:src/filehub/ui/app.py`; source diff at reproduction time confirmed the inspected UI files matched the freeze. Packaging, self-test additions and live state were excluded.

**Initial disposition at `244895d`: three actionable P2 defects. All three are resolved by the independent `dca4c55` re-review recorded below.** No additional speculative hardening or feature requests are included.

## P2 — Demo transition permits an old-state configuration write after releasing its lease

Primary location: `src/filehub/ui/main_window.py:360–368` (`toggle_pause` admits and captures old-state work without a transition/retirement guard). Related boundaries: `main_window.py:370–378`, `ui/app.py:267–269` and `main_window.py:257–261`.

Concrete trigger: start demo, hold `create_demo` at a worker checkpoint, then click the existing home `pause_button` while demo creation is in progress. The control is enabled even though `automation.accepting` is false. `toggle_pause` queues a closure capturing the old service/store behind `_demo_worker`. On release, `_demo_worker` switches Runtime to the new demo state and closes the old lease; the next ordinary-worker item then writes the old config. This is not merely a stale callback: the old persistent config is mutated.

Independent result: `old_lease_released_at_save=true`, `runtime_already_demo=true`, old `paused` changed from true to false, and demo became active. A callback generation check suppresses only the acknowledgement; it does not suppress the actual write. Thus the promised old-state settlement boundary is false and the original configuration can be changed, including enabling its automation, after ownership is released.

Minimal fix: use an explicit transition/retirement admission gate covering every old-state mutation entry point, including pause/settings and ordinary archive work; check it before enqueueing and ensure already queued work cannot mutate a retired generation after the switch. Freeze admission before retirement, drain/settle authorized old ordinary work and conversion work, and only then publish the new service/state and release the old lease. Disabling the home button is useful feedback but is insufficient as the enforcement boundary. Keep normal pause cancellation and theme-only behavior intact. Validate both admitted-before-transition settlement and rejected-after-transition requests, including the runtime/tray routes.

## P2 — Quit requested during demo creation is permanently stranded by rebind

Primary location: `src/filehub/ui/main_window.py:381–387` (unconditional service rebind after a pending quit). Related boundaries: `ui/app.py:283–293` and `automation_controller.py:351–354`. The recovery rebind at `main_window.py:398–400` needs the same lifecycle handling.

Concrete trigger: start demo, hold `create_demo`, trigger the tray `quit_action`, then allow demo creation to finish. Quit retires the old, already settled adapter and accounts for ordinary pending work. `demo_ready` subsequently calls `rebind`, which resets `accepting=True` and `settled=False` and loads the new executor. `_finish_quit` then refuses to finish because the new service is not settled, but no further retirement is scheduled for it.

Independent terminal state after all Coordinator work drains: `closed=false`, `quitting=true`, `pending=0`, `accepting=true`, `settled=false`, `lease_held=true`, `window_enabled=false`, `quit_action_enabled=false`, `demo_active=true`. There is no remaining completion capable of exiting. The process retains its lease/marker and presents no usable exit control. The sandbox harness explicitly retired the new service for cleanup after recording the failed state; that is not product behavior.

Minimal fix: make transition completion participate in Runtime's quit lifecycle. If quit wins while demo creation/recovery is outstanding, do not restore submission authority; either discard/settle the prepared service before publishing it, or immediately retire the newly bound service and wait for both queues before releasing its lease/marker and exiting. Handle successful demo creation, demo failure/same-state reconstruction, and quit before conversion settlement with the same monotonic closing state. Do not merely disable the tray action or bypass `_finish_quit`'s settlement requirement.

## P2 — Stale scheduler error permanently leaves tick_pending set

Primary location: `src/filehub/ui/app.py:248–249`.

Concrete trigger: while a scheduler check is running, edit/create a rule (the rule editor remains usable and increments `automation.rule_generation`); the in-flight check then raises an I/O error. The conditional error lambda skips `_tick_error` because its effective generation is obsolete. Unlike `_tick_done`, it never clears `tick_pending`. Every later timer/manual request returns at line 241.

Independent result with a controlled worker `OSError`: after rule editing and worker failure, `tick_pending=true` with `coordinator.pending=0`; issuing another `schedule_tick` leaves the scheduler call count at one. This is a deterministic error-path reproduction, not a claim that a real disk failure occurred during testing.

Minimal fix: unconditionally settle the completed request's pending ownership on both success and failure before applying generation-based UI/notification suppression (a common completion/finally path or equivalent request-token settlement). Stale errors should not paint the new state, but must release their own pending flag; guard against clearing a newer request if the lifecycle is refactored to permit one. Validate a stale error followed by a successful new check, as well as the current-generation failure notification.

## Evidence and limits

Owned reproduction: `sandbox/root-ui-astra-46e874f8bfcd403a9b6bff4400582712/repro.py`; exact observed results: sibling `results.json`. The script used real Runtime/MainWindow/Coordinator/services, isolated ConfigStores and leases, Qt offscreen widgets, actual button/action activation, and Event checkpoints around demo construction / scheduler failure. Only timing/failure injection and a fake installer marker were substituted; no codec or transaction claims are inferred from this reproduction.

Executed with the existing `.venv/Scripts/python.exe -B -X utf8`, worktree `PYTHONPATH=.../src`; exit 0. No full suite, installer, build, dependency install, original checkout write, live app/user state, registry mutation, or product/index edit occurred. All created runtimes were safely settled and closed by the harness after collecting evidence. The director/Sol 88-pass focused gate was read as prior evidence and not rerun or represented as independent passes. The reviewed core finding remains closed; these three defects are confined to UI/runtime lifecycle/error handling.

## Independent narrow review — packaged self-test integration (UI findings remain open)

Reviewed only new `src/filehub/selftest020.py`, new `tests/test_selftest020.py`, and the two-line `extend_report(fixture, report)` import/call inserted in `ui/app.py:self_test` against `244895d`. Concurrent Runtime lifecycle repairs are excluded. **No actionable defect or blocker found in this bounded self-test addition.** This disposition does not resolve any of the three UI findings above.

The original ten checks and their truth values remain intact. The new helper appends eleven separately named checks and the original entry sets overall `ok` only after the helper returns. The helper executes the real native codec capability/reader path, executor-issued previews, generation/publication, journal backups, same-path and cross-extension replacement, ADS/timestamp restoration, ordered copy-convert-move inverse, Scheduler rule matching and durable suppression, disabled import persistence, and persisted template routing. Its ordinary QImageReader assertions inspect emitted files; it does not replace these operations with synthetic successes. Existing video checks remain archive/probe compatibility checks, with no added video conversion route.

All helper state, inputs, destinations, projects and backup paths derive from a freshly created `release020` child of the existing `self-test-<uuid>` fixture. `mkdir()` refuses reuse; no live default ConfigStore, installed runtime, registry, settings, shell recycle or user-selected watch root is introduced. Reopened services address only their own fixture states, and owned conversion workers are closed in `finally`. The only production call site is inside the explicit existing `--self-test --state-dir` entry, which returns before normal Runtime/marker/integration startup. No new hidden runtime action or settings switch was added.

Helper assertion/operation failures propagate to the existing `self_test` exception handler while `ok` remains false; it writes the requested parent's `self-test.json`, and `run` returns 1 even without stdout. The new failure-injection test asserts this path and preservation of all original ten successful checks. The source success test checks the union of all 21 check names plus native tiny-WebP details, chain history, template persistence and fixture containment.

Evidence limit: source/API and test review only. Per dispatch, the earlier four-test gate was not duplicated, and no build, full suite, packaged executable, live installation, or product/index edit was performed. Actual frozen executable execution and its emitted 21-check JSON remain the root's packaging acceptance evidence.


## Independent narrow re-review — all three lifecycle findings resolved

Frozen product reviewed: **`dca4c55039e3e73aebaf797ba13aac7390b4ebe9`** against `244895d`. Read the correction and director `task4b-lifecycle-astra-review.md`; the previously reviewed self-test helper/hook was not reopened. At execution time HEAD had advanced to the packaging/docs commit `a5b8506`; a final `git diff dca4c55 --` over the reviewed app/controller/MainWindow/Coordinator and regression test files was empty, confirming the exercised product matched the frozen correction.

1. **Old-state post-lease write: resolved.** `capture_work_authority` rejects new normal work while transition/quit/close is active. Coordinator captures the service/generation for admitted work and calls `assert_work_authority` again on the worker before the action. Thus direct slots, tray actions and ordinary archive submissions do not rely solely on disabled widgets; queued old work is rejected once the service is retired. Already executing ordinary work keeps Coordinator pending, preventing demo from beginning/releasing its lease until it ends. Lifecycle bypasses remain explicit for demo/recovery, settlement/history reads and claim release. Independent cases verified zero old config/archive mutations during delayed demo, admitted writes completing while the old lease is held, and queued retired writes rejected before exit releases ownership.

2. **Quit across demo/recovery rebind: resolved.** `_quit_requested` remains set across rebind, prevents restored acceptance/loading, and suppresses a demo that has not yet begun when old conversion settlement finishes. Rebind resets only the separate retirement-started latch, allowing Runtime's service-identity-based `_retire_for_quit` to actually close the newly bound service even while it is nonaccepting. Both demo success and same-state recovery invoke that path. The final exit gate still requires conversion settlement and zero ordinary pending work before releasing lease/marker; it has not been weakened to escape the hang. Independent tests exercised success, recovery and quit before a real critical image publication safely commits.

3. **Stale tick error latch: resolved.** Success and failure both settle their own request token before generation checks suppress stale presentation. An obsolete request cannot clear a newer token. Independent cases verified a stale failure permits a second successful check, current errors still notify, and delayed old success/error callbacks leave the newer check pending.

Independent focused command (after the root's full suite finished; fresh owned basetemp, worktree PYTHONPATH, bytecode/cache disabled):

```powershell
& .venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_automation_ui.py -q -k 'transition_rejects_direct_home_tray_settings_and_archive_mutations or quit_during_demo_creation_or_recovery_retires_new_service_and_exits or stale_tick_error_settles_own_token_and_next_check_runs or admitted_config_write_finishes_before_demo_can_release_old_lease or queued_worker_guard_rejects_retired_mutation_before_ownership_release or tick_error_current_generation_notifies_and_old_token_cannot_clear_new_check or quit_before_demo_conversion_settlement_keeps_old_service_until_safe_commit' --basetemp=sandbox/root-ui-astra-dca4c55-pytest -p no:cacheprovider --junitxml=sandbox/root-ui-astra-dca4c55-results.xml
```

Result: **8 passed, 27 deselected in 1.81s, exit 0**. Independent stdout and JUnit: `sandbox/root-ui-astra-dca4c55-results.txt` and sibling `.xml`.

Additional independent lifecycle reproduction: `sandbox/root-ui-astra-dca4c55-executor/repro.py`, results in sibling `results.json`, exit 0. For each of successful demo creation and same-state recovery, the helper deliberately instantiated the new service's real ConversionExecutor before rebind and held one of its worker jobs at an Event checkpoint. It triggered the actual tray Quit action before creation/recovery returned. After the new service became effective, the observed state was `closed=false`, `lease_held=true`, `marker_held=true`, `accepting=false`, `settled=false`, with the new job's cancellation event set. Only after releasing that new worker did Runtime close and release its lease/marker. This proves settlement of a real preexisting new executor, rather than only the immediate no-executor close branch. The held job itself was a timing fixture, not a claimed codec transaction; the selected critical-publication test above supplies the real image mutation coverage.

**Final disposition: all three original P2 findings are closed at `dca4c55`; no blockers remain in this narrow UI/runtime re-review.** This reviewer did not run a full suite, build or installed executable; the director's 64-pass gate and root's 687-pass final suite are separate evidence, not included in the independent counts here. No frozen product, index, shared dependencies, original checkout, live user state, registry or user application was changed. Only this owned report and fresh owned verification artifacts were written; all helper runtimes/worker jobs settled and exited.
