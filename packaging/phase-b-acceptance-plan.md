# Phase B execution checklist — prepared, not executed

Start only after controller confirms reviewed runtime is stable and releases the build gate. No pip changes or Git staging while other writers/tests run. Fixed version 0.1.0. Existing phase A manifest stays fixed until a reviewed build-input change requires an explicit refresh.

## 1. Build once, inventory before install

1. Run fixed-input verifier, then `packaging/build.ps1`; save complete PyInstaller/Inno output and inspect every warning. Preserve executable, installer and payload SHA256/version inventory. Ensure no repository/reference/test/sandbox sweep, duplicate ffprobe payload or unsupported Qt addon plugins.
2. Inspect imports of every runtime PE using installed pefile or MSVC dumpbin. Resolve vendor DLLs within payload; do not count system-installed MSVCP/VCRUNTIME as proof they will exist on end-user PCs. Include legally redistributable copies as needed; retain Microsoft notice/source. Windows system/API-set imports are reported separately. Confirm Qt Windows plugin and source/license payload.
3. Run final full suite once on stable inputs and retain command/results. Later fixes get focused tests, impacted acceptance and required rebuilt artifacts rather than repeated whole-suite loops.

## 2. Owned process environment and install scope

- Create new UUID-owned QA directory under `F:/Hazel Windows/sandbox/task6-acceptance/`; state, fake sync/watch, cwd, screenshots, journal snapshots and evidence all stay there. Program target remains `F:/Hazel Windows/sandbox/installed`; reject a preexisting unowned target rather than remove it.
- Launch application tests from a separate sandbox cwd outside source/install. Remove inherited PYTHONPATH/PYTHONHOME/VIRTUAL_ENV and Qt/PySide development overrides. Child PATH only Windows/System32 and Windows; child LOCALAPPDATA redirected to the owned QA directory for no-argument launch/demo shortcut tests. Never change global environment.
- Save native environment build/architecture evidence; distinguish process-isolated Windows from untested fresh VM. Current known Windows11 build26200 is not evidence for Windows10.
- Preflight owned registry/shortcut paths: absent or exact previously captured QA owner only. No real Desktop shortcut task. Actual Start menu shortcut test uses a new uniquely named `FileHub-QA-<uuid>` group; record native path and cleanup. Installer initially has context/autostart tasks disabled and never auto-launches.

## 3. Startup, actual demo shortcut and busy lifecycle

1. Silent install `/CURRENTUSER /DIR=<owned installed> /GROUP=<unique QA group>` with optional registration tasks off; save installer log, exit code, installed file inventory.
2. Headless `FileHub.exe --self-test --state-dir <QAparent>`: require exit0 and schema1 `self-test.json` with all checks true, UUID fixture/state child, actual bundled probe path and width64. GUI executable stdout may be absent; JSON file is authoritative.
3. No-argument executable launch equivalent in isolated child LOCALAPPDATA: show unconfigured/paused first-run native Qt window; capture Chinese UI. Verify absence of real folder configuration, accidental watch mutations or ordinary user state.
4. Read actual normal/demo `.lnk` target/arguments through WScript.Shell. Launch demo shortcut equivalent with its exact `--demo` arguments in isolated child environment; archive/undo fake PNG and verify normal state remains unconfigured. Capture native demo/main/history/settings screenshots.
5. With primary GUI active, test installer upgrade and uninstaller refuse while `Local\\FileHub.Windows.v1.ProgramInUse` exists, with Chinese graceful-quit instruction. Quit through application/tray, wait for coordinator and process exit, then retry successfully. No forced kill. Capture pause/resume/background timer and close-to-tray/quit evidence through runtime/native Qt harness; do not label offscreen assertions native screenshots.

## 4. Original ten cases (fake folders only)

