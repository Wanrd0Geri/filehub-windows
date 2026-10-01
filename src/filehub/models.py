from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import os
import stat
import msvcrt

from .platform.metadata import file_times, final_path, held_streams, stream_names


def checked_path(path: Path) -> Path:
    """Reject reparse points in *every* existing component, before resolve."""
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("不支持符号链接或 junction")
    return path

@dataclass(frozen=True)
class StreamFingerprint:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Fingerprint:
    device: int
    file_id: int
    size: int
    mtime_ns: int
    sha256: str
    creation_ns: int = 0
    streams: tuple[StreamFingerprint, ...] = ()

    @classmethod
    def capture(cls, path: Path) -> "Fingerprint":
        path = checked_path(path)
        if path.is_dir():
            from .trees import TreeFingerprint
            return TreeFingerprint.capture(path)
        with path.open("rb") as stream:
            result = cls.from_stream(stream)
        info = path.stat()
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != result.identity:
            raise ValueError("文件在读取时被替换或修改")
        if info.st_birthtime_ns != result.creation_ns:
            raise ValueError("文件创建时间正在变化")
        return result

    @property
    def identity(self):
        return self.device, self.file_id, self.size, self.mtime_ns

    @classmethod
    def from_stream(cls, stream, named_streams=None) -> "Fingerprint":
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("暂不支持目录或非普通文件")
        handle = msvcrt.get_osfhandle(stream.fileno())
        path = final_path(handle)
        before_times = file_times(handle)
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if named_streams is None:
            with held_streams(path) as guards:
                streams = tuple(StreamFingerprint(*guards[name].digest()) for name in sorted(guards))
        else:
            if stream_names(path) != tuple(sorted(named_streams)):
                raise ValueError("命名流清单变化，已停止")
            streams = tuple(StreamFingerprint(*named_streams[name].digest()) for name in sorted(named_streams))
            if stream_names(path) != tuple(sorted(named_streams)):
                raise ValueError("命名流清单变化，已停止")
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("文件正在变化")
        stream.seek(0)
        if before_times != file_times(handle):
            raise ValueError("文件时间正在变化")
        return cls(after.st_dev, after.st_ino, after.st_size, before_times[1], digest, before_times[0], streams)

    def same_content(self, other: "Fingerprint") -> bool:
        """Full content equality for safe survivors; includes every named stream."""
        return self.same_primary_content(other) and self.streams == other.streams

    def same_primary_content(self, other: "Fingerprint") -> bool:
        """Business dedup equality, deliberately ignoring ADS and file times."""
        return self.size == other.size and self.sha256 == other.sha256

    @classmethod
    def from_dict(cls, value):
        if 'entries' in value:
            from .trees import TreeFingerprint
            return TreeFingerprint.from_dict(value)
        data = dict(value)
        data["streams"] = tuple(StreamFingerprint(**stream) for stream in data.get("streams", ()))
        return cls(**data)

    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class Operation:
    kind: str
    source: Path
    target: Path | None
    expected_source: Fingerprint | None


@dataclass(frozen=True)
class ItemResult:
    operation_id: str
    batch_id: str
    kind: str
    source: Path
    target: Path | None
    state: str
    message: str = ""
    expected_source: Fingerprint | None = None
    target_fingerprint: Fingerprint | None = None
    staging: Path | None = None
    recycle_identity: str | None = None
    undo_fingerprint: Fingerprint | None = None
    parent_operation_id: str | None = None

    @property
    def ok(self):
        return self.state in {"committed", "undone", "recycled"}


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    label: str
    items: tuple[ItemResult, ...]
    created: str = ""
    outcomes: tuple = ()

    @property
    def ok(self):
        return bool(self.items) and all(item.ok for item in self.items) and all(not item.error for item in self.outcomes)

    @property
    def status(self):
        if self.ok: return 'success'
        if any(item.ok for item in self.items): return 'partial'
        return 'failed'
