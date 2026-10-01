"""Immutable finite rule schema and atomic, state-local definition storage."""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
import json
import math
import os
import re
import tempfile
import uuid

from ..conversion.models import ConversionSpec
from ..models import checked_path
from ..naming import validate_component, validate_pattern
from ..platform.windows import process_lock

MAX_GROUP_LEVELS = 4
MAX_LEAVES = 100
MAX_ACTIONS = 20
MAX_RULES = 1000
MAX_DOCUMENT_BYTES = 2_000_000
TEXT_FIELDS = frozenset({'kind', 'extension', 'name'})
NUMBER_FIELDS = frozenset({'size_bytes', 'first_seen_age_seconds', 'stable_age_seconds'})
DATE_FIELDS = frozenset({'created', 'modified'})
TEXT_OPERATORS = frozenset({'equals', 'contains', 'starts_with', 'ends_with', 'glob'})
ORDER_OPERATORS = frozenset({'eq', 'lt', 'le', 'gt', 'ge'})
KINDS = frozenset({'file', 'folder', 'image', 'video', 'audio', 'document', 'other'})


def _text(value, label, limit=4096):
    if not isinstance(value, str) or not value or len(value) > limit or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f'{label}必须是非空、有界的文字')
    return value


def _keys(data, required, optional=()):
    if not isinstance(data, Mapping) or data.keys() - set(required) - set(optional) or set(required) - data.keys():
        raise ValueError('定义包含未知字段或缺少必要字段')


def aware_date(value):
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value)
        except ValueError as exc: raise ValueError('日期必须是包含时区的 ISO8601') from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('日期必须包含明确时区')
    return value


