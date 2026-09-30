# FileHub 0.2.1 — narrow image-page correction

Status: **UI source and regression tests frozen for independent review**.
Dispatch baseline `ad333d174d234d60a1eba22d942ebf93bae42123`, branch
`feature/filehub-rules-020`, managed worktree
`C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`.
Final focused source gate **103 passed in 11.03s, exit 0**; native Windows
regressions **26 passed in 4.29s, exit 0**. Full-suite integration remains the
root's serial gate, not a claim made by this report.

## Exact ownership

Modified `src/filehub/ui/conversion_page.py`, `action_editor.py`, `theme.py`,
and the conversion-only drag routing in `main_window.py`; added
`tests/test_conversion_ui021.py` and this report. The scope brief is root-owned.
All exploratory helpers, test state, logs and rendered pixels are under the
new owned `sandbox/ui021-sol-9b616f75/` directory. No backend, codec,
publication, journal, version/build metadata, dependency, installer, original
F: checkout, live application/state, watch/sync directory, registry, stage,
commit, push, process termination or shutdown was modified. Existing `.venv`
junction was only used through `.venv/Scripts/python.exe -B -X utf8`.
No subagents were spawned. Owned Qt windows, worker executors and services
were retired and closed before helper exit.

## Root causes and minimum remedies

1. ConversionPage registered no drop targets. Native list/table viewports and
   QLineEdit can handle their own events; MainWindow accepted local URLs and
   unconditionally changed archive selection and navigated to page 0. The page
   now handles DragEnter/DragMove/Drop on itself and its existing child widgets,
   including both viewports and editable output fields. MainWindow delegates
   those three events only when the conversion page is current. Ordinary
   archive drop behavior remains as before. Admission checks page busy state
   plus MainWindow's existing state/quit authority. Drop changes selection once,
   invalidates the token/results once, and emits no preview or execution intent.
2. Drops append local `.jpg/.jpeg/.png/.webp` files and deduplicate with Windows
   case and separator normalization, retaining the first selected spelling.
   Nonlocal URL, remote host, UNC/network path, directory, absent file and
   unsupported format reject the entire batch with feedback. Only local file
   metadata (`is_dir`/`is_file`) is queried; no codec inspection/read/decode or
   preview happens in the GUI. URL input cannot become output-directory text.
   Drag acceptance explicitly returns CopyAction even for a source proposing
   MoveAction; Move-only offers are rejected, so selection-only drops never
   signal permission for a drag source to remove its data.
3. A 90px source list inherited global 12px vertical item padding. Native
   pre-fix viewport height was 80px, row heights 58/55/55, reproducing three
   selected but only one fully visible. A source-list-only style reduces
   padding to 2px; each item gets a font-metric height plus 6px for its padding,
   border and clearance. Final rows are 22px, with all three fully visible in
   the 80px viewport and text clearance at least the font height. Other lists
   retain their styles.
4. The shared wrapped QFormLayout underestimates its height after switching
   from keep to replace. Native reproduction: field preferred height 220px
   versus HFW/minimum 140px; parent allocated 140px and reduced each 36px combo
   to 26px. The edit field was 8px for a 16px font. A preferred-height minimum
   is now recomputed on form refresh and style/font changes. Width and parent
   scrolling remain responsive. Both combo edit fields are now 18px for 16px
   fonts, with 36px outer controls and no row overlap. Exploratory preferred
   minimum-size/HFW Python overrides were bypassed by the parent Qt layout;
   they are not in the final code. A combo-only minimum-content style was also
   rejected because it preserved glyph height while allowing row overlap.
5. `QPushButton#primary` outweighed the generic disabled selector, painting an
   actually disabled Start button like an enabled primary. A matching
   `#primary:disabled` selector restores neutral surface and muted text. Native
   background pixels: dark disabled `#202022` / enabled `#ececea`; light
   disabled `#ffffff` / enabled `#242422`. Enabled state remains token-driven.
