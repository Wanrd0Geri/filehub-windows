from pathlib import Path
import os
import subprocess
import sys
import threading
import time
import uuid
import json

import pytest

from filehub.models import Fingerprint, Operation
from filehub.operations import OperationEngine
from filehub.platform.windows import WindowsPlatform, RecycleOutcome


def op(kind, source, target=None):
    return Operation(kind, source, target, Fingerprint.capture(source))


def source(tmp_path, name="源 文件.txt", content=b"original"):
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_no_overwrite(tmp_path):
    s = source(tmp_path)
    t = source(tmp_path, "目标.txt", b"existing")
    r = OperationEngine(tmp_path / "state").execute([op("move", s, t)], "x")
    assert not r.ok
    assert s.read_bytes() == b"original"
    assert t.read_bytes() == b"existing"


def test_copy_move_batch_undo(tmp_path):
    s = source(tmp_path)
    t, c = tmp_path / "moved", tmp_path / "copy"
    e = OperationEngine(tmp_path / "state")
    r = e.execute([op("copy", s, c), op("move", s, t)], "batch")
    assert r.ok and not s.exists()
    assert c.read_bytes() == t.read_bytes() == b"original"
    assert e.undo(r.batch_id).ok
    assert s.read_bytes() == b"original"
    assert not c.exists() and not t.exists()
    assert e.history()[0].label == "batch"


@pytest.mark.parametrize("change", ["edit", "replace", "occupied"])
def test_changed_or_conflicting_undo_refused(tmp_path, change):
    s = source(tmp_path)
    t = tmp_path / "target"
    e = OperationEngine(tmp_path / "state")
    r = e.execute([op("move", s, t)], "x")
    if change == "edit":
        t.write_bytes(b"edited")
    elif change == "replace":
        original_mtime = t.stat().st_mtime_ns
        t.unlink()
        t.write_bytes(b"original")
        os.utime(t, ns=(original_mtime, original_mtime))
    else:
        s.write_bytes(b"other")
    assert not e.undo(r.batch_id).ok
    assert t.exists()
    if change == "occupied":
        assert s.read_bytes() == b"other"


def test_stale_expected_source(tmp_path):
    s = source(tmp_path)
    planned = op("move", s, tmp_path / "target")
    s.write_bytes(b"changed")
    assert not OperationEngine(tmp_path / "state").execute([planned], "x").ok
    assert s.read_bytes() == b"changed"
    assert not planned.target.exists()


class RecycleFailure(WindowsPlatform):
    def recycle(self, path):
        raise OSError("recycle unavailable")


def test_recycle_failure_retains_source(tmp_path):
    s = source(tmp_path)
    e = OperationEngine(tmp_path / "state", RecycleFailure())
    assert not e.execute([op("recycle", s)], "x").ok
    assert s.read_bytes() == b"original"


class Crash(BaseException):
    pass


class Fault(WindowsPlatform):
    def __init__(self, stage):
        self.stage = stage

    def checkpoint(self, stage, item):
        if stage == self.stage:
            raise Crash(stage)


@pytest.mark.parametrize("stage", ["copy_started", "copy_chunk", "copy_verified", "source_removed"])
def test_crash_recovery_preserves_files_and_never_accepts_partial(tmp_path, stage):
    s = source(tmp_path, content=b"content" * 100)
    t = tmp_path / "target"
    state = tmp_path / "state"
    with pytest.raises(Crash):
        OperationEngine(state, Fault(stage)).execute([op("move", s, t)], "crash")
    e = OperationEngine(state)
    recovered = e.recover()
    assert recovered
    assert s.exists() or t.read_bytes() == b"content" * 100
    if stage in {"copy_started", "copy_chunk"}:
        assert not t.exists()
        assert recovered[0].staging.exists()
        assert recovered[0].state == "conflict"
        assert s.read_bytes() == b"content" * 100
    if stage == "copy_verified":
        assert s.exists() and t.exists()
        assert recovered[0].state == "conflict"
    if stage == "source_removed":
        assert recovered[0].state == "committed"
        assert e.undo(recovered[0].batch_id).ok