def _digest(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def absolute_folder(value):
    _text(value, '目标目录')
    path = PureWindowsPath(value)
    if not path.is_absolute(): raise ValueError('目标目录必须是明确选择的绝对目录')
    if path.drive.startswith('\\\\'):
        anchor_parts = path.drive[2:].split('\\')
        if len(anchor_parts) != 2: raise ValueError('不支持设备路径或扩展命名空间')
        for part in anchor_parts: validate_component(part)
    # Validate before normalizing: traversal must never disappear silently.
    tail = value.replace('\\', '/')[len(path.anchor.replace('\\', '/')):]
    if tail:
        for part in tail.split('/'): validate_component(part)
    return str(path)


def relative_folder(value):
    _text(value, '子目录')
    if PureWindowsPath(value).anchor: raise ValueError('子目录必须是相对路径')
    parts = value.replace('\\', '/').split('/')
    for part in parts: validate_component(part)
    return '/'.join(parts)


@dataclass(frozen=True)
class Predicate:
    field: str
    operator: str
    value: object

    def __post_init__(self):
        if not isinstance(self.field, str) or not isinstance(self.operator, str): raise ValueError('条件字段和运算符必须是文字')
        if self.field in TEXT_FIELDS:
            if self.operator not in TEXT_OPERATORS: raise ValueError('文字条件使用不支持的运算符')
            value = _text(self.value, '比较值')
            if self.field == 'extension':
                value = value.casefold()
                if self.operator in {'equals', 'starts_with'} or (self.operator == 'glob' and not value.startswith(('*', '?', '['))):
                    if not value.startswith('.'): value = '.' + value
            if self.field == 'kind' and (self.operator != 'equals' or value.casefold() not in KINDS):
                raise ValueError('类型条件仅支持 equals 和已知类型')
            object.__setattr__(self, 'value', value)
        elif self.field in NUMBER_FIELDS:
            if self.operator not in ORDER_OPERATORS: raise ValueError('数字条件使用不支持的运算符')
            if type(self.value) not in (int, float) or not 0 <= self.value <= 2**63-1 or not math.isfinite(self.value):
                raise ValueError('数字阈值必须是有限、非负的数字，不能是布尔值')
        elif self.field in DATE_FIELDS:
            if self.operator not in ORDER_OPERATORS: raise ValueError('日期条件使用不支持的运算符')
            object.__setattr__(self, 'value', aware_date(self.value).isoformat())
        else: raise ValueError('未知条件字段')

    def to_document(self):
        return {'field': self.field, 'operator': self.operator, 'value': self.value}


def _condition_limits(node, depth=0):
    if isinstance(node, Predicate): return 1
    if not isinstance(node, ConditionGroup): raise ValueError('条件必须是已验证的条件树')
    if depth + 1 > MAX_GROUP_LEVELS: raise ValueError('条件组最多 4 层（根组为第 1 层）')
    leaves = sum(_condition_limits(child, depth+1) for child in node.children)
    if leaves > MAX_LEAVES: raise ValueError('条件最多 100 个比较项')
    return leaves


@dataclass(frozen=True)
class ConditionGroup:
    mode: str
    children: tuple

    def __post_init__(self):
        if not isinstance(self.mode, str) or self.mode not in {'all', 'any', 'none'}: raise ValueError('未知条件组逻辑')
        if not isinstance(self.children, (tuple, list)) or not self.children or len(self.children) > MAX_LEAVES:
            raise ValueError('条件组不能为空且最多 100 个子项')
        object.__setattr__(self, 'children', tuple(self.children))
        _condition_limits(self)

    def to_document(self):
        return {'mode': self.mode, 'children': [child.to_document() for child in self.children]}


def condition_from_document(data, depth=0):
    if not isinstance(data, Mapping): raise ValueError('条件必须是对象')
    if 'mode' not in data:
        _keys(data, {'field', 'operator', 'value'})
        return Predicate(**data)
    _keys(data, {'mode', 'children'})
    if depth >= MAX_GROUP_LEVELS: raise ValueError('条件组超过 4 层')
    if not isinstance(data['children'], list) or not 0 < len(data['children']) <= MAX_LEAVES:
        raise ValueError('条件组不能为空或超过限制')
    return ConditionGroup(data['mode'], tuple(condition_from_document(child, depth+1) for child in data['children']))


@dataclass(frozen=True)
class Action:
    kind: str
    options: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.kind, str): raise ValueError('动作类型必须是文字')
        if not isinstance(self.options, Mapping): raise ValueError('动作配置必须是对象')
        options = dict(self.options)
        if self.kind == 'rename':
            _keys(options, {'pattern'})
            validate_pattern(options['pattern'])
            _text(options['pattern'], '命名模板')
        elif self.kind in {'move', 'copy'}:
            _keys(options, {'destination'})
            options['destination'] = absolute_folder(options['destination'])
        elif self.kind == 'subfolder':
            _keys(options, {'path'})
            options['path'] = relative_folder(options['path'])
        elif self.kind == 'project_route':
            _keys(options, {'tag'})
            _text(options['tag'], '项目口令')
        elif self.kind == 'image_convert':
            _keys(options, {'output_format'}, {'mode', 'destination', 'quality', 'background', 'lossless', 'timeout_seconds', 'max_pixels', 'kind'})
            mode = options.get('mode', 'keep')
            if not isinstance(mode, str) or mode not in {'keep', 'replace'}: raise ValueError('转换模式仅支持 keep 或 replace')
            if mode == 'replace' and 'destination' in options: raise ValueError('替换模式不接受外部目录')
            if mode == 'keep': options['destination'] = absolute_folder(options.get('destination'))
            try:
                spec = ConversionSpec(**{key: value for key, value in options.items() if key not in {'mode', 'destination'}})
            except (TypeError, OverflowError) as exc: raise ValueError('图片预设包含无效的字段类型或超大数字') from exc
            options.update(vars(spec))
            options['mode'] = mode
        else: raise ValueError('未知动作；此版本不支持脚本或视频转换')
        object.__setattr__(self, 'options', MappingProxyType(options))

    @property
    def conversion_spec(self):
        if self.kind != 'image_convert': return None
        return ConversionSpec(**{key: value for key, value in self.options.items() if key not in {'mode', 'destination'}})

    def to_document(self):
        return {'kind': self.kind, 'options': dict(self.options)}


