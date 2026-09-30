# FileHub 0.2.1 narrow UI independent review

**Result: no blocking findings in the reviewed UI delta.** Reviewed baseline
`ad333d174d234d60a1eba22d942ebf93bae42123` through UI commit `93bc94d`, against
`docs/briefs/rules-021-ui.md`. Packaging/version work is outside this review.

## Review evidence

- Independently inspected the four UI file changes and new regression file.
  Image-page and existing child-widget filters cover DragEnter, DragMove and
  Drop; MainWindow delegates those phases only while this page is current.
  Append/deduplication preserves first spelling, mutates selection once, and
  invalidates preview without decoding, previewing or executing. The unchanged
  archive branch retains its previous routing.
- All three phases recheck busy/admission and require CopyAction availability.
  Accepted events explicitly return CopyAction; Move-only offers reject.
  Directory, remote/UNC, missing-file and unsupported-extension batches reject
  before mutation. Destination edits cannot consume dropped URLs.
- Reviewed dynamic form-height refresh, compact source-row styling, disabled
  primary selector specificity and blank keep-destination validation. Replace
  does not require a destination.
- Visually inspected these native captures: DPR 1 dark 800x620 replace;
  DPR 1.25 light 1080x925 keep-again; DPR 1.5 dark 1080x925 replace; DPR 2 light
  800x620 replace. Three source names and both combo labels are readable;
  disabled Start is visually muted. Small windows retain vertical scrolling.
  Captures are under `sandbox/ui021-sol-9b616f75/native-dpr-*`.
- Independently parsed all four `metrics.json` files: Windows QPA and actual
  DPR 1/1.25/1.5/2, 40 scenarios each. Rechecked combo text clearance, complete
  source rows, source text clearance and distinct disabled/enabled backgrounds.
- Additional owned native Windows probe passed (exit 0): two admitted-enter
  cases becoming busy/retired before move/drop both reject without selection
  mutation; 27 shared ActionEditor image-form combinations cover dark/light/dark
  theme changes, JPEG/PNG/WebP, custom JPEG background and keep/replace/keep.
  Both combo edit rectangles fit their fonts and rows remain separated.
  Evidence: `sandbox/ui021-astra-9a34ffb7-2642-46ba-82a0-deb02dfaa573/probe.py`
  and `result.txt`.

The implementer's recorded 103 focused source passes and 26 native regression
passes were read, not rerun. Full-suite integration belongs to the director.
Drag evidence uses real Qt event objects, not a fresh external Explorer drag
or live installed-app session. This review makes no packaging/runtime-backend
acceptance claim. No product changes, stage/commit, installation, registry or
user-state operations were performed; owned probe widgets were closed.

## Reviewed working-file SHA-256

| File | SHA-256 |
| --- | --- |
| `src/filehub/ui/conversion_page.py` | `E37F7D9C181AB5C9724B3126AAB857B114443BB9951E2DC17A54183CE72D828F` |
| `src/filehub/ui/action_editor.py` | `A5D0525AC960EEEC8A2E23B533D4D471ABA88EF86FD53DC752118DB118F03AFD` |
| `src/filehub/ui/main_window.py` | `F87BFCAC9F1A48AF876DEB8FC9BBAFF7415FE9A82E173A6F151819FE8F557C4A` |
| `src/filehub/ui/theme.py` | `3E57D97A955895B9FC696D605FD9B64BAD87F9CB10C8407E3E27FC07ED7C43CB` |
| `tests/test_conversion_ui021.py` | `0537FBA4CFA9B8F418BFC7DD8980831712AD015C2D6C50C0F79CB49A98C137C9` |
