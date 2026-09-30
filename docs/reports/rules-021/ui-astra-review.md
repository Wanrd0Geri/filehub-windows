# 0.2.1 image UI correction — director review

Reviewed four UI-only source changes and the new focused regression module. Conversion drops use copy-only semantics, validate local supported files, append/deduplicate Windows paths, invalidate preview once, and intercept child viewports/edit controls without navigating to archive or changing archive selection. Busy/retired admission is checked. No codec work occurs in the GUI drop path; only local metadata classification is used.

Native reproduction established the clipped-combo cause: the form height-for-width minimum undercounted styled rows after changing visibility, allocating an 8px edit field for a 16px font. Refresh/style/font changes now preserve the actual preferred form height, retaining responsive width and scrolling. Compact source rows, explicit disabled-primary styling and a clear missing-output message address the other reported issues. No backend or execution semantics changed.

Sol final focused gate: **103 passed in 11.03s**; native regression gate: **26 passed in 4.29s**. Director fresh `tests/test_conversion_ui021.py` gate: **26 passed in 2.54s**. Initial expected failures and the copy-action RED are recorded in the Sol report.

The first nominal scaling captures multiplied the host's 150% scale; those labels were rejected. Corrected native evidence asserts actual DPR 1/1.25/1.5/2 and covers dark/light, 1080x925 and 800x620, all output formats and keep→replace→keep: 160 checks, 64 captures. Director viewed corrected actual-150% output; three source names and control glyphs are fully visible and Start is clearly disabled without a token. Root independent review remains the next gate; packaging and final source suite follow metadata freeze.