@dataclass(frozen=True)
class Rule:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = '新规则'
    condition: Predicate | ConditionGroup | None = None
    actions: tuple[Action, ...] = ()
    enabled: bool = False
    scope: tuple[str, ...] = ()
    revision: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', self.id): raise ValueError('规则 id 无效')
        _text(self.name, '规则名称', 256)
        if not self.name.strip(): raise ValueError('规则名称不能为空')
        if type(self.enabled) is not bool: raise ValueError('启用状态必须是布尔值')
        _condition_limits(self.condition)
        if not isinstance(self.actions, (list, tuple)) or not 0 < len(self.actions) <= MAX_ACTIONS:
            raise ValueError('规则必须有 1–20 个动作')
        if any(not isinstance(action, Action) for action in self.actions): raise ValueError('动作必须先通过验证')
        if any(action.kind == 'project_route' for action in self.actions[:-1]): raise ValueError('项目路由必须是最后一个动作')
        if not isinstance(self.scope, (list, tuple)) or len(self.scope) > 100: raise ValueError('观察范围无效或过多')
        scope = tuple(absolute_folder(value) for value in self.scope)
        if len({value.casefold() for value in scope}) != len(scope): raise ValueError('观察范围重复')
        object.__setattr__(self, 'actions', tuple(self.actions))
        object.__setattr__(self, 'scope', scope)
        object.__setattr__(self, 'revision', _digest({'condition': self.condition.to_document(),
            'actions': [action.to_document() for action in self.actions], 'scope': sorted(scope, key=str.casefold)}))

    def to_document(self):
        return {'id': self.id, 'name': self.name, 'enabled': self.enabled, 'scope': list(self.scope),
                'condition': self.condition.to_document(), 'actions': [a.to_document() for a in self.actions]}

    @classmethod
    def from_document(cls, data):
        _keys(data, {'id', 'name', 'enabled', 'scope', 'condition', 'actions'})
        if not isinstance(data['actions'], list) or not 0 < len(data['actions']) <= MAX_ACTIONS: raise ValueError('动作数量无效')
        actions = []
        for item in data['actions']:
            _keys(item, {'kind', 'options'})
            actions.append(Action(**item))
        return cls(**{**data, 'condition': condition_from_document(data['condition']), 'actions': tuple(actions)})


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...] = ()
    revision: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.rules, (list, tuple)) or len(self.rules) > MAX_RULES: raise ValueError('规则数量超过 1000 条限制')
        if any(not isinstance(rule, Rule) for rule in self.rules): raise ValueError('规则必须先通过验证')
        if len({rule.id for rule in self.rules}) != len(self.rules): raise ValueError('规则 id 重复')
        object.__setattr__(self, 'rules', tuple(self.rules))
        object.__setattr__(self, 'revision', _digest(self.to_document()))

    def to_document(self):
        return {'version': 1, 'rules': [rule.to_document() for rule in self.rules]}

    @classmethod
    def from_document(cls, data):
        _keys(data, {'version', 'rules'})
        if type(data['version']) is not int or data['version'] != 1: raise ValueError('不支持的规则版本')
        if not isinstance(data['rules'], list) or len(data['rules']) > MAX_RULES: raise ValueError('规则列表无效或超过限制')
        try:
            if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_DOCUMENT_BYTES:
                raise ValueError('规则文件超过 2 MB 限制')
        except (TypeError, RecursionError, UnicodeError, OverflowError) as exc:
            raise ValueError('规则文档包含无效数据或嵌套过深') from exc
        return cls(tuple(Rule.from_document(item) for item in data['rules']))

    def with_rule(self, rule):
        rules = tuple(rule if item.id == rule.id else item for item in self.rules)
        return RuleSet(rules if any(item.id == rule.id for item in self.rules) else (*rules, rule))

    def duplicate(self, identifier, name=None):
        original = next((item for item in self.rules if item.id == identifier), None)
        if original is None: raise ValueError('规则不存在')
        return RuleSet((*self.rules, replace(original, id=uuid.uuid4().hex, name=name or original.name+' 副本', enabled=False)))

    def delete(self, identifier):
        if not any(item.id == identifier for item in self.rules): raise ValueError('规则不存在')
        return RuleSet(tuple(item for item in self.rules if item.id != identifier))

    def reorder(self, identifiers):
        identifiers = tuple(identifiers)
        if len(identifiers) != len(self.rules) or set(identifiers) != {item.id for item in self.rules}: raise ValueError('排序必须包含每条规则一次')
        by_id = {item.id: item for item in self.rules}
        return RuleSet(tuple(by_id[identifier] for identifier in identifiers))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('JSON 对象包含重复字段')
        result[key] = value
    return result


