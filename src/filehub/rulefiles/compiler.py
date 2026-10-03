"""Resolve explicitly selected folders without creating or watching anything."""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re

from ..automation.models import Action, Rule, absolute_folder
from ..models import checked_path
from .protocol import Diagnostic, ID_PATTERN, PathReference, RulePackage, expand_variables, encode_package, parse_package


def runtime_id(package_id: str, rule_id: str) -> str:
    return 'ext_' + sha256((package_id+'\0'+rule_id).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class PackageCompilation:
    rules: tuple[Rule, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    unresolved: frozenset[str] = frozenset()


def compile_package(package: RulePackage, bindings: Mapping[str, Path], runtime_ids: Mapping[str, str],
                    enabled_ids: frozenset[str], *, state_dir: Path) -> PackageCompilation:
    package = parse_package(encode_package(package))  # Never trust directly constructed objects.
    diagnostics = []; unresolved = set(); rules = []
    state = checked_path(state_dir)
    def resolve(ref, path):
        if ref.binding not in bindings:
            unresolved.add(ref.binding)
            raise ValueError(f'未绑定目录 {ref.binding}')
        raw = bindings[ref.binding]
        if not isinstance(raw, (Path, str)) or not Path(raw).is_absolute(): raise ValueError('绑定必须是绝对目录')
        root = checked_path(Path(absolute_folder(str(raw))))
        if root.exists() and not root.is_dir(): raise ValueError('绑定必须是目录')
        relative = expand_variables(ref.relative, package.variables, path)
        target = checked_path(root.joinpath(*relative.split('/'))) if relative else root
        if len(str(target).encode('utf-16-le'))//2>=32767: raise ValueError('目标超过 Windows UTF-16 长路径限制')
        # checked_path prohibits all existing reparse ancestors, including missing tails.
        root_key = os.path.normcase(str(root)).casefold(); target_key = os.path.normcase(str(target)).casefold()
        state_key = os.path.normcase(str(state)).casefold()
        def inside(child, parent): return child == parent or child.startswith(parent.rstrip('\\/')+os.sep)
        if not inside(target_key, root_key): raise ValueError('路径超出绑定目录')
        if any(inside(key, state_key) or inside(state_key, key) for key in (root_key, target_key)):
            raise ValueError('目录与应用状态重叠')
        return str(target)
    for index, definition in enumerate(package.rules):
        path = f'$.rules[{index}]'; failed = False; scope = []; actions = []
        for number, reference in enumerate(definition.scope):
            try: scope.append(resolve(reference, path+f'.scope[{number}]'))
            except (ValueError,OSError) as exc: diagnostics.append(Diagnostic(path+f'.scope[{number}]', str(exc))); failed = True
        for number, action in enumerate(definition.actions):
            location = path+f'.actions[{number}]'; options = dict(action['options'])
            try:
                if isinstance(options.get('destination'), PathReference): options['destination'] = resolve(options['destination'], location+'.options.destination')
                for key in ('pattern', 'path'):
                    if key in options: options[key] = expand_variables(options[key], package.variables, location+'.options.'+key)
                actions.append(Action(action['kind'], options))
            except (ValueError,OSError) as exc: diagnostics.append(Diagnostic(location, str(exc))); failed = True
        if failed: continue
        try:
            identifier = runtime_ids.get(definition.id, runtime_id(package.id, definition.id))
            if not isinstance(identifier, str) or not re.fullmatch(ID_PATTERN, identifier): raise ValueError('运行时规则 ID 无效')
            rules.append(Rule(identifier, definition.name, definition.condition, tuple(actions), definition.id in enabled_ids, tuple(scope)))
        except ValueError as exc: diagnostics.append(Diagnostic(path, str(exc)))
    if len({rule.id for rule in rules}) != len(rules):
        return PackageCompilation((), (*diagnostics, Diagnostic('$.rules', '运行时规则 ID 重复')), frozenset(unresolved))
    return PackageCompilation(tuple(rules), tuple(diagnostics), frozenset(unresolved))
