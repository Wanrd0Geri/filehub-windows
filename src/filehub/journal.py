"""Durable typed write-ahead records. Each transition commits before mutation."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from .models import BatchResult, Fingerprint, ItemResult


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tree_children(parent TEXT NOT NULL,child TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS tree_lineage(previous_operation TEXT NOT NULL,restoration_operation TEXT NOT NULL,old_fp TEXT NOT NULL,new_fp TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tree_inverse_roots(operation TEXT PRIMARY KEY,directories TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tree_undo_blocks(operation TEXT PRIMARY KEY,reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, label TEXT NOT NULL,
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    ordinal INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('move','copy','recycle')),
                    source TEXT NOT NULL, target TEXT, expected TEXT,
                    state TEXT NOT NULL CHECK(state IN (
                        'prepared','copying','publishing','copied','removing_source','committed',
                        'staging_recycle','recycling','recycled','recycle_unknown',
                        'undo_removing_copy','undo_copying','undo_publishing','undo_copied','undo_removing_target',
                        'undone','failed','conflict','manual_restore')),
                    message TEXT NOT NULL DEFAULT '',
                    target_fp TEXT, staging TEXT, recycle_identity TEXT, undo_fp TEXT);
            """)

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