def _document_text(ruleset):
    data = json.dumps(ruleset.to_document(), ensure_ascii=False, indent=2, allow_nan=False)
    if len(data.encode('utf-8')) > MAX_DOCUMENT_BYTES: raise ValueError('规则文件超过 2 MB 限制')
    return data


class RuleStore:
    """Only definitions are written; deleting rules never touches run history."""
    def __init__(self, state_dir):
        self.state_dir = Path(os.path.abspath(state_dir))
        self.path = self.state_dir/'automation-rules.json'
        self._lock = process_lock(self.state_dir)

    def _load(self):
        checked_path(self.state_dir)
        checked_path(self.path)
        if not self.path.exists(): return RuleSet()
        if self.path.stat().st_size > MAX_DOCUMENT_BYTES: raise ValueError('规则文件超过 2 MB 限制')
        try:
            with self.path.open('r', encoding='utf-8') as stream:
                data = json.load(stream, object_pairs_hook=_unique_object)
            return RuleSet.from_document(data)
        except (json.JSONDecodeError, RecursionError, UnicodeError, OverflowError) as exc:
            raise ValueError('规则文件损坏或嵌套过深；原文件保持不变') from exc

    def load(self):
        checked_path(self.state_dir)
        checked_path(self.path)
        if not self.path.exists(): return RuleSet()
        checked_path(self.state_dir/'engine.lock')
        with self._lock.acquire(): return self._load()

    def _save(self, ruleset, expected_revision=None):
        current = self._load()
        if expected_revision is not None and current.revision != expected_revision: raise ValueError('规则已变化，请重新加载后保存')
        data = _document_text(ruleset)
        fd, name = tempfile.mkstemp(prefix='.automation-rules-', dir=checked_path(self.state_dir))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(data)
                stream.flush(); os.fsync(stream.fileno())
            checked_path(self.path)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)
        return ruleset

    def save(self, ruleset, expected_revision=None):
        if not isinstance(ruleset, RuleSet): raise ValueError('必须保存 RuleSet')
        validated = RuleSet.from_document(ruleset.to_document())
        _document_text(validated)
        checked_path(self.state_dir).mkdir(parents=True, exist_ok=True)
        checked_path(self.state_dir/'engine.lock')
        with self._lock.acquire(): return self._save(validated, expected_revision)

    def import_document(self, data, expected_revision=None):
        # Full validation precedes creating state or replacing any settings.
        imported = RuleSet.from_document(data)
        imported = tuple(replace(rule, id=uuid.uuid4().hex, enabled=False) for rule in imported.rules)
        _document_text(RuleSet(imported))
        checked_path(self.state_dir).mkdir(parents=True, exist_ok=True)
        checked_path(self.state_dir/'engine.lock')
        with self._lock.acquire():
            current = self._load()
            return self._save(RuleSet((*current.rules, *imported)), expected_revision)

    def export_document(self):
        return self.load().to_document()
