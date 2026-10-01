# Task 5 Astra stage review — runtime phase B

Verdict: **Approved for Task 6 packaging/isolated acceptance**, no open Critical/Important stage findings. This does not claim final installed-program acceptance or independent whole-branch release review.

Evidence: controller inspected the runtime/CLI, MainWindow and ArchiveDialog changes, config drive-root boundary, all 16 runtime fixtures plus prior 8 UI fixtures, implementer report, and actual Windows Qt `runtime-demo.png`, `runtime-settings.png`, `runtime-claimed-dialog.png` with runtime-state.txt. Controller final command `.venv/Scripts/python.exe -X utf8 -m pytest -q` returned **248 passed in 17.53s**; `git diff --check` returned exit 0 (normal LF/CRLF notices only).

Resolved review findings:

- Idle/generation gates and captured claim queue prevent an ordinary queue callback crossing an in-process demo switch; durable original pending requests remain in ordinary state. Concrete slow-demo RED became GREEN.
- ProgramInUse mutex starts before bootstrap/recovery and remains held through graceful worker completion. Startup and busy-quit tests inspect native mutex/instance lifetime.
- Existing native integration state is read before save; unknown state cannot silently become unchecked. Partial config/integration save refreshes actual flags and tray state.
- Root review identified sync disk root acceptance as unsafe for recursive global sanitation. Pure validation now rejects it with Chinese error, even with state on another volume; no real root scan occurred.
- Valid PNG replaces textual demo placeholder. GUI/service/scheduler/queue/lease ownership moves together and native integration stays disabled in demo. KnownFolder values only seed explicit selection dialogs and never activate monitoring.
- IPC display never acknowledges; explicit cancel or persisted execution does. Crash lease redelivery, execution exception preservation, secondary aggregation/reveal and pending quit are covered.

Clarification: initial controller suspicion that packaged ffprobe defaults depended on cwd was disproved by existing media.probe_width resource resolver. No core resolver rewrite was made. Source development default uses the licensed third_party probe through a runtime closure; custom setting and persisted logical default remain unchanged. A real arbitrary-cwd service video archive/undo test passes.

Remaining release gates: frozen executable and Chinese installer, native owned registry/Shell and upgrade/uninstall tests, clean child environment, cross-volume/whole-tree recycle evidence, novice documentation, and final independent Astra review. Mac execution, actual two-machine sync and fresh VM remain explicitly unverified unless later evidence is added.
