# FileHub 0.2.1 final acceptance

UI source is frozen at `93bc94d`. Independent Astra review found no blocking issue. The patch fixes local image drag/drop routing and copy-only append/deduplication, compact selected-file rows, clipped mode/format controls after keep/replace changes, disabled Start styling and the missing-output-folder message. No backend or conversion execution behavior changed.

Root final suite: **713 passed in 57.09s**, exit 0, after packaging metadata freeze. Corrected native scaling evidence asserts actual DPR 1/1.25/1.5/2, dark/light and both requested sizes after mode toggles (160 checks, 64 captures). The independent review additionally checked transition-time drops and shared form combinations.

The actual clean-environment 0.2.1 executable passed **21/21 self-tests**, exit 0, `runtime_frozen=true`. Both packaging and root independent artifact audits passed **46/46 current-source/PYZ comparisons**, all required materials/native imports/unique WebP plugin, exclusion checks, icons and 0.2.1.0 PE metadata. Existing 0.2.0 and original 0.1.1 installers retain their original hashes.

Final installer: `dist/installer/FileHub-0.2.1-windows-x64-setup.exe`, 143130835 bytes, SHA256 `9268a5c324d311476bca00538321166d42b18f45bfb167442c45e70b7b544f07`. Root copied it to `F:/FileHub交付/0.2.1/` and verified the same hash, with adjacent installation instructions. EXE SHA256: `dd0f250c50ff5c7d90a1b23101f97ff2c1d0e3620824c510acb52f54fb9fdbc6`.

All implementer-owned windows/services/workers/build/test processes have exited, reports and artifacts are saved. No live installation, user-state/registry mutation, user application termination, push or merge was performed. The user's separately authorized shutdown is reserved for root after final delivery; no subagent performs it.
