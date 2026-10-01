# Generated same-path replacement chain — scoped Sol fix

Base reviewed HEAD: `f46fdbd25e77f7783013d7e5a9cf3bc55d600d3f`, managed `feature/filehub-rules-020` worktree. This report covers only `src/filehub/generated.py`, `tests/test_generated.py`, and this report. Runtime, planner, operations, journal, and UI implementation were not edited. The original F: checkout and shared virtual environment were used read-only. No full suite, installation, staging, commit, registry access, or live application work was performed.

## Root cause and exact exception

The existing shared-batch selected-source overlap check rejected earlier committed same-path JPEG replacement rows. A valid two-action preview therefore committed quality 90 and failed quality 80; three-action previews stopped at the same second action.

The exception applies only when the current mode is `replace` and normalized current source equals normalized target. Every other row whose source aliases this target must be strictly earlier in the current ordered batch and prove membership in the same replacement lineage:

1. Start the cursor at the current operation's bound expected source fingerprint.
2. Walk the conflicting earlier rows in reverse journal order. Each must be a committed `convert` in this exact batch, with both source and target equal to the current normalized subject path.
3. Require complete `Fingerprint` values for current cursor and predecessor input, and exact dataclass equality between predecessor target fingerprint and cursor. This comparison includes device, file identity, primary size/hash, creation/mtime, and the complete ADS manifest/digests.
4. Require its validated generated ownership record to have `mode=replace` and `phase=committed`; `_record` also checks its allocated internal ownership paths.
5. Advance the cursor to this predecessor's bound input fingerprint. This links older rows without incorrectly requiring their historical outputs to equal the newest output.

If any conflicting row fails any condition, the existing selected-source rejection remains. Non-same-path publication receives no exception. The process-issued, single-use engine/source/target/output ticket binding, occupied-target checks, held source/output verification, durable backup, exclusive swap/publication, and recovery/undo remain unchanged. The live original still must satisfy `original.verify(expected_source)` before backup or mutation. There is no path-only, content-only, cross-batch, general occupied-name, or cross-extension reuse bypass.

## Fresh RED/GREEN evidence

All runs used the shared `F:/Hazel Windows/.venv/Scripts/python.exe` with `-B -X utf8`, `PYTHONDONTWRITEBYTECODE=1`, worktree `PYTHONPATH=src`, and pytest cache disabled. All generated files/state stayed under owned worktree sandbox directories.

RED, before changing production code:

```powershell
& 'F:/Hazel Windows/.venv/Scripts/python.exe' -B -X utf8 -m pytest tests/test_generated.py -q -k 'same_path_replace_chain_commits or rule_preview_same_path_replace_chain' --basetemp=sandbox/generated-chain-sol-red -p no:cacheprovider
```

Result: **4 failed, 91 deselected in 0.86s**, exit 1. Both direct-engine cases (2 and 3 replacements) stopped with first row committed, second row failed with `目标与批次其他选中源重叠`. Both real service-issued rule preview/submit cases accepted 2/3 same-path steps but returned `partial` after the first action. These were actual Qt JPEG encodes and publications, without runtime doubles.

Final GREEN:

```powershell
& 'F:/Hazel Windows/.venv/Scripts/python.exe' -B -X utf8 -m pytest tests/test_generated.py -q --basetemp=sandbox/generated-chain-sol-final -p no:cacheprovider
```

Result: **99 passed in 10.28s**, exit 0: 80 existing generated tests plus 19 new cases. An intermediate new-case run passed 14 cases and failed one assertion expecting `failed` after an external identity replacement following ticket issuance; inspection confirmed frozen recovery correctly uses `conflict` after a consumed ticket. The test now explicitly expects this conservative existing result and checks the external occupant remains exactly unchanged; production recovery was not altered.

Positive cases exercise 2 and 3 ordered same-path replacements at JPEG qualities 90/80/70 through both direct engine and real frozen `FileHubService` worker preview/submit. They assert every row commits, verify connected full output/input fingerprints in the direct path, run real reverse batch undo, and compare restored original bytes, ADS bytes and fingerprints, creation time, and mtime against the initial file. The original image is textured, has a named ADS, and visibly different recompressed bytes, avoiding a trivial identical-output fixture.

New negative cases cover unrelated selected-source aliases in prepared/failed/committed states; non-convert/conflicting cross-path rows; full file identity, creation/mtime, and ADS fingerprint differences; an older broken link even while the latest predecessor exactly matches the current live file; missing/prepared/keep generated ownership; another batch's committed predecessor; and real identical-byte, identical-time external file replacement with a new file identity both before and after ticket issuance. Existing selected-source overlap, occupied-target, capability binding, interruption/recovery, metadata, and undo conflict cases all pass in the same focused file.

`git diff --check -- src/filehub/generated.py tests/test_generated.py` returned exit 0. Git emitted only its configured LF-to-CRLF conversion notices. A scoped `git diff HEAD -- src/filehub/automation src/filehub/operations.py src/filehub/journal.py` was empty. Concurrent UI changes belong to their separate owner and were not included in these claims.

## Freeze and evidence boundary

The three owned files are frozen for root independent delta review and scoped integration. No claim is made about the full suite, package, UI, original F: fixture cross-volume behavior, or live app. Root will perform its own focused recheck and cross-volume fixture verification. Same-rule PNG→JPG→PNG remains conservatively planner-rejected; this fix intentionally does not expand that contract.
