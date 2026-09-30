# Task5 — 0.2.0 packaging, staged handoff

## Phase A: inputs frozen, build pending

Director dispatched this phase before UI4B freeze, explicitly restricting it to packaging inputs/metadata, third-party manifest/notices and delivery docs. Base `d5b6f88cf0ce7b8f70e0ea402852f5b69a75a42b`, branch `feature/filehub-rules-020`, managed worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`. No final build or executable functional acceptance has occurred in this phase. Concurrent app/UI/runtime-test changes belong to UI4B, not this implementer.

Read the task brief, rules design/plan, current image-only/replacement addendum, media-core provenance and Astra review, Task3A/3B and Task4A reports/reviews, and final core review context. No applicable AGENTS.md found in worktree/ancestor paths. The using-superpowers entry explicitly excludes dispatched subagents; the verification-before-completion requirement was applied to the concrete input claims below. Existing phase/task briefs and director ownership override generic whole-plan commit/review/cleanup steps. No agents, stage/commit, shared dependency update, live app stop, install/uninstall, registry or real state/watch/sync mutation, original checkout write or remote publication.

### Exact owned tracked changes

1. `pyproject.toml`: release version 0.2.0.
2. `packaging/installer.iss`: AppVersion 0.2.0; existing upgrade identity, settings/history retention, no automatic launch and no process termination behavior preserved.
3. `packaging/filehub.spec`: exact reviewed qwebp binary explicitly passed into Analysis and resolved as one singleton at `PySide6/plugins/imageformats/qwebp.dll`; sole added image plugin allowlist entry. Existing Qt module/plugin, ffprobe-path, ICU/API-set and Mesa software-OpenGL exclusions retained. EXE uses the existing warm-yellow icon plus new version metadata.
4. `packaging/version-info.txt`: EXE fixed 0.2.0.0 and string 0.2.0 version resource; metadata only.
5. `packaging/freeze-input-manifest.py`: derives app version from pyproject, adds exact QtImageFormats source archive/provenance and version resource; preserves frozen ffprobe imports from the checked existing manifest instead of missing historical `sandbox/task6-media-probes/dll-imports.json`. Manifest writes LF to preserve vendor-input file conventions.
6. `packaging/verify-inputs.py`: checks pyproject/installer/manifest/EXE metadata agreement, all pinned runtime/source/notice hashes and distributions, qwebp pinned wheel RECORD/hash, exact corresponding source and verbatim LGPL/BSD/libwebp PATENTS/materials, actual qwebp/ffprobe PE imports and the bounded native payload inputs.
7. `third_party/components.json`: refreshed 0.2.0 prepared-input manifest, 228 pinned files and four source archives. All old pinned inputs except the intentionally updated third-party notice have identical hashes.
8. `docs/第三方许可.md`: 0.2.0 QtImageFormats/libwebp license, patent, source, path and dynamic replacement disclosures.
9. `README.md`: 0.2.0 workflow/delivery entry points and opt-in/image/replacement limits.
10. `docs/使用说明.md`: user upgrade steps, templates, first-match rules before legacy age gate, independent generic rules, keep/replace/backups/undo and codec limits.
11. `docs/交付说明-0.2.0.md`: concise Chinese upgrade, retention, feature and limitation guide, explicitly pending final build.
12. `docs/evidence/rules-020/task5-input-audit.json`: this phase's input-only evidence, separate from root reports and executable evidence.
13. This report.

No app.py/self-test/UI/tests/backend delta was made. `packaging/build.ps1` and frozen conversion source/binaries/materials were not modified. Old install/registry QA tools retain their historical version and were not executed.

### Input verification actually executed

Initial existing gate: `.venv/Scripts/python.exe -B -X utf8 packaging/verify-inputs.py` → exit 0, pinned 0.1.1 inputs verified before any change.

Freeze command: `.venv/Scripts/python.exe -B -X utf8 packaging/freeze-input-manifest.py` → exit 0, `Frozen 228 inputs and 4 source archives`. After notice LF normalization the freeze was rerun; no old vendor material changed.

Final owned audit:

```powershell
& .venv/Scripts/python.exe -B -X utf8 sandbox/packaging020-phaseA-680882e65dad43eaa8cf632f1c5ba8f5/audit.py
```

Result: exit 0, `passed=true`, 228 pinned inputs, four archives, original 0.1.1 installer preserved. The audit invokes the verifier in a child with only pinned Python + Windows PATH, clearing Qt/PySide/Python developer overrides; compares every extracted conversion notice byte-for-byte with the source ZIP; parses the version resource using PyInstaller's real parser; simulates spec Analysis solely to exercise plugin/Qt/ffprobe/ICU/Mesa filters and source/icon/version inputs. **Spec simulation is input verification, not a build or executable acceptance.** All packaging Python/spec inputs also compile through these executions; `git diff --check` for owned tracked changes exits 0.

Audit harness development had two script-only failures before the final pass: ordinary dict environment keys were uppercase on Windows (`SystemRoot` lookup fixed via os.environ), and simulated data destination comparison needed slash normalization. Neither changed product code or proves a product defect. Final gate output retained at `sandbox/packaging020-phaseA-680882e65dad43eaa8cf632f1c5ba8f5/verify-inputs.txt`; final evidence is `docs/evidence/rules-020/task5-input-audit.json`.

- qwebp: 564536 bytes, SHA256 `6b2c53cc4423140c29a6a1eb6dd908016e09d794b5739a05a3a39c8c49a0df8a`; installed PySide6_Essentials 6.11.2 binary and wheel RECORD agree with reviewed vendor copy.
- QtImageFormats v6.11.2 source: 3041992 bytes, SHA256 `a0003652945eeafc8bc28cc639f5941350fe27e91236908306d4733b703a23b5`; libwebp 1.6.0/BSD-3-Clause attribution and LGPL/BSD/COPYING/AUTHORS/PATENTS retained verbatim.
- Actual qwebp imports: Qt6Gui.dll, Qt6Core.dll, VCRUNTIME140.dll, five Windows CRT API-set DLLs (string/heap/math/utility/runtime), KERNEL32.dll. No new encoder DLL.
- Actual existing ffprobe.exe/avcodec-62.dll/avformat-62.dll/avutil-60.dll import sets equal frozen manifest; old bytes/licenses/source/resources and warm-yellow icon remain unchanged.
- Original `F:/Hazel Windows/dist/installer/FileHub-0.1.1-windows-x64-setup.exe` still hashes `bacd74379bc38e02d924f381aad8980f07bd738e68800668cc4b699f68d37f1a`. Original checkout remains read-only.

### Phase B handoff required

Wait for director's explicit UI4B freeze and scope transfer. Director approved in principle a narrowly scoped new `src/filehub/selftest020.py` helper, invocation from existing `app.py:self_test` and corresponding `tests/test_app_runtime.py`; these are deferred until the handoff. The helper must use real runtime APIs under the existing explicit UUID-owned `--state-dir` self-test, retain ten old checks and exercise JPEG/PNG/WebP native roundtrip including ordinary QImageReader tiny 42-byte transparent WebP, JPEG background, keep/true same-path/cross-extension replace+backup+undo, generic rules without syncroot before the old three-day gate, ordered copy/convert/move/history/undo, disabled import and persisted template routing. No general QA framework, hidden normal-state switch or live installation.

After narrow source/tests freeze, root owns final full-suite. Then build the actual EXE/installer with:

```powershell
& packaging/build.ps1 -ISCC 'F:/Hazel Windows/sandbox/tools/inno-6.7.3/{app}/ISCC.exe'
```

Require actual packaged self-test in clean bounded child environment and new owned UUID data/state; source Python passes are not EXE acceptance. Verify actual singleton plugin path/hash/native imports, material presence, EXE and installer version/icon/size/hash, encoder/ICU/Mesa exclusions, and final PYZ/code-object source agreement including all new modules plus changed app/main/service/scheduler. Root's independent `sandbox/root-artifact-audit020.py` runs only after artifact freeze. Build exit 0 alone is insufficient. Root's `root-cross-volume-replacement.json` is source runtime evidence and must remain separate from actual packaged acceptance.

Final build command/output, self-test result, source/PYZ match, artifact hashes and limitations will be appended here after Phase B. Historical 0.1.0 live install/uninstall and 0.1.1 patch acceptance remain historical; none were repeated for 0.2.0.

**Phase A frozen. Phase B and final delivery are pending; no active owned process remains.**

## Phase B1: acceptance source hook frozen, build pending

Director explicitly transferred the self-test-only scope after UI4B `244895d` freeze, then retained that scope while a separately owned UI lifecycle fix/review proceeded. Added product/test ownership is exactly `src/filehub/selftest020.py`, two lines in `ui/app.py:self_test` (import/call), and new `tests/test_selftest020.py`. No Runtime, controller, UI behavior, backend or `tests/test_app_runtime.py` edit. Source hook freeze observed HEAD `4e298795717b9e7d47e375ba8bde85426294a9bb`; concurrent committed UI deltas are excluded from this claim. No stage/commit or executable build.

The existing explicit `--self-test --state-dir` creates its UUID fixture and performs the unchanged ten old checks, including real bundled ffprobe 64px and two distinct 1920px video archives/undo. Only then the new helper creates a fresh `release020` child. It uses FileHubService, ConversionExecutor, RuleStore, Scheduler, TemplateStore, engine journal/history and ordinary QImageReader; all data/state are within that existing fixture. Any failure propagates into the existing error JSON and nonzero exit. Every owned conversion executor settles in a finally block.

Added eleven checks: real PNG→JPEG→PNG→lossless WebP→JPEG decode/encode roundtrip at unchanged dimensions; fingerprint-bound keep/inverse; PNG/WebP alpha; ordinary native decode of generated transparent 42-byte WebP; actual white/black/custom JPEG backgrounds; same-path JPEG recompression and cross-extension PNG→JPEG true replacement with durable private backup, full recorded fingerprint and ADS preservation, inverse bytes/ADS/times; fresh generic automatic copy with no sync root and before legacy three-day gate, durable restart suppression plus undo; copy→replace-convert→move rule with actual WebP, one ordered journal/history batch and complete inverse; imported enabled definition persisted with fresh disabled ID and no automatic mutation; saved custom template assignment reloaded by a new service, real custom project route and undo.

Focused evidence (read-only pinned `.venv`, bytecode/cache disabled, new owned basetemp each):

- RED: `pytest tests/test_selftest020.py -q --basetemp=sandbox/task5-hook-red-5fb5640e9d114a659b039a12940ab614 -p no:cacheprovider` → 2 expected failures in 0.71s: existing self-test omitted new checks; helper absent. Log `sandbox/task5-hook-red.txt`.
- Initial GREEN: same new test file, `--basetemp=sandbox/task5-hook-green-89ce5b84055843ad8f2e58d04237ec5a` → 2 passed in 2.87s. Log `sandbox/task5-hook-green.txt`.
- Final exact gate: `.venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_selftest020.py tests/test_app_runtime.py -q -k selftest --basetemp=sandbox/task5-hook-final-3e42a35ba77c42899dcb25e14e7825d3 -p no:cacheprovider` → **4 passed, 17 deselected in 6.28s, exit 0**. Existing runtime file was only read/executed for its two self-test regressions, not edited. Log `sandbox/task5-hook-final.txt`.

The failure-injection test makes the new helper raise after the ten old checks and proves actual CLI dispatch returns 1, writes JSON `ok=false` with the new failure, and cannot accept only historical checks. The real integration test verifies native capabilities, tiny WebP alpha/42 bytes, recorded rule order, persisted template route, all fixture paths under the UUID and retained original backup bytes. Owned source/doc `git diff --check` exits 0. Final successful source report is copied as `docs/evidence/rules-020/task5-source-selftest.json`, explicitly labeled source Python; **21 checks true, runtime_frozen=false**. It is not executable acceptance.

**B1 source frozen. Wait for director go/no-go after independent source delta/full-suite and UI repair freeze before final build.** All Phase A packaging inputs remain owned and unchanged except the requested narrow user-guide button-label example. Root retains final suite and independent source/artifact audit. No active owned process remains.
