"""Complete, explicitly selected legacy tag dialect; no discovery or defaults."""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
import re

from ..automation.models import absolute_folder
from ..models import checked_path
from ..naming import validate_component
from ..templates import ProjectTemplate, TemplateLibrary
from ..automation.planner import paths_overlap, path_key
from .protocol import PathReference, PackageError, _keys, _reference, _identifier, _text, expand_variables


@dataclass(frozen=True)
class ArchivePolicies:
    inbox_root: PathReference
    categories: Mapping
    arrival_delay_seconds: int
    expiry_delay_seconds: int
    disposable_filenames: tuple[str, ...]
    sanitization_roots: tuple[PathReference, ...]

    def to_document(self):
        return {'inbox_root':self.inbox_root.to_document(), 'categories':dict(self.categories),
                'arrival_delay_seconds':self.arrival_delay_seconds, 'expiry_delay_seconds':self.expiry_delay_seconds,
                'disposable_filenames':list(self.disposable_filenames),
                'sanitization_roots':[r.to_document() for r in self.sanitization_roots]}


@dataclass(frozen=True)
class ArchiveProfile:
    root: PathReference
    projects: Mapping
    templates: tuple[ProjectTemplate, ...]
    assignments: Mapping
    default_template: str
    general_test: PathReference
    policies: ArchivePolicies

    def to_document(self):
        return {'format':'filehub.archive.v1', 'root':self.root.to_document(),
                'projects':{k:v.to_document() for k,v in self.projects.items()},
                'templates':[t.to_document() for t in self.templates], 'assignments':dict(self.assignments),
                'default_template':self.default_template, 'general_test':self.general_test.to_document(),
                'policies':self.policies.to_document()}


@dataclass(frozen=True)
class ResolvedArchiveContext:
    package_id: str
    root: Path
    projects: Mapping
    templates: TemplateLibrary
    general_test: Path
    inbox_root: Path
    categories: Mapping
    arrival_delay_seconds: int
    expiry_delay_seconds: int
    disposable_filenames: tuple[str, ...]
    sanitization_roots: tuple[Path, ...]

    def route(self, tag):
        from ..rules import parse_tag
        return parse_tag(tag, self.projects, self.root, self.templates, general_test=self.general_test)

    def inbox_ancestors(self,source):
        """Capture only empty-parent pruning authority inside the declared inbox."""
        from ..trees import DirectoryIdentity
        inbox=checked_path(self.inbox_root);source=checked_path(source)
        if not source.is_relative_to(inbox):return ()
        parts=source.relative_to(inbox).parts
        if len(parts)<3 or parts[0] not in self.categories.values() or not re.fullmatch(r'\d{6}',parts[1]):return ()
        day=inbox/parts[0]/parts[1];result=[];path=source.parent
        while path==day or path.is_relative_to(day):
            info=checked_path(path).stat()
            result.append((path,DirectoryIdentity('.',info.st_dev,info.st_ino,info.st_birthtime_ns,info.st_mtime_ns)))
            if path==day:break
            path=path.parent
        return tuple(result)


