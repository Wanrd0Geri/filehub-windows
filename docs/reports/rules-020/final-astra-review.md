# FileHub 0.2.0 final acceptance

Product source frozen at `dca4c55`; packaging inputs/docs at `a5b8506` plus the final installer version-resource correction. No remaining Critical/Important findings. Independent core review closed the repeated same-path replacement issue; independent UI review closed all three reproduced lifecycle/error races, including real new-executor settlement before lease/marker release.

- Root final source suite: **687 passed in 61.14s**, exit 0. No source changes followed this gate.
- Root cross-volume source acceptance: C-state/F-data same-path and cross-extension replacement, full backup and restart undo passed both cases, including bytes/ADS/times and distinct volume identity.
- Actual frozen EXE in clean isolated environment: **21 checks passed**, exit 0, `runtime_frozen=true`. This retains ten legacy/video/archive checks and adds eleven image/rule/template/undo checks.
- Sol and root independent artifact audits: **46/46 filehub PYZ modules match current source**; required vendor/source/license/icon bytes match; unique pinned qwebp; no encoder, ICU or Mesa payload; EXE and installer PE versions are 0.2.0.0; artifact manifest matches actual files; original 0.1.1 installer unchanged.

Final installer: `dist/installer/FileHub-0.2.0-windows-x64-setup.exe`, 143135555 bytes, SHA256 `a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735`.

Final portable executable: `dist/FileHub/FileHub.exe`, 2558501 bytes, SHA256 `f6237d57897469f8cbb6898494e02df8e3b7c40e6109b99b7e64b682f9becab9`; the adjacent `_internal` payload is required.

The installer was built and inspected but never installed or uninstalled here. No user's live state, registry, watch/sync folders, running FileHub/Explorer or original checkout was modified. No merge/push performed. The user can close their existing app and run the new installer themselves. Automatic rules are opt-in, conversion defaults to retaining originals, and verified replacement backups remain retained.

Evidence: `root-final-pytest.txt/xml`, `root-cross-volume-replacement.json`, `task5-portable-selftest.json`, `task5-artifact-audit.json`, `root-final-artifact-audit.json` under `docs/evidence/rules-020`, with independent review reports under `docs/reports/rules-020`.
