# Task 1 Astra review

Reviewer: GPT-6 Astra controller, delegated stage review. Head `e6a729cafb103700643e1617cfbb34f66a3adb22`, scope safety engine. Read code, tests and implementer report; did not repeat the already reported suite.

## Verdict

Spec/quality: **Needs fixes**. No stage advancement until metadata preservation is corrected. Reported test evidence: 59 passed in 3.45s, including native Windows recycle shell-item confirmation. This proves the covered cases, not missing metadata behavior.

## Confirmed strengths and addressed pre-review findings

- `operations.py::_transfer` and `undo` now publish verified sibling staging using no-replace rename before removing guarded source; crash states retain both paths/fingerprints. Original names no longer expose partial copy contents.
- `undo` for copy now holds a matching-content survivor guard before deleting its unchanged supplemental copy. Missing/edited original and failed move undo preserve the last original version; regression tests cover these cases.
- Windows handles deny concurrent write/delete, and target/restored guards remain held until destructive source/target deletion completes.
- Local lock is reentrant in-thread, shared across engine instances and excludes another Windows process; SQLite has durable typed state transitions.
- Native recycle uses IFileOperation with recycle-only intent, exact sandbox item was found in recycle bin, manual restore/unknown states are honest. Directory refusal is within this phase's declared scope.

## Important — metadata is silently discarded by move

`src/filehub/operations.py:92` `_copy` reads/writes only the default stream, and `_transfer` subsequently removes the original. It does not preserve Windows creation/last-write timestamps or named NTFS alternate streams. `Fingerprint` in `src/filehub/models.py` hashes only the default stream. This changes later naming dates for files moved and archived again, silently drops ADS during a normal move, and fails to detect ADS-only edits before undo. The implementer's documented limitation does not make destructive loss safe.

Required fix: preserve creation and last-write timestamps through move/copy/undo; preserve and verify ordinary NTFS streams including Zone.Identifier and user-named streams; include stream content in stale-source/undo identity checks. If a target filesystem or stream cannot be supported safely, refuse that item before removing source with a Chinese reason. Do not broadly refuse ordinary browser downloads. ACL inheritance at destination remains an explicit boundary, not a requirement to clone security descriptors.

Test requirements: real Windows NTFS main+Zone.Identifier+custom-stream copy/move and undo roundtrip, creation/mtime equality, ADS-only source edit after plan and destination edit before undo are protected, unsupported stream target failure leaves source intact. Preserve existing no-overwrite/atomic publication and guard-lifetime guarantees.

## Limits to carry forward

- Actual second-volume transfer, abrupt process termination/power loss and folder operations remain later acceptance work; current fault tests inject interruption on F:.
- Recycle restore is manual; GUI must expose source path, exact recycled staging name and no false success.
- Public history should expose persisted batch timestamp in Task3 for UI records.
