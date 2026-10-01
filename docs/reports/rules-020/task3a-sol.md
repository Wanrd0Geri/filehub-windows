# Task3A — frozen guarded generated-image publication

Task3A scope is complete and frozen for Astra review. Owned files are
`src/filehub/generated.py`, narrow generated dispatch/file inverse changes in
`src/filehub/operations.py`, migration/generated metadata/lineage additions in
`src/filehub/journal.py`, `tests/test_generated.py`, and this report. The image
backend, templates, automation models/planner/service/scheduler/UI and packaging
were not edited. Work and subprocess crash fixtures stayed under this new
worktree's owned sandbox. No stage/commit, installation, pip, live FileHub state,
registry, user-file operations, full suite or child agents.

## Frozen integration API

Public publication signature remains:

```python
OperationEngine.publish_generated(
    source: Path, target: Path, expected_source: Fingerprint,
    staging: OwnedStaging, expected_output: Fingerprint, label: str,
    *, mode: Literal['keep', 'replace'] = 'keep',
    batch_id: str | None = None, cancel_event: Event | None = None,
) -> BatchResult
```

The brief's Path staging parameter is intentionally tightened to the approved
`OwnedStaging` value object. A bare Path, forged equivalent object, consumed
ticket, or ticket issued for another engine is rejected as an explicit failed
`convert` record. This avoids claiming any arbitrary caller path was generated.
`execute()` still rejects convert; it never routes conversion through byte copy.

The wrapper around the unchanged frozen generator is:

```python
filehub.generated.generate_owned(
    engine: OperationEngine, source: Path, target: Path,
    spec: ConversionSpec | None = None,
    cancel_event: Event | None = None, progress: Callable | None = None,
    *, expected_source: Fingerprint | None = None,
    expected_capability_digest: str | None = None,
) -> OwnedStaging

filehub.generated.discard_owned(engine: OperationEngine, staging: OwnedStaging) -> None
```

These are type-contract descriptions; the implementation retains the project's
existing mostly unannotated method style. Generation does not acquire the engine
process lock. The helper requires the engine so it can reject state sources,
state targets and reparse/containment-invalid parents before creating a sibling
`.filehub-generated-<UUID>.tmp`. It uses the frozen generator's actual Qt encode,
format/dimensions validation and closed fingerprints.

`OwnedStaging` is a frozen dataclass with `path`, `source`, `target`,
`source_fingerprint`, `output_fingerprint`, `spec`, `result`, `owner`, and `token`.
`result` is the unchanged `ConversionResult` (format/dimensions/warnings remain
available to integration). The process registry admits only the exact issued
object and exact engine instance; source/target/fingerprints must match at
publication. A ticket is consumed once after matching publication preflight,
before any material transaction. Invalid binding/preflight does not transfer
ownership; the original issuer can discard the still-owned staging. Discard
consumes its ticket and removes only a held, exact-fingerprint artifact.

Task3B must pass the plan's expected source and codec digest to generation, bind
the exact spec/target and current rule/template/generation snapshots, stop future
steps when cancel is set, and use this publication path rather than implement a
second transaction. Exact engine binding rejects old demo/service capabilities.
For each successful later step, follow the actual journal target fingerprint:
same-path publication can change the OS creation timestamp as described below.

`Journal.generated(operation_id) -> GeneratedRecord` exposes `mode`, `phase`,
`backup`, `backup_fingerprint`, `swap`, `undo_stage`, and `undo_swap`. Standard
history/BatchResult keeps kind `convert`, distinct original `expected_source`
and generated `target_fingerprint`, and actionable backup/swap locations in
conflicts. Existing ItemResult/Operation models remain unchanged.

## Publication and inverse transitions

Every row intent commits with synchronous FULL before its corresponding file
mutation. `generated_operations.phase` refines the existing valid engine state;
no ordinary state checks or public state-directory protection were expanded.

| Phase | Existing state | Bound action and survivor guarantee |
| --- | --- | --- |
| prepared | prepared | Exact issued output/source recorded, cancellation checked; no source mutation |
| backing_up | copying | Private backup location durably recorded; original held unchanged |
| backed_up | copied | Complete bytes/ADS/both times verified and flushed; fingerprint durable |
| swapping (same path only) | publishing | Held original renamed exclusively to operation-owned sibling swap |
| publishing | publishing | Held generated staging renamed without overwrite; actual output identity bound |
| removing_original | removing_source | Original/swap, generated survivor and intact backup all guarded and verified before bound original removal |
| committed | committed | Complete keep or real replace; replace message includes retained backup |
| rollback_removing_output / rollback_restoring_original | removing_source / publishing | Ordinary failure removes only guarded exact output, then returns held original swap into a vacant name |
| aborted | failed | Unstarted/rolled-back operation; original preserved/restored, exact stage cleaned when safe |
| undo_swapping / undo_copying | undo_copying | Same-path generated output guarded into owned undo swap; complete original copied from verified backup |
| undo_publishing | undo_publishing | Verified restored original published exclusively into vacant original name |
| undo_removing_output | undo_removing_copy / undo_removing_target | Untouched original (keep) or restored guarded original plus backup (replace) verified before exact generated removal |
| undone | undone | Inverse completed; replace backups remain retained |

Backup paths are solely trusted-code values:
`checked state_dir/conversion-backups/<32-hex-operation-UUID>/<original filename>`.
They are never accepted from UI/rule/import data. Private record access rechecks
this exact location and all swap/restore names. Existing `_copy` preserves full
bytes, every ADS and exact creation/last-write timestamps with held handles,
flush and full-stream verification. Backup failure precedes source mutation.
No retention/expiry or automatic backup removal exists.

