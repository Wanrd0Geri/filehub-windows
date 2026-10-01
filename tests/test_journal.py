from filehub.journal import Journal
from filehub.models import Fingerprint, Operation
import sqlite3
import pytest


def test_write_ahead_operation_persists_typed_identity(tmp_path):
    s = tmp_path / "source"
    s.write_bytes(b"abc")
    path = tmp_path / "state.sqlite"
    j = Journal(path)
    batch = j.create_batch("测试", [Operation("copy", s, tmp_path / "target", Fingerprint.capture(s))])
    item = Journal(path).items(batch)[0]
    assert item.kind == "copy" and item.state == "prepared"
    assert item.expected_source == Fingerprint.capture(s)
    assert Journal(path).history()[0].batch_id == batch


def test_journal_rejects_unknown_state_instead_of_false_recovery(tmp_path):
    s = tmp_path / "source"
    s.write_bytes(b"abc")
    j = Journal(tmp_path / "state.sqlite")
    batch = j.create_batch("x", [Operation("copy", s, tmp_path / "target", Fingerprint.capture(s))])
    item = j.items(batch)[0]
    with pytest.raises(sqlite3.IntegrityError):
        j.transition(item.operation_id, "commited_typo")
    assert j.items(batch)[0].state == "prepared"
