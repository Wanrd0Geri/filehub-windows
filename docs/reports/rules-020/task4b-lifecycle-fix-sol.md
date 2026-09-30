# Task4B lifecycle correction — Sol

Status: **owned production source/tests frozen for independent review**. The three
P2 findings in `root-ui-final-astra.md` are addressed. Final focused gate:
**64 passed in 18.63s, exit 0**. Worktree:
`C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`.

## Changes

1. Ordinary `Coordinator.submit` captures MainWindow's admitted service/state
   generation before enqueueing and verifies it on the worker before invoking
   the action. Transition/quit requests are rejected at admission; queued work
   cannot mutate a closed or replaced service. MainWindow applies this boundary
   to pause, settings, preview/execute, manual check, undo and archive opening;
   home/tray controls reflect it. Undo and integration callbacks capture their
   authority rather than using a later binding. Existing ordinary busy policy
   remains: demo cannot begin while an admitted ordinary write is pending.
   Explicit `lifecycle=True` bypasses are restricted to demo/recovery setup,
   final outcome/history reads and claim settlement/release.
2. Quit is monotonic across delayed demo success and same-state recovery.
   Rebinding while quitting keeps the new adapter nonaccepting and avoids executor
   and store loading or Scheduler creation. Runtime retires each newly bound service
   with Coordinator settlement accounting, then retains its lease/marker until
   ordinary work and the current adapter settle. Retirement initiation is tracked
   separately from admission: a fresh nonaccepting adapter still needs retirement.
   If quit wins before conversion settlement, demo creation is skipped and the
   actual in-progress critical publication safely finishes before exit.
3. Every scheduled tick owns a unique token. Success and error callbacks settle
   their own pending token before generation-based presentation suppression.
   Stale errors therefore permit the next check; stale callbacks cannot clear a
   newer check. Current errors retain their status/notification behavior.

Owned edits: `src/filehub/ui/{app.py (Runtime only),main_window.py,
automation_controller.py,coordinator.py}`, `tests/test_automation_ui.py`, and this
report. Packaging's separate self-test hook in `app.py` was preserved. No backend,
forms/style, archive-dialog implementation, packaging or dependency changes.

## RED / GREEN evidence

Original regression command (same existing runtime, worktree cwd, fresh sandbox):

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_ui.py -q -k 'transition_rejects or quit_during_demo_creation_or_recovery or stale_tick_error' --basetemp=sandbox/task4b-lifecycle-red1 | Tee-Object -FilePath sandbox/task4b-lifecycle-red1.txt
```

RED: **4 failed, 27 deselected in 1.09s**. Recorded old config writes occurred
after old lease release/demo activation; demo-success and recovery quit cases
remained open; stale tick error left `tick_pending=True`.

The same selection with `task4b-lifecycle-green1` first produced **2 failed,
2 passed, 2 teardown errors in 41.09s**. It exposed the fresh nonaccepting adapter's
retirement early-return; separating `_retirement_started` fixed that lifecycle
condition. One owned diagnostic test session was interrupted through its tool
session during investigation. No user process was touched.

The same selection with `--basetemp=sandbox/task4b-lifecycle-green2` and matching
Tee log then produced **4 passed, 27 deselected in 1.04s**.

Final command:

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_automation_ui.py tests/test_ui.py tests/test_app_runtime.py -q --basetemp=sandbox/task4b-lifecycle-focused1 --junitxml=sandbox/task4b-lifecycle-focused1.xml | Tee-Object -FilePath sandbox/task4b-lifecycle-focused1.txt
```

Result: **64 passed in 18.63s, exit 0**: 35 integrated automation UI cases,
10 existing UI cases and 19 existing app/runtime cases. Eight added lifecycle
cases cover transition rejection through direct/home/tray/settings/archive
routes; demo success/recovery quit; stale tick followed by another check;
admitted config write before old lease release; queued retired-write rejection;
current error notification/old-token isolation; and quit before a real critical
image commit, including output/history and lease/marker retention.

`git diff --check -- src/filehub/ui/app.py src/filehub/ui/automation_controller.py
src/filehub/ui/coordinator.py src/filehub/ui/main_window.py
tests/test_automation_ui.py tests/test_app_runtime.py` returned **exit 0**, no
whitespace errors (only standard LF-to-CRLF notices). No production/test edits
after this final gate.

## Boundaries

All tests use fresh owned sandbox state, real isolated services/leases and Qt
widgets, injected worker checkpoints/errors, and a fake marker/notifier/exit
callback. Failed RED teardown explicitly retired its stranded owned service only
after recording assertions; cleanup is not acceptance evidence. Existing `.venv`
junction was read-only; no pip, full suite, build/install, stage/commit, live app,
user state/registry/process operation, agent spawning or original checkout write.
No new visual work: previously accepted Task4B captures remain the layout evidence.
Root owns full-suite and packaging acceptance after this freeze.
