# FileHub 0.2.2 source review

Scope: image conversion collision numbering, the two settings day spin buttons, and global scrollbar appearance. Astra directed and reviewed explicit GPT-6.1 Sol implementation. No sharing, project registration, AI rule generation, or import workflow changes.

The former standalone preview rejected an occupied target and reserved names before image inspection succeeded. Rule conversion delegated directly to generic collision rejection. The new conversion-only allocator selects an exact free name during preview, uses the maximum matching final hyphen-number suffix, preserves padding and source spelling, and includes casefolded disk entries and batch reservations. It leaves available names unchanged. Original-path replacement remains replacement with private backup and undo; execution still rejects late occupancy rather than reallocating. Generic publication, journal and path security were not relaxed. Failed standalone inspection now leaves no target reservation.

Review included standalone/rule integration, selected-source and intermediate reservations, virtual same-format replacement, failed-plan rollback of reservations, original-content protection, and execution against the frozen preview. Root caught a Unicode family casefold mismatch (Straße versus STRASSE); Sol fixed it with a regression before freeze. No remaining blocking finding in this bounded change.

Evidence read: backend targeted GREEN 94 passed in 10.68 seconds; RED reproducer bypassed the allocator to exercise the former occupied-target rejection without editing the shared sources. Real codec execution/backup/undo, late occupancy, keep and replace semantics are covered. Existing executable self-test retains all 21 checks and adds two collision checks. These are source test results; packaged acceptance and root's final suite remain separate release gates.

UI diff is limited to two NoButtons settings controls, native scrollbar stylesheet rules including status-footer specificity, and short shared conversion help. Native owned-window evidence covers dark/light themes, actual DPR 1 and 2, typed day values, bounds 1–365, keyboard, wheel and thumb drag; quality spin buttons remain. Astra inspected dark settings DPR 1 and light conversion DPR 2 raster captures directly. Existing conversion UI tests: 26 passed in 2.59 seconds. This does not claim installed-program mouse testing.

Version inputs and pinned manifest are consistently 0.2.2 / PE 0.2.2.0. Input verification passed; only current license heading and version-resource hashes changed among pinned files. Existing 0.2.1 and 0.2.0 installer hashes were preserved. Final build is authorized after the source-freeze commit; root owns the single final suite, independent packaged audit and delivery copy.

No live installation, registry, user state/watch paths, existing process stops, dependency updates, remote Git operations, or shutdown occurred.
