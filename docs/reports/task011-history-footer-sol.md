# FileHub 0.1.1 reusable tag history and status footer — frozen Sol handoff

Scope completed: valid preview tags persist per state in `tag-history.sqlite`, with exact trimmed deduplication and durable AUTOINCREMENT ordering. Construction is lazy and free of filesystem I/O; load, remember, delete and clear run on the existing single Coordinator worker under the engine's existing per-state `process_lock.acquire()`. Connections commit/rollback and explicitly close. The action journal schema and source files are unaffected by history deletion.

Main window and every opened archive dialog share one HistoryController. Chips fill the field and invalidate preview, including clicking the same value; they never execute a move. Separate × buttons delete one entry; “清空全部” deletes history only. History is unbounded and horizontally scrollable; long labels are elided visually with full tooltips/accessibility names. Empty history hides its strip. I/O errors remain visible in the strip without discarding an otherwise valid preview.

Preview callbacks capture immutable service, input, editor generation and history state/revision. Only current previews containing a valid item enqueue remember. State switching clears visible history and rejects old load/mutation deliveries; normal/demo stores are independent. Delete/clear intent increments history revision immediately, so a pending older valid preview cannot recreate deleted history. Queued remember also checks that revision before writing. Shared Coordinator busy signals remain the sole busy mechanism.

Status remains a QStatusBar with a distinct theme-aware surface, one-pixel top border, disabled size grip and 16px/8px text padding. The selectable label keeps the exact full message and tooltip; messages wrap and scroll within at most 144 logical pixels. Empty messages leave no tall panel. Native evidence exposed existing home-layout compression at 800×620 with tags and three records. A home-only QScrollArea plus minimum input/preview heights now preserves all controls and lets the user scroll to records; the existing settings scroll was not changed.

Owned product files: `src/filehub/tag_history.py`, `src/filehub/ui/tag_history.py`, `src/filehub/ui/status_footer.py`, and local edits to `main_window.py`, `archive_dialog.py`, `theme.py`. Owned validation/evidence: `tests/test_tag_history.py`, `docs/evidence/ui/render_history_011.py`, `docs/evidence/ui/history-011-*`, and this report. No integration, engine, rules, config schema, app runtime, packaging or resource files were edited by this agent. No staging, commit, build, installer, uninstall, process termination, Explorer restart or real user state/registry operation was performed.

RED/GREEN evidence:

- Inherited initial RED: `sandbox/task611-history-red.txt`, missing `filehub.tag_history`.
- New combined RED: `--basetemp sandbox/task011-history-red2`, missing UI history and footer behavior (11 failures).
- First GREEN: history tests, 11 passed in 1.87s.
- Same-value chip RED: `sandbox/task011-history-red-click`, 2 failures and 12 passed. Fixed by explicit preview invalidation.
- Small home RED: `sandbox/task011-history-small-red`, expected scroll-safe readable controls missing.
- Final focused command: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_tag_history.py tests/test_ui.py tests/test_app_runtime.py -q --basetemp sandbox/task011-history-focused-green2` — **44 passed in 7.48s**. Coverage includes 57-item persistence/restart/dedup/order, current/invalid/empty/stale preview, shared delete/clear with byte-identical journal and preserved source, same-value click, error preservation, worker execution, demo and stale delivery isolation, in-flight delete intent, long footer scrolling and small-window overflow. Full repository suite is delegated to controller, as explicitly required for this parallel handoff.

Native evidence uses Windows Qt, actual DPR 1.5, new owned fixtures only under `sandbox/task011-history-native/demo/<uuid>/`. `render_history_011.py` creates three real fixture archive records and retains a selected original PNG; screenshots have 59 history entries. No Runtime/registry hook is instantiated. Reproduction: set PYTHONPATH to workspace `src`, QT_QPA_PLATFORM to `windows`, then run workspace `.venv/Scripts/python.exe -X utf8 docs/evidence/ui/render_history_011.py`.

Evidence in `F:/Hazel Windows/docs/evidence/ui/`:

- `history-011-dark-1000x700.png`, `history-011-dark-800x620.png`, and corresponding light variants.
- `history-011-dialog-dark.png`, `history-011-dialog-light.png`.
- `history-011-settings-footer-dark.png`, `history-011-settings-footer-light.png`.
- `history-011-small-history-long-footer-dark.png` and light variant: selected file, overflowing tag strip and long status together.
- `history-011-small-recent-long-footer-dark.png` and light variant: same small window/state scrolled to all three recent records while long status remains accessible.
- `history-011-long-footer-dark.png`, light variant, and `history-011-native-state.txt`: exact rendered message retains 4559 characters, footer height 144, vertical scroll maximum 1323.

Visually inspected dark/light home, small overflowing tag strip, archive dialog, settings footer and long footer. Input/chip/preview text no longer suffers layout compression. All owned test/render commands have exited; there are no active sessions launched by this agent. Product code is now frozen for controller review and the other Sol's final combined build/portable checks.
