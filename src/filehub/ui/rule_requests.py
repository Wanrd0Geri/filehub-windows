"""Immutable GUI intents. Controllers own all IO and opaque preview tokens."""
from dataclasses import dataclass
from ..conversion.models import ConversionSpec
from ..automation.models import absolute_folder


def _paths(value):
    if isinstance(value, (str, bytes)): raise ValueError('路径必须是已选项目列表')
    paths = tuple(str(path) for path in value)
    if not paths or any(not path for path in paths): raise ValueError('请选择样本或图片')
    return paths


@dataclass(frozen=True)
class RulePreviewRequest:
    rule_id: str | None
    paths: tuple[str, ...]
    ruleset_revision: str
    generation: int

    def __post_init__(self):
        object.__setattr__(self, 'paths', _paths(self.paths))


@dataclass(frozen=True)
class ConversionRequest:
    paths: tuple[str, ...]
    spec: ConversionSpec
    mode: str = 'keep'
    output_dir: str | None = None
    generation: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'paths', _paths(self.paths))
        if not isinstance(self.spec, ConversionSpec): raise ValueError('必须提供已验证的图片设置')
        if self.mode not in ('keep', 'replace'): raise ValueError('请选择保留或替换模式')
        if self.mode == 'replace' and self.output_dir is not None: raise ValueError('替换模式不接受输出目录')
        if self.mode == 'keep': object.__setattr__(self, 'output_dir', absolute_folder(self.output_dir))
