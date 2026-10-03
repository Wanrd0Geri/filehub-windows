"""Portable, closed rule definitions. Parsing never accesses application state."""
from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from types import MappingProxyType

from ..automation.models import Action, Predicate, ConditionGroup
from ..naming import validate_component, validate_pattern

MAX_PACKAGE_BYTES = 2_000_000
ID_PATTERN = r'[A-Za-z0-9_-]{1,128}'
ORDINARY_TOKENS = frozenset({'original', 'stem', 'ext', 'date', 'date_long', 'period', 'sequence'})
_VARIABLE = re.compile(r'\$\{([A-Za-z0-9_-]{1,128})\}')


@dataclass(frozen=True)
class Diagnostic:
    path: str
    message: str


class PackageError(ValueError):
    def __init__(self, path, message):
        self.diagnostic = Diagnostic(path, str(message))
        super().__init__(f'{path}: {message}')


def _keys(value, required, optional, path):
    if not isinstance(value, Mapping): raise PackageError(path, '必须是对象')
    if set(value) - set(required) - set(optional) or set(required) - set(value):
        raise PackageError(path, '包含未知字段或缺少必要字段')


def _text(value, path, limit, blank=False):
    if not isinstance(value, str) or len(value) > limit or any(0xD800 <= ord(c) <= 0xDFFF for c in value) or (not blank and not value.strip()):
        raise PackageError(path, '必须是有界的有效文字')
    if '${' in value: raise PackageError(path, '此字段不接受变量')
    return value


def _identifier(value, path):
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value): raise PackageError(path, '标识符无效')
    return value


def expand_variables(value, variables, path):
    if not isinstance(value, str): raise PackageError(path, '必须是文字')
    def substitute(match):
        if match[1] not in variables: raise PackageError(path, f'未声明变量 {match[1]}')
        return variables[match[1]]
    expanded = _VARIABLE.sub(substitute, value)
    if '$' in expanded: raise PackageError(path, '变量只能使用声明的 ${NAME}，且只展开一次')
    return expanded


def _relative(value, variables, path, *, empty=False):
    expanded = expand_variables(value, variables, path)
    if any(len(text.encode('utf-16-le',errors='surrogatepass'))//2>=32767 for text in (value,expanded)):
        raise PackageError(path, '相对路径超过 Windows UTF-16 长路径限制')
    if expanded == '' and empty: return expanded
    if '\\' in expanded: raise PackageError(path, '相对路径只接受斜线分隔')
    try:
        for component in expanded.split('/'): validate_component(component)
    except ValueError as exc: raise PackageError(path, exc) from exc
    return expanded


@dataclass(frozen=True)
class PathReference:
    binding: str
    relative: str

    def to_document(self): return {'binding': self.binding, 'relative': self.relative}


def _reference(data, bindings, variables, path):
    _keys(data, {'binding', 'relative'}, (), path)
    identifier = _identifier(data['binding'], path+'.binding')
    if identifier not in bindings: raise PackageError(path+'.binding', '未声明目录绑定')
    _relative(data['relative'], variables, path+'.relative', empty=True)
    return PathReference(identifier, data['relative'])


def _freeze(value):
    if isinstance(value, Mapping): return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list): return tuple(_freeze(v) for v in value)
    return value


def _thaw(value):
    if isinstance(value, PathReference): return value.to_document()
    if isinstance(value, Mapping): return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple): return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    scope: tuple[PathReference, ...]
    condition: object
    actions: tuple[Mapping, ...]

    def __post_init__(self):
        object.__setattr__(self, 'scope', tuple(self.scope))
        object.__setattr__(self, 'actions', tuple(_freeze(a) for a in self.actions))

    def to_document(self):
        return {'id': self.id, 'name': self.name, 'scope': [p.to_document() for p in self.scope],
                'condition': self.condition.to_document(), 'actions': _thaw(self.actions)}


