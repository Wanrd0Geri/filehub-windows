"""Owned real-image publication and backed-up replacement, Windows sandbox only."""
import importlib
import sqlite3
import threading
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from PySide6.QtGui import QImage, QColor

from filehub.models import Fingerprint, Operation
from filehub.operations import OperationEngine
from filehub.platform.windows import WindowsPlatform


def image(root, name='original.png'):
    path = root / name
    value = QImage(19, 13, QImage.Format.Format_ARGB32)
    value.fill(QColor('#307080'))
    assert value.save(str(path), 'JPEG' if path.suffix == '.jpg' else 'PNG')
    return path


def generated(engine, source, target, **kwargs):
    api = importlib.import_module('filehub.generated')
    from filehub.conversion import ConversionSpec
    return api.generate_owned(engine, source, target, ConversionSpec(output_format='jpeg'), **kwargs)


def publish(engine, source, target, stage, **kwargs):
    return engine.publish_generated(source, target, stage.source_fingerprint, stage,
                                    stage.output_fingerprint, '图片转换', **kwargs)


@pytest.mark.parametrize('mode,same', [('keep', False), ('replace', False), ('replace', True)])
def test_real_publication_and_undo(tmp_path, mode, same):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    before = Fingerprint.capture(source)
    original = source.read_bytes()
    target = source if same else tmp_path / 'original.jpg'
    engine = OperationEngine(tmp_path / 'state')
    stage = generated(engine, source, target)
    result = publish(engine, source, target, stage, mode=mode)
    assert result.ok and result.items[0].kind == 'convert'
    assert target.read_bytes().startswith(b'\xff\xd8')
    assert source.exists() == (mode == 'keep' or same)
    if mode == 'replace':
        record = engine.journal.generated(result.items[0].operation_id)
        assert record.backup.read_bytes() == original
        backup = Fingerprint.capture(record.backup)
        assert backup.same_content(before)
        assert (backup.creation_ns, backup.mtime_ns) == (before.creation_ns, before.mtime_ns)
        if same:
            assert result.items[0].target_fingerprint == Fingerprint.capture(target)
            assert result.items[0].target_fingerprint.creation_ns == before.creation_ns
    assert engine.undo(result.batch_id).ok
    assert source.read_bytes() == original
    assert engine.undo(result.batch_id).ok
    if not same:
        assert not target.exists()


def test_bare_staging_and_reused_capability_rejected(tmp_path):
    source = image(tmp_path)
    target = tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    stage = generated(engine, source, target)
    result = engine.publish_generated(source, target, stage.source_fingerprint, stage.path,
                                     stage.output_fingerprint, 'unowned')
    assert not result.ok and not target.exists()
    assert publish(engine, source, target, stage).ok
    assert not publish(engine, source, tmp_path / 'other.jpg', stage).ok


@pytest.mark.parametrize('what', ['source', 'stage', 'occupied', 'state'])
def test_invalid_inputs_preserve_original(tmp_path, what):
    source = image(tmp_path)
    target = tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    stage = generated(engine, source, target)
    if what == 'source':
        source.write_bytes(b'changed')
    elif what == 'stage':
        stage.path.write_bytes(b'changed')
    elif what == 'occupied':
        target.write_bytes(b'foreign')
    else:
        target = engine.state_dir / 'out.jpg'
    before = source.read_bytes()
    assert not publish(engine, source, target, stage, mode='replace').ok
    assert source.read_bytes() == before
    if what == 'occupied':
        assert target.read_bytes() == b'foreign'


@pytest.mark.parametrize('kind', ['move', 'copy', 'convert'])
def test_inverse_lineage_chain(tmp_path, kind):
    source = image(tmp_path)
    engine = OperationEngine(tmp_path / 'state')
    first = tmp_path / 'first.jpg'
    if kind == 'convert':
        stage = generated(engine, source, first)
        result = publish(engine, source, first, stage, mode='replace')
    else:
        result = engine.execute([Operation(kind, source, first, Fingerprint.capture(source))], 'chain')
    second, third = tmp_path / 'renamed.jpg', tmp_path / 'moved.jpg'
    engine.execute([Operation('move', first, second, Fingerprint.capture(first))], 'chain', batch_id=result.batch_id)
    engine.execute([Operation('move', second, third, Fingerprint.capture(second))], 'chain', batch_id=result.batch_id)
    undone = engine.undo(result.batch_id)
    assert undone.ok, [(item.state, item.message) for item in undone.items]
    assert source.exists() and not first.exists() and not second.exists() and not third.exists()


