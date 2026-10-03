"""Preview and locked execution coordination over the sole typed action journal."""
from dataclasses import dataclass, replace, asdict
from datetime import datetime
from pathlib import Path
import json
import os
import stat
from .models import Fingerprint, Operation, checked_path
from .operations import OperationEngine
from .rules import build_targets, VIDEO_EXT
from .media import probe_width
from .trees import TreeFingerprint, prune_inbox_ancestors
from .templates import TemplateLibrary

@dataclass(frozen=True)
class PreviewItem:
    source: Path
    source_time: datetime | None = None
    fingerprint: Fingerprint | None = None
    targets: tuple[Path,...] = ()
    warnings: tuple[str,...] = ()
    error: str = ''
    notify: bool = False
    video_width: int | None = None

@dataclass(frozen=True)
class PreviewBatch:
    tag: str
    items: tuple[PreviewItem,...]
    template_revision: str = ''
    catalog_revision: str = ''

@dataclass(frozen=True)
class ServiceOutcome:
    source: Path
    targets: tuple[Path,...] = ()
    warnings: tuple[str,...] = ()
    error: str = ''
    duplicate: Path | None = None
    reallocated: bool = False


class CatalogRuleReader:
    """Read-only compatibility surface for existing runner/scheduler callers."""
    def __init__(self,catalog): self.catalog=catalog
    def load(self): return self.catalog.runtime_snapshot()