@dataclass(frozen=True)
class RulePackage:
    id: str
    name: str
    bindings: Mapping
    variables: Mapping
    rules: tuple[RuleDefinition, ...]
    compatibility: object = None

    def __post_init__(self):
        object.__setattr__(self, 'bindings', _freeze(self.bindings))
        object.__setattr__(self, 'variables', _freeze(self.variables))
        object.__setattr__(self, 'rules', tuple(self.rules))

    def to_document(self):
        result = {'format': 'filehub.rules', 'version': 1, 'id': self.id, 'name': self.name,
                  'bindings': _thaw(self.bindings), 'variables': dict(self.variables),
                  'rules': [rule.to_document() for rule in self.rules]}
        if self.compatibility is not None: result['compatibility'] = self.compatibility.to_document()
        return result


def _action(data, bindings, variables, path, compatibility):
    _keys(data, {'kind', 'options'}, (), path)
    kind = data['kind']; options = data['options']
    if not isinstance(kind, str) or kind not in {'rename', 'move', 'copy', 'subfolder', 'image_convert', 'project_route'}:
        raise PackageError(path+'.kind', '未知动作')
    if kind == 'project_route' and compatibility is None: raise PackageError(path, '项目路由需要显式兼容配置')
    if not isinstance(options, Mapping): raise PackageError(path+'.options', '必须是对象')
    portable = dict(options); validated = dict(options)
    if kind in {'move', 'copy'} or (kind == 'image_convert' and options.get('mode', 'keep') == 'keep'):
        if 'destination' not in options: raise PackageError(path+'.options.destination', '缺少目标绑定')
        ref = _reference(options['destination'], bindings, variables, path+'.options.destination')
        portable['destination'] = ref
        validated['destination'] = 'C:\\FileHubPortableValidation'
    if kind == 'rename':
        if 'pattern' not in options: raise PackageError(path, '缺少命名模板')
        validated['pattern'] = expand_variables(options['pattern'], variables, path+'.options.pattern')
        try: validate_pattern(validated['pattern'], ORDINARY_TOKENS)
        except (ValueError, TypeError) as exc: raise PackageError(path, exc) from exc
    elif kind == 'subfolder':
        if 'path' not in options: raise PackageError(path, '缺少子目录')
        validated['path'] = _relative(options['path'], variables, path+'.options.path')
    for key, value in options.items():
        if isinstance(value, str) and '${' in value and not (kind == 'rename' and key == 'pattern' or kind == 'subfolder' and key == 'path'):
            raise PackageError(path+'.options.'+key, '此字段不接受变量')
    try: Action(kind, validated)
    except (ValueError, TypeError, OverflowError) as exc: raise PackageError(path, exc) from exc
    return _freeze({'kind': kind, 'options': portable})


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise PackageError('$', f'重复字段 {key}')
        result[key] = value
    return result


def _condition(data, path, depth=0):
    if not isinstance(data, Mapping): raise PackageError(path, '条件必须是对象')
    try:
        if 'mode' not in data:
            _keys(data, {'field', 'operator', 'value'}, (), path)
            if isinstance(data['value'], str) and '${' in data['value']: raise PackageError(path+'.value', '条件不接受变量')
            return Predicate(**data)
        _keys(data, {'mode', 'children'}, (), path)
        if depth >= 4: raise PackageError(path, '条件组超过 4 层')
        children = data['children']
        if not isinstance(children, list) or not 1 <= len(children) <= 100: raise PackageError(path+'.children', '条件组需要 1–100 个子项')
        return ConditionGroup(data['mode'], tuple(_condition(child, path+f'.children[{i}]', depth+1) for i, child in enumerate(children)))
    except PackageError: raise
    except (ValueError, TypeError) as exc: raise PackageError(path, exc) from exc


def parse_package(data: bytes) -> RulePackage:
    if not isinstance(data, bytes): raise PackageError('$', '输入必须是 UTF-8 字节')
    if len(data) > MAX_PACKAGE_BYTES: raise PackageError('$', '文件超过 2000000 字节')
    try:
        doc = json.loads(data.decode('utf-8'), object_pairs_hook=_unique,
                         parse_constant=lambda value: (_ for _ in ()).throw(PackageError('$', '禁止非有限数字')))
        return _parse_document(doc)
    except PackageError: raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise PackageError('$', 'JSON 无效或嵌套过深') from exc