| Case | Planned check and evidence classification |
| --- | --- |
| 1 | Generate two distinct 1920-wide short valid videos under fake watch, capture source creation time/timezone at preview. Installed service/probe → `LYX020822` → exact first `_01_<dateAM/PM>_1080p.mp4`, second distinct-content `_02`. Record real native probe + installed archive; any registry dispatch simulation is labeled separately. |
| 2 | Two-shot `LYX020815+20` copy+move; three-shot `LYX020815+16+17` one output and visible notice; restart and unified undo, root summaries distinct from typed action rows. |
| 3 | Real valid PNG → exact `E02S08_C022_<date>-1.png`; captured planned date remains fixed. |
| 4 | `LYX苏云法相`, `LYX破败庠序`, `LYX角色新角色`, `LYXPV决战`: exact asset/PV routing/filename fixtures against read-only Mac rule baseline; no original Mac execution. |
| 5 | Invalid code keeps source bytes/path, inline error and once-per-unchanged issue notification; edit/correct permits retry. |
| 6 | Existing matching primary content within project prevents second copy, native recycle result points to existing project survivor, manual restore boundary and exact recycle staging name shown. |
| 7 | Legal Windows basenames with math/emoji get expected explicit global-job sanitation; literal `|` cannot be created on Windows, therefore that particular illegal-character rule fixture remains simulated rather than claimed filesystem-native. Preserve approved normal asset naming. |
| 8 | First seen persisted gives full three-day grace despite old creation/mtime. Scheduler tick uses controlled clock (simulated time); native fake filesystem operations separately recorded. Advanced global jobs off is no shared cleanup; on expires owned inbox date tree as one native recycle item. |
| 9 | Typed unified journal survives restart, records forward/undo/partial errors; copies and moves independently protected; manual recycle restoration clearly disclosed. |
| 10 | Mac execution and real dual-machine Baidu sync explicitly 未验证. Windows source-derived fixture equality is evidence only for Windows rules, not two-machine parity. |

## 5. Required safety boundaries

- Existing target/occupied undo origin preserved; invalid/traversal/device/overlong input rejected without truncation; changed/locked/download-temp source skipped. ADS, timestamps and survivor safety use approved native core tests and installed service evidence where applicable.
- Copy undo refuses sole-survivor deletion and edited/replaced output; first-arrival/restart grace and paused/default-global boundaries; inbox directory handling and named hidden residuals. Crash injection and recycle-failure injection remain **模拟** with exact test reference, never represented as real power-loss or filesystem recycle failure.
- True cross-volume: choose a **new** `C:/FileHub-Task6-CrossVolume-<uuid>` only after verifying it does not exist; write an ownership sentinel and record exact path. Archive C→F and undo F→C with hashes/ADS/timestamps as applicable, preserving survivor/conflict cases. No enumeration/deletion of existing temp content. Cleanup only captured newly created files/directories, or leave fixtures with recorded path if safe cleanup cannot be proven.

## 6. Native registration, Shell dispatch and aggregation

1. Snapshot exact HKCU context/Run values and reject collision with any unrelated preexisting owner. Test optional installer registration only for absent/owned FileHub entries; verify quoted installed executable command, Player multi-select model and optional background Run command. Restore/remove only unchanged captured QA values, preserving deliberate foreign-modification fixture.
2. Native Shell single-file dispatch uses one self-created file and a uniquely owned QA verb whose command includes explicit `--state-dir <QAstate>`. Enumerate its exact `送进项目…` verb via Shell.Application; invoke only that owned verb and require installed IPC/dialog receipt. Label **native Shell single-file**, not Explorer mouse selection.
3. More than15 independent installed `--state-dir <QAstate> --send <owned path>` processes: durable persistence, settled aggregation, one dialog/batch, no duplicate/missing selection, restart/unacked delivery. Label **multi-process dispatch/aggregation**, not Explorer mouse multi-select unless real UI evidence exists.
4. Toggle login startup on/off and check only owned Run value; installation checkbox alone is not GUI toggle verification. Test removal when command/Run changed by controlled QA fixture; foreign replacement remains. Restore fixture changes and clean only exact ownership entries.

## 7. Upgrade/uninstall preservation and delivery

1. Before upgrade, gracefully quit. Snapshot settings/journal/history IDs and hashes of fake project/source files. Reinstall same controlled program path, launch with same independent state and verify state/history remain and no watch starts automatically.
2. Gracefully quit; uninstall and verify only program/owned shortcut/integration removal. State/journal/history and fake project/source content must survive. Preserve logs and final installer/portable artifacts outside installed target.
3. Write Chinese novice README/usage and acceptance table from actual evidence. Every row states Windows实测 / 模拟 / 未验证, exact command/test and result. Include source naming fixed at preview, creation-time sync caveat, computer-off timing caveat, global jobs default off, three-day grace, same-shot single writer, manual recycle restore and post-uninstall state location.
4. Independent Astra review → focused fixes/review → rebuild if any input changed → impacted acceptance → scoped Git-index window. Deliver exact0.1.0 installer/portable path, SHA256 and source/license materials, without push/merge.
