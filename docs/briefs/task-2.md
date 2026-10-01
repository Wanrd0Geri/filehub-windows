# Task 2 brief — exact rule port

Implement Task 2 of `docs/superpowers/plans/2026-09-30-filehub-v1.md` and global constraints. Read original reference source as text (never import/execute its module): `reference/mac/filehub_打包_260930/脚本/filehub.py`, specifically constants + lines 110–432. Read original requirements and rule compatibility examples.

This task consumes existing `models.py` only if useful; keep rules pure and testable, no mutation or shell/media probing. Add focused models to rules module if needed, no gratuitous engine refactor. Report `docs/reports/task-2-sol.md`, no subagents. GPT-6.1 Sol implementation; Astra reviews. Install dependencies only .venv.

Requirements beyond examples:
- Discover numeric area `/项目/YYMMDD_CODE_Name` dynamically, excluding 0_收件箱 and 2_资料库 as source does. Longest matching code; reject case-insensitive duplicate codes rather than guess.
- Source `next_seq` is same prefix + date, not all files globally. Preserve existing DATESEQ and existing note when tag has none, but collisions must increment semantic version (never `...1080p 2.mp4` for generated names).
- Source PV/正片 parsed shot bug is corrected by populating shots and preserving C003/C020. Source time (aware datetime accepted) fixed by caller; do not consult current clock/mtime mid-build.
- Only ep+scene videos use team naming; PV video may have no shot. Two-shot video produces 2 targets, >=3 one target + warning; non-video multi-shot source behavior remains first only. Use width thresholds exactly.
- Files with `keep` retain original name except safe_name sanitation and collision suffix, dated uses **source date** (sweep later uses arrival/current date). Directories route unchanged base name, and source dirs bypass dated child just like Mac; describe explicitly.
- Sanitation maps ASCII illegal chars to fullwidth, normalizes only math alphanumeric block, removes original source excluded Unicode classes and supplementary symbols. No arbitrary total 150 char cut. Windows trailing dot/space and device names are explicit validation errors rather than silent changes. Ensure traversal/tag separators never create escapes; sanitized asset component remains within intended project.
- Video probe absent/error: caller signals error, never omit required resolution silently. build_targets may receive `video_width=None` for nonvideos only.
- Source file suffix lowercased except `keep`; existing-name note matching must not accidentally duplicate C shot.
- Main output should describe actual public API signatures, warnings and error types for service phase.

TDD matrix must include every plan example plus E01C3, missing mirror number inferred `C15A.mp4`, dated filename preservation, prefix/day sequence, final notes rules, reserved `CON`, reparse/path traversal, 151-char accepted if below real limits, >255 UTF-16 component rejected, and source names with emoji/math characters. Keep Windows behavior distinct from pure string test (Windows cannot create literal `|`).

No execution of original scripts, no Mac parity claim. Compatibility doc lists intended fixes versus inherited source behavior; Windows tests only. Commit scoped files and report, compact response with SHA and exact test totals.
