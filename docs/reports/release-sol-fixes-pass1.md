# Sol scoped fixes for independent review pass 1

Read and checked `release-astra-review-pass1.md`. Only operations directory-undo boundary, MainWindow result/history presentation and their tests changed; no schema, deduplication rule, runtime app, packaging, config or scheduler edits.

## Directory inverse boundary

Every TreeFingerprint root with a committed child enters the root gate before the reversed child loop. A root that did not commit and has no proven owned move inverse blocks the whole descendant group, persists that refusal and identifies staging/target for manual recovery. It never merges into a newly occupied original root or removes the captured staging contents. Committed move roots and owned interrupted inverse roots retain existing `prepare_move_inverse` identity checks/pinning and restart semantics. Committed copy roots verify both original survivor tree and target before child removal. Native recycled/manual/unknown tree outcomes keep their established manual-only child block and root messages.

New isolated regressions exercise failed whole-tree recycle and partially completed move (external target arrival), followed by external recreation/occupation of the original root. Both assert original external bytes unchanged, no captured child inserted there, staging/target captured bytes preserved, committed child states retained on repeated undo and full manual recovery location exposed. Existing owned inverse restart, native/manual recovery and source/target race tests remain in the green matrix.

## Duplicate result presentation

MainWindow shares a duplicate detail formatter between immediate actual-result status and persisted history details. It states the duplicate source, same-content reason and full existing-copy path. A recorded recycled/manual-restoration source is identified as 来源已回收; other recorded states explicitly say 来源回收未完成 and request source/staging/bin inspection. Existing recycle identity/name/manual-restore details remain. No notification/runtime changes were needed; archive-dialog completion already invokes MainWindow.show_result.

Two real Qt regressions use FileHubService with an isolated fake recycle adapter for successful and failed recycle, assert persisted duplicate path and both immediate/history texts, and verify the existing copy remains intact plus actual source outcome.

## RED/GREEN evidence

- RED `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_directories.py tests/test_ui.py -k 'conflicted_tree_undo or duplicate_result' --basetemp=sandbox/review-fixes-red`: **4 failed, 32 deselected in 0.75s**. Directory children merged into external source roots; both UI results omitted duplication/path.
- First expanded run caught two existing manual-only tree recycling regressions caused by the new root gate also seeing already blocked committed children. The gate now continues after establishing that pre-existing manual-only block, preserving recycled/manual/unknown behavior.
- Final focused matrix `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_directories.py tests/test_operations.py tests/test_ui.py --basetemp=sandbox/review-fixes-final-green`: **93 passed in 8.71s**.

Files frozen for controller diff review and independent scoped re-review. No full repository run, Git index change or commit performed in this fix phase.
