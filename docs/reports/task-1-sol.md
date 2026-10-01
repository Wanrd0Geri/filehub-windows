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
