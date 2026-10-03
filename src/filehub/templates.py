"""State-local immutable project templates; missing state remains read-only."""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import PureWindowsPath
from types import MappingProxyType
import json
import os
import re
import tempfile

from .models import checked_path
from .naming import validate_component, validate_pattern
from .platform.windows import process_lock


def _relative(value):
    if not isinstance(value, str) or not value or PureWindowsPath(value).anchor:
        raise ValueError('模板目录必须是项目内的相对路径')
    parts = value.replace('\\', '/').split('/')
    for part in parts: validate_component(part)
    return '/'.join(parts)


def _mapping(value, label):
    if not isinstance(value, Mapping): raise ValueError(f'{label}必须是映射')
    return dict(value)


def _keyword(word):
    validate_component(word)
    if not word.strip(): raise ValueError('类别和口令不能为空')
    if re.search(r'[\s_-]', word): raise ValueError('类别和口令不能包含空格、横线或下划线')
    if word.startswith('成片') or word.upper().startswith('PV') or word.startswith('正片') or word == '测试' or re.match(r'^(?:[Ee]\d|\d)', word):
        raise ValueError('类别或口令与保留路由语法冲突')
    return word


@dataclass(frozen=True)
class ProjectTemplate:
    id: str = 'default'
    name: str = '默认模板'
    production_dir: str = '3_制作'
    asset_root: str = '1_设定'
    asset_categories: Mapping[str, str] = field(default_factory=lambda: {'角色': '角色', '场景': '场景', '道具': '道具'})
    final_dir: str = '4_交付'
    keep_name_routes: Mapping[str, str] = field(default_factory=lambda: {'剧本': '2_剧本分镜', '甲方': '0_甲方', '参考': '_参考'})
    test_dir: str = '_测试'
    naming_patterns: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', self.id):
            raise ValueError('模板 id 只能使用字母、数字、横线和下划线')
        if not isinstance(self.name, str) or not self.name.strip(): raise ValueError('模板名称不能为空')
        for key in ('production_dir', 'asset_root', 'final_dir', 'test_dir'):
            object.__setattr__(self, key, _relative(getattr(self, key)))
        for key in ('asset_categories', 'keep_name_routes'):
            mapping = _mapping(getattr(self, key), key)
            object.__setattr__(self, key, MappingProxyType({_keyword(k): _relative(v) for k, v in mapping.items()}))
        categories = {k.casefold() for k in self.asset_categories}
        routes = {k.casefold() for k in self.keep_name_routes}
        if len(categories) != len(self.asset_categories) or len(routes) != len(self.keep_name_routes) or categories & routes:
            raise ValueError('类别与保留名称口令冲突或重复')
        patterns = _mapping(self.naming_patterns, '命名模板')
        if patterns.keys() - {'shot', 'asset', 'final'}: raise ValueError('未知命名模式')
        for pattern in patterns.values(): validate_pattern(pattern)
        object.__setattr__(self, 'naming_patterns', MappingProxyType(patterns))

    def to_document(self):
        return {key: dict(value) if isinstance(value, Mapping) else value for key, value in vars(self).items()}


_DEFAULT = ProjectTemplate()