def validate_archive_profile(data, bindings, variables) -> ArchiveProfile:
    path='$.compatibility'
    _keys(data, {'format','root','projects','templates','assignments','default_template','general_test','policies'}, (), path)
    if data['format']!='filehub.archive.v1': raise PackageError(path+'.format','未知兼容格式')
    root=_reference(data['root'],bindings,variables,path+'.root')
    general=_reference(data['general_test'],bindings,variables,path+'.general_test')
    projects=data['projects']; assignments=data['assignments']; records=data['templates']
    if not isinstance(projects, Mapping) or len(projects)>100: raise PackageError(path+'.projects','项目映射最多 100 项')
    validated={}
    for code, reference in projects.items():
        if not isinstance(code,str) or not re.fullmatch('[A-Za-z0-9]{1,128}',code) or code.upper() in validated:
            raise PackageError(path+'.projects','项目代码无效或重复')
        validated[code.upper()]=_reference(reference,bindings,variables,path+'.projects.'+code)
    if not isinstance(records,list) or not 1<=len(records)<=100: raise PackageError(path+'.templates','需要完整模板记录 1–100 项')
    templates={}
    for i,row in enumerate(records):
        location=path+f'.templates[{i}]'
        _keys(row, set(ProjectTemplate.__dataclass_fields__), (), location)
        _identifier(row['id'],location+'.id'); _text(row['name'],location+'.name',256)
        for key in ('production_dir','asset_root','final_dir','test_dir'):
            _text(row[key],location+'.'+key,4096)
        for key in ('asset_categories','keep_name_routes','naming_patterns'):
            if not isinstance(row[key],Mapping) or len(row[key])>100: raise PackageError(location+'.'+key,'必须是有界映射')
            for name,value in row[key].items():
                _text(name,location+'.'+key,256); _text(value,location+'.'+key,4096)
        try: template=ProjectTemplate(**row)
        except (ValueError,TypeError) as exc: raise PackageError(location,exc) from exc
        if template.id in templates: raise PackageError(location+'.id','模板 ID 重复')
        templates[template.id]=template
    default=_identifier(data['default_template'],path+'.default_template')
    if default not in templates: raise PackageError(path+'.default_template','未知默认模板')
    if not isinstance(assignments,Mapping) or len(assignments)>100: raise PackageError(path+'.assignments','无效模板分配')
    normalized={}
    for code, identifier in assignments.items():
        if not isinstance(code,str) or not re.fullmatch('[A-Za-z0-9]{1,128}',code) or code.upper() in normalized or not isinstance(identifier,str) or identifier not in templates:
            raise PackageError(path+'.assignments','模板分配必须使用有效项目代码和已声明模板')
        normalized[code.upper()]=identifier
    policy=data['policies']; location=path+'.policies'
    _keys(policy, {'inbox_root','categories','arrival_delay_seconds','expiry_delay_seconds','disposable_filenames','sanitization_roots'}, (), location)
    inbox=_reference(policy['inbox_root'],bindings,variables,location+'.inbox_root')
    _keys(policy['categories'], {'image','video','other'}, (), location+'.categories')
    for value in policy['categories'].values():
        try: validate_component(value)
        except (ValueError,TypeError) as exc: raise PackageError(location+'.categories',exc) from exc
        _text(value,location+'.categories',256)
    if len({v.casefold() for v in policy['categories'].values()})!=3: raise PackageError(location+'.categories','类别目录不能重复')
    for key in ('arrival_delay_seconds','expiry_delay_seconds'):
        if type(policy[key]) is not int or not 0<=policy[key]<=2**63-1: raise PackageError(location+'.'+key,'必须是非负整数秒')
    filenames=policy['disposable_filenames']; roots=policy['sanitization_roots']
    if not isinstance(filenames,list) or len(filenames)>100: raise PackageError(location+'.disposable_filenames','需要至多 100 个精确文件名')
    for value in filenames:
        try: validate_component(value)
        except (ValueError,TypeError) as exc: raise PackageError(location+'.disposable_filenames',exc) from exc
        if '${' in value: raise PackageError(location+'.disposable_filenames','文件名不接受变量')
    if len(set(v.casefold() for v in filenames))!=len(filenames): raise PackageError(location+'.disposable_filenames','文件名重复')
    if not isinstance(roots,list) or len(roots)>100: raise PackageError(location+'.sanitization_roots','需要至多 100 项范围')
    safe_roots=tuple(_reference(r,bindings,variables,location+f'.sanitization_roots[{i}]') for i,r in enumerate(roots))
    if len(set(safe_roots))!=len(safe_roots): raise PackageError(location+'.sanitization_roots','范围重复')
    policies=ArchivePolicies(inbox,MappingProxyType(dict(policy['categories'])),policy['arrival_delay_seconds'],policy['expiry_delay_seconds'],tuple(filenames),safe_roots)
    return ArchiveProfile(root,MappingProxyType(validated),tuple(templates.values()),MappingProxyType(normalized),default,general,policies)


def resolve_archive_profile(package, bindings, *, state_dir: Path) -> ResolvedArchiveContext:
    profile=package.compatibility
    if not isinstance(profile,ArchiveProfile): raise ValueError('未配置兼容档案')
    state=checked_path(state_dir)
    def resolve(reference):
        if reference.binding not in bindings: raise ValueError(f'兼容档案未绑定 {reference.binding}')
        raw=bindings[reference.binding]
        root=checked_path(Path(absolute_folder(str(raw))))
        if root.exists() and not root.is_dir(): raise ValueError('兼容绑定必须是目录')
        path=checked_path(root.joinpath(*expand_variables(reference.relative,package.variables,'$.compatibility').split('/')))
        if not path.is_relative_to(root): raise ValueError('兼容路径逃出绑定目录')
        if paths_overlap(root,state) or paths_overlap(path,state): raise ValueError('兼容路径与应用状态重叠')
        if path.exists() and not path.is_dir(): raise ValueError('兼容路径必须是目录')
        return path
    root=resolve(profile.root)
    if root==Path(root.anchor): raise ValueError('兼容根目录不能是磁盘根')
    projects={code:resolve(reference) for code,reference in profile.projects.items()}
    if any(not path.is_relative_to(root) for path in projects.values()): raise ValueError('项目目录必须在显式根目录内')
    if len({path_key(p) for p in projects.values()})!=len(projects): raise ValueError('项目目录重复')
    library=TemplateLibrary({t.id:t for t in profile.templates},profile.assignments,profile.default_template,False)
    policy=profile.policies
    return ResolvedArchiveContext(package.id,root,MappingProxyType(projects),library,resolve(profile.general_test),resolve(policy.inbox_root),
        policy.categories,policy.arrival_delay_seconds,policy.expiry_delay_seconds,policy.disposable_filenames,tuple(resolve(r) for r in policy.sanitization_roots))