def test_old_check_schema_preserves_rows_indices_and_foreign_keys(tmp_path):
    from filehub.journal import Journal
    path = tmp_path / 'journal.sqlite'
    # Genuine released 0.1 operations schema, not a mock new convert schema.
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE batches(id TEXT PRIMARY KEY,label TEXT NOT NULL,created TEXT NOT NULL DEFAULT 'old');
        CREATE TABLE operations(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES batches(id),
        ordinal INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('move','copy','recycle')),
        source TEXT NOT NULL,target TEXT,expected TEXT,state TEXT NOT NULL CHECK(state IN
        ('prepared','copying','publishing','copied','removing_source','committed','staging_recycle',
        'recycling','recycled','recycle_unknown','undo_removing_copy','undo_copying','undo_publishing',
        'undo_copied','undo_removing_target','undone','failed','conflict','manual_restore')),
        message TEXT NOT NULL DEFAULT '',target_fp TEXT,staging TEXT,recycle_identity TEXT,undo_fp TEXT);
        CREATE INDEX old_operation_batch ON operations(batch_id);
        CREATE TABLE notifications(id INTEGER PRIMARY KEY,operation TEXT REFERENCES operations(id));
        CREATE TABLE outcomes(id TEXT PRIMARY KEY, value TEXT);
        INSERT INTO batches VALUES('batch','old','old');
        INSERT INTO operations(id,batch_id,ordinal,kind,source,state) VALUES('op','batch',0,'copy','old','failed');
        INSERT INTO notifications VALUES(7,'op');
        INSERT INTO outcomes VALUES('retained','value');
        CREATE TABLE tree_children(parent TEXT NOT NULL,child TEXT PRIMARY KEY);
        CREATE TABLE tree_lineage(previous_operation TEXT NOT NULL,restoration_operation TEXT NOT NULL,old_fp TEXT NOT NULL,new_fp TEXT NOT NULL);
        CREATE TABLE tree_inverse_roots(operation TEXT PRIMARY KEY,directories TEXT NOT NULL);
        CREATE TABLE tree_undo_blocks(operation TEXT PRIMARY KEY,reason TEXT NOT NULL);
        INSERT INTO tree_children VALUES('parent','op');
        INSERT INTO tree_lineage VALUES('prior','op','old','new');
        INSERT INTO tree_inverse_roots VALUES('op','[]');
        INSERT INTO tree_undo_blocks VALUES('op','old reason');
        CREATE TRIGGER preserved_update AFTER UPDATE OF message ON operations
        BEGIN UPDATE outcomes SET value=NEW.message WHERE id='retained'; END;
        """)
    journal = Journal(path)
    assert journal.batch('batch').items[0].operation_id == 'op'
    with journal.connection() as db:
        assert db.execute('SELECT * FROM notifications').fetchone()['operation'] == 'op'
        assert db.execute('SELECT * FROM outcomes').fetchone()['value'] == 'value'
        assert db.execute("SELECT name FROM sqlite_master WHERE name='old_operation_batch'").fetchone()
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT child FROM tree_children').fetchone()[0] == 'op'
        assert db.execute('SELECT new_fp FROM tree_lineage').fetchone()[0] == 'new'
        assert db.execute('SELECT directories FROM tree_inverse_roots').fetchone()[0] == '[]'
        assert db.execute('SELECT reason FROM tree_undo_blocks').fetchone()[0] == 'old reason'
        db.execute("INSERT INTO operations(id,batch_id,ordinal,kind,source,state) VALUES('converted','batch',1,'convert','image','failed')")
    Journal(path)  # Idempotent.
    journal.transition('op', 'failed', 'trigger survives')
    with journal.connection() as db:
        assert db.execute('SELECT value FROM outcomes').fetchone()[0] == 'trigger survives'


class Crash(BaseException):
    pass


class Fault(WindowsPlatform):
    def __init__(self, stage, action=None):
        self.stage, self.action = stage, action

    def checkpoint(self, stage, item):
        if stage == self.stage:
            if self.action:
                self.action(item)
            else:
                raise Crash(stage)


@pytest.mark.parametrize('same,stage,expected', [
    (False, 'before_generated_backup', 'failed'),
    (False, 'generated_backup_verified', 'failed'),
    (False, 'before_generated_publish', 'failed'),
    (False, 'after_generated_publish', 'conflict'),
    (False, 'before_generated_remove', 'conflict'),
    (False, 'after_generated_remove', 'committed'),
    (True, 'before_generated_swap', 'failed'),
    (True, 'after_generated_swap', 'failed'),
    (True, 'after_generated_rename_before_binding', 'conflict'),
    (True, 'after_generated_publish', 'conflict'),
    (True, 'before_generated_remove', 'conflict'),
    (True, 'after_generated_remove', 'committed'),
])
def test_interrupted_replace_reopen_never_destroys_survivors(tmp_path, same, stage, expected):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    original = source.read_bytes()
    target = source if same else tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state', Fault(stage))
    owned = generated(engine, source, target)
    with pytest.raises(Crash):
        publish(engine, source, target, owned, mode='replace')
    reopened = OperationEngine(engine.state_dir)
    recovered = reopened.recover()
    assert recovered[0].state == expected, recovered[0].message
    record = reopened.journal.generated(recovered[0].operation_id)
    if stage != 'before_generated_backup':
        assert record.backup.read_bytes() == original
    if expected == 'failed':
        assert source.read_bytes() == original
        if not same:
            assert not target.exists()
    elif expected == 'conflict':
        assert target.exists()
        assert '备份' in recovered[0].message
        if same:
            assert record.swap.read_bytes() == original
    else:
        assert target.exists() and (same or not source.exists())
    assert reopened.recover() == []


@pytest.mark.parametrize('same', [False, True])
@pytest.mark.parametrize('stage', ['generated_validated', 'before_generated_backup',
                                  'generated_backup_verified', 'before_generated_critical',
                                  'before_generated_publish', 'after_generated_publish',
                                  'before_generated_remove'])
def test_cancel_before_critical_aborts_inside_critical_settles(tmp_path, same, stage):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    original = source.read_bytes()
    target = source if same else tmp_path / 'out.jpg'
    cancel = threading.Event()
    engine = OperationEngine(tmp_path / 'state', Fault(stage, lambda item: cancel.set()))
    owned = generated(engine, source, target)
    result = publish(engine, source, target, owned, mode='replace', cancel_event=cancel)
    critical = stage in {'before_generated_publish', 'after_generated_publish', 'before_generated_remove'}
    assert result.ok == critical, result.items[0].message
    if not critical:
        assert source.read_bytes() == original and not owned.path.exists()
        if not same:
            assert not target.exists()
    else:
        assert '取消' in result.items[0].message
        assert target.exists() and (same or not source.exists())
        assert engine.undo(result.batch_id).ok
        assert source.read_bytes() == original


@pytest.mark.parametrize('stage', ['copy_chunk', 'named_stream_chunk', 'before_metadata_set'])
def test_backup_failure_keeps_full_original_and_no_final(tmp_path, stage):
    source = image(tmp_path)
    with open(str(source) + ':custom', 'wb') as stream:
        stream.write(b'original named stream')
    before = Fingerprint.capture(source)
    target = tmp_path / 'out.jpg'
    def fail(item):
        raise OSError('injected backup failure')
    engine = OperationEngine(tmp_path / 'state', Fault(stage, fail))
    owned = generated(engine, source, target)
    result = publish(engine, source, target, owned, mode='replace')
    assert not result.ok and Fingerprint.capture(source) == before
    assert not target.exists() and not owned.path.exists()


def test_backup_preserves_ads_and_both_times_and_undo(tmp_path):
    source = image(tmp_path)
    with open(str(source) + ':metadata', 'wb') as stream:
        stream.write(b'ADS must survive replacement')
    before = Fingerprint.capture(source)
    target = tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    owned = generated(engine, source, target)
    result = publish(engine, source, target, owned, mode='replace')
    assert result.ok
    saved = Fingerprint.capture(engine.journal.generated(result.items[0].operation_id).backup)
    assert saved.same_content(before) and saved.streams == before.streams
    assert (saved.creation_ns, saved.mtime_ns) == (before.creation_ns, before.mtime_ns)
    assert engine.undo(result.batch_id).ok
    restored = Fingerprint.capture(source)
    assert restored.same_content(before)
    assert (restored.creation_ns, restored.mtime_ns) == (before.creation_ns, before.mtime_ns)


@pytest.mark.parametrize('same', [False, True])
@pytest.mark.parametrize('change', ['output', 'missing_backup', 'changed_backup', 'occupied_original'])
def test_replace_undo_conflicts_retain_every_existing_file(tmp_path, same, change):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    target = source if same else tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    assert result.ok
    record = engine.journal.generated(result.items[0].operation_id)
    if change == 'output' or same and change == 'occupied_original':
        target.write_bytes(b'edited output')
    elif change == 'missing_backup':
        record.backup.unlink()
    elif change == 'changed_backup':
        record.backup.write_bytes(b'edited backup')
    else:
        source.write_bytes(b'external original occupant')
    target_content = target.read_bytes()
    original_content = source.read_bytes() if source.exists() else None
    undone = engine.undo(result.batch_id)
    assert not undone.ok and undone.items[0].state == 'conflict'
    assert target.read_bytes() == target_content
    if original_content is not None:
        assert source.read_bytes() == original_content
    assert str(record.backup) in undone.items[0].message


@pytest.mark.parametrize('change', ['source_edit', 'source_missing', 'output_edit'])
def test_keep_undo_requires_distinct_unchanged_original_and_output(tmp_path, change):
    source = image(tmp_path)
    target = tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    result = publish(engine, source, target, generated(engine, source, target))
    assert result.ok
    if change == 'source_edit':
        source.write_bytes(b'edited original')
    elif change == 'source_missing':
        source.unlink()
    else:
        target.write_bytes(b'edited generated image')
    output = target.read_bytes()
    assert not engine.undo(result.batch_id).ok
    assert target.read_bytes() == output


def test_capability_engine_binding_and_cannot_forge(tmp_path):
    source = image(tmp_path)
    target = tmp_path / 'out.jpg'
    first = OperationEngine(tmp_path / 'state')
    owned = generated(first, source, target)
    second = OperationEngine(first.state_dir)
    assert not publish(second, source, target, owned).ok
    assert not publish(first, source, target, replace(owned, token=owned.token)).ok
    assert publish(first, source, target, owned).ok


def test_same_path_case_alias_is_bound_original_only(tmp_path):
    source = image(tmp_path, 'original.jpg')
    target = source.with_name('ORIGINAL.JPG')
    original = source.read_bytes()
    engine = OperationEngine(tmp_path / 'state')
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    assert result.ok and engine.undo(result.batch_id).ok
    assert source.read_bytes() == original


@pytest.mark.parametrize('same', [False, True])
def test_publish_failure_rollback_retains_original_and_backup(tmp_path, same):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    original = source.read_bytes()
    target = source if same else tmp_path / 'out.jpg'
    def fail(item):
        raise OSError('after-publish injected failure')
    engine = OperationEngine(tmp_path / 'state', Fault('after_generated_publish', fail))
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    assert not result.ok and result.items[0].state == 'failed', result.items[0].message
    assert source.read_bytes() == original
    if not same:
        assert not target.exists()
    assert engine.journal.generated(result.items[0].operation_id).backup.read_bytes() == original


@pytest.mark.parametrize('same', [False, True])
@pytest.mark.parametrize('stage', ['after_generated_restore_publish', 'before_generated_undo_remove', 'after_generated_undo_remove'])
def test_interrupted_undo_preserves_backup_and_original(tmp_path, same, stage):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    original = source.read_bytes()
    target = source if same else tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    assert result.ok
    with pytest.raises(Crash):
        OperationEngine(engine.state_dir, Fault(stage)).undo(result.batch_id)
    reopened = OperationEngine(engine.state_dir)
    recovered = reopened.recover()
    assert source.read_bytes() == original
    assert recovered[0].state == ('undone' if stage == 'after_generated_undo_remove' else 'conflict')
    assert reopened.journal.generated(result.items[0].operation_id).backup.read_bytes() == original


def test_crash_same_swap_external_occupant_blocks_restore(tmp_path):
    source = image(tmp_path, 'original.jpg')
    original = source.read_bytes()
    engine = OperationEngine(tmp_path / 'state', Fault('after_generated_swap'))
    with pytest.raises(Crash):
        publish(engine, source, source, generated(engine, source, source), mode='replace')
    source.write_bytes(b'external occupant')
    reopened = OperationEngine(engine.state_dir)
    recovered = reopened.recover()
    assert recovered[0].state == 'conflict'
    assert source.read_bytes() == b'external occupant'
    record = reopened.journal.generated(recovered[0].operation_id)
    assert record.swap.read_bytes() == original and record.backup.read_bytes() == original


@pytest.mark.parametrize('stage', ['after_generated_swap', 'after_generated_rename_before_binding', 'after_generated_remove'])
def test_real_process_exit_recovery(tmp_path, stage):
    source = image(tmp_path, 'original.jpg')
    original = source.read_bytes()
    script = tmp_path / 'crash_owned.py'
    script.write_text('''
import os, sys
from pathlib import Path
from filehub.operations import OperationEngine
from filehub.platform.windows import WindowsPlatform
from filehub.generated import generate_owned
from filehub.conversion import ConversionSpec
class CrashPlatform(WindowsPlatform):
    def checkpoint(self, phase, item):
        if phase == sys.argv[2]: os._exit(77)
source=Path(sys.argv[1]); engine=OperationEngine(source.parent/'state', CrashPlatform())
owned=generate_owned(engine,source,source,ConversionSpec(output_format='jpeg'))
engine.publish_generated(source,source,owned.source_fingerprint,owned,owned.output_fingerprint,'crash',mode='replace')
''', encoding='utf-8')
    result = subprocess.run([sys.executable, '-X', 'utf8', str(script), str(source), stage],
                            env=dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'src')),
                            capture_output=True, timeout=15)
    assert result.returncode == 77, result.stderr.decode('utf-8')
    engine = OperationEngine(tmp_path / 'state')
    recovered = engine.recover()
    assert recovered[0].state == {'after_generated_swap': 'failed',
                                  'after_generated_rename_before_binding': 'conflict',
                                  'after_generated_remove': 'committed'}[stage]
    assert engine.journal.generated(recovered[0].operation_id).backup.read_bytes() == original
    if stage == 'after_generated_swap':
        assert source.read_bytes() == original


def test_owned_generator_rejects_state_source_and_target_before_creation(tmp_path):
    from filehub.generated import generate_owned
    source = image(tmp_path)
    engine = OperationEngine(tmp_path / 'state')
    state_image = image(engine.state_dir)
    with pytest.raises(ValueError, match='状态'):
        generate_owned(engine, state_image, tmp_path / 'out.jpg')
    with pytest.raises(ValueError, match='状态'):
        generate_owned(engine, source, engine.state_dir / 'nested' / 'out.jpg')
    assert not (engine.state_dir / 'nested').exists()
    assert not list(engine.state_dir.glob('.filehub-generated-*'))


def test_junction_input_and_output_are_rejected(tmp_path):
    from filehub.generated import generate_owned
    real = tmp_path / 'real'
    real.mkdir()
    source = image(real)
    link = tmp_path / 'junction'
    created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(real)], capture_output=True)
    assert created.returncode == 0
    engine = OperationEngine(tmp_path / 'state')
    try:
        with pytest.raises(ValueError, match='junction'):
            generate_owned(engine, link / source.name, tmp_path / 'out.jpg')
        with pytest.raises(ValueError, match='junction'):
            generate_owned(engine, source, link / 'out.jpg')
        assert not (real / 'out.jpg').exists()
    finally:
        link.rmdir()


def test_other_selected_source_overlap_is_rejected_even_when_vacant(tmp_path):
    source = image(tmp_path)
    selected = image(tmp_path, 'selected.jpg')
    selected_fp = Fingerprint.capture(selected)
    engine = OperationEngine(tmp_path / 'state')
    batch = engine.journal.create_batch('selection', [Operation('copy', selected, tmp_path / 'elsewhere', selected_fp)])
    owned = generated(engine, source, selected)
    selected.unlink()  # Planner's other source became missing; it stays selected.
    result = publish(engine, source, selected, owned, mode='replace', batch_id=batch)
    assert result.items[-1].state == 'failed' and '选中' in result.items[-1].message
    assert source.exists() and not selected.exists()
    from filehub.generated import discard_owned
    discard_owned(engine, owned)


def test_backup_verification_failure_leaves_source_untouched(tmp_path, monkeypatch):
    source = image(tmp_path)
    original = Fingerprint.capture(source)
    target = tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state')
    owned = generated(engine, source, target)
    real_copy = engine._copy
    def corrupted_metadata(src, dst, item):
        return replace(real_copy(src, dst, item), sha256='0' * 64)
    monkeypatch.setattr(engine, '_copy', corrupted_metadata)
    result = publish(engine, source, target, owned, mode='replace')
    assert not result.ok and Fingerprint.capture(source) == original
    assert not target.exists()


def test_ordinary_execute_cannot_dispatch_conversion_as_copy(tmp_path):
    source = image(tmp_path)
    with pytest.raises(ValueError):
        OperationEngine(tmp_path / 'state').execute([Operation('convert', source, tmp_path / 'out.jpg', Fingerprint.capture(source))], 'invalid')
    assert not (tmp_path / 'out.jpg').exists()


def test_internal_backup_path_not_accepted_as_public_operation(tmp_path):
    source = image(tmp_path)
    engine = OperationEngine(tmp_path / 'state')
    target = tmp_path / 'out.jpg'
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    backup = engine.journal.generated(result.items[0].operation_id).backup
    assert not engine.execute([Operation('move', backup, tmp_path / 'stolen', Fingerprint.capture(backup))], 'invalid').ok
    assert backup.exists() and not (tmp_path / 'stolen').exists()


@pytest.mark.parametrize('same', [False, True])
def test_external_destination_race_at_publish_is_never_overwritten(tmp_path, same):
    source = image(tmp_path, 'original.jpg' if same else 'original.png')
    original = source.read_bytes()
    target = source if same else tmp_path / 'out.jpg'
    engine = OperationEngine(tmp_path / 'state', Fault('before_generated_publish', lambda item: target.write_bytes(b'external arrival')))
    result = publish(engine, source, target, generated(engine, source, target), mode='replace')
    assert not result.ok and target.read_bytes() == b'external arrival'
    record = engine.journal.generated(result.items[0].operation_id)
    assert record.backup.read_bytes() == original
    if same:
        assert record.swap.read_bytes() == original
    else:
        assert source.read_bytes() == original


def test_original_swap_and_output_pinned_during_source_removal(tmp_path):
    source = image(tmp_path, 'original.jpg')
    attempts = []
    def race(item):
        for path in [source, source.with_name('.filehub-convert-' + item.operation_id + '.tmp')]:
            try:
                path.write_bytes(b'concurrent writer')
            except OSError:
                attempts.append('blocked')
            else:
                attempts.append('unsafe')
    engine = OperationEngine(tmp_path / 'state', Fault('before_generated_remove', race))
    result = publish(engine, source, source, generated(engine, source, source), mode='replace')
    assert result.ok and attempts == ['blocked', 'blocked']


def test_migration_corrupt_fk_refused_without_fake_success(tmp_path):
    from filehub.journal import Journal
    path = tmp_path / 'corrupt.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE parent(id PRIMARY KEY);CREATE TABLE orphan(id REFERENCES parent(id));INSERT INTO orphan VALUES('missing');")
    with pytest.raises(sqlite3.IntegrityError, match='foreign'):
        Journal(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT id FROM orphan').fetchone()[0] == 'missing'
        assert db.execute("SELECT name FROM sqlite_master WHERE name='operations'").fetchone() is None


def test_migration_failure_rolls_back_old_table_and_indexes(tmp_path, monkeypatch):
    from filehub.journal import Journal
    # Start from the actual complete released table DDL, then inject recreation
    # failure after table copy/drop/rename to exercise transactional DDL rollback.
    path = tmp_path / 'old.sqlite'
    base = Journal(tmp_path / 'template.sqlite')
    with base.connection() as db:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name='operations'").fetchone()[0].replace(",'convert'", '')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE batches(id TEXT PRIMARY KEY,label TEXT,created TEXT)')
        db.execute(sql)
        db.execute("INSERT INTO batches VALUES('b','label','old')")
        db.execute("INSERT INTO operations(id,batch_id,ordinal,kind,source,state) VALUES('op','b',0,'copy','source','failed')")
        db.execute('CREATE INDEX retained_index ON operations(batch_id)')
    connect = sqlite3.connect
    class FailAfterRename(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith('CREATE INDEX retained_index'):
                raise sqlite3.OperationalError('injected index restoration failure')
            return super().execute(sql, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: connect(*args, **kwargs, factory=FailAfterRename))
    with pytest.raises(sqlite3.OperationalError, match='injected'):
        Journal(path)
    with connect(path) as db:
        assert db.execute('SELECT id FROM operations').fetchone()[0] == 'op'
        assert 'convert' not in db.execute("SELECT sql FROM sqlite_master WHERE name='operations'").fetchone()[0]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='retained_index'").fetchone()
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute("SELECT name FROM sqlite_master WHERE name='operations_convert_migration'").fetchone() is None
