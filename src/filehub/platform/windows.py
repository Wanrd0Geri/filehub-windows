"""Windows handle guards, exclusive publication, local process lock and recycling."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import msvcrt
import os
from pathlib import Path
import threading
import time
import uuid

from ..models import Fingerprint, checked_path
from .metadata import NamedStream, held_streams, final_path, set_times, winpath, stream_names

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL
kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
kernel.SetFileInformationByHandle.restype = wintypes.BOOL
kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
kernel.FlushFileBuffers.restype = wintypes.BOOL
kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
kernel.GetFileAttributesW.restype = wintypes.DWORD


class Guard:
    def __init__(self, path, *, create=False, destructive=False):
        self.path = checked_path(path)
        if not create:
            attributes = kernel.GetFileAttributesW(winpath(self.path))
            if attributes == 0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error())
            if attributes & 0x4000:
                raise ValueError("不支持 EFS 加密文件的无损复制；源已保留")
        # No write/delete sharing: concurrent writers, renames and deletes fail.
        access = 0x80000000 | (0x40000000 if create else 0) | (0x10000 if destructive else 0)
        handle = kernel.CreateFileW(winpath(self.path), access, 1, None, 1 if create else 3,
                                    0x80 | 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        self.stream = os.fdopen(fd, "r+b" if create else "rb")
        self.handle = handle
        self.named_streams = {}
        self._held_streams = held_streams(final_path(handle), share_delete=destructive)
        try:
            self.named_streams = self._held_streams.__enter__()
        except BaseException:
            self.stream.close()
            raise
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._held_streams.__exit__(None, None, None)
            finally:
                self.stream.close()

    def fingerprint(self):
        return Fingerprint.from_stream(self.stream, self.named_streams)

    def copy_metadata_from(self, source, checkpoint):
        """Copy all held streams then preserve exact creation/lastwrite times."""
        for name, src in source.named_streams.items():
            dst = NamedStream(final_path(self.handle), name, create=True, share_delete=True)
            try:
                src.stream.seek(0)
                while block := src.stream.read(1024 * 1024):
                    dst.stream.write(block)
                    checkpoint("named_stream_chunk")
                dst.flush()
                if src.digest() != dst.digest():
                    raise ValueError("命名流复制校验失败")
            finally:
                dst.close()
            # Reopen read-only so writes cannot be deferred past SetFileTime,
            # and keep this guard through publication and original removal.
            self.named_streams[name] = NamedStream(final_path(self.handle), name, share_delete=True)
        source_fp = source.fingerprint()
        checkpoint("before_metadata_set")
        set_times(self.handle, source_fp.creation_ns, source_fp.mtime_ns)
        self.flush()

    def verify(self, expected):
        actual = self.fingerprint()
        if expected is None or actual != expected:
            raise ValueError("文件指纹变化，已停止以保护文件")
        return actual

    def flush(self):
        self.stream.flush()
        if not kernel.FlushFileBuffers(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def remove(self):
        disposition = ctypes.c_ubyte(1)
        if not kernel.SetFileInformationByHandle(self.handle, 4, ctypes.byref(disposition), 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def rename(self, target):
        target = checked_path(target)
        encoded = winpath(target).encode("utf-16-le")
        class RenameInfo(ctypes.Structure):
            _fields_ = [("ReplaceIfExists", wintypes.BOOL), ("RootDirectory", wintypes.HANDLE),
                        ("FileNameLength", wintypes.DWORD), ("FileName", ctypes.c_wchar * (len(encoded)//2 + 1))]
        info = RenameInfo()
        info.ReplaceIfExists = False
        info.RootDirectory = None
        info.FileNameLength = len(encoded)
        info.FileName = winpath(target)
        if not kernel.SetFileInformationByHandle(self.handle, 3, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.path = target


@dataclass(frozen=True)
class RecycleOutcome:
    status: str  # recycled | failed | unknown
    identity: str | None = None
    message: str = ""


class _SharedLock:
    def __init__(self, path):
        self.path = path
        self.thread_lock = threading.RLock()
        self.depth = 0
        self.file = None

    @contextmanager
    def acquire(self):
        with self.thread_lock:
            if not self.depth:
                self.file = self.path.open("a+b")
                if not self.path.stat().st_size:
                    self.file.write(b"\0")
                    self.file.flush()
                self.file.seek(0)
                try:
                    while True:
                        try:
                            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            time.sleep(.05)
                except BaseException:
                    self.file.close()
                    self.file = None
                    raise
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
                if not self.depth:
                    try:
                        self.file.seek(0)
                        msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                    finally:
                        self.file.close()
                        self.file = None


_locks = {}
_registry_lock = threading.Lock()


def process_lock(state_dir):
    path = checked_path(state_dir).resolve() / "engine.lock"
    key = os.path.normcase(str(path))
    with _registry_lock:
        return _locks.setdefault(key, _SharedLock(path))


class WindowsPlatform:
    def directory_guard(self,path,*,destructive=False):
        return DirectoryGuard(path,destructive=destructive)

    def guard(self, path, *, destructive=False):
        return Guard(path, destructive=destructive)

    def create_target(self, path):
        return Guard(path, create=True, destructive=True)

    def checkpoint(self, stage, item):
        """Optional injected fault/event hook; production is a no-op."""

    def recycle(self, path):
        """IFileOperation's RECYCLEONDELETE refuses permanent deletion.

        Unlike legacy FOF_ALLOWUNDO, FOFX_RECYCLEONDELETE means *recycle*, not
        "delete with undo if possible". Unavailable bins fail instead of unlinking.
        No COM progress sink is installed; reliable item identity is unavailable,
        so successful native undo is explicitly manual.
        """
        path = checked_path(path)
        drive = Path(path).anchor
        kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        kernel.GetDriveTypeW.restype = wintypes.UINT
        if kernel.GetDriveTypeW(drive) != 3:
            return RecycleOutcome("failed", message="仅支持本机固定磁盘回收站")

        class GUID(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]

        def guid(text):
            return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)

        def method(pointer, index, *argtypes):
            table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])

        def checked(hr):
            if hr < 0:
                raise OSError(f"Windows Shell HRESULT=0x{hr & 0xffffffff:08x}")

        ole = ctypes.WinDLL("ole32")
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole.CoInitializeEx.restype = ctypes.c_long
        ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole.CoCreateInstance.restype = ctypes.c_long
        ole.CoUninitialize.argtypes = []
        init = ole.CoInitializeEx(None, 2)
        initialized = init >= 0
        if init < 0 and init & 0xffffffff != 0x80010106:  # existing different apartment is usable
            return RecycleOutcome("failed", message=f"COM 初始化失败：0x{init & 0xffffffff:08x}")
        operation, shell_item = ctypes.c_void_p(), ctypes.c_void_p()
        performed = False
        try:
            clsid = guid("3ad05575-8857-4850-9277-11b85bdb8e09")
            iid = guid("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8")
            checked(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(operation)))
            # RECYCLEONDELETE | ADDUNDORECORD | EARLYFAILURE | ALLOWUNDO |
            # SILENT | NOCONFIRMATION | NOERRORUI. No permanent-delete fallback.
            checked(method(operation, 5, wintypes.DWORD)(operation, 0x80000 | 0x20000000 | 0x100000 | 0x40 | 0x4 | 0x10 | 0x400))
            shell = ctypes.WinDLL("shell32")
            shell.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                                         ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
            shell.SHCreateItemFromParsingName.restype = ctypes.c_long
            shell_iid = guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")
            checked(shell.SHCreateItemFromParsingName(str(path), None, ctypes.byref(shell_iid), ctypes.byref(shell_item)))
            checked(method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, shell_item, None))
            performed = True
            checked(method(operation, 21)(operation))
            aborted = wintypes.BOOL()
            checked(method(operation, 22, ctypes.POINTER(wintypes.BOOL))(operation, ctypes.byref(aborted)))
            if aborted.value or path.exists():
                return RecycleOutcome("unknown", message="Windows Shell 回收未确认，请人工核对")
            return RecycleOutcome("recycled", message="已送至回收站；需要从回收站手动还原")
        except OSError as exc:
            return RecycleOutcome("unknown" if performed else "failed", message=str(exc))
        finally:
            if shell_item.value:
                method(shell_item, 2)(shell_item)
            if operation.value:
                method(operation, 2)(operation)
            if initialized:
                ole.CoUninitialize()

class DirectoryGuard:
    """Pin a directory against rename/replacement; children may still arrive.

    Handle disposition refuses a nonempty directory; it never deletes a tree.
    """
    def __init__(self,path,*,destructive=False):
        self.path=checked_path(path)
        self.handle=kernel.CreateFileW(winpath(self.path),0x80|0x100|(0x10000 if destructive else 0),3,None,3,0x02000000|0x00200000,None)
        if self.handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        self._closed=False
        try:
            checked_path(self.path)
            if not self.path.is_dir():raise ValueError('需要普通目录')
        except BaseException:
            self.close();raise
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if not self._closed:self._closed=True;kernel.CloseHandle(self.handle)
    def remove(self):
        checked_path(self.path)
        if any(self.path.iterdir()):raise ValueError('目录非空，保留')
        if stream_names(self.path):raise ValueError('空目录仍有命名流元数据，保留')
        disposition=ctypes.c_ubyte(1)
        if not kernel.SetFileInformationByHandle(self.handle,4,ctypes.byref(disposition),1):raise ctypes.WinError(ctypes.get_last_error())
