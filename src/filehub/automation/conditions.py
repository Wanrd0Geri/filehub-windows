"""Snapshot facts and complete, Chinese tri-state condition explanations."""
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
import math
import operator

from ..models import Fingerprint, checked_path
from ..trees import TreeFingerprint
from .models import Predicate, ConditionGroup, Rule, RuleSet, KINDS, aware_date

_EXTENSIONS = {
    'image': frozenset({'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif', '.heic'}),
    'video': frozenset({'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv'}),
    'audio': frozenset({'.wav', '.mp3', '.flac', '.aac', '.m4a', '.ogg', '.wma'}),
    'document': frozenset({'.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.md', '.rtf'}),
}
_LABELS = {'kind': '类型', 'extension': '扩展名', 'name': '名称', 'size_bytes': '大小（字节）',
    'created': '创建时间', 'modified': '修改时间', 'first_seen_age_seconds': '首次观察时长（秒）',
    'stable_age_seconds': '稳定时长（秒）'}
_OPS = {'eq': operator.eq, 'lt': operator.lt, 'le': operator.le, 'gt': operator.gt, 'ge': operator.ge}
_OP_LABELS = {'eq': '等于', 'equals': '等于', 'lt': '小于', 'le': '小于等于', 'gt': '大于', 'ge': '大于等于',
    'contains': '包含', 'starts_with': '开头为', 'ends_with': '结尾为', 'glob': '通配匹配'}


@dataclass(frozen=True)
class FileFacts:
    path: Path
    fingerprint: object | None
    kind: str = 'other'
    size_bytes: int | None = None
    created: datetime | None = None
    modified: datetime | None = None
    first_seen: datetime | None = None
    stable_since: datetime | None = None
    video_width: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'path', Path(self.path))
        if not isinstance(self.kind, str) or self.kind not in KINDS: raise ValueError('未知文件类型')
        if self.size_bytes is not None and (type(self.size_bytes) is not int or self.size_bytes < 0): raise ValueError('文件大小无效')
        if self.video_width is not None and (type(self.video_width) is not int or self.video_width <= 0): raise ValueError('视频宽度无效')
        for name in ('created', 'modified', 'first_seen', 'stable_since'):
            if getattr(self, name) is not None: object.__setattr__(self, name, aware_date(getattr(self, name)))

    @property
    def name(self): return self.path.name

    @property
    def extension(self): return '' if self.kind == 'folder' else self.path.suffix.casefold()

    @classmethod
    def capture(cls, path, *, first_seen=None, stable_since=None, video_width=None):
        """Filesystem facts only; no codec decode or observation persistence."""
        path = checked_path(path)
        fingerprint = Fingerprint.capture(path)
        kind = 'folder' if path.is_dir() else next((kind for kind, extensions in _EXTENSIONS.items() if path.suffix.casefold() in extensions), 'other')
        return cls(path, fingerprint, kind, fingerprint.size,
                   datetime.fromtimestamp(fingerprint.creation_ns/1e9, timezone.utc),
                   datetime.fromtimestamp(fingerprint.mtime_ns/1e9, timezone.utc),
                   first_seen, stable_since, video_width)

    def value(self, field, now):
        if field not in {'first_seen_age_seconds', 'stable_age_seconds'}: return getattr(self, field)
        observed = self.first_seen if field == 'first_seen_age_seconds' else self.stable_since
        if observed is None: return None
        if field == 'stable_age_seconds':
            # A recently changed file cannot inherit a longer stable observation.
            if self.modified is None or self.created is None: return None
            times = [observed, self.created, self.modified]
            if isinstance(self.fingerprint, TreeFingerprint):
                for child in (*[fp for _, fp in self.fingerprint.entries], *self.fingerprint.directories):
                    times.extend((datetime.fromtimestamp(child.creation_ns/1e9, timezone.utc),
                                  datetime.fromtimestamp(child.mtime_ns/1e9, timezone.utc)))
            observed = max(times)
        seconds = (now-observed).total_seconds()
        return seconds if math.isfinite(seconds) and seconds >= 0 else None


@dataclass(frozen=True)
class MatchExplanation:
    status: str
    reason: str
    children: tuple['MatchExplanation', ...] = ()
    field: str = ''
    actual: object = None
    threshold: object = None

    @property
    def matched(self): return self.status == 'true'