@pytest.mark.parametrize("kind", ["move", "copy", "recycle"])
def test_directory_rejected_without_changes(tmp_path, kind):
    s = tmp_path / "folder"
    s.mkdir()
    (s / "child").write_text("safe")
    operation = Operation(kind, s, tmp_path / "target" if kind != "recycle" else None, None)
    assert not OperationEngine(tmp_path / "state").execute([operation], "x").ok
    assert (s / "child").read_text() == "safe"
    assert not (tmp_path / "target").exists()


def test_overlap_rejected(tmp_path):
    s = source(tmp_path)
    e = OperationEngine(tmp_path / "state")
    r = e.execute([op("move", s, s)], "x")
    assert not r.ok and s.exists()


def test_same_state_engines_share_reentrant_allocation_lock(tmp_path):
    e1, e2 = OperationEngine(tmp_path / "state"), OperationEngine(tmp_path / "state")
    entered = threading.Event()
    def worker():
        with e2.locked():
            entered.set()
    with e1.locked():
        thread = threading.Thread(target=worker)
        thread.start()
        assert not entered.wait(.2)
        s = source(tmp_path)
        assert e1.execute([op("copy", s, tmp_path / "target")], "nested").ok
    thread.join(3)
    assert entered.is_set()


def test_second_process_blocks_on_same_engine_lock(tmp_path):
    e = OperationEngine(tmp_path / "state")
    marker = tmp_path / "entered"
    code = "from filehub.operations import OperationEngine; from pathlib import Path; import sys\nprint('READY', flush=True)\nwith OperationEngine(Path(sys.argv[1])).locked(): Path(sys.argv[2]).write_text('entered')"
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    with e.locked():
        p = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "state"), str(marker)], env=env, stdout=subprocess.PIPE)
        assert p.stdout.readline().strip() == b"READY"
        time.sleep(.2)
        assert not marker.exists() and p.poll() is None
    try:
        assert p.wait(5) == 0 and marker.read_text() == "entered"
    finally:
        if p.poll() is None:
            p.kill()
        p.stdout.close()


