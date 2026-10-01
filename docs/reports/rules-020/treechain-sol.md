# Required directory-chain inverse fix — frozen for director review

Worked only in the feature/filehub-rules-020 worktree, based on ab7e406.
Owned changes are `src/filehub/operations.py`, `src/filehub/trees.py`,
`tests/test_directories.py`, and this report. Runtime/generated/UI changes in
the shared worktree belong to other tasks and were not edited. The original
F: checkout and its junctioned venv were used read-only; no installation,
stage/commit, live user operation, full suite, or subagent was performed.

## Cause and narrow correction

`OperationEngine.undo` previously preflighted every tree before executing any
inverse. In a single engine batch containing directory move/copy then rename
(implemented as move), the first target had already been consumed by the second
operation. The early check permanently blocked the first group before the second
inverse could restore it. `undo_tree` then excluded the entire same batch from
verified tree restoration lineage, so delaying the first check alone would still
leave its old target identities stale.

The whole-tree gate now runs once for each root at its reverse execution boundary,
before its first child inverse, or at the root itself for an empty tree. It uses
the explicit journal parent relationship, not adjacent ordinal blocks; unrelated
parents allocated before appended children remain supported. The gate refreshes
the root after later inverses, then applies the existing complete-tree checks and
inverse-root ownership checks. Owned inverse directories stay pinned across all
children and their parent. Each group's pins close when its parent settles so an
earlier group can safely remove the restored intermediate directory.

Same-batch tree lineage now admits only operations with a strictly earlier
ordinal. Full `captured_predecessor` checks, each restored file's precise
`undo_fingerprint`, restored directory identity membership, held verification,
content and both-time checks remain intact. External equal-byte replacements
cannot acquire lineage. The generated/file inverse lineage code is unchanged.

Persistent `tree_undo_blocks`, incomplete/conflicted tree refusal with committed
children, whole-group external-change refusal, owned interrupted inverse retry,
and recycle/manual-restoration behavior remain unchanged. Failed tail operations
remain failed, so their batch retains its partial outcome even when all previously
committed operations are successfully undone.

## Evidence

The direct engine test was written before the production fix. Initial command:

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_directories.py -k "same_batch_directory_chain or directory_chain_external_change or noncontiguous" --basetemp=sandbox/treechain-sol-red -q
4 failed, 4 passed, 26 deselected in 2.13s
```

All four failures were the expected state assertion: move/copy followed by rename,
with or without a subsequent failed step, did not fully undo its committed rows.
After the narrow fix those original eight selected cases passed. The final tests
also exercise empty directory chains and an external identical-byte predecessor
captured by a later same-batch move; the latter restores the later operation but
refuses to rebind/undo the earlier operation.

Final focused gate (exit 0):

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_operations.py tests/test_directories.py tests/test_automation_runtime.py::test_directory_move_rename_chain_undo_and_provenance --basetemp=sandbox/treechain-sol-focused2 -q
97 passed in 10.13s
```

The exact runtime regression now verifies directory move → rename → undo and
unchanged-rule provenance suppression. Added/changed/identically replaced
children leave the complete later target fingerprint unchanged, create neither
inverse source root, and retain every child as committed on both undo attempts.
Existing reoccupied-root/conflicted-parent refusal and interrupted inverse retry
regressions passed in the focused gate. Multiple unrelated roots with both parent
rows allocated before any child rows also passed. No broader runtime or generated
test file was run. Full integration/release checks remain the director's separate
gate; this scoped change is frozen for review.
