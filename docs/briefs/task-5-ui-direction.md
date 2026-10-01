# Binding UI direction for Task 5

Read `reference/filehub-ui-graphite.html` including final overrides beginning `Compact graphite surfaces with warm yellow icon accents` around line 103; earlier CSS is superseded. HTML fixed here for durable review.

- Main #19191b, sidebar #111113, panel #202022 and top #252527, borders #303032, text #ececea, secondary #969693, icon gold #d8bd65. Light alternatives use final CSS exact values. Default dark; system option follows platform.
- 180 px sidebar at normal width; 32 px titlebar; main padding approx 25/26/17; 10 px main corner radius. Compact 13 px body, 11 px metadata, 24–25 px heading, 20 px brand; sensible DPI scaling and system Chinese font. User particularly cares about typography/spacing quality.
- Navigation 整理 / 收件箱 / 记录 / 设置, gold icons, selected subtly lighter with right gold indicator.
- Desktop/download management cards side by side. Recent records in one bordered compact panel, 12–13 px row vertical padding. Actual sources/status rather than fabricated counts.
- Right-click dialog about 438 px, 22 px title, 19 px code input, clear source file count + preview, Chinese action labels.
- Never use remote fonts or emoji as primary UI icons; bundle simple SVG assets or use Qt paths. Chinese text not clipped, paths wrapping/eliding with tooltip; controls accessible by keyboard.
- First run real product empty state and choose folders flow. Demo fixtures only behind explicit `--demo` isolated state. User should not need technical paths/flags in ordinary use.
- Capture real Qt-rendered dark main, light main, archive preview, records, settings and first-run state to `docs/evidence/ui/` for Astra visual review. Tests should verify key controls trigger actual service flow, not just string presence.
- Font refinement: system already has Inter Regular/Medium/SemiBold and NotoSansSC-VF. Prefer QFont families Inter + Noto Sans SC, fallback Segoe UI + Microsoft YaHei UI; do not replace approved typography unnecessarily. Bundling optional only with exact OFL notices.
- manual_restore must be actionable: show exact recycle staging name, original file name and original full path, provide 打开回收站. Explain restore may bring back .filehub staging name and user must rename to original; do not offer fuzzy automatic restore or raw HRESULT-only errors. Keep details copyable.

- Root delivery refinement: expose --demo via a clear 演示 button/shortcut requiring no typed command or config. One-click creates only self-owned fake sync/watch/sample files and isolated state; novice user can try archive/undo before selecting real directories. Ordinary launch remains unconfigured/paused.

- Advanced global_jobs switch must state both effects beside it: 共享收件箱到期清理 + 同步空间不合规文件名修正（包括已有项目），仅一台电脑开启；默认由 Mac 管理/关闭。Normal names and project routing remain unchanged. No silent ownership takeover.
