# FileHub 0.2.1 final packaging

**Actual artifacts frozen; owned packaged acceptance passed.** Root independently reviews the final artifact using its separate audit. Build source `93bc94d57682eae4cc36f2af76192fcfb48dd45f`, managed filehub-rules worktree, branch feature/filehub-rules-020. No product/UI/self-test edits by this packaging task.

## Final files

| Worktree-relative artifact | Bytes | SHA256 |
| --- | ---: | --- |
| `dist/FileHub/FileHub.exe` | 2561670 | `dd0f250c50ff5c7d90a1b23101f97ff2c1d0e3620824c510acb52f54fb9fdbc6` |
| `dist/installer/FileHub-0.2.1-windows-x64-setup.exe` | 143130835 | `9268a5c324d311476bca00538321166d42b18f45bfb167442c45e70b7b544f07` |

Full base directory: `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`. `dist/artifacts.json` matches final values and also records the preserved0.2.0 installer. Portable use requires the whole `dist/FileHub/`.

## Executed gates

- Version inputs: pyproject/installer (all four existing PE directives)/version-info/verifier/manifest updated consistently0.2.1. Pinned-input verifier exit0, 228 files/four source ZIPs; previous pinned input changes limited to current license heading and version resource. `packaging-input-audit.json` is input-only evidence.
- Exact build: `& packaging/build.ps1 -ISCC 'F:/Hazel Windows/sandbox/tools/inno-6.7.3/{app}/ISCC.exe'` → exit0, Inno27.110s, no native-dependency WARNING/ERROR. Full log `docs/evidence/rules-021/packaging-build.log`. Existing normal optional platform imports remain the reviewed PyInstaller warnings; no new FileHub import failure.
- Actual `FileHub.exe --self-test --state-dir <owned UUID>/portable-state` → **exit0,21/21true,runtime_frozen=true,1.922s**. Absolute command and environment in `packaging-portable-selftest.json`. Child PATH contains only Windows/System32; Qt/PySide/Python developer overrides removed, hidden child with120s bound, new UUID sandbox `sandbox/packaging021-final-cf7591bae8184171948aca8d386303c2`. All owned child processes/executors settled. Source Python is only the launcher, not substituted application APIs.
- Actual self-test preserves ten original checks including bundled ffprobe64px plus distinct1920px video archive/naming/undo. Eleven existing0.2 checks cover real JPEG/PNG/WebP roundtrip/dimensions, alpha and ordinary native42B WebP decode, JPEG backgrounds, keep/undo, same-path/cross-extension true replacement with private full backup/ADS/times/undo, generic no-sync pre-three-day automatic rule/restart suppression, ordered copy→convert→move history/undo, fresh-disabled persisted import and persisted custom template route/undo.
- Read-only artifact audit exit0: **46/46FileHub PYZ code objects equal frozen source**, including all four changed UI modules; deployed pinned native/license/icon/self-test materials and four source archives match. Singleton qwebp at `_internal/PySide6/plugins/imageformats/qwebp.dll`, reviewed hash/native imports, unchanged isolated ffprobe, no encoder/OpenH264/ICU override/Mesa payload. Actual EXE and installer fixed0.2.1.0/text0.2.1 and every original warm-yellow ICO image byte verified. Evidence `packaging-artifact-audit.json`. Validated0.2 harness reused with new UUID/version/paths; no framework or product change.

Root's fresh UI review reported no blockers, and its unique full suite **713 passed in57.09s**. These are external source evidence, not repeated or represented as executable UI interactions here. Source native UI captures/regressions remain in ui-sol.md/ui-astra-review.md; packaged21checks verify real runtime functions. Root's independent final payload audit is separate.

## Scope and preservation

Owned metadata/docs: pyproject.toml; packaging/installer.iss, version-info.txt, verify-inputs.py, freeze-input-manifest.py; third_party/components.json; README.md; docs/使用说明.md, 第三方许可.md; new docs/交付说明-0.2.1.md; this report. New evidence under rules-021: packaging-input-audit.json, packaging-portable-selftest.json, packaging-artifact-audit.json, packaging-build.log. No filehub.spec/backend/UI/runtime/selftest changes. Historical0.2.0 reports/guide/evidence untouched. Director owns staging/commit.

Preserved0.2.0 installer143135555B SHA256 `a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735`. Original F0.1.1 installer SHA256 `bacd74379bc38e02d924f381aad8980f07bd738e68800668cc4b699f68d37f1a`. Original F checkout/junction runtime read-only. No pip/update/download, live installation/upgrade/uninstall, registry/user state/watch/sync mutation, user-program stop/shutdown, stage/commit or remote action. User upgrades themselves, preserving settings/history. Root owns any later delivery copy or shutdown; neither performed here.

Existing image/metadata/cancellation/backup-retention limitations remain in the guide. Windows10,clean VM,Mac/real dual-machine sync remain unverified. **Artifacts/source/docs frozen; no active owned process.**
