"""Windows file times and named data streams, with no lossy fallback."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import msvcrt
import os
from pathlib import Path

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                               ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
kernel.GetFileTime.restype = wintypes.BOOL
kernel.SetFileTime.argtypes = kernel.GetFileTime.argtypes
kernel.SetFileTime.restype = wintypes.BOOL
kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
kernel.FlushFileBuffers.restype = wintypes.BOOL
kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL


class StandardInfo(ctypes.Structure):
    _fields_ = [("AllocationSize", ctypes.c_longlong), ("EndOfFile", ctypes.c_longlong),
                ("NumberOfLinks", wintypes.DWORD), ("DeletePending", ctypes.c_ubyte), ("Directory", ctypes.c_ubyte)]


def require_not_delete_pending(handle):
    info = StandardInfo()
    if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if info.DeletePending:
        raise ValueError("命名流被外部标记删除，源移除已停止")


def winpath(path):
    text = str(Path(path).absolute())
    if text.startswith("\\\\?\\"):
        return text
    return "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text


def final_path(handle):
    size = kernel.GetFinalPathNameByHandleW(handle, None, 0, 0)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size + 1)
    length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise OSError("无法获取文件 handle 的最终路径")
    return Path(buffer.value)


def file_times(handle):
    created, modified = wintypes.FILETIME(), wintypes.FILETIME()
    if not kernel.GetFileTime(handle, ctypes.byref(created), None, ctypes.byref(modified)):
        raise ctypes.WinError(ctypes.get_last_error())
    def ns(value):
        return ((value.dwHighDateTime << 32 | value.dwLowDateTime) - 116444736000000000) * 100
    return ns(created), ns(modified)


def set_times(handle, created_ns, modified_ns):
    def filetime(ns):
        ticks = ns // 100 + 116444736000000000
        return wintypes.FILETIME(ticks & 0xffffffff, ticks >> 32)
    created, modified = filetime(created_ns), filetime(modified_ns)
    if not kernel.SetFileTime(handle, ctypes.byref(created), None, ctypes.byref(modified)):
        raise ctypes.WinError(ctypes.get_last_error())
    if file_times(handle) != (created_ns, modified_ns):
        raise ValueError("目标文件系统未完整保留创建/修改时间")


class FindStreamData(ctypes.Structure):
    _fields_ = [("StreamSize", ctypes.c_longlong), ("StreamName", ctypes.c_wchar * 296)]


kernel.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(FindStreamData), wintypes.DWORD]
kernel.FindFirstStreamW.restype = wintypes.HANDLE
kernel.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(FindStreamData)]
kernel.FindNextStreamW.restype = wintypes.BOOL
kernel.FindClose.argtypes = [wintypes.HANDLE]


def stream_names(path):
    data = FindStreamData()
    handle = kernel.FindFirstStreamW(winpath(path), 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error == 38:  # ERROR_HANDLE_EOF: valid file with no streams
            return ()
        raise OSError(f"无法枚举命名流，不能保证无损复制 (Windows error={error})")
    names = []
    try:
        while True:
            name = data.StreamName
            if name != "::$DATA":
                if not name.startswith(":") or not name.endswith(":$DATA") or name.count(":") != 2:
                    raise ValueError("不支持的命名流类型；源将保留")
                names.append(name)
            if not kernel.FindNextStreamW(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error != 38:
                    raise OSError(f"命名流枚举中断 (Windows error={error})")
                break
    finally:
        kernel.FindClose(handle)
    return tuple(sorted(names))


class NamedStream:
    """Hold a stream against writes, and against deletes when share_delete=False.

    DELETE-capable main handles require weak stream guards with DELETE sharing.
    Survivors use non-DELETE main handles and strong no-DELETE stream guards.
    """
    def __init__(self, path, name, *, create=False, share_delete=False):
        if name not in stream_names(path) and not create:
            raise ValueError("命名流在打开前消失")
        self.name = name
        access = 0x80000000 | (0x40000000 if create else 0)
        handle = kernel.CreateFileW(winpath(path) + name, access, 1 | (4 if share_delete else 0), None, 1 if create else 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(f"命名流无法读取/写入，源将保留：{name} (Windows error={ctypes.get_last_error()})")
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        self.handle = handle
        self.stream = os.fdopen(fd, "r+b" if create else "rb")

    def close(self):
        self.stream.close()

    def flush(self):
        self.stream.flush()
        if not kernel.FlushFileBuffers(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def digest(self):
        require_not_delete_pending(self.handle)
        before = os.fstat(self.stream.fileno())
        self.stream.seek(0)
        digest = hashlib.file_digest(self.stream, "sha256").hexdigest()
        after = os.fstat(self.stream.fileno())
        self.stream.seek(0)
        require_not_delete_pending(self.handle)
        if before.st_size != after.st_size:
            raise ValueError("命名流正在变化")
        return self.name, after.st_size, digest


@contextmanager
def held_streams(path, *, share_delete=False):
    guards = {}
    try:
        for name in stream_names(path):
            guards[name] = NamedStream(path, name, share_delete=share_delete)
        if stream_names(path) != tuple(sorted(guards)):
            raise ValueError("命名流清单正在变化")
        yield guards
    finally:
        for guard in guards.values():
            guard.close()
