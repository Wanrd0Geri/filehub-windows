"""Preview and locked execution coordination over the sole typed action journal."""
from dataclasses import dataclass, replace, asdict
from datetime import datetime
from pathlib import Path
import json
import os
import stat
from .models import Fingerprint, Operation, checked_path
from .operations import OperationEngine
from .rules import discover_projects, parse_tag, build_targets, VIDEO_EXT
from .media import probe_width

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

@dataclass(frozen=True)
class ServiceOutcome:
    source: Path
    targets: tuple[Path,...] = ()
    warnings: tuple[str,...] = ()
    error: str = ''
    duplicate: Path | None = None
    reallocated: bool = False

class FileHubService:
    def __init__(self,config,state_dir,*,platform=None,probe=None,source_time=None):
        config.validate(state_dir)
        self.config=config;self.engine=OperationEngine(state_dir,platform)
        self.probe=probe or (lambda p:probe_width(p,config.ffprobe_path))
        self.source_time=source_time
        with self.engine.locked(),self.engine.journal.connection() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS service_outcomes(batch_id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS notifications(key TEXT PRIMARY KEY);')

    def _route(self,tag):
        if self.config.sync_root is None:raise ValueError('请先选择同步根目录')
        projects=discover_projects(self.config.sync_root)
        return parse_tag(tag,projects,self.config.sync_root),projects

    @staticmethod
    def _occupied(dest):return [p.name for p in dest.iterdir()] if dest.is_dir() else []

    def _notify(self,path,fp,tag,error):
        identity=fp.to_dict() if fp else str(path)
        key=json.dumps([str(path),identity,tag,error],sort_keys=True,ensure_ascii=False)
        with self.engine.locked(),self.engine.journal.connection() as db:
            return db.execute('INSERT OR IGNORE INTO notifications(key) VALUES(?)',(key,)).rowcount==1

    def preview(self,paths,tag):
        items=[];reserved={}
        try:spec,_=self._route(tag);route_error=''
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
                if path.suffix.lower() in VIDEO_EXT and spec.mode not in {'keep','dated'}:width=self.probe(path)
                actual=spec.dest/when.strftime('%y%m%d') if spec.mode=='dated' else spec.dest
                occupied=reserved.setdefault(actual,self._occupied(actual))
                targets=build_targets(path,spec,when,width,occupied)
                occupied.extend(p.name for p in targets)
                items.append(PreviewItem(path,when,fp,tuple(targets),targets.warnings,video_width=width))
            except (OSError,ValueError) as exc:
                error=str(exc);items.append(PreviewItem(path,when,fp,error=error,notify=self._notify(path,fp,tag,error)))
        return PreviewBatch(tag,tuple(items))

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
            try:spec,projects=self._route(preview.tag);route_error=''
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
                    project=next((p for p in projects.values() if spec.dest.is_relative_to(p)),None)
                    duplicate=None
                    if project:
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
                        outcomes.append(ServiceOutcome(item.source,(duplicate,),item.warnings,duplicate=duplicate))
                        continue
                    actual=spec.dest/item.source_time.strftime('%y%m%d') if spec.mode=='dated' else spec.dest
                    occupied=self._occupied(actual)
                    targets=build_targets(item.source,spec,item.source_time,item.video_width,occupied)
                    if any(t==item.source for t in targets):raise ValueError('源与目标相同')
                    occupied.extend(t.name for t in targets)
                    if len(targets)==2:operations.append(Operation('copy',item.source,targets[1],current))
                    operations.append(Operation('move',item.source,targets[0],current))
                    result=self.engine.execute(operations,preview.tag,batch_id=batch_id)
                    outcomes.append(ServiceOutcome(item.source,tuple(targets),targets.warnings,reallocated=tuple(targets)!=item.targets))
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
    def undo(self,batch_id):return self._with_outcomes(self.engine.undo(batch_id))