def test_exclusive_copy_racing_external_target_preserves_it(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    class Race(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "before_target_create":
                t.write_bytes(b"outside")
    assert not OperationEngine(tmp_path / "state", Race()).execute([op("copy", s, t)], "x").ok
    assert t.read_bytes() == b"outside"


def test_guard_blocks_real_windows_write_delete_and_rename(tmp_path):
    s = source(tmp_path)
    platform = WindowsPlatform()
    expected = Fingerprint.capture(s)
    with platform.guard(s, destructive=True) as guard:
        with pytest.raises(PermissionError):
            s.write_bytes(b"damage")
        with pytest.raises(PermissionError):
            s.unlink()
        with pytest.raises(PermissionError):
            s.rename(tmp_path / "stolen")
        guard.verify(expected)
    assert s.read_bytes() == b"original"


def test_locked_source_is_skipped(tmp_path):
    s = source(tmp_path)
    operation = op("move", s, tmp_path / "target")
    with s.open("r+b"):
        result = OperationEngine(tmp_path / "state").execute([operation], "busy")
    assert not result.ok
    assert s.read_bytes() == b"original" and not operation.target.exists()


@pytest.mark.parametrize("stage", ["copy_started", "copy_chunk", "copy_verified"])
def test_failed_copy_does_not_become_success_during_recovery(tmp_path, stage):
    s = source(tmp_path)
    t = tmp_path / "target"
    class Error(WindowsPlatform):
        def checkpoint(self, actual_stage, item):
            if actual_stage == stage:
                raise OSError("IO failure")
    state = tmp_path / "state"
    result = OperationEngine(state, Error()).execute([op("move", s, t)], "x")
    assert not result.ok
    assert result.items[0].state == "conflict"
    assert s.read_bytes() == b"original"
    e = OperationEngine(state)
    e.recover()
    assert not e.history()[0].ok


def test_recovery_cannot_trust_replaced_verified_target(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    state = tmp_path / "state"
    with pytest.raises(Crash):
        OperationEngine(state, Fault("source_removed")).execute([op("move", s, t)], "x")
    t.unlink()
    t.write_bytes(b"outside replacement")
    recovered = OperationEngine(state).recover()
    assert recovered[0].state == "conflict"
    assert t.read_bytes() == b"outside replacement"


@pytest.mark.parametrize("stage", ["undo_copy_verified", "undo_target_removed"])
def test_undo_crash_recovery_keeps_at_least_one_valid_copy(tmp_path, stage):
    s = source(tmp_path)
    t = tmp_path / "target"
    state = tmp_path / "state"
    e = OperationEngine(state)
    result = e.execute([op("move", s, t)], "x")
    with pytest.raises(Crash):
        OperationEngine(state, Fault(stage)).undo(result.batch_id)
    recovered = OperationEngine(state).recover()
    assert s.read_bytes() == b"original"
    assert recovered[0].state == ("conflict" if stage == "undo_copy_verified" else "undone")


def test_undo_changed_copy_preserves_edit(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "copy"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([op("copy", s, t)], "x")
    t.write_bytes(b"edited")
    assert not e.undo(result.batch_id).ok
    assert t.read_bytes() == b"edited"


class FakeRecycle(WindowsPlatform):
    def __init__(self, bin_path, status="recycled"):
        self.bin_path = bin_path
        self.status = status

    def recycle(self, path):
        path.rename(self.bin_path)
        return RecycleOutcome(self.status, message="test recycle result")


def test_recycle_without_identity_is_explicit_manual_restore(tmp_path):
    s = source(tmp_path)
    e = OperationEngine(tmp_path / "state", FakeRecycle(tmp_path / "test-bin"))
    result = e.execute([op("recycle", s)], "recycle")
    assert result.ok and not s.exists()
    assert result.items[0].staging.name.startswith("源 文件.filehub-")
    undo = e.undo(result.batch_id)
    assert not undo.ok and undo.items[0].state == "manual_restore"
    assert str(s) in undo.items[0].message


def test_unknown_recycle_never_claims_success(tmp_path):
    s = source(tmp_path)
    e = OperationEngine(tmp_path / "state", FakeRecycle(tmp_path / "test-bin", "unknown"))
    result = e.execute([op("recycle", s)], "x")
    assert not result.ok and result.items[0].state == "recycle_unknown"
    assert (tmp_path / "test-bin").read_bytes() == b"original"


def test_recycle_crash_restores_staging_without_recycling_again(tmp_path):
    s = source(tmp_path)
    state = tmp_path / "state"
    with pytest.raises(Crash):
        OperationEngine(state, Fault("recycle_staged")).execute([op("recycle", s)], "x")
    assert not s.exists()
    recovered = OperationEngine(state).recover()
    assert s.read_bytes() == b"original"
    assert recovered[0].state == "failed"


def test_recycle_failure_original_location_conflict_retains_staging(tmp_path):
    s = source(tmp_path)
    class Conflict(WindowsPlatform):
        def recycle(self, path):
            s.write_bytes(b"new occupant")
            raise OSError("cannot recycle")
    result = OperationEngine(tmp_path / "state", Conflict()).execute([op("recycle", s)], "x")
    assert not result.ok and result.items[0].state == "conflict"
    assert s.read_bytes() == b"new occupant"
    assert result.items[0].staging.read_bytes() == b"original"


def test_parent_junction_rejected_before_resolution(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    s = source(real)
    link = tmp_path / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True)
    assert result.returncode == 0
    try:
        planned = Operation("move", link / s.name, tmp_path / "target", Fingerprint.capture(s))
        result = OperationEngine(tmp_path / "state").execute([planned], "x")
        assert not result.ok and s.read_bytes() == b"original"
        planned = Operation("copy", s, link / "target", Fingerprint.capture(s))
        assert not OperationEngine(tmp_path / "state").execute([planned], "x").ok
        assert not (real / "target").exists()
    finally:
        link.rmdir()


def test_state_directory_is_not_an_archive_source_or_target(tmp_path):
    state = tmp_path / "state"
    e = OperationEngine(state)
    s = source(tmp_path)
    assert not e.execute([op("copy", s, state / "target")], "x").ok
    protected = source(state)
    assert not e.execute([op("move", protected, tmp_path / "target")], "x").ok
    assert protected.read_bytes() == b"original"


@pytest.mark.parametrize("name", ["video.mp4.crdownload", "a.part", "~$office.docx"])
def test_download_and_office_lock_files_are_rejected(tmp_path, name):
    s = source(tmp_path, name)
    result = OperationEngine(tmp_path / "state").execute([op("move", s, tmp_path / "target")], "x")
    assert not result.ok and s.exists()


def test_source_delete_intent_only_removes_while_target_guard_is_held(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    class Held(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "source_removed":
                with pytest.raises(PermissionError):
                    t.unlink()
    assert OperationEngine(tmp_path / "state", Held()).execute([op("move", s, t)], "x").ok
    assert t.read_bytes() == b"original"


def test_native_recycle_is_present_in_windows_recycle_bin(tmp_path):
    name = "FileHub_sandbox_recycle_" + uuid.uuid4().hex + ".txt"
    s = source(tmp_path, name, b"FileHub sandbox recycle test only")
    engine = OperationEngine(tmp_path / "state")
    result = engine.execute([op("recycle", s)], "native recycle sandbox acceptance")
    assert result.ok, result.items[0].message
    assert not s.exists()
    staged_name = result.items[0].staging.name
    # Inspect only the exact test item. Do not print/list unrelated bin contents.
    command = "$expected = $args[0]; $item = (New-Object -ComObject Shell.Application).Namespace(10).Items() | Where-Object { $_.Name -eq $expected -or $_.Name -eq [IO.Path]::GetFileNameWithoutExtension($expected) }; if ($item) { 'FOUND' } else { exit 3 }"
    script = tmp_path / "check-test-recycle.ps1"
    script.write_text(command, encoding="utf-8-sig")
    found = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script), staged_name], capture_output=True)
    assert found.returncode == 0 and b"FOUND" in found.stdout, (found.stdout, found.stderr)
    undo = engine.undo(result.batch_id)
    assert undo.items[0].state == "manual_restore" and not undo.ok
    receipt = Path(__file__).resolve().parents[1] / "sandbox" / "native-recycle-receipts.jsonl"
    with receipt.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"source": str(s), "staging": staged_name,
                              "shell_item": "FOUND", "undo": "manual_restore"}, ensure_ascii=False) + "\n")


