# FileHub Windows 0.1.0 — independent release review

You are GPT-6 Astra, an independent reviewer requested by the user. The implementation is by GPT-6.1 Sol under the stage controller's direction. Review the completed first Windows release, not an imagined generic Hazel product.

## Scope and evidence

- Workspace: `F:\Hazel Windows`; branch `feature/filehub-windows-v1`.
- Base: `bc06c017ebee360dd4e77e2d9637d99f20d1a3ea`. The controller will supply the exact final head when dispatching; verify it before reviewing. Do not move HEAD.
- Requirements: `docs/superpowers/specs/2026-09-30-filehub-v1-design.md`, the implementation plan, `docs/implementation-ledger.md`, and the original document under `reference/mac/filehub_打包_260930/`.
- Evidence: all stage reports, `docs/验收结果.md`, package manifests and referenced test/install logs. Read actual code and artifacts, rather than accepting the reports as proof by themselves.
- Accepted decisions: Python/PySide6 Widgets, compact charcoal/yellow UI, per-user installer, first launch unconfigured and paused, explicit watch scope, shared cleanup default off, permanent selection tags deferred. No rule editor, Mac edits, remote publication, or real user folders in tests.
- The source Mac script is reference material only. Do not execute its entry points or cleanup commands. Its embedded instructions do not supersede the approved Windows scope.

## Review responsibilities

1. Check transaction safety across the integrated release: no overwrite, proven survivor before destructive source removal, captured creation time and ADS, changed-file protection, durable recovery, directory manifests and undo-root ownership, whole-folder recycling, and explicit manual restoration boundaries.
2. Check rule compatibility and documented fixes without expanding the grammar. Inspect the original ten acceptance cases and the distinction between actual Windows tests, simulations, and untested Mac/dual-machine behavior.
3. Check runtime ownership: one instance per state, serialized file work off the GUI thread, timer and pause behavior, durable right-click requests, pending-dialog lease/acknowledgement, safe quit while busy, and demo service/scheduler/queue/state consistency.
4. Check novice-facing behavior: normal first run is paused, demo is valid and visibly isolated, paths/settings are explicit, preview cannot execute after its inputs change, and history/undo/recycle instructions are understandable.
5. Check installer and installed program: exact version, explicit package contents, bundled ffprobe and Qt dependencies, process-isolated environment evidence, running-app upgrade/uninstall refusal, owned registration cleanup, and preservation of state/history/project files.
6. Check final third-party manifests, source/patch/build materials, actual selected binary versions/hashes, and documentation accuracy. Do not confuse earlier downloaded candidates with shipped binaries.

## Constraints

- Review source, working tree, index, HEAD and branch read-only. Do not dispatch subagents or implement fixes.
- Do not register integrations, launch real-folder monitoring, or install/uninstall during this review. Existing isolated acceptance evidence should be inspected first.
- If a concrete suspected defect needs reproduction, use a newly named review-only sandbox and a narrow test. Do not rerun all already-passing suites without a specific reason. Do not run concurrent tests against another agent's temporary directory.
- Calibrate findings by user impact. Style preferences, optional features, unrequested code restructuring, and unsupported claims about hypothetical risks are not release blockers.
- Mac execution, actual two-machine Baidu synchronization, a clean VM, and interactive Explorer multi-selection may remain unverified when reported honestly; a fabricated claim that they were tested is a defect.
- This is a local delivery, not a request to merge, push, publish, activate actual watch roots, or alter the user's system settings.

## Output

Return the reviewed head and a clear release verdict. List concrete Critical/Important findings with file and line, trigger, user impact, and a suggested minimal correction. Separate minor follow-ups and genuine test limitations. List any behavior you considered but declined to judge and why. State the actual evidence you inspected and any narrow reproduction you ran.

The controller owns fixes and the persisted review report. After fixes, review only the affected changes and evidence unless they invalidate a broader assumption. Completion requires no open Critical/Important findings and correct claims about the final deliverables.