6. Blank keep destination reached the model's technical bounded-text error.
   ConversionFields now reports `请选择输出文件夹` before calling the existing
   folder validator. Replace still needs no destination. No backend validation
   contract was changed.

## RED to GREEN

The initial regression run against unchanged baseline produced **22 failed,
2 passed in 2.43s** (`sandbox/ui021-sol-9b616f75/red.txt`). Failures directly
exercised real Qt routing, preview invalidation, text geometry, rendered button
pixels and the missing-folder UI message. No production code preceded this
RED. Subsequent geometry failures rejected ineffective layout overrides;
the explicit dynamic height floor passed all 24 initial cases.

The fuller native event sequence then exposed MainWindow DragMove default
rejection; `dragmove.txt` records **2 failed / 22 passed**. Only conversion-page
move routing was corrected; the archive branch still delegates its default.
The root's drag-copy review supplied an additional contract. Before the
CopyAction correction, `copy-red.txt` records both proposed-Move and Move-only
cases failing (**2 failed / 24 deselected**). They pass in the final 26 cases.

Final command:

```powershell
& .venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_conversion_ui021.py tests/test_automation_forms.py tests/test_automation_ui.py tests/test_ui.py -q --basetemp=sandbox/ui021-sol-9b616f75/pytest-freeze -p no:cacheprovider
```

Result **103 passed in 11.03s**, log `sandbox/ui021-sol-9b616f75/freeze-focused.txt`.
Native QPA Windows run of the new file: **26 passed in 4.29s**, log
`sandbox/ui021-sol-9b616f75/native-freeze.txt`. These exercise synthetic real
Qt drag events, not an external Explorer or live installed app session. The
invalid image fixture bytes remain untouched and codec calls are forbidden
during drops. `git diff --check` is clean (Git prints only its LF/CRLF notice).

## Actual DPI and native visual evidence

The host's Windows base DPR is 1.5. The first exploratory captures used Qt
multipliers and therefore represent extra stress scales, not the requested DPI.
They are explicitly superseded by `native-dpr-*` evidence. Final child-process
Qt multipliers are requested DPR / 1.5, with actual
`window.devicePixelRatioF()` asserted to equal the target within 0.00001.
No host display setting was changed.

| Actual DPR | Qt multiplier | Geometry/pixel scenarios | PNG captures |
| --- | --- | --- | --- |
| 1.00 | 0.6666666666666666 | 40 passed | 16 |
| 1.25 | 0.8333333333333334 | 40 passed | 16 |
| 1.50 | 1 | 40 passed | 16 |
| 2.00 | 1.3333333333333333 | 40 passed | 16 |

Each process covers dark/light, actual logical 1080×925 (matching the supplied
user screenshot's approximate logical dimensions) and 800×620, all
JPEG/PNG/WebP target formats, and keep→replace→keep. Assertions measure both
combo edit-field rectangles, font height, row separation, all three complete
source rows and row text clearance; actual pixel checks compare enabled and
disabled Start. Each `native-dpr-*/metrics.json` records actual DPR, multiplier,
screen logical/physical DPI, QPA Windows, state directory and every result.

Final evidence base: `sandbox/ui021-sol-9b616f75/`. Script `render.py` uses a
fresh UUID state per process and retires all owned work before exit. The 64
screenshots and 160 scenarios are the corrected acceptance matrix. Actual
100/125/150/200% dark/light images were visually inspected; control text,
three source names and disabled buttons are legible after mode toggles.
Representative files:

- `native-dpr-1/dark-800x620-png-replace.png`
- `native-dpr-1.25/light-1080x925-png-keep-again.png`
- `native-dpr-1.5/dark-1080x925-png-replace.png`
- `native-dpr-2/light-800x620-png-replace.png`

Small-window forms retain scrolling; this pass does not redesign table/header
theme rendering. Source is ready for root review and serial integration.