class FileHubService:
    def __init__(self,config,state_dir,*,platform=None,probe=None,source_time=None):
        config.validate(state_dir)
        self.config=config;self.engine=OperationEngine(state_dir,platform)
        from .rulefiles.catalog import RuleCatalogStore
        self.catalog=RuleCatalogStore(self.engine.state_dir)
        self.rules=CatalogRuleReader(self.catalog)
        self.migration_candidate=None; self.migration_error=''
        from .rulefiles.migration import inspect_legacy
        try: self.migration_candidate=inspect_legacy(self.engine.state_dir,config)
        except (OSError,ValueError,TypeError) as exc: self.migration_error=str(exc)
        from threading import RLock
        from weakref import WeakValueDictionary
        self._runtime_lock=RLock();self._automation=None;self._conversions=None;self._closing=False
        self._archive_previews=WeakValueDictionary()
        self.probe=probe or (lambda p:probe_width(p,self.config.ffprobe_path))
        self.source_time=source_time
        with self.engine.locked(),self.engine.journal.connection() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS service_outcomes(batch_id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS notifications(key TEXT PRIMARY KEY);')

    def reload_templates(self):
        """Load current immutable definitions; call from the shared worker."""
        snapshot=self.catalog.load()
        if snapshot.compatibility_selection is None or not snapshot.compatibility_permissions:
            return TemplateLibrary({}, {}, None, False)
        return self.archive_context(permission=None,snapshot=snapshot).templates

    def archive_context(self, *, permission='manual_archive', rule_id=None, snapshot=None):
        from .rulefiles.compatibility import resolve_archive_profile
        snapshot=snapshot or self.catalog.load()
        selected=snapshot.compatibility_selection
        if selected is None or (permission is not None and permission not in snapshot.compatibility_permissions):
            raise ValueError('个人归档需要显式选择兼容档案并授予权限')
        if rule_id is not None and rule_id not in snapshot.runtime_ids[selected].values():
            raise ValueError('项目规则与所选兼容档案不属于同一个规则文件')
        context=resolve_archive_profile(snapshot.packages[selected],snapshot.bindings[selected],state_dir=self.engine.state_dir)
        from .automation.planner import paths_overlap
        policies=snapshot.compatibility_permissions
        if policies & {'unmatched_inbox','cleanup'} and any(paths_overlap(context.inbox_root,watch) for watch in self.config.watch_roots):
            raise ValueError('兼容收件箱不能与观察目录重叠')
        if 'cleanup' in policies and any(paths_overlap(root,watch) for root in context.sanitization_roots for watch in self.config.watch_roots):
            raise ValueError('兼容清理范围不能与观察目录重叠')
        if 'cleanup' in policies and any(paths_overlap(context.inbox_root,project) for project in context.projects.values()):
            raise ValueError('兼容收件箱过期范围不能与项目目录重叠')
        return context

    @property
    def automation(self):
        with self._runtime_lock:
            if self._automation is None:
                from .automation.runner import AutomationRunner
                self._automation=AutomationRunner(self)
            return self._automation

    @property
    def conversions(self):
        with self._runtime_lock:
            if self._closing:raise ValueError('当前服务已关闭；不能启动旧图片任务')
            if self._conversions is None:
                from .automation.executor import ConversionExecutor
                self._conversions=ConversionExecutor(self)
            return self._conversions

    def close_conversions(self,callback=None):
        """UI must rebind/release service only from the settled callback."""
        with self._runtime_lock:
            self._closing=True
            if self._conversions is not None:return self._conversions.close(callback)
        from threading import Event
        settled=Event();settled.set()
        if callback:callback()
        return settled

    def _route(self,tag,templates=None):
        if self._closing:raise ValueError('当前服务已关闭；请重新预览')
        context=self.archive_context()
        return context.route(tag),context.projects

    @staticmethod
    def _occupied(dest):return [p.name for p in dest.iterdir()] if dest.is_dir() else []

    def _notify(self,path,fp,tag,error):
        identity=fp.to_dict() if fp else str(path)
        key=json.dumps([str(path),identity,tag,error],sort_keys=True,ensure_ascii=False)
        with self.engine.locked(),self.engine.journal.connection() as db:
            return db.execute('INSERT OR IGNORE INTO notifications(key) VALUES(?)',(key,)).rowcount==1

    def preview(self,paths,tag):
        items=[];reserved={}
        revision='';catalog_revision=''
        try:
            catalog_revision=self.catalog.load().revision
            library=self.reload_templates();revision=library.revision
            spec,_=self._route(tag,library);route_error=''
        except (OSError,ValueError) as exc:spec=None;route_error=str(exc)
        for path in paths:
            path=Path(os.path.abspath(path));fp=None;when=None;width=None
            try:
                checked_path(path)
                if self.engine.overlaps(path,self.engine.state_dir):raise ValueError('不能操作应用状态目录')
                fp=Fingerprint.capture(path)
                when=self.source_time(path) if self.source_time else datetime.fromtimestamp(fp.creation_ns/1_000_000_000).astimezone()
                if when.tzinfo is None:raise ValueError('源时间必须包含时区')
                if route_error:raise ValueError(route_error)
                if not isinstance(fp,TreeFingerprint) and path.suffix.lower() in VIDEO_EXT and spec.mode not in {'keep','dated'}:width=self.probe(path)
                actual=spec.dest/when.strftime('%y%m%d') if spec.mode=='dated' and not isinstance(fp,TreeFingerprint) else spec.dest
                occupied=reserved.setdefault(actual,self._occupied(actual))
                targets=build_targets(path,spec,when,width,occupied)
                occupied.extend(p.name for p in targets)
                items.append(PreviewItem(path,when,fp,tuple(targets),targets.warnings,video_width=width))
            except (OSError,ValueError) as exc:
                error=str(exc);items.append(PreviewItem(path,when,fp,error=error,notify=self._notify(path,fp,tag,error)))
        batch=PreviewBatch(tag,tuple(items),revision,catalog_revision)
        self._archive_previews[id(batch)]=batch
        return batch

    @staticmethod
    def _candidates(project,source,fp,excluded=()):
        for folder,dirs,files in os.walk(project,followlinks=False):
            def visible(path):
                try:
                    info=path.lstat()
                    return not path.name.startswith('.') and not getattr(info,'st_file_attributes',0)&(0x2|0x400) and not stat.S_ISLNK(info.st_mode)
                except OSError:return False
            dirs[:]=[d for d in dirs if visible(Path(folder)/d)]
            for name in files:
                path=Path(folder)/name
                try:
                    if not visible(path):continue
                    info=path.stat()
                    if (info.st_dev,info.st_ino) in {*excluded,(fp.device,fp.file_id)} or info.st_size!=fp.size:continue
                    yield path
                except OSError:continue

    def execute(self,preview):
        outcomes=[]
        with self.engine.locked():
            result=self.engine.execute([],preview.tag)
            batch_id=result.batch_id
            excluded={(i.fingerprint.device,i.fingerprint.file_id) for i in preview.items if i.fingerprint}
            try:
                if self._archive_previews.get(id(preview)) is not preview:
                    raise ValueError('归档预览不属于当前服务，请重新预览')
                library=self.reload_templates()
                if not preview.catalog_revision or preview.catalog_revision!=self.catalog.load().revision:
                    raise ValueError('归档权限或规则文件在预览后已变化，请重新预览')
                if not preview.template_revision or preview.template_revision != library.revision:
                    raise ValueError('模板在预览后已变化，请重新预览')
                context=self.archive_context()
                spec,projects=self._route(preview.tag,library);route_error=''
            except (OSError,ValueError) as exc:spec=None;projects={};route_error=str(exc)
            seen=set()
            for item in preview.items:
                operations=[]
                try:
                    if item.error:raise ValueError(item.error)
                    if route_error:raise ValueError(route_error)
                    if item.fingerprint is None or item.source_time is None:raise ValueError('缺少预览源指纹或时间')
                    current=Fingerprint.capture(item.source)
                    if current!=item.fingerprint:raise ValueError('源在预览后已变化，请重新预览')
                    identity=(current.device,current.file_id)
                    if identity in seen:raise ValueError('重复选择同一个源文件')
                    seen.add(identity)
                    if self.engine.overlaps(item.source,self.engine.state_dir):raise ValueError('不能操作应用状态目录')
                    if not item.targets:raise ValueError('缺少已批准的精确目标')
                    if any(t.exists() or (t.parent.is_dir() and any(p.name.casefold()==t.name.casefold() for p in t.parent.iterdir())) for t in item.targets):
                        raise ValueError('预览目标已被占用，请重新预览')
                    ancestors=context.inbox_ancestors(item.source)
                    project=next((p for p in projects.values() if spec.dest.is_relative_to(p)),None)
                    duplicate=None
                    if project and not isinstance(current,TreeFingerprint):
                        for candidate in self._candidates(project,item.source,current,excluded):
                            guard=None
                            try:
                                guard=self.engine.platform.guard(candidate)
                                guard.__enter__()
                                if guard.fingerprint().same_primary_content(current):
                                    duplicate=candidate;break
                                guard.__exit__(None,None,None)
                            except (OSError,ValueError):
                                if guard is not None:guard.__exit__(None,None,None)
                                continue
                    if duplicate:
                        operations.append(Operation('recycle',item.source,None,current))
                        try:result=self.engine.execute(operations,preview.tag,batch_id=batch_id)
                        finally:guard.__exit__(None,None,None)
                        if all(i.ok for i in result.items if i.source==item.source):prune_inbox_ancestors(ancestors,self.engine.platform)
                        outcomes.append(ServiceOutcome(item.source,(duplicate,),item.warnings,duplicate=duplicate))
                        continue
                    targets=item.targets
                    if not targets: raise ValueError('缺少已批准的精确目标')
                    if any(t.exists() or (t.parent.is_dir() and any(p.name.casefold()==t.name.casefold() for p in t.parent.iterdir())) for t in targets):
                        raise ValueError('预览目标已被占用，请重新预览')
                    # Validate frozen paths against current route without allocating.
                    expected=build_targets(item.source,spec,item.source_time,item.video_width,())
                    if len(expected)!=len(targets) or any(t.parent!=p.parent for t,p in zip(targets,expected)):
                        raise ValueError('预览目标与当前归档目的地不一致')
                    if any(t==item.source for t in targets):raise ValueError('源与目标相同')
                    if len(targets)==2:operations.append(Operation('copy',item.source,targets[1],current))
                    operations.append(Operation('move',item.source,targets[0],current))
                    result=self.engine.execute(operations,preview.tag,batch_id=batch_id)
                    if all(i.ok for i in result.items if i.source==item.source):prune_inbox_ancestors(ancestors,self.engine.platform)
                    outcomes.append(ServiceOutcome(item.source,tuple(targets),item.warnings))
                except (OSError,ValueError) as exc:outcomes.append(ServiceOutcome(item.source,error=str(exc),warnings=item.warnings))
            outcomes=[replace(o,error='；'.join(i.message for i in result.items if i.source==o.source and not i.ok))
                      if not o.error else o for o in outcomes]
            data=[{**asdict(o),'source':str(o.source),'targets':[str(t) for t in o.targets],'duplicate':str(o.duplicate) if o.duplicate else None} for o in outcomes]
            with self.engine.journal.connection() as db:
                db.execute('INSERT INTO service_outcomes VALUES(?,?)',(result.batch_id,json.dumps(data,ensure_ascii=False)))
            return replace(result,outcomes=tuple(outcomes))

    def _with_outcomes(self,result):
        with self.engine.journal.connection() as db:row=db.execute('SELECT data FROM service_outcomes WHERE batch_id=?',(result.batch_id,)).fetchone()
        if not row:return result
        outcomes=[]
        for d in json.loads(row[0]):
            d['source']=Path(d['source']);d['targets']=tuple(Path(p) for p in d['targets']);d['warnings']=tuple(d['warnings'])
            d['duplicate']=Path(d['duplicate']) if d['duplicate'] else None
            outcomes.append(ServiceOutcome(**d))
        return replace(result,outcomes=tuple(outcomes))
    def history(self):return [self._with_outcomes(r) for r in self.engine.history()]
    def undo(self,batch_id):
        result=self._with_outcomes(self.engine.undo(batch_id))
        if self._automation is not None:self._automation.ledger.reconcile()
        return result
