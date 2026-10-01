from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import os
import stat


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
class Fingerprint:
    device: int
    file_id: int
    size: int
    mtime_ns: int
    sha256: str

    @classmethod
    def capture(cls, path: Path) -> "Fingerprint":
        path = checked_path(path)
        with path.open("rb") as stream:
            result = cls.from_stream(stream)
        info = path.stat()
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != result.identity:
            raise ValueError("文件在读取时被替换或修改")
        return result

    @property
    def identity(self):
        return self.device, self.file_id, self.size, self.mtime_ns

    @classmethod
    def from_stream(cls, stream) -> "Fingerprint":
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("暂不支持目录或非普通文件")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("文件正在变化")
        stream.seek(0)
        return cls(after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, digest)

    def same_content(self, other: "Fingerprint") -> bool:
        return self.size == other.size and self.sha256 == other.sha256

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

    @property
    def ok(self):
        return self.state in {"committed", "undone", "recycled"}


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    label: str
    items: tuple[ItemResult, ...]

    @property
    def ok(self):
        return bool(self.items) and all(item.ok for item in self.items)