@dataclass(frozen=True)
class TemplateLibrary:
    templates: Mapping[str, ProjectTemplate] = field(default_factory=lambda: {'default': _DEFAULT})
    assignments: Mapping[str, str] = field(default_factory=dict)
    default_template_id: str | None = 'default'
    inject_defaults: bool = True
    revision: str = field(init=False)

    def __post_init__(self):
        templates = _mapping(self.templates, '模板')
        if self.inject_defaults: templates.setdefault('default', _DEFAULT)
        for key, template in templates.items():
            if not isinstance(template, ProjectTemplate) or key != template.id: raise ValueError('模板 id 不一致')
        if self.inject_defaults and templates['default'] != _DEFAULT: raise ValueError('默认模板不可修改，请先复制')
        if self.default_template_id is not None and self.default_template_id not in templates: raise ValueError('缺少所选默认模板')
        if templates and self.default_template_id is None: raise ValueError('需要显式默认模板')
        assignments = {}
        for code, identifier in _mapping(self.assignments, '项目分配').items():
            if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9]+', code): raise ValueError('项目代码无效')
            code = code.upper()
            if code in assignments: raise ValueError('项目代码重复')
            if not isinstance(identifier, str) or identifier not in templates: raise ValueError('项目引用未知模板')
            assignments[code] = identifier
        object.__setattr__(self, 'templates', MappingProxyType(templates))
        object.__setattr__(self, 'assignments', MappingProxyType(assignments))
        document = self.to_document()
        if not self.inject_defaults: document['default_template_id'] = self.default_template_id
        digest = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        object.__setattr__(self, 'revision', sha256(digest.encode('utf-8')).hexdigest())

    def for_project(self, code):
        return self.templates[self.assignments.get(code.upper(), self.default_template_id)]

    def with_template(self, template):
        templates = dict(self.templates); templates[template.id] = template
        return TemplateLibrary(templates, self.assignments, self.default_template_id, self.inject_defaults)

    def copy_template(self, identifier, new_id, name):
        if new_id in self.templates: raise ValueError('模板 id 已存在')
        return self.with_template(replace(self.templates[identifier], id=new_id, name=name))

    def assign(self, code, identifier):
        assignments = dict(self.assignments)
        if identifier is None: assignments.pop(code.upper(), None)
        else: assignments[code.upper()] = identifier
        return TemplateLibrary(self.templates, assignments, self.default_template_id, self.inject_defaults)

    def delete_template(self, identifier):
        if identifier == 'default': raise ValueError('默认模板不可删除')
        if identifier in self.assignments.values(): raise ValueError('已分配的模板不可删除，请先解除分配')
        templates = dict(self.templates); del templates[identifier]
        return TemplateLibrary(templates, self.assignments, self.default_template_id, self.inject_defaults)

    def to_document(self):
        return {'version': 1, 'templates': [self.templates[k].to_document() for k in sorted(self.templates)],
                'assignments': dict(self.assignments)}

    @classmethod
    def from_document(cls, data):
        if not isinstance(data, dict) or set(data) != {'version', 'templates', 'assignments'}:
            raise ValueError('模板文档结构无效')
        if type(data['version']) is not int or data['version'] != 1: raise ValueError('不支持的模板版本')
        if not isinstance(data['templates'], list): raise ValueError('模板列表无效')
        templates = {}
        fields = set(ProjectTemplate.__dataclass_fields__)
        for row in data['templates']:
            if not isinstance(row, dict) or set(row) - fields or not {'id', 'name'} <= set(row): raise ValueError('模板字段无效')
            template = ProjectTemplate(**row)
            if template.id in templates: raise ValueError('模板 id 重复')
            templates[template.id] = template
        return cls(templates, data['assignments'])


class TemplateStore:
    def __init__(self, state_dir):
        self.state_dir = checked_path(state_dir)
        self.path = self.state_dir/'templates.json'
        self._lock = process_lock(self.state_dir)

    def _load(self):
        checked_path(self.path)
        if not self.path.exists(): return TemplateLibrary()
        return TemplateLibrary.from_document(json.loads(self.path.read_text(encoding='utf-8')))

    def load(self):
        # The absent case deliberately creates neither directory nor lock file.
        checked_path(self.path)
        if not self.path.exists(): return TemplateLibrary()
        checked_path(self.state_dir/'engine.lock')
        with self._lock.acquire(): return self._load()

    def save(self, library, expected_revision=None):
        if not isinstance(library, TemplateLibrary): raise ValueError('必须保存 TemplateLibrary')
        library = TemplateLibrary.from_document(library.to_document())
        checked_path(self.state_dir).mkdir(parents=True, exist_ok=True)
        checked_path(self.state_dir/'engine.lock')
        with self._lock.acquire():
            current = self._load()
            if expected_revision is not None and current.revision != expected_revision:
                raise ValueError('模板已变化，请重新加载后保存')
            deleted = current.templates.keys() - library.templates.keys()
            if deleted & set(current.assignments.values()): raise ValueError('已分配的模板不可删除，请先解除分配并保存')
            fd, name = tempfile.mkstemp(prefix='.templates-', dir=self.state_dir)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(library.to_document(), stream, ensure_ascii=False, indent=2)
                    stream.flush(); os.fsync(stream.fileno())
                checked_path(self.path)
                os.replace(name, self.path)
            finally:
                if os.path.exists(name): os.unlink(name)
            return library
