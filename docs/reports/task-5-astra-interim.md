# Task 5 Astra interim review (phase A ongoing)

Reviewed native Qt dark/light/main/dialog/records/settings/first-run screenshots under docs/evidence/ui. This is not final approval. Palette/sidebar/card direction established, but requested focused corrections:

- Fix clipped watch list row at current Windows scale; keep readable rows/scroll.
- Preview source name to target name with labeled sync-relative destination, exact paths available in details/tooltips.
- Local human time instead of raw UTC ISO; Chinese action/state labels instead of raw enum.
- Watch cards identify actual roots/roles; no arbitrary watch[0] labeled Desktop; light icons use dark gold.
- First-run direct sync-folder action. Idle workbench hides archive form until select/drop; top-right archive action; add vector brand/card icons and subtle reference highlight.
- Capture real demo archive recent-record content for final density review.

Functional pre-review requirements passed to Sol: authoritative Qt system colorScheme and change signal; stale preview generation/path/tag checks in main and dialog; immutable preview captured before worker dispatch; routing-config changes invalidate both windows. Inbox payloads must be real user items below category/day, not structural folders. Task4 parent_operation_id allows public root/child grouping without UI SQL.

Phase A uses UI-owned files only while Task4 backend proceeds. Full app/tray/IPC/CLI binding and whole suite are downstream; focused UI tests use separate sandbox paths.

## Phase A scoped approval
Head ca2a8c1. Re-reviewed updated native dark-main/settings/dialog/first-run and functional implementation. Spec/quality approved for UI-only phase A: readable previews, local times, Chinese states, compact actual recent records, correct folder labels and no settings overlap; authoritative system theme and async invalidation addressed. Final 8 focused UI tests passed in1.26s, including busy dialog/delayed config save/integration failure and immutable execute capture. No duplicate full-suite run. Runtime, tray, queue ownership/renew/ack, demo shared-service ownership and packaged registration callbacks remain phase B and are not yet approved as full Task5.