def test_undo_move_removes_target_while_restored_source_is_still_guarded(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    state = tmp_path / "state"
    result = OperationEngine(state).execute([op("move", s, t)], "x")
    class Held(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "undo_target_removed":
                with pytest.raises(PermissionError):
                    s.unlink()
    assert OperationEngine(state, Held()).undo(result.batch_id).ok
    assert s.read_bytes() == b"original" and not t.exists()


def test_hash_catches_content_change_with_size_and_mtime_preserved(tmp_path):
    s = source(tmp_path)
    planned = op("move", s, tmp_path / "target")
    old_mtime = s.stat().st_mtime_ns
    s.write_bytes(b"modified")
    os.utime(s, ns=(old_mtime, old_mtime))
    assert not OperationEngine(tmp_path / "state").execute([planned], "x").ok
    assert s.read_bytes() == b"modified"


def test_guarded_rename_does_not_overwrite_existing_destination(tmp_path):
    s = source(tmp_path)
    target = source(tmp_path, "existing", b"outside")
    with WindowsPlatform().guard(s, destructive=True) as guard:
        with pytest.raises(OSError):
            guard.rename(target)
    assert s.read_bytes() == b"original" and target.read_bytes() == b"outside"


def test_source_change_attempt_after_copy_is_blocked_and_move_stops(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    class Writer(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "copy_verified":
                s.write_bytes(b"outside modification")
    result = OperationEngine(tmp_path / "state", Writer()).execute([op("move", s, t)], "x")
    assert not result.ok and result.items[0].state == "conflict"
    assert s.read_bytes() == t.read_bytes() == b"original"


@pytest.mark.parametrize("source_status", ["deleted", "edited"])
def test_copy_undo_refuses_to_delete_sole_original_content(tmp_path, source_status):
    s = source(tmp_path)
    t = tmp_path / "copy"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([op("copy", s, t)], "x")
    if source_status == "deleted":
        s.unlink()
    else:
        s.write_bytes(b"edited")
    assert not e.undo(result.batch_id).ok
    assert t.read_bytes() == b"original"


def test_failed_move_undo_does_not_remove_last_original_supplemental_copy(tmp_path):
    s = source(tmp_path)
    t, c = tmp_path / "moved", tmp_path / "supplemental"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([op("copy", s, c), op("move", s, t)], "x")
    t.write_bytes(b"edited")
    assert not e.undo(result.batch_id).ok
    assert c.read_bytes() == b"original" and t.read_bytes() == b"edited"


@pytest.mark.parametrize("stage", ["after_stage_verified", "before_publish", "after_publish"])
@pytest.mark.parametrize("kind", ["copy", "move"])
def test_atomic_publication_crash_never_exposes_partial_final_name(tmp_path, stage, kind):
    s = source(tmp_path)
    t, state = tmp_path / "target", tmp_path / "state"
    with pytest.raises(Crash):
        OperationEngine(state, Fault(stage)).execute([op(kind, s, t)], "x")
    assert s.read_bytes() == b"original"
    e = OperationEngine(state)
    item = e.history()[0].items[0]
    if stage == "after_publish":
        assert t.read_bytes() == b"original" and not item.staging.exists()
    else:
        assert not t.exists() and item.staging.read_bytes() == b"original"
    recovered = e.recover()
    assert recovered[0].state == ("committed" if kind == "copy" and stage == "after_publish" else "conflict")


def test_final_destination_race_at_publish_never_overwrites(tmp_path):
    s = source(tmp_path)
    t = tmp_path / "target"
    class Occupied(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "before_publish":
                t.write_bytes(b"outside")
    result = OperationEngine(tmp_path / "state", Occupied()).execute([op("move", s, t)], "x")
    assert not result.ok
    assert s.read_bytes() == b"original" and t.read_bytes() == b"outside"
    assert result.items[0].staging.read_bytes() == b"original"


@pytest.mark.parametrize("stage", ["undo_after_stage_verified", "undo_before_publish", "undo_after_publish"])
def test_move_undo_uses_atomic_publication_and_preserves_target_on_crash(tmp_path, stage):
    s = source(tmp_path)
    t, state = tmp_path / "target", tmp_path / "state"
    result = OperationEngine(state).execute([op("move", s, t)], "x")
    with pytest.raises(Crash):
        OperationEngine(state, Fault(stage)).undo(result.batch_id)
    assert t.read_bytes() == b"original"
    assert s.exists() == (stage == "undo_after_publish")
    recovered = OperationEngine(state).recover()
    assert recovered[0].state == "conflict"


def test_undo_copy_survivor_guard_blocks_concurrent_source_removal(tmp_path):
    s = source(tmp_path)
    t, state = tmp_path / "copy", tmp_path / "state"
    result = OperationEngine(state).execute([op("copy", s, t)], "x")
    class Writer(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "before_undo_remove":
                s.unlink()
    assert not OperationEngine(state, Writer()).undo(result.batch_id).ok
    assert s.read_bytes() == t.read_bytes() == b"original"


def test_undo_publish_race_preserves_new_source_and_archived_target(tmp_path):
    s = source(tmp_path)
    t, state = tmp_path / "target", tmp_path / "state"
    result = OperationEngine(state).execute([op("move", s, t)], "x")
    class Occupied(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "undo_before_publish":
                s.write_bytes(b"outside")
    undone = OperationEngine(state, Occupied()).undo(result.batch_id)
    assert not undone.ok
    assert s.read_bytes() == b"outside" and t.read_bytes() == b"original"
    assert undone.items[0].staging.read_bytes() == b"original"