def evaluate(condition, facts: FileFacts, now: datetime) -> MatchExplanation:
    aware_date(now)
    if isinstance(condition, ConditionGroup):
        children = tuple(evaluate(child, facts, now) for child in condition.children)
        states = {child.status for child in children}
        if condition.mode == 'all':
            status = 'false' if 'false' in states else 'unavailable' if 'unavailable' in states else 'true'
            label = '全部条件'
        elif condition.mode == 'any':
            status = 'true' if 'true' in states else 'unavailable' if 'unavailable' in states else 'false'
            label = '任一条件'
        else:
            status = 'false' if 'true' in states else 'unavailable' if 'unavailable' in states else 'true'
            label = '没有条件匹配'
        conclusion = {'true': '满足', 'false': '不满足', 'unavailable': '信息不可用，无法确定'}[status]
        return MatchExplanation(status, f'{label}：{conclusion}', children)
    if not isinstance(condition, Predicate): raise ValueError('必须提供已验证条件')
    actual = facts.value(condition.field, now)
    label = _LABELS[condition.field]
    if actual is None:
        return MatchExplanation('unavailable', f'{label}不可用；阈值为 {condition.value}，本项不匹配',
                                field=condition.field, threshold=condition.value)
    threshold = condition.value
    if condition.field in {'created', 'modified'}:
        matched = _OPS[condition.operator](actual, aware_date(threshold))
        actual = actual.isoformat()
    elif condition.field in {'size_bytes', 'first_seen_age_seconds', 'stable_age_seconds'}:
        matched = _OPS[condition.operator](actual, threshold)
    else:
        left, right = actual.casefold(), threshold.casefold()
        if condition.field == 'kind' and right == 'file': matched = left != 'folder'
        elif condition.operator == 'equals': matched = left == right
        elif condition.operator == 'contains': matched = right in left
        elif condition.operator == 'starts_with': matched = left.startswith(right)
        elif condition.operator == 'ends_with': matched = left.endswith(right)
        else: matched = fnmatchcase(left, right)
    return MatchExplanation('true' if matched else 'false',
        f'{label}实际为 {actual}，要求{_OP_LABELS[condition.operator]} {threshold}：'+('满足' if matched else '不满足'),
        field=condition.field, actual=actual, threshold=threshold)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    rule_name: str
    status: str
    reason: str
    explanation: MatchExplanation | None = None


@dataclass(frozen=True)
class FirstMatch:
    rule: Rule | None
    evaluations: tuple[RuleEvaluation, ...]
    ruleset_revision: str
    captured_at: datetime
    explicit_selection: bool = False


def first_match(ruleset: RuleSet, facts: FileFacts, now: datetime, *, rule_id=None,
                watch_root=None, configured_watch_roots=None) -> FirstMatch:
    """Selected disabled rule may be tested; this never authorizes execution.

    Automatic callers supply configured_watch_roots to reject obsolete scopes.
    Scope names alone cannot add or recursively expand watched roots.
    """
    aware_date(now)
    if rule_id is not None and not any(rule.id == rule_id for rule in ruleset.rules): raise ValueError('所选规则不存在')
    root = str(Path(watch_root) if watch_root is not None else facts.path.parent).casefold()
    configured = None if configured_watch_roots is None else {str(Path(path)).casefold() for path in configured_watch_roots}
    winner = None
    evaluations = []
    for rule in ruleset.rules:
        status = reason = ''
        explanation = None
        if winner is not None: status, reason = 'not_evaluated', '前面的规则已匹配，本规则未评估'
        elif rule_id is not None and rule.id != rule_id: status, reason = 'not_evaluated', '本次只测试所选规则，本规则未评估'
        elif rule_id is None and not rule.enabled: status, reason = 'disabled', '规则已停用，未评估'
        elif configured is not None and {str(Path(path)).casefold() for path in rule.scope} - configured:
            status, reason = 'invalid_scope', '规则引用未配置的观察目录，不能新增观察范围'
        elif rule_id is None and ((configured is not None and root not in configured) or root != str(facts.path.parent).casefold()):
            status, reason = 'out_of_scope', '自动规则仅评估已配置观察目录的顶层项目'
        elif rule_id is None and rule.scope and root not in {str(Path(path)).casefold() for path in rule.scope}:
            status, reason = 'out_of_scope', '文件不在此规则的顶层观察目录中'
        else:
            explanation = evaluate(rule.condition, facts, now)
            status, reason = explanation.status, explanation.reason
            if explanation.matched: winner = rule
        evaluations.append(RuleEvaluation(rule.id, rule.name, status, reason, explanation))
    return FirstMatch(winner, tuple(evaluations), ruleset.revision, now, rule_id is not None)
