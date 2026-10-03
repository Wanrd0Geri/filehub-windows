"""Atomic local definition authority; never writes watches, jobs or history."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
import json
import os
import re
import tempfile
import uuid
from datetime import datetime

from ..models import checked_path
from ..platform.windows import process_lock
from .protocol import parse_package, encode_package
from .compiler import compile_package, runtime_id

MAX_BYTES = 16_000_000
PERMISSIONS = frozenset({'manual_archive', 'unmatched_inbox', 'cleanup'})

def _json(data):
    result=json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(result)>MAX_BYTES: raise ValueError('Catalogue exceeds size limit')
    return result

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate catalogue key')
        result[key]=value
    return result

def _keys(value, expected):
    if type(value) is not dict or set(value)!=set(expected): raise ValueError('Invalid catalogue fields')

@dataclass(frozen=True)
class CompiledRules:
    rules: tuple
    revision: str

@dataclass(frozen=True)
class CatalogSnapshot:
    revision: str
    packages: object
    compiled: CompiledRules
    bindings: object
    enabled: object
    order: tuple
    compatibility_selection: str | None
    compatibility_permissions: frozenset
    runtime_ids: object
    sources: object
    generation: str
    diagnostics: tuple = ()

@dataclass(frozen=True)
class PackageDelta:
    added: tuple
    changed: tuple
    removed: tuple
    binding_changes: tuple
    metadata_changed: bool = False
    variables_changed: bool = False
    compatibility_changed: bool = False
    order_changed: bool = False

@dataclass(frozen=True)
class BackupInfo:
    id: str
    revision: str
    created: str = ''
    package_names: tuple = ()
    summary: str = ''

def compare_packages(old,new):
    if old.id!=new.id: raise ValueError('Package IDs must match')
    a={r.id:r.to_document() for r in old.rules}; b={r.id:r.to_document() for r in new.rules}
    variables_changed=old.variables!=new.variables
    profile_changed=old.to_document().get('compatibility')!=new.to_document().get('compatibility')
    return PackageDelta(tuple(k for k in b if k not in a),tuple(k for k in b if k in a and (a[k]!=b[k] or variables_changed or profile_changed)),
        tuple(k for k in a if k not in b),tuple(sorted(k for k in set(old.bindings)|set(new.bindings) if old.bindings.get(k)!=new.bindings.get(k))),
        old.name!=new.name,variables_changed,profile_changed,tuple(a)!=tuple(b))

class RuleCatalogStore:
    def __init__(self,state_dir):
        self.state_dir=Path(os.path.abspath(state_dir)); self.path=self.state_dir/'rule-catalog.json'
        self.backup_dir=self.state_dir/'rule-catalog-backups'; self._lock=process_lock(self.state_dir)

    def _empty(self):
        return dict(format='filehub.catalog',version=1,generation='initial',packages=[],compatibility_selection=None,compatibility_permissions=[])

    def _snapshot(self,doc):
        _keys(doc, self._empty())
        if doc['format']!='filehub.catalog' or type(doc['version']) is not int or doc['version']!=1: raise ValueError('Invalid catalogue version')
        if not isinstance(doc['generation'],str) or not re.fullmatch(r'initial|[0-9a-f]{32}',doc['generation']): raise ValueError('Invalid generation')
        entries=doc['packages']
        if type(entries) is not list or len(entries)>100: raise ValueError('Invalid packages')
        packages={}; bindings={}; enabled={}; ids={}; sources={}; rules=[]; diagnostics=[]; all_ids=set()
        for entry in entries:
            _keys(entry,{'package','source','bindings','enabled','runtime_ids'})
            package=parse_package(_json(entry['package'])); key=package.id
            if key in packages: raise ValueError('Duplicate package')
            if entry['source'] is not None and (type(entry['source']) is not str or len(entry['source'])>32768): raise ValueError('Invalid provenance')
            rule_keys={r.id for r in package.rules}
            if type(entry['bindings']) is not dict or not set(entry['bindings'])<=set(package.bindings): raise ValueError('Invalid bindings')
            values={}
            for binding,value in entry['bindings'].items():
                if type(value) is not str or not Path(value).is_absolute(): raise ValueError('Invalid binding path')
                root=checked_path(Path(value))
                if root.exists() and not root.is_dir(): raise ValueError('Binding is not a folder')
                state=str(self.state_dir).casefold().rstrip('\\/'); resolved=str(root).casefold().rstrip('\\/')
                if state==resolved or state.startswith(resolved+os.sep) or resolved.startswith(state+os.sep): raise ValueError('Binding overlaps state')
                values[binding]=root
            if type(entry['enabled']) is not list or any(type(r) is not str for r in entry['enabled']) or len(set(entry['enabled']))!=len(entry['enabled']) or not set(entry['enabled'])<=rule_keys: raise ValueError('Invalid enable states')
            if type(entry['runtime_ids']) is not dict or set(entry['runtime_ids'])!=rule_keys: raise ValueError('Invalid runtime mappings')
            for value in entry['runtime_ids'].values():
                if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value) or value in all_ids: raise ValueError('Invalid runtime ID')
                all_ids.add(value)
            compilation=compile_package(package,values,entry['runtime_ids'],frozenset(entry['enabled']),state_dir=self.state_dir)
            available={r.id for r in compilation.rules}
            if any(entry['runtime_ids'][r] not in available for r in entry['enabled']): raise ValueError('Enabled rule unavailable')
            packages[key]=package; bindings[key]=MappingProxyType(values); enabled[key]=frozenset(entry['enabled'])
            ids[key]=MappingProxyType(dict(entry['runtime_ids'])); sources[key]=entry['source']
            rules.extend(compilation.rules); diagnostics.extend(compilation.diagnostics)
        if len(all_ids)>1000: raise ValueError('Too many installed rules')
        selection=doc['compatibility_selection']; permissions=doc['compatibility_permissions']
        if selection is not None and (type(selection) is not str or selection not in packages or packages[selection].compatibility is None): raise ValueError('Invalid compatibility selection')
        if type(permissions) is not list or any(type(p) is not str for p in permissions) or len(set(permissions))!=len(permissions) or not set(permissions)<=PERMISSIONS or (permissions and selection is None): raise ValueError('Invalid compatibility permissions')
        for key,package in packages.items():
            for rule in package.rules:
                if rule.id in enabled[key] and any(a['kind']=='project_route' for a in rule.actions):
                    if selection!=key or 'manual_archive' not in permissions: raise ValueError('Enabled project route lacks owning profile permission')
        if selection is not None and permissions:
            from .compatibility import resolve_archive_profile
            resolve_archive_profile(packages[selection],bindings[selection],state_dir=self.state_dir)
        revision=sha256(_json(doc)).hexdigest()
        return CatalogSnapshot(revision,MappingProxyType(packages),CompiledRules(tuple(rules),revision),MappingProxyType(bindings),MappingProxyType(enabled),tuple(packages),selection,frozenset(permissions),MappingProxyType(ids),MappingProxyType(sources),doc['generation'],tuple(diagnostics))

    def _read(self,path):
        checked_path(path)
        with path.open('rb') as stream: raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError('Catalogue exceeds size limit')
        try: doc=json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (UnicodeError,json.JSONDecodeError,RecursionError) as exc: raise ValueError('Corrupt catalogue; restore required') from exc
        try: self._snapshot(doc)
        except (TypeError,RecursionError,OverflowError) as exc: raise ValueError('Invalid catalogue types') from exc
        return doc,raw

    def _load_doc(self):
        checked_path(self.path); checked_path(self.backup_dir)
        if self.path.exists(): return self._read(self.path)[0]
        if self.backup_dir.exists() and any(self.backup_dir.iterdir()): raise ValueError('Active catalogue missing; explicit restore required')
        return self._empty()

    def load(self):
        if not self.state_dir.exists(): return self._snapshot(self._empty())
        with self._lock.acquire(): return self._snapshot(self._load_doc())

    def runtime_snapshot(self): return self.load().compiled

    def _fault(self,stage): pass

    def _flush(self,path,data,exclusive=True):
        with checked_path(path).open('xb' if exclusive else 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())

    def _commit(self,doc,*,recovery=False):
        doc['generation']=uuid.uuid4().hex; snapshot=self._snapshot(doc); data=_json(doc)
        self._fault('before_backup')
        if self.path.exists():
            try: _,prior=self._read(self.path)
            except ValueError:
                if not recovery: raise
                prior=None
            if prior is not None:
                checked_path(self.backup_dir).mkdir(exist_ok=True)
                backup=self.backup_dir/(uuid.uuid4().hex+'.json')
                self._flush(backup,prior)
                _,verified=self._read(backup)
                if verified!=prior: raise ValueError('Backup verification failed')
        self._fault('after_backup')
        fd,name=tempfile.mkstemp(prefix='.rule-catalog-',suffix='.tmp',dir=checked_path(self.state_dir)); os.close(fd)
        try:
            self._flush(Path(name),data,False); self._fault('after_temp_write')
            if self._read(Path(name))[1]!=data: raise ValueError('Temporary verification failed')
            self._fault('before_swap'); checked_path(self.path); os.replace(name,self.path); self._fault('after_swap')
        finally:
            if os.path.exists(name): os.unlink(name)
        return snapshot

    def _mutate(self,expected_revision,change):
        if type(expected_revision) is not str: raise ValueError('Expected revision required')
        checked_path(self.state_dir).mkdir(parents=True,exist_ok=True)
        with self._lock.acquire():
            doc=self._load_doc()
            if self._snapshot(doc).revision!=expected_revision: raise ValueError('Catalogue changed; reload required')
            change(doc)
            return self._commit(doc)

    def _entry(self,doc,key):
        for entry in doc['packages']:
            if entry['package']['id']==key: return entry
        raise ValueError('Package not installed')

    def import_package(self,data,source=None,*,expected_revision):
        package=parse_package(data)
        def change(doc):
            if any(e['package']['id']==package.id for e in doc['packages']): raise ValueError('Package installed; use replace')
            doc['packages'].append(dict(package=package.to_document(),source=source,bindings={},enabled=[],runtime_ids={r.id:runtime_id(package.id,r.id) for r in package.rules}))
        return self._mutate(expected_revision,change)

    def replace_package(self,package_id,data,source=None,*,expected_revision):
        package=parse_package(data)
        if package.id!=package_id: raise ValueError('Package IDs must match')
        def change(doc):
            entry=self._entry(doc,package_id); entry.update(package=package.to_document(),source=source,enabled=[],
                bindings={k:v for k,v in entry['bindings'].items() if k in package.bindings},
                runtime_ids={r.id:entry['runtime_ids'].get(r.id,runtime_id(package_id,r.id)) for r in package.rules})
            if doc['compatibility_selection']==package_id:
                doc['compatibility_permissions']=[]
                if package.compatibility is None: doc['compatibility_selection']=None
        return self._mutate(expected_revision,change)

    def bind(self,package_id,values,*,expected_revision):
        return self._mutate(expected_revision,lambda doc:self._entry(doc,package_id).update(bindings={k:str(v) for k,v in values.items()}))

    def set_enabled(self,package_id,rule_id,enabled,*,expected_revision):
        if type(enabled) is not bool: raise ValueError('Enabled must be boolean')
        def change(doc):
            entry=self._entry(doc,package_id)
            if rule_id not in entry['runtime_ids']: raise ValueError('Unknown rule')
            definition=next(r for r in entry['package']['rules'] if r['id']==rule_id)
            if enabled and any(a['kind']=='project_route' for a in definition['actions']):
                if doc['compatibility_selection']!=package_id or 'manual_archive' not in doc['compatibility_permissions']:
                    raise ValueError('Project routing requires its selected permitted profile')
            values=set(entry['enabled']); values.add(rule_id) if enabled else values.discard(rule_id); entry['enabled']=sorted(values)
        return self._mutate(expected_revision,change)

    def reorder(self,package_ids,*,expected_revision):
        def change(doc):
            by_id={e['package']['id']:e for e in doc['packages']}
            if len(package_ids)!=len(by_id) or set(package_ids)!=set(by_id): raise ValueError('Order must contain every package once')
            doc['packages']=[by_id[k] for k in package_ids]
        return self._mutate(expected_revision,change)

    def remove(self,package_id,*,expected_revision):
        def change(doc):
            entry=self._entry(doc,package_id); doc['packages'].remove(entry)
            if doc['compatibility_selection']==package_id: doc.update(compatibility_selection=None,compatibility_permissions=[])
        return self._mutate(expected_revision,change)

    def set_compatibility(self,package_id,permissions,*,expected_revision):
        if not isinstance(permissions,frozenset) or not permissions<=PERMISSIONS: raise ValueError('Invalid compatibility permissions')
        def change(doc):
            doc.update(compatibility_selection=package_id,compatibility_permissions=sorted(permissions))
            for entry in doc['packages']:
                if entry['package']['id']!=package_id or 'manual_archive' not in permissions:
                    routes={r['id'] for r in entry['package']['rules'] if any(a['kind']=='project_route' for a in r['actions'])}
                    entry['enabled']=[r for r in entry['enabled'] if r not in routes]
        return self._mutate(expected_revision,change)

    def export_package(self,package_id): return encode_package(self.load().packages[package_id])

    def _backup_path(self,backup_id):
        if type(backup_id) is not str or not re.fullmatch('[0-9a-f]{32}',backup_id): raise ValueError('Invalid backup ID')
        return checked_path(self.backup_dir/(backup_id+'.json'))

    def list_backups(self):
        checked_path(self.backup_dir)
        if not self.backup_dir.exists(): return ()
        result=[]
        for path in sorted(self.backup_dir.glob('*.json')):
            if not re.fullmatch('[0-9a-f]{32}',path.stem): continue
            try:
                doc,_=self._read(path);snapshot=self._snapshot(doc)
                created=datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                names=tuple(p.name for p in snapshot.packages.values())
                summary='\n'.join(p.name+' · '+str(len(p.rules))+' 条规则\n'+ '\n'.join(r.name for r in p.rules) for p in snapshot.packages.values())
                result.append(BackupInfo(path.stem,snapshot.revision,created,names,summary))
            except (ValueError,OSError): continue
        return tuple(result)

    def restore(self,backup_id,*,expected_revision):
        path=self._backup_path(backup_id)
        checked_path(self.state_dir).mkdir(parents=True,exist_ok=True)
        with self._lock.acquire():
            # Recovery CAS is the digest of corrupt active bytes, or 'missing'.
            current=self._recovery_revision()
            if expected_revision!=current: raise ValueError('Catalogue changed; reload required')
            doc,_=self._read(path)
            for entry in doc['packages']: entry['enabled']=[]
            doc['compatibility_permissions']=[]
            return self._commit(doc,recovery=True)

    def _recovery_revision(self):
        try: return self._snapshot(self._load_doc()).revision
        except ValueError:
            if not self.path.exists(): return 'missing'
            digest=sha256()
            with checked_path(self.path).open('rb') as stream:
                for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
            return digest.hexdigest()

    def recovery_revision(self):
        """CAS token for explicit recovery, including missing/corrupt authority."""
        if not self.state_dir.exists(): return self._snapshot(self._empty()).revision
        with self._lock.acquire(): return self._recovery_revision()

    def adopt_legacy(self,candidate,*,expected_revision):
        """Explicit first adoption; raw originals are never catalogue backups."""
        from .migration import MigrationCandidate, LEGACY_FILES, inspect_legacy, read_legacy_sources
        from ..config import Config
        if not isinstance(candidate,MigrationCandidate): raise ValueError('Validated migration candidate required')
        if not isinstance(candidate.config,Config): raise ValueError('Validated migration configuration required')
        checked_path(self.state_dir).mkdir(parents=True,exist_ok=True)
        with self._lock.acquire():
            doc=self._load_doc()
            if self._snapshot(doc).revision!=expected_revision: raise ValueError('Catalogue changed; reload required')
            if self.path.exists() or doc['packages']: raise ValueError('Migration already adopted')
            raw=read_legacy_sources(self.state_dir)
            digests={name:sha256(value).hexdigest() if value is not None else None for name,value in raw.items()}
            if dict(candidate.source_digests)!=digests: raise ValueError('Legacy sources changed; inspect again')
            current=inspect_legacy(self.state_dir,candidate.config)
            if current is None or [encode_package(p) for p in current.packages]!=[encode_package(p) for p in candidate.packages] or current.bindings!=candidate.bindings or current.runtime_ids!=candidate.runtime_ids:
                raise ValueError('Legacy candidate changed; inspect again')
            doc['packages']=[dict(package=p.to_document(),source=None,
                bindings={k:str(v) for k,v in current.bindings[p.id].items()},enabled=[],runtime_ids=dict(current.runtime_ids[p.id])) for p in current.packages]
            self._snapshot(doc)  # Full validation before raw backup or publication.
            backup_root=checked_path(self.state_dir/'legacy-migration-backups'); backup_root.mkdir(exist_ok=True)
            backup=checked_path(backup_root/uuid.uuid4().hex); backup.mkdir()
            for name in LEGACY_FILES:
                if raw[name] is None: continue
                self._flush(backup/name,raw[name])
                if checked_path(backup/name).read_bytes()!=raw[name]: raise ValueError('Legacy raw backup verification failed')
            manifest=_json({'format':'filehub.legacy-backup','version':1,'source_digests':digests})
            self._flush(backup/'manifest.json',manifest)
            if (backup/'manifest.json').read_bytes()!=manifest: raise ValueError('Legacy manifest verification failed')
            self._fault('after_legacy_backup')
            return self._commit(doc)
