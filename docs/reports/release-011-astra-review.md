# FileHub 0.1.1 bounded follow-up — Astra review

Scope: Explorer icon ownership, reusable recent preview commands, and whole-window footer readability. Base: `3f159740e7be97db0402006af39a1e6ce3e3efb2`. No engine, routing-rule, watch/sync or journal schema changes.

## Source and UI verdict

Approved for final combined packaging, with no open Critical/Important findings in the reviewed patch. Root independently ran the complete suite: **276 passed in 23.18s**, exit 0; output: [root-011-final-pytest.txt](../evidence/root-011-final-pytest.txt). The implementation agent's changed-area gate passed 44 tests after the final small-window layout fix.

- Runtime and installer register the quoted executable icon for both file and directory menu keys, reject conflicting existing icons, and preserve externally modified icon values during removal. The six new fake-registry cases cover both key types. No live user registry mutation was used for this patch.
- History is independently persisted in `tag-history.sqlite`, uses the serial worker and existing process lock, trims accepted preview commands, preserves exact-string distinctions, has no arbitrary item cap, and shares one controller between the main window and archive dialog. Tests cover restart, 57 retained entries, invalid/empty/typing exclusion, independent deletion/clear, worker I/O, and demo isolation.
- Same-value chip clicks explicitly invalidate the prior preview. Generation/service checks suppress stale preview delivery; deletion/clear revision tokens stop in-flight old previews from repopulating history. Storage failures remain visible while preserving a valid executable preview.
- Footer retains QStatusBar ownership, theme-aware sidebar background and border, padding, selectable wrapped text, and a 144-logical-pixel cap with vertical scrolling. Small-home layout initially compressed controls; a narrow home-only scroll wrapper and input/preview minimum heights resolved the observed clipping.
- Native Windows evidence uses an isolated demo state at DPR 1.5. Controller and root inspected small/default dark/light views, archive dialog, settings footer, and long-message overflow. The final crowded home contains a selected file, 59 commands, three recent batches, and a 4,559-character footer; separate scroll positions prove access to chips and all three recent rows. Relevant evidence: [chips and long footer](../evidence/ui/history-011-small-history-long-footer-dark.png), [recent rows and long footer](../evidence/ui/history-011-small-recent-long-footer-dark.png), and [native state](../evidence/ui/history-011-native-state.txt). System-theme behavior uses the existing dynamic theme path; native screenshots are not a claim of exhaustive physical DPI/device coverage.

## Release boundary

The earlier icon-only 0.1.1 diagnostic build is superseded only by the forthcoming combined build. Final artifact hashes, portable ten-check self-test and installer/resource verification belong in the packaging report. The real user's installed 0.1.0, application process, state, watched folders and registry were not changed by this patch QA. Upgrade requires the user to exit the old tray application and run the new installer with the Explorer menu option enabled. Existing 0.1.0 acceptance remains historical evidence, not a claim that its installation/uninstallation matrix was repeated for 0.1.1.

## Final artifact verdict

Root independently verified the final combined archive against current source: all five packaged history/footer/main-window/archive-dialog code objects equal freshly compiled source. This specifically excludes delivery of the earlier icon-only diagnostic build. Evidence: [artifact audit](../evidence/root-011-artifact-audit.json).

- Installer: `dist/installer/FileHub-0.1.1-windows-x64-setup.exe`, 139,814,259 bytes; SHA-256 `bacd74379bc38e02d924f381aad8980f07bd738e68800668cc4b699f68d37f1a`.
- Portable executable: SHA-256 `ff8a4183bbbe44bba023d1d36ae5b77afd6c2491adba6602990169e31cc17963`.
- The existing 0.1.0 installer retains SHA-256 `0de7a4cf0c246087318a60c9f77c782c1d05d684bc6d6ea22b7cc39efcb422f8`.

The packaging evidence confirms Inno compilation success (24.375s), isolated portable self-test exit 0 with all ten checks true, the existing warm-yellow icon's exact embedded PNG match at 256×256, and installer ProductVersion 0.1.1. See [portable self-test](../evidence/packaging-011/portable-selftest.json) and [packaging audit](../evidence/packaging-011/artifact-audit.json). Root independently inspected the same evidence and artifacts. **Final verdict: approved for local 0.1.1 delivery, zero open Critical/Important findings in this follow-up scope.** No remote push or merge.
