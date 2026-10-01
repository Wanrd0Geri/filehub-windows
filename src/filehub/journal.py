"""Durable typed write-ahead records. Each transition commits before mutation."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid
import re
from dataclasses import dataclass

from .models import BatchResult, Fingerprint, ItemResult


@dataclass(frozen=True)
class GeneratedRecord:
    mode: str
    phase: str
    backup: Path | None
    backup_fingerprint: Fingerprint | None
    swap: Path | None
    undo_stage: Path | None
    undo_swap: Path | None


def _migrate_operations(db):
    """Rebuild only the old kind CHECK, retaining all columns and SQL objects.

    Foreign keys are suspended outside the transaction; table names in dependent
    tables never change. Failure rolls back the entire rebuild, including DDL.
    """
    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise sqlite3.DatabaseError('Journal integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise sqlite3.IntegrityError('Journal has broken foreign keys')
    row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='operations'").fetchone()
    if row is None:
        return
    old = row[0]
    pattern = r"CHECK\s*\(\s*kind\s+IN\s*\(\s*'move'\s*,\s*'copy'\s*,\s*'recycle'\s*\)\s*\)"
    updated, count = re.subn(pattern, "CHECK(kind IN ('move','copy','recycle','convert'))", old, flags=re.I)
    if not count:
        if not re.search(r"CHECK\s*\(\s*kind\s+IN\s*\([^)]*'convert'", old, re.I):
            raise sqlite3.DatabaseError('Unrecognized operations schema; migration refused')
        return
    if count != 1:
        raise sqlite3.DatabaseError('Ambiguous operations schema')
    objects = db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='operations' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        updated = re.sub(r'^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)["`\[]?operations["`\]]?', r'\1operations_convert_migration', updated, count=1, flags=re.I)
        db.execute(updated)
        columns = [r[1] for r in db.execute('PRAGMA table_info(operations)')]
        names = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
        db.execute(f'INSERT INTO operations_convert_migration({names}) SELECT {names} FROM operations')
        db.execute('DROP TABLE operations')
        db.execute('ALTER TABLE operations_convert_migration RENAME TO operations')
        for sql in objects:
            db.execute(sql[0])
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise sqlite3.IntegrityError('Journal migration validation failed')
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute('PRAGMA foreign_keys=ON')


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            _migrate_operations(db)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS generated_operations(
                    operation TEXT PRIMARY KEY REFERENCES operations(id),
                    mode TEXT NOT NULL CHECK(mode IN ('keep','replace')),
                    phase TEXT NOT NULL,backup TEXT,backup_fp TEXT,swap TEXT,
                    undo_stage TEXT,undo_swap TEXT);
                CREATE TABLE IF NOT EXISTS file_lineage(
                    previous_operation TEXT NOT NULL REFERENCES operations(id),
                    restoration_operation TEXT NOT NULL REFERENCES operations(id),
                    old_fp TEXT NOT NULL,new_fp TEXT NOT NULL,
                    UNIQUE(previous_operation,restoration_operation,old_fp,new_fp));
                CREATE TABLE IF NOT EXISTS tree_children(parent TEXT NOT NULL,child TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS tree_lineage(previous_operation TEXT NOT NULL,restoration_operation TEXT NOT NULL,old_fp TEXT NOT NULL,new_fp TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tree_inverse_roots(operation TEXT PRIMARY KEY,directories TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tree_undo_blocks(operation TEXT PRIMARY KEY,reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, label TEXT NOT NULL,
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    ordinal INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('move','copy','recycle','convert')),
                    source TEXT NOT NULL, target TEXT, expected TEXT,
                    state TEXT NOT NULL CHECK(state IN (
                        'prepared','copying','publishing','copied','removing_source','committed',
                        'staging_recycle','recycling','recycled','recycle_unknown',
                        'undo_removing_copy','undo_copying','undo_publishing','undo_copied','undo_removing_target',
                        'undone','failed','conflict','manual_restore')),
                    message TEXT NOT NULL DEFAULT '',
                    target_fp TEXT, staging TEXT, recycle_identity TEXT, undo_fp TEXT);
            """)

    def create_generated(self, operation_id, mode, staging, expected_output):
        with self.connection() as db:
            db.execute('INSERT INTO generated_operations(operation,mode,phase) VALUES(?,?,?)', (operation_id, mode, 'prepared'))
            db.execute('UPDATE operations SET staging=?,target_fp=? WHERE id=?', (str(staging), self.encode(expected_output), operation_id))

    def generated(self, operation_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM generated_operations WHERE operation=?', (operation_id,)).fetchone()
        if row is None:
            raise ValueError('Missing generated-operation ownership record')
        return GeneratedRecord(row['mode'], row['phase'], Path(row['backup']) if row['backup'] else None,
                               self.decode(row['backup_fp']), Path(row['swap']) if row['swap'] else None,
                               Path(row['undo_stage']) if row['undo_stage'] else None,
                               Path(row['undo_swap']) if row['undo_swap'] else None)

    def generated_transition(self, operation_id, phase, state, message='', **fields):
        allowed = {'backup', 'backup_fp', 'swap', 'undo_stage', 'undo_swap'}
        if fields.keys() - allowed:
            raise ValueError('Unknown generated field')
        fields = {key: self.encode(value) if key == 'backup_fp' else str(value) if value else None
                  for key, value in fields.items()}
        with self.connection() as db:
            db.execute('UPDATE generated_operations SET ' + ','.join(f'{key}=?' for key in ('phase', *fields)) +
                       ' WHERE operation=?', (phase, *fields.values(), operation_id))
            db.execute('UPDATE operations SET state=?,message=? WHERE id=?', (state, message, operation_id))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def encode(fp):
        return json.dumps(fp.to_dict()) if fp is not None else None

    @staticmethod
    def decode(fp):
        return Fingerprint.from_dict(json.loads(fp)) if fp else None

    def create_batch(self, label, operations) -> str:
        batch_id = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO batches(id,label) VALUES(?,?)", (batch_id, label))
        self.append_operations(batch_id,operations)
        return batch_id

    def append_operations(self,batch_id,operations):
        ids=[]
        with self.connection() as db:
            if db.execute('SELECT id FROM batches WHERE id=?',(batch_id,)).fetchone() is None:
                raise KeyError(batch_id)
            start=db.execute('SELECT COALESCE(MAX(ordinal)+1,0) FROM operations WHERE batch_id=?',(batch_id,)).fetchone()[0]
            for ordinal, op in enumerate(operations,start):
                operation_id=uuid.uuid4().hex;ids.append(operation_id)
                db.execute("""INSERT INTO operations
                    (id,batch_id,ordinal,kind,source,target,expected,state)
                    VALUES(?,?,?,?,?,?,?,'prepared')""", (
                    operation_id, batch_id, ordinal, op.kind, str(op.source),
                    str(op.target) if op.target else None, self.encode(op.expected_source)))
        return ids

    def transition(self, operation_id, state, message="", **fields):
        allowed = {"target_fp", "staging", "recycle_identity", "undo_fp"}
        if fields.keys() - allowed:
            raise ValueError("Unknown journal field")
        values = {"state": state, "message": message, **fields}
        for key in {"target_fp", "undo_fp"} & values.keys():
            values[key] = self.encode(values[key])
        for key in {"staging"} & values.keys():
            values[key] = str(values[key]) if values[key] else None
        with self.connection() as db:
            db.execute("UPDATE operations SET " + ",".join(f"{key}=?" for key in values) +
                       " WHERE id=?", (*values.values(), operation_id))

    def items(self, batch_id):
        with self.connection() as db:
            rows = db.execute("SELECT o.*,t.parent AS parent_id FROM operations o LEFT JOIN tree_children t ON t.child=o.id WHERE o.batch_id=? ORDER BY ordinal", (batch_id,)).fetchall()
        return [ItemResult(
            r["id"], r["batch_id"], r["kind"], Path(r["source"]),
            Path(r["target"]) if r["target"] else None, r["state"], r["message"],
            self.decode(r["expected"]), self.decode(r["target_fp"]),
            Path(r["staging"]) if r["staging"] else None, r["recycle_identity"], self.decode(r["undo_fp"]),r['parent_id']) for r in rows]

    def batch(self, batch_id):
        with self.connection() as db:
            row = db.execute("SELECT label,created FROM batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise KeyError(batch_id)
        return BatchResult(batch_id, row["label"], tuple(self.items(batch_id)), row['created'])

    def history(self):
        with self.connection() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM batches ORDER BY created DESC,rowid DESC")]
        return [self.batch(batch_id) for batch_id in ids]
