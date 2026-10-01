"""Image conversion contracts. Originals and final publication belong to callers."""
from dataclasses import dataclass
from pathlib import Path
import math
import re

from ..models import Fingerprint


class ConversionError(ValueError):
    """Unsupported input, invalid plan or unsuccessful codec operation."""


class ConversionCancelled(ConversionError):
    """Cancelled at a codec boundary; no generated output is retained."""


@dataclass(frozen=True)
class ConversionSpec:
    kind: str = 'image'
    output_format: str = 'jpeg'
    quality: int = 90
    background: str = '#FFFFFF'
    lossless: bool = False
    timeout_seconds: float = 60
    max_pixels: int = 40_000_000

    def __post_init__(self):
        if self.kind != 'image':
            raise ConversionError('此版本仅支持图片转换')
        if self.output_format not in ('jpeg', 'png', 'webp'):
            raise ConversionError('输出格式仅支持 JPEG、PNG、WebP')
        if type(self.quality) is not int or not 0 <= self.quality <= 100:
            raise ConversionError('质量应为 0–100 的整数')
        if not isinstance(self.background, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', self.background):
            raise ConversionError('JPEG 背景应为 #RRGGBB 颜色')
        if type(self.lossless) is not bool:
            raise ConversionError('WebP 无损选项必须为布尔值')
        if type(self.max_pixels) is not int or not 0 < self.max_pixels <= 40_000_000:
            raise ConversionError('像素上限应为 1–40000000；大图需要较多内存')
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 3600):
            raise ConversionError('分阶段超时应为大于 0、至多 3600 的秒数')

    @property
    def extension(self):
        return {'jpeg': '.jpg', 'png': '.png', 'webp': '.webp'}[self.output_format]


@dataclass(frozen=True)
class ConversionCapabilities:
    qt_version: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class ConversionProgress:
    phase: str
    percent: int


@dataclass(frozen=True)
class ConversionPlan:
    source: Path
    spec: ConversionSpec
    source_fingerprint: Fingerprint
    input_format: str
    width: int
    height: int
    orientation_applied: bool
    capability_digest: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    staging: Path
    source_fingerprint: Fingerprint
    output_fingerprint: Fingerprint
    input_format: str
    output_format: str
    width: int
    height: int
    orientation_applied: bool
    capability_digest: str
    warnings: tuple[str, ...]
