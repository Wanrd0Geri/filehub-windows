import ctypes
from ctypes import wintypes
import os
from pathlib import Path

import pytest

from filehub.models import Fingerprint, Operation
from filehub.operations import OperationEngine
from filehub.platform.windows import WindowsPlatform, Guard


def set_file_times(path, creation_ns, mtime_ns):
    # Independent real WinAPI fixture, not the production metadata setter.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                  ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    kernel.SetFileTime.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x100, 7, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    def filetime(ns):
        ticks = ns // 100 + 116444736000000000
        return wintypes.FILETIME(ticks & 0xffffffff, ticks >> 32)
    birth, modified = filetime(creation_ns), filetime(mtime_ns)
    try:
        assert kernel.SetFileTime(handle, ctypes.byref(birth), None, ctypes.byref(modified))
    finally:
        kernel.CloseHandle(handle)


def fixture_file(tmp_path):
    path = tmp_path / "下载 文件.mp4"
    path.write_bytes(b"main content")
    Path(str(path) + ":Zone.Identifier").write_bytes(b"[ZoneTransfer]\r\nZoneId=3\r\n")
    Path(str(path) + ":用户备注").write_bytes("独立备注内容".encode("utf-8"))
    set_file_times(path, 1609459200000000000, 1640995200000000000)
    return path


@pytest.mark.parametrize("kind", ["copy", "move"])
def test_creation_and_lastwrite_are_preserved_through_transfer_and_move_undo(tmp_path, kind):
    source = fixture_file(tmp_path)
    expected_birth, expected_modified = source.stat().st_birthtime_ns, source.stat().st_mtime_ns
    target = tmp_path / "archive.mp4"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([Operation(kind, source, target, Fingerprint.capture(source))], "metadata")
    assert result.ok, result.items[0].message
    assert target.stat().st_birthtime_ns == expected_birth
    assert target.stat().st_mtime_ns == expected_modified
    if kind == "move":
        assert e.undo(result.batch_id).ok
        assert source.stat().st_birthtime_ns == expected_birth
        assert source.stat().st_mtime_ns == expected_modified


