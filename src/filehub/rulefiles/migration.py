"""Inspect legacy definitions without mutation; acceptance is a separate transaction."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType

from ..automation.models import RuleSet
from ..config import ConfigStore
from ..models import checked_path
from ..rules import discover_projects
from ..templates import TemplateLibrary
from ..automation.planner import paths_overlap
from .protocol import MAX_PACKAGE_BYTES, ORDINARY_TOKENS, _unique, parse_package
from ..naming import validate_pattern

LEGACY_FILES=('config.json','automation-rules.json','templates.json')


@dataclass(frozen=True)
class MigrationCandidate:
    source_digests: object
    packages: tuple
    bindings: object
    runtime_ids: object
    compatibility: str | None
    warnings: tuple[str, ...] = ()
    config: object = None


def read_legacy_sources(state_dir):
    result={}
    for name in LEGACY_FILES:
        path=checked_path(Path(state_dir)/name)
        if not path.exists(): result[name]=None; continue
        with path.open('rb') as stream: raw=stream.read(MAX_PACKAGE_BYTES+1)
        if len(raw)>MAX_PACKAGE_BYTES: raise ValueError(f'{name}: legacy file exceeds size limit')
        result[name]=raw
    return result


def _decode(raw,name):
    try:
        return json.loads(raw.decode('utf-8'),object_pairs_hook=_unique,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (ValueError,UnicodeError,RecursionError) as exc: raise ValueError(f'{name}: invalid legacy document') from exc


def legacy_package(rules,config,library,projects):
    """Pure translation used by migration and explicit owned regression fixtures."""
    values={}; declarations={}; by_path={}
    def reference(path,label='Folder'):
        key=str(Path(path)).casefold()
        identifier=by_path.get(key)
        if identifier is None:
            identifier=f'folder_{len(values)+1}'
            values[identifier]=Path(path); declarations[identifier]={'label':label}; by_path[key]=identifier
        return {'binding':identifier,'relative':''}
    definitions=[]
    for rule in rules.rules:
        actions=[]
        for action in rule.actions:
            options=dict(action.options)
            if action.kind=='rename':
                try:validate_pattern(options['pattern'],ORDINARY_TOKENS)
                except ValueError as exc:
                    raise ValueError(f'automation-rules.json: rule {rule.id}, rename.pattern {options["pattern"]!r}: '
                        'use only original/stem/ext/date/date_long/period/sequence in an externally edited rule file') from exc
            if 'destination' in options: options['destination']=reference(options['destination'],'Destination')
            actions.append({'kind':action.kind,'options':options})
        definitions.append({'id':rule.id,'name':rule.name,'scope':[reference(p,'Scope') for p in rule.scope],
                            'condition':rule.condition.to_document(),'actions':actions})
    document={'format':'filehub.rules','version':1,'id':'legacy-import','name':'Migrated definitions',
              'bindings':declarations,'variables':{},'rules':definitions}
    if config.sync_root is not None:
        root=reference(config.sync_root,'Archive root')
        inbox=reference(config.sync_root/'0_收件箱','Legacy inbox')
        general=reference(config.sync_root/'2_资料库'/'技术测试','General test')
        project_refs={code:reference(path,'Project '+code) for code,path in projects.items()}
        assignments=dict(library.assignments)
        disposable={'.baiduyun.uploading.cfg'}
        for watch in config.watch_roots:
            if checked_path(watch).is_dir():
                disposable.update(p.name for p in watch.iterdir() if p.name.endswith('.baiduyun.uploading.cfg') and not p.is_dir())
        document['compatibility']={'format':'filehub.archive.v1','root':root,'projects':project_refs,
            'templates':[t.to_document() for t in library.templates.values()], 'assignments':assignments,'default_template':'default',
            'general_test':general,'policies':{'inbox_root':inbox,'categories':{'image':'图片','video':'视频','other':'其他'},
                'arrival_delay_seconds':config.sweep_days*86400,'expiry_delay_seconds':config.inbox_days*86400,
                'disposable_filenames':sorted(disposable),'sanitization_roots':[root]}}
    package=parse_package(json.dumps(document,ensure_ascii=False).encode('utf-8'))
    return package,MappingProxyType(values),MappingProxyType({rule.id:rule.id for rule in rules.rules})


def inspect_legacy(state_dir,config) -> MigrationCandidate | None:
    state=checked_path(state_dir)
    if checked_path(state/'rule-catalog.json').exists(): return None
    backups=checked_path(state/'rule-catalog-backups')
    if backups.exists() and any(backups.iterdir()): raise ValueError('Active catalogue missing; explicit recovery required before migration')
    sources=read_legacy_sources(state)
    actual_config=config
    if sources['config.json'] is not None:
        _decode(sources['config.json'],'config.json')
        try: actual_config=ConfigStore(state).load()
        except (ValueError,TypeError,OSError) as exc: raise ValueError(f'config.json: {exc}') from exc
    actual_config.validate(state)
    try: rules=RuleSet() if sources['automation-rules.json'] is None else RuleSet.from_document(_decode(sources['automation-rules.json'],'automation-rules.json'))
    except (ValueError,TypeError) as exc: raise ValueError(f'automation-rules.json: {exc}') from exc
    try: library=TemplateLibrary() if sources['templates.json'] is None else TemplateLibrary.from_document(_decode(sources['templates.json'],'templates.json'))
    except (ValueError,TypeError) as exc: raise ValueError(f'templates.json: {exc}') from exc
    if not rules.rules and actual_config.sync_root is None and sources['templates.json'] is None: return None
    projects={}
    if actual_config.sync_root is not None:
        try:
            root=checked_path(actual_config.sync_root)
            if root==Path(root.anchor) or paths_overlap(root,state) or any(paths_overlap(root,p) for p in actual_config.watch_roots):
                raise ValueError('旧同步根目录与状态/观察目录重叠或是磁盘根')
            projects=discover_projects(root)
        except (ValueError,OSError) as exc: raise ValueError(f'config.json: legacy sync_root: {exc}') from exc
    if actual_config.sync_root is None and sources['templates.json'] is not None:
        raise ValueError('templates.json: legacy templates require an explicitly configured sync_root')
    try:package,bindings,ids=legacy_package(rules,actual_config,library,projects)
    except ValueError as exc:raise ValueError(f'legacy definitions: {exc}') from exc
    digests={name:sha256(raw).hexdigest() if raw is not None else None for name,raw in sources.items()}
    return MigrationCandidate(MappingProxyType(digests),(package,),MappingProxyType({package.id:bindings}),
        MappingProxyType({package.id:ids}),package.id if package.compatibility else None,
        ('Migration requires explicit acceptance; all rules and compatibility permissions remain disabled.',),actual_config)