def _parse_document(doc):
    _keys(doc, {'format', 'version', 'id', 'name', 'bindings', 'variables', 'rules'}, {'compatibility'}, '$')
    if doc['format'] != 'filehub.rules' or type(doc['version']) is not int or doc['version'] != 1:
        raise PackageError('$.version', '不支持的格式或版本')
    identifier = _identifier(doc['id'], '$.id'); name = _text(doc['name'], '$.name', 256)
    bindings = doc['bindings']; variables = doc['variables']
    for value, label in ((bindings, 'bindings'), (variables, 'variables')):
        if not isinstance(value, dict) or len(value) > 100: raise PackageError('$.'+label, '必须是至多 100 项的对象')
        for key in value: _identifier(key, '$.'+label+'.'+key)
    for key, declaration in bindings.items():
        _keys(declaration, {'label'}, {'description'}, '$.bindings.'+key)
        _text(declaration['label'], '$.bindings.'+key+'.label', 256)
        if 'description' in declaration: _text(declaration['description'], '$.bindings.'+key+'.description', 512, blank=True)
    for key, value in variables.items():
        _text(value, '$.variables.'+key, 256)
        try:
            validate_component(value)
            if any(c in value for c in '${}'): raise ValueError('变量必须是字面量组件文字')
        except ValueError as exc: raise PackageError('$.variables.'+key, exc) from exc
    compatibility = None
    if 'compatibility' in doc:
        # Task 3 owns the complete dialect. Absence is explicitly fail closed.
        try: from .compatibility import validate_archive_profile
        except ImportError as exc: raise PackageError('$.compatibility', '此版本尚无兼容配置验证器') from exc
        try: compatibility = validate_archive_profile(doc['compatibility'], bindings, variables)
        except (ValueError, TypeError) as exc: raise PackageError('$.compatibility', exc) from exc
        if not callable(getattr(compatibility, 'to_document', None)): raise PackageError('$.compatibility', '兼容验证器未返回已验证配置')
    if not isinstance(doc['rules'], list) or len(doc['rules']) > 1000: raise PackageError('$.rules', '规则必须是至多 1000 项的数组')
    rules = []; identifiers = set()
    for index, rule in enumerate(doc['rules']):
        path = f'$.rules[{index}]'
        _keys(rule, {'id', 'name', 'scope', 'condition', 'actions'}, (), path)
        rid = _identifier(rule['id'], path+'.id')
        if rid in identifiers: raise PackageError(path+'.id', '规则 ID 重复')
        identifiers.add(rid)
        rname = _text(rule['name'], path+'.name', 256)
        if not isinstance(rule['scope'], list) or len(rule['scope']) > 100: raise PackageError(path+'.scope', '范围必须是至多 100 项的数组')
        scope = tuple(_reference(ref, bindings, variables, path+f'.scope[{i}]') for i, ref in enumerate(rule['scope']))
        if len(set(scope)) != len(scope): raise PackageError(path+'.scope', '范围重复')
        condition = _condition(rule['condition'], path+'.condition')
        if not isinstance(rule['actions'], list) or not 1 <= len(rule['actions']) <= 20: raise PackageError(path+'.actions', '需要 1–20 个动作')
        actions = tuple(_action(a, bindings, variables, path+f'.actions[{i}]', compatibility) for i, a in enumerate(rule['actions']))
        if any(a['kind'] == 'project_route' for a in actions[:-1]): raise PackageError(path+'.actions', '项目路由必须最后执行')
        rules.append(RuleDefinition(rid, rname, scope, condition, actions))
    return RulePackage(identifier, name, _freeze(bindings), _freeze(variables), tuple(rules), compatibility)


def encode_package(package: RulePackage) -> bytes:
    if not isinstance(package, RulePackage): raise PackageError('$', '必须是 RulePackage')
    data = json.dumps(package.to_document(), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    parse_package(data)
    return data