@pytest.mark.parametrize("kind", ["copy", "move"])
def test_named_streams_are_copied_and_preserved_by_move_undo(tmp_path, kind):
    source = fixture_file(tmp_path)
    target = tmp_path / "archive.mp4"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([Operation(kind, source, target, Fingerprint.capture(source))], "ADS")
    assert result.ok, result.items[0].message
    assert Path(str(target) + ":Zone.Identifier").read_bytes() == b"[ZoneTransfer]\r\nZoneId=3\r\n"
    assert Path(str(target) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")
    if kind == "move":
        assert e.undo(result.batch_id).ok
        assert Path(str(source) + ":Zone.Identifier").read_bytes() == b"[ZoneTransfer]\r\nZoneId=3\r\n"
        assert Path(str(source) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")


@pytest.mark.parametrize("change", ["edit", "added", "removed"])
def test_stream_only_change_invalidates_preview_even_if_main_mtime_is_restored(tmp_path, change):
    source = fixture_file(tmp_path)
    original_birth, original_mtime = source.stat().st_birthtime_ns, source.stat().st_mtime_ns
    operation = Operation("move", source, tmp_path / "target", Fingerprint.capture(source))
    if change == "edit":
        Path(str(source) + ":用户备注").write_bytes(b"edited stream")
    elif change == "added":
        Path(str(source) + ":new stream").write_bytes(b"added")
    else:
        Path(str(source) + ":用户备注").unlink()
    set_file_times(source, original_birth, original_mtime)
    result = OperationEngine(tmp_path / "state").execute([operation], "changed ADS")
    assert not result.ok
    assert source.read_bytes() == b"main content" and not operation.target.exists()


def test_target_ads_only_edit_blocks_undo_without_touching_archived_file(tmp_path):
    source = fixture_file(tmp_path)
    target = tmp_path / "archive"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([Operation("move", source, target, Fingerprint.capture(source))], "x")
    assert result.ok
    birth, mtime = target.stat().st_birthtime_ns, target.stat().st_mtime_ns
    Path(str(target) + ":Zone.Identifier").write_bytes(b"changed zone stream")
    set_file_times(target, birth, mtime)
    assert not e.undo(result.batch_id).ok
    assert target.read_bytes() == b"main content"
    assert Path(str(target) + ":Zone.Identifier").read_bytes() == b"changed zone stream"
    assert not source.exists()


def test_stream_identity_roundtrips_through_journal(tmp_path):
    source = fixture_file(tmp_path)
    planned = Fingerprint.capture(source)
    e = OperationEngine(tmp_path / "state")
    result = e.execute([Operation("copy", source, tmp_path / "target", planned)], "ADS")
    restored = OperationEngine(tmp_path / "state").history()[0].items[0].expected_source
    assert restored == planned
    assert {stream.name for stream in restored.streams} == {":Zone.Identifier:$DATA", ":用户备注:$DATA"}


def test_copy_undo_preserves_sole_original_named_stream_content(tmp_path):
    source = fixture_file(tmp_path)
    target = tmp_path / "copy"
    e = OperationEngine(tmp_path / "state")
    result = e.execute([Operation("copy", source, target, Fingerprint.capture(source))], "x")
    Path(str(source) + ":用户备注").write_bytes(b"new notes")
    assert not e.undo(result.batch_id).ok
    assert Path(str(target) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")


def test_business_dedup_ignores_ads_but_safe_survivor_equality_includes_it(tmp_path):
    first, second = fixture_file(tmp_path), tmp_path / "second.mp4"
    second.write_bytes(b"main content")
    a, b = Fingerprint.capture(first), Fingerprint.capture(second)
    assert a.same_primary_content(b)
    assert not a.same_content(b)


@pytest.mark.parametrize("stage", ["copy_verified", "before_source_remove"])
def test_existing_source_and_target_streams_deny_real_windows_writes_through_removal(tmp_path, stage):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    class StreamRace(WindowsPlatform):
        def checkpoint(self, actual_stage, item):
            if actual_stage == stage:
                for path in (source, target):
                    with pytest.raises(PermissionError):
                        Path(str(path) + ":用户备注").write_bytes(b"outside changes")
                with pytest.raises(PermissionError):
                    Path(str(target) + ":Zone.Identifier").unlink()
    result = OperationEngine(tmp_path / "state", StreamRace()).execute([
        Operation("move", source, target, Fingerprint.capture(source))], "ADS race")
    assert result.ok, result.items[0].message
    assert not source.exists()
    assert Path(str(target) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")


def test_undo_holds_archived_and_restored_stream_guards_until_target_removed(tmp_path):
    source = fixture_file(tmp_path)
    target, state = tmp_path / "target", tmp_path / "state"
    result = OperationEngine(state).execute([Operation("move", source, target, Fingerprint.capture(source))], "x")
    class StreamRace(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "undo_copy_verified":
                for path in (source, target):
                    with pytest.raises(PermissionError):
                        Path(str(path) + ":Zone.Identifier").write_bytes(b"outside")
    undone = OperationEngine(state, StreamRace()).undo(result.batch_id)
    assert undone.ok, undone.items[0].message
    assert Path(str(source) + ":Zone.Identifier").read_bytes() == b"[ZoneTransfer]\r\nZoneId=3\r\n"


@pytest.mark.parametrize("stage", ["named_stream_chunk", "before_metadata_set"])
def test_stream_copy_or_time_write_failure_preserves_original(tmp_path, stage):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    class Failure(WindowsPlatform):
        def checkpoint(self, actual_stage, item):
            if actual_stage == stage:
                raise OSError("injected metadata IO failure")
    result = OperationEngine(tmp_path / "state", Failure()).execute([
        Operation("move", source, target, Fingerprint.capture(source))], "failure")
    assert not result.ok and not target.exists()
    assert source.read_bytes() == b"main content"
    assert Path(str(source) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")


def test_unreadable_named_stream_does_not_delete_original(tmp_path):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    planned = Fingerprint.capture(source)
    with Path(str(source) + ":用户备注").open("r+b"):
        result = OperationEngine(tmp_path / "state").execute([
            Operation("move", source, target, planned)], "busy ADS")
    assert not result.ok and not target.exists()
    assert source.read_bytes() == b"main content"


def test_stream_unsupported_target_refuses_move_before_original_removal(tmp_path):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    class UnsupportedGuard(Guard):
        def copy_metadata_from(self, source_guard, checkpoint):
            raise OSError("target filesystem does not support named data streams")
    class Unsupported(WindowsPlatform):
        def create_target(self, path):
            return UnsupportedGuard(path, create=True, destructive=True)
    result = OperationEngine(tmp_path / "state", Unsupported()).execute([
        Operation("move", source, target, Fingerprint.capture(source))], "unsupported target")
    assert not result.ok and not target.exists()
    assert Path(str(source) + ":Zone.Identifier").read_bytes() == b"[ZoneTransfer]\r\nZoneId=3\r\n"


def test_efs_attribute_rejected_before_plaintext_copy(tmp_path, monkeypatch):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    # EFS is not enabled on the user's machine; inject only the native attribute.
    from filehub.platform import windows
    monkeypatch.setattr(windows.kernel, "GetFileAttributesW", lambda path: 0x4000)
    result = OperationEngine(tmp_path / "state").execute([
        Operation("move", source, target, Fingerprint.capture(source))], "EFS")
    assert not result.ok
    assert source.read_bytes() == b"main content" and not target.exists()
    assert "EFS" in result.items[0].message


@pytest.mark.parametrize("stage", ["before_survivor_guard", "before_undo_survivor_guard"])
def test_survivor_guard_takeover_gap_modification_preserves_deletion_candidate(tmp_path, stage):
    source = fixture_file(tmp_path)
    target, state = tmp_path / "target", tmp_path / "state"
    class Gap(WindowsPlatform):
        def checkpoint(self, actual_stage, item):
            if actual_stage == stage:
                path = target if stage == "before_survivor_guard" else source
                Path(str(path) + ":用户备注").write_bytes(b"gap edited stream")
    if stage == "before_survivor_guard":
        result = OperationEngine(state, Gap()).execute([Operation("move", source, target, Fingerprint.capture(source))], "x")
        candidate = source
    else:
        result = OperationEngine(state).execute([Operation("move", source, target, Fingerprint.capture(source))], "x")
        result = OperationEngine(state, Gap()).undo(result.batch_id)
        candidate = target
    assert not result.ok
    assert candidate.read_bytes() == b"main content"
    assert Path(str(candidate) + ":用户备注").read_bytes() == "独立备注内容".encode("utf-8")


@pytest.mark.parametrize("stage", ["source_removed", "undo_target_removed"])
def test_all_deletion_handles_close_under_ads_survivor_guard(tmp_path, stage):
    source = fixture_file(tmp_path)
    target, state = tmp_path / "target", tmp_path / "state"
    class Lifecycle(WindowsPlatform):
        def checkpoint(self, actual_stage, item):
            if actual_stage == stage:
                survivor, removed = (target, source) if stage == "source_removed" else (source, target)
                assert not removed.exists()
                with pytest.raises(PermissionError):
                    Path(str(survivor) + ":Zone.Identifier").unlink()
                with pytest.raises(PermissionError):
                    survivor.unlink()
    engine = OperationEngine(state, Lifecycle())
    result = engine.execute([Operation("move", source, target, Fingerprint.capture(source))], "x")
    assert result.ok
    if stage == "undo_target_removed":
        assert engine.undo(result.batch_id).ok


def test_source_ads_unlink_after_publication_is_detected_before_source_removal(tmp_path):
    source = fixture_file(tmp_path)
    target = tmp_path / "target"
    class UnlinkRace(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "before_source_remove":
                # Weak DELETE-sharing source readers cannot block stream unlink.
                # The source inventory must detect it; the strong target remains.
                Path(str(source) + ":Zone.Identifier").unlink()
    result = OperationEngine(tmp_path / "state", UnlinkRace()).execute([
        Operation("move", source, target, Fingerprint.capture(source))], "x")
    assert not result.ok and source.read_bytes() == b"main content"
    assert Path(str(target) + ":Zone.Identifier").read_bytes() == b"[ZoneTransfer]\r\nZoneId=3\r\n"


def test_ads_recovery_refuses_target_stream_edit_after_source_removed(tmp_path):
    source = fixture_file(tmp_path)
    target, state = tmp_path / "target", tmp_path / "state"
    class Crash(BaseException):
        pass
    class Interrupted(WindowsPlatform):
        def checkpoint(self, stage, item):
            if stage == "source_removed":
                raise Crash()
    with pytest.raises(Crash):
        OperationEngine(state, Interrupted()).execute([
            Operation("move", source, target, Fingerprint.capture(source))], "x")
    created, mtime = target.stat().st_birthtime_ns, target.stat().st_mtime_ns
    Path(str(target) + ":Zone.Identifier").write_bytes(b"edited zone")
    set_file_times(target, created, mtime)
    recovered = OperationEngine(state).recover()
    assert recovered[0].state == "conflict"
    assert target.read_bytes() == b"main content"
    assert Path(str(target) + ":Zone.Identifier").read_bytes() == b"edited zone"
