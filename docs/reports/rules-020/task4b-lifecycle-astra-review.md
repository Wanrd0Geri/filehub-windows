# Lifecycle delta and frozen acceptance hook — Astra review

Root independent review reopened three P2 lifecycle issues after the earlier 4B gate: retired old-state writes during delayed demo creation, quit stranded by success/recovery rebind, and stale scheduler errors retaining tick_pending. The original stage approval did not cover these reproduced interleavings.

Reviewed the correction: normal Coordinator work captures service/state authority at admission and verifies it again at worker entry; mutation entry points reject transition work. Lifecycle bypasses are explicit and limited to settlement, demo/recovery, claim release and history reads. Quit intent survives rebind; nonaccepting and retirement-started are separate states so a newly bound service still settles before lease/marker release. Scheduler completions settle only their own request token before stale presentation suppression.

Sol reproduced four failures before the change and four direct passes after. Director focused gate: `.venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_automation_ui.py tests/test_ui.py tests/test_app_runtime.py -q --basetemp=sandbox/astra020-lifecycle-review -p no:cacheprovider` — **64 passed in 18.80s**. Sol same-file gate: **64 passed in 18.63s**. No open finding in director delta review; root independent reproduction rerun remains required.

Also reviewed the separately owned, frozen selftest020 helper and two-line app self_test hook. It adds eleven real API/codec checks to the ten existing checks inside a fresh child of the explicit self-test UUID. Director focused hook gate: **4 passed, 17 deselected in 6.78s**. Root independent static hook review reports no blocker. These are source checks only; packaged executable acceptance remains pending.
