# Task 1 Sol implementation report

Status: implementation complete; independent Astra review pending. Branch: `feature/filehub-windows-v1`; base: `bc06c01`. Scope is the safety engine only. No UI, rules, scheduler, registration, real desktop/download/sync files, or Mac script execution. Development runtime is workspace `.venv`, created with `py -3.12 -m venv .venv`; pytest 9.1.1 installed only there.

## Public interfaces for Task 3

```python
Fingerprint(device: int, file_id: int, size: int, mtime_ns: int, sha256: str)
Fingerprint.capture(path: Path) -> Fingerprint
Fingerprint.same_content(other: Fingerprint) -> bool  # size + SHA256 only
Operation(kind: str, source: Path, target: Path | None,
          expected_source: Fingerprint | None)
OperationEngine(state_dir: Path, platform=None)
OperationEngine.locked() -> context manager
OperationEngine.execute(operations: Iterable[Operation], label: str) -> BatchResult
OperationEngine.undo(batch_id: str) -> BatchResult
OperationEngine.recover() -> list[ItemResult]
OperationEngine.history() -> list[BatchResult]
```

`kind` is `move`, `copy`, or `recycle`. Recycling requires `target=None`; other kinds require a target. Ordinary files require a captured source fingerprint; directory operations may be represented with `None` and are explicitly refused without mutation. Sources/targets become absolute paths. A batch executes in supplied order; put supplemental copies before the primary move. Undo runs in reverse order. Invalid operation kinds raise `ValueError`; other path/preflight failures return recorded failed items. A batch can partially succeed and is not an all-or-nothing transaction.

`BatchResult` is frozen and has `batch_id`, `label`, `items: tuple[ItemResult, ...]`, and derived `ok`. An empty batch is not successful. `ItemResult` is frozen and has `operation_id`, `batch_id`, `kind`, `source`, `target`, `state`, `message`, `expected_source`, `target_fingerprint`, `staging`, `recycle_identity`, `undo_fingerprint`, and `ok`. Only `committed`, `undone`, and `recycled` are successful states. `conflict`, `recycle_unknown`, and `manual_restore` are explicitly not success; display their Chinese messages and retained paths to the user.

Task 3 must use the same state directory for all local coordinators, and atomically allocate/replan semantic versions inside `with engine.locked():`, then call `engine.execute(...)` inside that context. The lock is reentrant across same-state instances on the owning thread, excludes other threads, and uses an actual Windows byte-range lock to exclude other processes. Execute/undo/recover/history all acquire it; constructor journal initialization does too. Calling another process and waiting for it while holding this lock is not supported.

The injectable platform supplies `guard(path, destructive=False)`, `create_target(path)`, `checkpoint(stage, item)`, and `recycle(path)->RecycleOutcome(status, identity=None, message='')`. Guards provide `stream`, `fingerprint()`, `verify(expected)`, `flush()`, `remove()`, and exclusive `rename(target)` plus context management. `RecycleOutcome.status` is `recycled|failed|unknown`; optional identities are preserved in the journal. Native Windows supplies no reliable restore identity, so no automatic recycle restore is claimed. The platform must honor handle locking and no-overwrite semantics; the engine is Windows-only in this stage.

Fault/event hooks: `before_target_create`, `copy_started`, `copy_chunk`, `after_stage_verified`, `before_publish`, `after_publish`, `copy_verified`, `before_source_remove`, `source_removed`, `copy_complete`, `before_recycle_stage`, `recycle_staged`, `before_undo_remove`, `undo_after_stage_verified`, `undo_before_publish`, `undo_after_publish`, `undo_copy_verified`, `undo_target_removed`. Inject `Exception` for normal failure or `BaseException` for simulated process interruption. Item arguments are original immutable journal snapshots; read history for updated durable fields.

## Safety design

SQLite records typed operation kinds and an enumerated state constraint, source identity, target identity, temporary paths and Chinese results. Every mutation has durable write-ahead intent, using `synchronous=FULL` and an explicit committed transaction. Identity includes Windows file ID/device, size, nanosecond mtime, and SHA256. Replacement with identical size/mtime/content is refused if identity differs; same-size content edits with restored mtime are refused by hash.

