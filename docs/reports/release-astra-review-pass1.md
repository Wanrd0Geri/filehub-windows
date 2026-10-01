# Independent Astra release review — pass 1

Reviewer: `/root/astra_release_review`, GPT-6 Astra, clean context. Product head `641cdcb0ca6d59b1d4a58b859c91be8754b9e4cd`, base `bc06c017ebee360dd4e77e2d9637d99f20d1a3ea`. Returned 2026-10-01. Root transcribed this report; reviewer did not modify controlled files or Git state.

**Verdict: Needs fixes. Two Important findings; no confirmed Critical finding. No final release approval.** Packaging and installed-artifact evidence are explicitly deferred to pass 2. The reviewer verified `git diff 641cdcb -- src tests` was empty during this pass despite later documentation commits.

## Important 1 — conflicted directory roots bypass undo ownership checks

Frozen code: `src/filehub/operations.py:222`, followed by child inverses at line 245.

Whole-directory recycle fails after captured contents have been staged and the original empty root removed. Root state is `conflict`, while a child is `committed`. An external actor then recreates the original root with its own `external.txt`. Undo skips the root ownership check but reverses the committed child: `[conflict, committed]` becomes `[conflict, undone]`, the old `asset.txt` moves into the externally occupied root, and that file disappears from staging. External contents were not overwritten, but the explicitly approved all-child refusal boundary was violated.

All directory roots with reversible children must pass the root ownership boundary before any child inverse. A conflicted root whose ownership cannot be established must block all automatic child undo and report the reachable manual recovery location. Add regressions for failed whole-tree recycle and partially completed directory moves followed by original-root occupation.

Independent reproduction: `sandbox/astra-independent-733cd205308e4da7bb37f9c548053495`.

## Important 2 — duplicate recycling does not identify the existing copy to the user

Frozen code: `src/filehub/ui/main_window.py:214`; generic runtime completion notification at `src/filehub/ui/app.py:176`.

`ServiceOutcome.duplicate` persists the correct existing project path, but history renders only outcome errors. Successful duplicate recycling shows recycled state, no target and the recycle staging name, without explaining duplication or identifying the existing copy. This misses original acceptance case 6.

Show the duplicate reason and full existing-copy path in actual result/history UI; distinguish successful recycling from a failed attempt. Keep exact manual recycle-restoration information. Add a real Qt assertion without changing deduplication rules or the journal schema.

Independent Qt reproduction with a fake recycle adapter: `sandbox/astra-independent-ui-c34b6f3a21ac4e888cfac13193c98b5d`. Observed `result_ok=true`, `history_contains_duplicate_path=false`. No operating-system recycle action was performed by this reproduction.

## Minor, nonblocking follow-up

An unconfigured application permits Continue sorting and then displays running, although tick can only report that sync space is unconfigured. Prefer a pending-configuration status. This is not a release blocker and is not authorization for a broader onboarding redesign.

## Evidence and deferred scope

The reviewer inspected approved specification/plan/ledger, original requirements and Mac routing/naming source, product modules, related tests, stage reports, and actual demo/settings screenshots. It did not execute Mac code, repeat the full suite, register integrations or mutate real watch/sync folders. Only the two named isolated reproductions were run. The 248-pass/17.53s full suite was controller-provided existing evidence, not rerun by this reviewer.

Pass 2 must cover scoped fixes, final Task 6 code/artifacts/hashes/licensing, isolated install/upgrade/uninstall, cross-volume and Shell evidence, and accurate user documentation. Actual Mac/two-machine Baidu synchronization and a clean VM remain unverified. Permanent selection tags, a generic rule editor and remote publication are outside the approved release scope.

## Scoped fix review — approved

The same independent reviewer reviewed `acf3fdfa04aa403d3060bd2d4d1de756c22fb77b` and closed both Important findings. No open Important/Critical issue remains in that reviewed scope.

- Incomplete directory roots without proven inverse ownership now block every child inverse, persist the refused result, and show the retained staging/target recovery location. Existing whole-directory manual recycle restoration and controlled inverse retry remain intact.
- Immediate result text and persisted history now explain duplication, show the existing copy's complete path, and distinguish successfully recycled sources from incomplete recycling.

The reviewer read all five changed files and the fix report, confirmed no further working-tree changes in the four product/test files, and independently ran the four new focused regressions: **4 passed in 0.59s**, at `sandbox/astra-independent-fix1-20261001-0142`. Tests cover failed recycle, partially moved tree with original-root occupation, and real Qt duplicate success/failure display. It did not modify source or index or include the ongoing packaging-only self-test enhancement.

This approves the two fixes only. Final installer, runtime dependency packaging, installed execution and all remaining Task 6 evidence still require pass 2; this is not final release approval.

Subsequent Task 6 diagnosis corrected the initial VC-runtime hypothesis: unrelated ICU78 DLLs collected from the build PATH caused the Qt import failure. Removing those DLLs and using Windows system ICU resolved it; the original Python/Qt VC runtime combination also passed. Final review must assess the corrected clean-environment evidence rather than treating VC version unification as the necessary fix.
