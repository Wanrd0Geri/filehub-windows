# Task5 — FileHub 0.2.0 final packaging

**Complete and frozen.** Actual packaged EXE acceptance and director/root independent artifact audit passed. No product or output changes after freeze.

Build HEAD `a5b8506eee5492a9377a8c215a10dffe4fd0f983`; product source `dca4c55` unchanged. Worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`, branch `feature/filehub-rules-020`. Root's unique source suite **687 passed in 61.14s** and resolved UI review are external evidence, not repeated by packaging.

## Final artifacts

| Artifact relative to worktree | Bytes | SHA256 |
| --- | ---: | --- |
| `dist/FileHub/FileHub.exe` | 2558501 | `f6237d57897469f8cbb6898494e02df8e3b7c40e6109b99b7e64b682f9becab9` |
| `dist/installer/FileHub-0.2.0-windows-x64-setup.exe` | 143135555 | `a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735` |

`dist/artifacts.json` contains these final values. Both actual PE files have fixed version 0.2.0.0, text version 0.2.0 and every original warm-yellow ICO image byte. Portable use requires the whole `dist/FileHub/` directory.

## Executed acceptance

- Exact build: `& packaging/build.ps1 -ISCC 'F:/Hazel Windows/sandbox/tools/inno-6.7.3/{app}/ISCC.exe'` → exit 0; initial Inno compile 30.156s. Full log `docs/evidence/rules-020/task5-build.log`.
- Actual `dist/FileHub/FileHub.exe --self-test --state-dir sandbox/packaging020-final-1b1d51c9b70a44e6b2f43c454ec9a80e/portable-state` (absolute command in evidence) → **exit 0, 21/21 checks true, runtime_frozen=true, 2.141s**. New UUID fixtures/state, Windows-only child PATH, Qt/PySide/Python developer overrides cleared, hidden child and 120s bound. Actual bundled ffprobe path verified. Evidence `task5-portable-selftest.json`.
- Real JPEG→PNG→WebP roundtrip, unchanged dimensions; alpha-preserving PNG/WebP, ordinary native decode of 42-byte transparent WebP; JPEG white/black/custom backgrounds; fingerprint-bound keep/undo; cross-extension and same-path true replace with private durable backup, ADS/times verification and undo; generic fresh automatic copy without syncroot before legacy three-day gate and restart suppression; copy→convert→move journal/history/undo; fresh-disabled persisted import; custom persisted template route/undo. The original ten checks include two distinct real 1920px video archives/naming/undo and 64px probe.
- Owned read-only audit → **46/46 FileHub PYZ code objects equal current source**, all deployed pinned materials and four source ZIPs match; actual native imports, unique qwebp path/hash, ffprobe uniqueness, icon/version and exclusions pass. Evidence `task5-artifact-audit.json`.
- Root independently confirmed source/PYZ, all materials/icon, PE version, unique qwebp, exclusions/manifest and original installer preservation in `root-final-artifact-audit.json`. This is root-owned evidence.

The first installer had ProductVersion text 0.2.0 but blank FileVersion / fixed 0.0.0.0. Director authorized only four explicit Inno version directives, then installer-only compile using the same ISCC → exit 0, 26.750s; log `task5-installer-metadata.log`. Initial installer SHA256 `b53f28a693db4a9812ef10bf5aa97da418955ec4f7591b5ddb5e984886b91415`; final above. EXE/source/payload never changed, so actual EXE acceptance remained valid. No further rebuild. Normal optional Unix/platform/multiprocessing import entries in PyInstaller warn-filehub.txt were reviewed; no missing FileHub module or unresolved native-dependency warning.

## Inputs and staged source validation

228 fixed inputs / four corresponding-source ZIPs. qwebp564536B SHA256 `6b2c53cc4423140c29a6a1eb6dd908016e09d794b5739a05a3a39c8c49a0df8a`, matching PySide6_Essentials6.11.2 wheel RECORD. QtImageFormats6.11.2 full ZIP3041992B SHA256 `a0003652945eeafc8bc28cc639f5941350fe27e91236908306d4733b703a23b5`; LGPL3 plus libwebp1.6.0 BSD3 COPYING/AUTHORS/PATENTS retained verbatim. qwebp is only at `_internal/PySide6/plugins/imageformats`; it imports existing Qt Core/Gui, VC runtime and Windows APIs. No new encoder/OpenH264/ICU override/Mesa payload; old ffprobe unchanged.

Phase A owned changes: README.md, pyproject.toml, packaging/filehub.spec, installer.iss, version-info.txt, freeze-input-manifest.py, verify-inputs.py, third_party/components.json, docs/第三方许可.md, 使用说明.md, 交付说明-0.2.0.md, this report and task5-input-audit.json. Missing historical scratch import JSON was replaced by preserving the checked frozen ffprobe manifest and inspecting actual binary imports. Every old pinned input except the intentionally updated notice stayed byte-identical. Initial and final input verifiers passed; final audit evidence explicitly means inputs only.

B1 added only src/filehub/selftest020.py, two import/call lines in app.py:self_test, tests/test_selftest020.py. No Runtime/controller/backend/test_app_runtime edit. RED2 expected failures preceded GREEN2. Final command `.venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_selftest020.py tests/test_app_runtime.py -q -k selftest --basetemp=sandbox/task5-hook-final-3e42a35ba77c42899dcb25e14e7825d3 -p no:cacheprovider` → **4 passed,17 deselected in6.28s,exit0**. Failure injection proves new-hook errors produce exit1/error JSON despite ten historical successes. `task5-source-selftest.json` is explicitly source-only, distinct from packaged acceptance. All owned workers settled; owned final diff check passed.

Final new tracked evidence: task5-artifact-audit.json, task5-portable-selftest.json, task5-build.log and task5-installer-metadata.log; final changed files after prior packaging commit: installer.iss, this report, 交付说明-0.2.0.md. Root-owned evidence/reports/ledger are excluded from implementer ownership.

## Delivery boundary

Original `F:/Hazel Windows/dist/installer/FileHub-0.1.1-windows-x64-setup.exe` remains SHA256 `bacd74379bc38e02d924f381aad8980f07bd738e68800668cc4b699f68d37f1a`. Original checkout and junction .venv read-only; no pip/install/update, live installation/upgrade/uninstall, actual FileHub/Explorer stop, registry/user state/watch/sync mutation, stage/commit or remote action. User closes old FileHub and runs installer themselves; existing settings/history remain. New/copied/imported rules require opt-in. Replacement defaults to keep; explicit replacement retains backups with no automatic cleanup. Codec cancel waits for current native call; metadata fidelity/RAW/HDR/animation/video conversion unsupported. Windows10/full clean VM/Mac/real dual-machine sync unverified. Historical0.1 install/uninstall evidence and root cross-volume source tests remain separate from actual0.2 portable acceptance.

**All outputs frozen. No active owned process remains.**