All transfers use the same cross-volume-capable copy algorithm, including same-volume moves. The destination is a unique sibling `.filehub-<UUID>.tmp`; its bytes are flushed and SHA256 verified. Journal `publishing` stores its fingerprint before an atomic handle-based rename with `ReplaceIfExists=False`. Only then is `copied` recorded. Moves record `removing_source`, reverify source and target, and remove the original using its already-held DELETE handle. The verified target guard stays held until source deletion completes. Undo(move) similarly copies to a sibling `.filehub-undo-<UUID>.tmp`, records `undo_publishing`, atomically publishes the original name, then removes its guarded target while the restored survivor is still protected.

Windows guards deny write/delete sharing and bind identity verification and destructive actions to the same handle. Real concurrent writes, unlinks and renames are denied. Exclusive `CREATE_NEW` staging and no-overwrite rename preserve an external occupant arriving just before publication. Reparse points/junctions in any existing source or target parent component are rejected before resolving paths. Sources/targets cannot overlap each other or the state directory. Download temporary files and Office lock files are skipped. Folders are explicitly refused pending Task 4.

Undo(copy) holds a second guard on the original source and requires matching size/SHA256 before removing the unchanged copy. This accepts a newly recreated source from a prior move undo despite its new file ID. A missing/edited source, or a failed primary move undo leaving the supplemental copy as the last original content, causes conflict and keeps that copy. Occupied original names and edited/replaced targets are also preserved.

Recovery never continues destructive source removal or removes temporary copies. Incomplete/unverified staging remains conflict, with paths retained. A publishing-stage copy may be classified committed only if its final target matches the recorded fingerprint and its staging is gone. A move is classified committed only after a durable source-removal intent, an absent source, and a matching final target. Verified duplicates where source removal never completed remain explicit conflict. Interrupted recycle staging may be restored by a guarded no-overwrite rename, otherwise its location or unknown recycle outcome is retained. Conflict items are not silently retried.

Native recycle uses `IFileOperation` with mandatory `FOFX_RECYCLEONDELETE`, `FOFX_EARLYFAILURE` and undo flags; it refuses non-fixed drives. It does not use legacy delete-with-optional-undo, generic send2trash, or an unlink fallback. The source is first fingerprint-verified and renamed by handle to `<original stem>.filehub-<short UUID><suffix>`, with that path journaled before mutation. Failure restores it only when fingerprint and original-name availability allow; otherwise staging is retained. Successful native undo returns `manual_restore`, including the exact recycle name and original destination. Unknown return/missing staging becomes `recycle_unknown`, never a success.

## TDD and validation evidence

All tests mutate workspace `sandbox/pytest-tmp` only; `tests/conftest.py` creates its parent without clearing the larger sandbox. No global Python dependency was installed.

- Initial setup exposed missing pytest/imports and a missing basetemp parent; these were corrected before the behavioral RED run. Constructor/method stubs then produced the intended `NotImplementedError` failures: `.venv\Scripts\python.exe -X utf8 -m pytest -q` -> **19 failed**. First implementation -> **19 passed in 1.40s**.
- A new survivor-lifetime regression failed because the target guard originally closed before source deletion completed. It was fixed so deletion completes under the held survivor guard. The guard test also initially attempted to capture through a DELETE-held handle; its setup was corrected to capture before locking. Expanded suite -> **38 passed in 2.10s**.
- A new undo(move) survivor-lifetime regression produced **1 failed, 3 passed, 39 deselected**, then the target handle was closed under the held restored-source guard -> **42 passed, 1 deselected in 1.93s**.
- Unknown journal-state RED: `pytest -q tests/test_journal.py` -> **1 failed, 1 passed** (`DID NOT RAISE IntegrityError`). SQLite state CHECK added; full suite -> **44 passed in 2.52s**.
- Astra's copy-undo sole-original finding plus atomic publication tests were added before implementation: `pytest -q -k 'sole_original or supplemental or atomic_publication or race_at_publish'` -> **13 failed, 44 deselected**. Failures showed unsafe successful copy undo and missing publication hooks. Survivor guard and forward/undo atomic staging fixed them -> **56 passed, 1 deselected in 2.68s**. Added final publish-race and copy-survivor race coverage.
- Final full command: `.venv\Scripts\python.exe -X utf8 -m pytest -q` -> **59 passed in 3.45s**. No warnings or unresolved test failures. `git diff --cached --check` is checked before commit; an initial extra pyproject EOF blank was corrected.