Cross-extension replace atomically publishes and verifies new output while the
original remains pinned, then removes the exact held original only while verified
output and backup are protected. Same-path, including Windows case aliases,
renames the held original into its owned swap, publishes into the vacant name,
then verifies output/backup before removing the held swap. External occupied
targets, other batch-selected sources, state paths and reparse paths are rejected.
Same-name exceptions apply solely to the bound original in replace mode.

Cancellation before critical intent aborts with the source unchanged and no final
publication. Cancellation inside publication/removal does not strand an empty
original path: this item safely settles and reports committed with a cancellation
message; integration must stop following items. Runtime failure after a verified
publish rolls back with all survivors guarded when ownership is conclusive.
An external occupant or uncertain ownership preserves every recoverable copy.

NTFS name tunneling was reproduced with real JPEG recompression: rename into the
recently vacated original name inherits its creation time. Only this same-path
transaction accepts that OS effect from the continuously held owned output
handle, while file ID/device/full bytes/ADS/size/mtime remain exactly unchanged.
The actual published fingerprint is durable before survivor checks/success.
Cross-path/ordinary transfers do not receive this exception. Original restoration
uses its exclusively created writable handle to set backup times after rename,
preventing tunneling from changing the restored original timestamps.

## Conservative recovery and undo

Recovery never re-encodes or replays uncertain source/output removals. A verified
backup and exact bound swap may restore the original only into a vacant path.
Publication with original/swap and output both surviving is a conflict after a
crash; copies and locations are retained. Completed source removal is classified
committed only with durable remove intent, verified output and backup, and the
intended original/swap truly absent. Missing/mutated backups, originals, outputs
or external occupants preserve data and report conflicts. A crash between owned
same-path rename and durable output-fingerprint rebinding preserves backup/swap
and reports conflict. Recovery is idempotent and does not revisit stable conflicts.

Keep undo checks the exact untouched original and separately checks generated
output; intentionally different bytes never enter copy-style survivor logic.
Replace undo checks output plus exact backup, restores the full original before
generated removal, and refuses occupied original paths. Same-path undo exchanges
only the guarded bound output into an owned undo swap, then restores exclusively.
Interrupted undo is complete only when restored identity and output absence
conclusively match durable intent; otherwise original/backup/generated swap are
retained. Already-undone calls do not perform another inverse.

`file_lineage` stores previous operation, verified restoration operation, exact
old fingerprint and actual new fingerprint. `_complete_file_inverse` is called
only with the restored survivor pinned, after the exact inverse target was
removed and full original content/ADS/timestamps verified. It atomically updates
an earlier still-committed target only when both path and *complete original
input identity* match, then records the completed inverse. Undo refreshes each
earlier item so it sees durable lineage produced by later inverse steps. This
supports move→rename, copy→rename→move and conversion→rename→move within/shared
batches; exact identity ownership is not replaced with arbitrary hash equality.
The existing approved copy-source survivor policy is unchanged. Existing tree
inverse/lineage behavior passed its directory regression suite.

## Old-journal migration

Before adding tables, check SQLite quick integrity and all existing foreign keys;
broken databases fail rather than receive apparent migration success. Recognize
the released `move,copy,recycle` CHECK and rebuild only `operations`, adding
`convert` to that kind CHECK while retaining the complete original column/state
constraints. Foreign keys are suspended outside `BEGIN IMMEDIATE`, so all dependent
tables continue referring to the unchanged final `operations` name. Copy every
column and row, swap the table within the transaction, recreate its explicit
indices/triggers from stored SQL, run FK/integrity checks and commit. Any copy,
rename, index/trigger or validation failure rolls back transactional DDL; FK checks
are reenabled. The existing convert schema is idempotent. Other batches, tree,
notification, outcome tables/rows and dependent FK definitions remain untouched.

Tests exercise authentic released CHECK/column/state schema plus old records,
all tree tables, notifications/outcomes, index/trigger preservation, successful
convert insertion and reopen, corrupted FK refusal, and injected index recreation
failure *after* copy/drop/rename proving the old table and index return intact.

## Evidence and limits

Initial RED was 11 failed/1 passed: generated API absent and real file chain undo
failed after inverse recreation changed Windows file identity. The first focused
GREEN was 71 passed. Expanded final command:

```powershell
$env:PYTHONPATH='src'
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_generated.py tests/test_operations.py tests/test_journal.py tests/test_directories.py --basetemp=sandbox/task3a-focused -q --junitxml=sandbox/task3a-focused-results.xml
```

Result: **163 passed in 15.47s, no failures/skips**. Astra independently reran the
same scope: **163 passed in 15.52s**. No full suite was run. Tests use actual
small Qt-generated image artifacts, not byte-copy fake images, plus injected
platform checkpoints. Coverage includes keep/replace/cross-extension/same-path
case variants; complete ADS/time backup and undo; invalid/mutated staging/source;
state/junction/public backup bypasses; occupied targets and selected-source
overlap; writer-blocking survivor guards; backup write/metadata/verification
failure; cancellation before and inside critical phases; missing/edited backup,
source and output; rollback; repeated undo; general inverse chains and directory
regressions. Three real child-process `os._exit(77)` fixtures prove reopened
recovery at original swap, publication-before-fingerprint-rebind, and completed
source removal. Injected interrupted undo verifies original/backup retention.

One deliberate limitation: process death after generation but before publication
intent can leave an unjournaled verified hidden staging artifact. Its in-memory
capability dies with the process; recovery does not invent ownership or delete
such an orphan. Once publication intent exists, exact owned staging is handled
by durable journal evidence. Incomplete/uncertain backups, swaps and inverse
staging are retained on conflict; there is no cleanup/expiry feature. Standalone
UI/rule preview, cancellation scheduling, ledger/executor integration and final
combined source/installer acceptance remain later tasks.

Implementation, tests and this report are frozen for controller review/commit.
