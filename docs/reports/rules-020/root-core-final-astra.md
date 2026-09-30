# Final independent core review — FileHub 0.2.0

Review target: `f46fdbd25e77f7783013d7e5a9cf3bc55d600d3f` against `6d7c4d77f6d746f6926f613442646d196da00e67`. Reviewed the rules design and current image-only conversion addendum, Task3 integration report, and the backend changes across models/conditions/planner, runner/ledger/executor, scheduler/service, templates/naming/routes, generated publication, operations/tree inverse handling and journal migration. Uncommitted UI integration was excluded. A final diff against the frozen head confirmed the reviewed backend files were unchanged.

## Actionable finding

### P2 — accepted consecutive in-place replacements fail after the first mutation

Location: `src/filehub/generated.py:170–173`, specifically the unconditional same-batch `other.source == target` rejection. Relevant acceptance boundary: `src/filehub/automation/planner.py:140–148` permits repeated same-subject replacements, including an original-path exception and a matching intermediate reservation.

Reproduction with real Qt JPEG input in a fresh owned sandbox:

1. Create `watch/a.jpg`; save a rule matching `.jpg` with two ordered `image_convert` actions: JPEG/replace/quality 90, then JPEG/replace/quality 80.
2. Call `service.conversions.submit_rule_preview([source], rule.id)`. Preview has no errors and two steps, both `a.jpg → a.jpg`.
3. Submit that exact issued preview. The first replacement commits with a durable backup. The second fails with `目标与批次其他选中源重叠` because the previous conversion's source path equals the current target.

Observed result: `partial`, one completed step; journal rows are `convert/committed`, then `convert/failed`. Sandbox: `sandbox/core-final-astra-q30uwytj`. The process used the existing shared `.venv/Scripts/python.exe`, explicit worktree `PYTHONPATH`, and disabled bytecode writes. No test suite or dependency installation was run. The sandbox is preserved.

Impact: the displayed executable rule cannot finish, after it has already recompressed the source once. The durable partial claim then requires history review instead of normal completion. This is a correctness/preview-authority mismatch, not an observed overwrite or original-data-loss defect; the first operation retains its recovery backup.

Minimal fix boundary: distinguish a prior action on the current subject from another selected source using verified ordered journal lineage. Permit the same-path replacement exception only when `mode=replace`, normalized source/target identify the same bound current subject, and the earlier conflicting rows belong to its already committed lineage, with full output-to-next-input fingerprints connecting the actions and the live original matching the current expected fingerprint. A third consecutive replacement must also work, so simply requiring every earlier output fingerprint to equal the latest fingerprint is insufficient. Preserve the occupied-target check, held-source verification, exact staging ticket ownership and backup transaction. **Do not delete the batch overlap guard, exempt every same-path replacement, or allow unrelated/prepared/failed batch source rows based only on path or content hashes.** An equivalent explicit trusted lineage capability is acceptable if it enforces these same boundaries.

Focused validation should include two and three consecutive same-path replacements with different JPEG quality settings, complete reverse undo restoring the original bytes/times/streams, and the existing negative selected-source-overlap test. Add a negative case where a same-path replacement has no proven committed subject lineage while an unrelated batch source aliases its target.

Scope clarification: one-rule PNG→JPG→PNG is rejected in the current planner before execution because the last target overlaps the original selected source (`planner.py:140–143`). That conservative planned-path reservation is explicit in the planner and is not this accepted-preview/partial-mutation defect. Enabling within-plan vacated-name reuse would require a separate planner contract change and is unnecessary for this fix. The already supported separate-rule PNG→JPG→PNG automatic chain/cycle remains within existing scope.

## Other review conclusions and evidence limits

No additional actionable P0/P1 or concrete security/data-loss blocker was found in the reviewed frozen backend. The reviewed controls retain exclusive publication, engine-bound single-use staging, recoverable replacement backup/swap phases, exact inverse identity rebinding, rule semantic lineage suppression, queued authority revalidation, cancellation settlement and old-journal migration safeguards. This is a source review plus one focused real reproduction; earlier focused test results were read as context, not re-executed or represented as new independent passes. The final source suite, packaged artifact and UI review remain the root's separate gates.

No product code, index, shared dependencies, original checkout, live user state, registry or application lifecycle was changed. Only this report and the authorized fresh reproduction sandbox were written. Re-review the narrowly scoped fix before treating the finding as resolved.

## Independent narrow re-review — finding resolved

Fix reviewed: `d5b6f88cf0ce7b8f70e0ea402852f5b69a75a42b` against the original frozen `f46fdbd25e77f7783013d7e5a9cf3bc55d600d3f`. Reviewed only the `generated.py` / `test_generated.py` product delta and `generated-chain-sol.md` / `generated-chain-astra-review.md`; concurrent UI integration is excluded.

The exception preserves the requested ownership boundary. Every conflicting source row must occur strictly before this item in the same ordered batch. `_same_path_predecessors` walks those rows backward from the current bound input: each row must be a committed same-path `convert`, with an internally validated committed replace ownership record, and its complete output fingerprint must equal the cursor before advancing to that row's complete input fingerprint. This links all historical generations, including the oldest predecessor in a three-step chain. Cross-path, different-batch, unrelated, failed/prepared and missing-ownership rows cannot qualify. Full current held-source verification and engine-bound staging-ticket validation still precede backup and mutation. The batch overlap guard has not been removed or replaced by a blanket same-path/content-only exemption. No planner or general occupied-name policy changed.

Fresh independent focused command (worktree `PYTHONPATH`, bytecode and pytest cache disabled, prechecked-new owned sandbox):

```powershell
& .venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_generated.py -q -k 'rule_preview_same_path_replace_chain or same_path_chain_never_exempts_unrelated_selected_source or same_path_chain_requires_older_links or same_path_chain_rejects_external_identical_bytes_new_identity' --basetemp=sandbox/root-core-astra-delta-d5b6f88 -p no:cacheprovider
```

Result: **9 passed, 90 deselected in 1.92s**, exit 0. These include the original real-worker rule reproduction with two and three JPEG replacements plus complete inverse restoration (original bytes, ADS, creation/mtime), unrelated selected-source aliases in four state/kind combinations, an older broken full-fingerprint link despite an exact newest predecessor, and an external identical-byte/time file with a different identity both before and after ticket issuance. The previously reported Sol 99-pass and director 147-pass gates were read as context only; the nine-case result above is this reviewer's independent execution.

**Disposition: original P2 resolved at `d5b6f88`; no blockers found in this narrow fix.** This does not replace the root's final full-suite, UI or packaged-artifact gates. No product code or index was edited during re-review; only this owned report and fresh test sandbox were written.