Coverage includes no overwrite at preflight/create/publish; Chinese/spaced paths; stale/replaced/edited identities; content edits with same size and mtime; batch undo; sole-original copy preservation; locked sources; real write/delete/rename sharing denial; same-state thread serialization, reentrant allocation and a READY-handshaked second-process lock; directory/reparse/state/temporary-file rejection; copy interruption/IO failures; lost/replaced verified targets; forward and reverse staging/rename/journal crash points; recycle failure, unknown result, staging recovery, original-name conflict, and manual restore.

Cross-volume interruption is tested through the same unconditional copy+verify+delete implementation on F: with injected fault checkpoints; this is not a real second-volume hardware test. BaseException hooks model process interruption at deterministic boundaries; power loss and abrupt OS termination are not tested here.

## Actual Windows recycle acceptance

The native API moved a 32-byte, explicitly named workspace test file into the real Windows recycle bin. A PowerShell `Shell.Application.Namespace(10)` query matched only the exact staged test name and returned `FOUND`; it did not print unrelated recycle entries. Undo returned `manual_restore`. The first query had a PowerShell `$args` scope issue; the script was corrected and native acceptance passed. Some earlier runs therefore also left small clearly named FileHub sandbox test entries; no user recycle items were changed.

Final test receipt source: `F:\Hazel Windows\sandbox\pytest-tmp\test_native_recycle_is_present0\FileHub_sandbox_recycle_05d229609411408886e0675572cff62c.txt`; recycle name from that run: `FileHub_sandbox_recycle_05d229609411408886e0675572cff62c.filehub-0d6126c1.txt`. Native receipts are appended to `sandbox/native-recycle-receipts.jsonl` with source, exact staged name, `FOUND`, and `manual_restore`; they remain in the recycle bin for manual inspection. No permanent cleanup was attempted.

## Self-review and limits

Read the full staged production diff, reviewed write-ahead ordering and guard lifetimes, and checked scoped staging. Controller-owned brief/plan/ledger changes are excluded from the commit. Safety fixes found during pre-review are included, with regression evidence above.

Native recycle has no reliable programmatic item token and requires manual restore. Folder support belongs to Task 4. Copies preserve contents, not timestamps, ACLs or alternate data streams; moves currently use this copy path and undo creates a fresh file identity. The state directory must be local app state; there is no distributed lock for cloud-sync peers. Conflict/unknown records preserve files and require manual reconciliation; rollback does not automatically delete incomplete staging. Very long original names may prevent a readable recycle staging name and fail safely without truncation. Config migration, UI presentation and future managed-directory overlap checks belong to later tasks.

## Fix round 1 — Windows times and NTFS named-stream preservation

Review base: `e6a729cafb103700643e1617cfbb34f66a3adb22`. This fix **supersedes the preceding timestamps/ADS limitation**. Copy, move and move undo now preserve exact Windows creation and last-write times and all enumerated named `$DATA` streams, including ordinary downloaded-file `Zone.Identifier` and user-defined Chinese stream names. ACL/security descriptors retain target-directory inheritance; full ACL cloning and access-time preservation are not part of this change. EFS-encrypted sources are explicitly refused before any plaintext copy, rather than silently losing encryption semantics. EFS attribute testing is injected; the user's machine was not configured for EFS.

New helper: `src/filehub/platform/metadata.py` wraps `GetFileTime/SetFileTime`, `FindFirstStreamW/FindNextStreamW`, `GetFinalPathNameByHandleW`, and `GetFileInformationByHandleEx(FileStandardInfo)`. It gets stream paths from the actual main-file handle, including after rename. Named streams are copied with exclusive stream creation to the existing unpublished sibling staging file, flushed, individually SHA256 verified, then held read-only. Creation/lastwrite are set after named-stream writer handles close, and exact readback is required. The completed file fingerprint is checked again after closing the publishing handle and taking the survivor guard. Unsupported stream enumeration/type, unreadable/busy streams, unsupported destination streams, failed stream copy or failed/exact-time write all stop before source removal and keep the original.

Updated interfaces:

```python
StreamFingerprint(name: str, size: int, sha256: str)  # frozen
Fingerprint(device, file_id, size, mtime_ns, sha256,
            creation_ns: int = 0,
            streams: tuple[StreamFingerprint, ...] = ())
Fingerprint.same_primary_content(other) -> bool  # main size + SHA256 only
Fingerprint.same_content(other) -> bool  # main + every named-stream name/size/hash
Fingerprint.from_dict(value) -> Fingerprint  # typed nested journal roundtrip
Guard.close()  # idempotently closes ALL named streams and main handle
Guard.copy_metadata_from(source_guard, checkpoint)  # internal transfer interface
```

`same_primary_content` is the business duplicate check for Task 3, consistent with the original main-file dedup rule. ADS differences do not block business dedup; duplicate removal still uses recycle, retaining its original ADS. `same_content` is the stronger safe-survivor comparison used before deleting a supplemental copy: all original named-stream content must have another verified survivor. Neither content comparator includes file identity or creation/mtime; strict fingerprint equality still includes identity, both times, main hash and the complete stream inventory. Old development journal fingerprints missing new fields decode conservatively with defaults and will not authorize deletion against a new full fingerprint.

Real Windows sharing experiments exposed an important distinction: a persistent stream reader with `FILE_SHARE_DELETE` prevents writes but does not prevent stream `DeleteFile`; denying DELETE sharing is incompatible with the owning main DELETE handle (`WinError 32`). Therefore deletion candidates hold persistent weak ADS readers (deny writes, allow DELETE), whereas survivors hold a non-DELETE main handle and strong ADS readers (deny both writes and DELETE). After atomic publication, the engine closes the publishing guard, obtains the strong survivor guard, and matches the full fingerprint before permitting original removal. During this takeover gap the original deletion candidate still exists; changing the published/restored file causes conflict and preserves it. Undo(move) uses the same takeover. Undo(copy) protects its surviving source with a strong guard throughout.

Delete-pending ADS can remain visible to stream enumeration and readable through the existing weak handle. Checking `FileStandardInfo.DeletePending` before and after each stream hash catches this case and stops source removal. `Guard.close()` closes all ADS and the main file while its strong survivor remains held; closing only the primary stream would defer the actual file deletion and recreate the earlier guard-lifetime risk. Tests confirm the deletion candidate is already absent while attempts to delete the surviving file or its Zone stream still fail. This does not claim one Windows handle can freeze all arbitrary future new stream names: inventory and delete-pending checks detect changes, existing streams are persistently guarded, and the verified complete survivor remains protected through destructive transitions.

New fault hooks: `named_stream_chunk`, `before_metadata_set`, `before_survivor_guard`, `before_undo_survivor_guard`. No public operation/journal state names changed.

TDD evidence:

- `.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_metadata.py` initially produced **10 failed in 0.60s**, showing altered creation times, lost real ADS, accepted ADS-only stale previews/undo, missing stream fingerprints, and unsafe supplemental-copy deletion. Initial metadata implementation produced **10 passed in 0.66s**.
- Persistent-stream sharing/EFS additions produced **3 failed, 16 passed in 1.20s**. Real ADS writes were denied, but ADS unlink succeeded and EFS was not refused. A trial no-DELETE reader caused **9 failed, 10 passed in 0.69s** with genuine Windows sharing violations. Strong-survivor takeover, full-handle close, and EFS refusal then produced **19 passed in 1.02s**.
- A new weak-source stream-unlink regression made the full suite **1 failed, 83 passed in 5.26s**: enumeration still saw a delete-pending stream and the operation incorrectly committed. `FileStandardInfo.DeletePending` checking fixed it; focused regression -> **1 passed in 0.12s**.
- Final full command `.venv\Scripts\python.exe -X utf8 -m pytest -q` -> **84 passed in 5.26s**, no warnings or remaining failures. This includes all prior safety tests and the native recycle acceptance again.

Additional real NTFS coverage: source creation/mtime preservation for copy and move plus move undo; real Zone.Identifier and Unicode user ADS transfer and restoration; ADS-only edit/add/remove with main times restored; typed journal roundtrip; target ADS-only edit blocks undo/recovery; business main equality differs from safe full-content equality; source/target stream writes denied; strong target ADS unlink denied; undo restored/archived streams guarded; publish-to-strong-guard gap edits preserve the deletion candidate; all stream handles close under a guarded survivor; delete-pending source ADS stops source removal. Unsupported-target filesystem, metadata IO failure, and EFS checks are deterministic injected tests, not real FAT/exFAT or EFS hardware acceptance. All filesystem tests remain under workspace sandbox. Native recycle receipts continue to be recorded in `sandbox/native-recycle-receipts.jsonl`; no user files or unrelated recycle items were changed.

Self-review: read all modified production diff and the new helper, reviewed file-time ordering, named-stream resource closure, source/survivor sharing and the takeover gap, then staged only this fix and report. No UI/rules/controller-document changes are included.
