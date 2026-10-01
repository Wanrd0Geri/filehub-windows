"""One serial image worker. Cancellation and asynchronous settlement bypass it."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread
import hashlib
import json
import uuid

from ..models import Fingerprint, checked_path
from ..conversion.images import inspect
from ..conversion.models import ConversionCancelled
from ..conversion.naming import allocate_conversion_target
from ..generated import generate_owned, discard_owned
from .planner import path_key, paths_overlap, _existing_collision, PlannedStep, RulePlan
from .runner import RunOutcome, config_revision, AuthorityChanged


@dataclass(frozen=True)
class JobHandle:
    id: str
    cancel_event: Event
    future: object
    automatic: bool = False


@dataclass(frozen=True)
class ImagePreviewItem:
    source: Path
    target: Path | None = None
    conversion_plan: object | None = None
    error: str = ''


@dataclass(frozen=True)
class ImagePreview:
    items: tuple
    mode: str
    config_revision: str
    authority_config_revision: str


class ConversionExecutor:
    def __init__(self,service):
        self.service=service;self.runner=service.automation
        self._worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='filehub-images')
        self._lock=RLock();self._jobs={};self._accepting=True;self._settled=None;self._previews={}
        self._idle_callbacks=[]

    def submit(self,work,*,completion=None,progress=None,automatic=False):
        cancel=Event();key=uuid.uuid4().hex
        def report(value):
            if progress:
                if hasattr(value,'phase'):value={'phase':'committing' if value.phase=='complete' else value.phase,'percent':min(value.percent,99)}
                try:progress(value)
                except Exception:
                    import logging
                    logging.exception('图片进度回调失败；任务仍按事务结果完成')
        def run():
            if cancel.is_set():raise ConversionCancelled('已取消排队任务')
            return work(cancel,report)
        with self._lock:
            if not self._accepting:raise ValueError('图片工作线程正在结束；不能提交新任务')
            future=self._worker.submit(run);job=JobHandle(key,cancel,future,automatic);self._jobs[key]=job
        def finished(future):
            try:
                if completion:completion(future)
            finally:
                with self._lock:
                    self._jobs.pop(key,None)
                    callbacks=self._idle_callbacks[:] if not self._jobs else []
                    if callbacks:self._idle_callbacks.clear()
                for callback in callbacks:callback()
        future.add_done_callback(finished)
        return job

    def cancel(self,job_id=None):
        with self._lock:
            jobs=list(self._jobs.values()) if job_id is None else [self._jobs[job_id]] if job_id in self._jobs else []
            for job in jobs:job.cancel_event.set()

    def cancel_automatic(self):
        with self._lock:
            for job in self._jobs.values():
                if job.automatic:job.cancel_event.set()

    def when_idle(self,callback):
        with self._lock:
            if self._jobs:self._idle_callbacks.append(callback);return
        callback()

    def close(self,callback=None):
        """Return immediately; callback/Event fire AFTER every old mutation settles."""
        with self._lock:
            self._accepting=False;self.cancel()
            if self._settled is not None:
                settled=self._settled
                if callback:
                    def after():settled.wait();callback()
                    Thread(target=after,name='filehub-image-close-callback',daemon=True).start()
                return settled
            settled=self._settled=Event()
        def finish():
            self._worker.shutdown(wait=True,cancel_futures=False)
            settled.set()
            if callback:callback()
        Thread(target=finish,name='filehub-image-settle',daemon=True).start()
        return settled

    def state_change(self,callback=None):return self.close(callback)

    def submit_rule_preview(self,paths,rule_id=None,*,completion=None,progress=None):
        paths=tuple(paths)
        return self.submit(lambda cancel,report:self.runner.preview(paths,rule_id,inspect_images=True,cancel_event=cancel),completion=completion,progress=progress)

    def submit_rule(self,preview,*,completion=None,progress=None,automatic=False,claims=None):
        def work(cancel,report):
            try:validated=self.runner.validate_images(preview,automatic=automatic,cancel_event=cancel)
            except Exception as exc:
                if not isinstance(exc,(AuthorityChanged,ConversionCancelled)):
                    for run in (claims or {}).values():self.runner.ledger.update(run,'failed',str(exc))
                raise
            return self.runner.execute(validated,cancel_event=cancel,progress=report,automatic=automatic,claims=claims)
        def finished(future):
            if future.exception() is not None:
                for run in (claims or {}).values():
                    row=self.runner.ledger.get(run)
                    error=future.exception()
                    released=automatic and isinstance(error,(AuthorityChanged,ConversionCancelled)) and self.runner.ledger.release_unstarted(run,str(error))
                    if not released and row['status'] in ('queued','running'):self.runner.ledger.update(run,'failed',str(error))
            if completion:completion(future)
        return self.submit(work,completion=finished,progress=progress,automatic=automatic)

    def submit_image_preview(self,paths,spec,*,mode='keep',output_dir=None,completion=None,progress=None):
        paths=tuple(paths)
        return self.submit(lambda cancel,report:self.preview_images(paths,spec,mode=mode,output_dir=output_dir,cancel_event=cancel),completion=completion,progress=progress)

    def preview_images(self,paths,spec,*,mode='keep',output_dir=None,cancel_event=None):
        self._previews.clear()
        if mode not in ('keep','replace'):raise ValueError('转换模式必须是 keep 或 replace')
        if mode=='keep' and output_dir is None:raise ValueError('保留原件模式需要输出文件夹')
        if mode=='replace' and output_dir is not None:raise ValueError('替换模式不能另选输出文件夹')
        snapshot_config_revision=config_revision(self.service.config)
        authority_config_revision=config_revision(self.service.config,ignore_paused=True,ignore_theme=True)
        sources=tuple(checked_path(p) for p in paths);items=[];targets=[];e=self.service.engine
        for source in sources:
            target=None
            try:
                if cancel_event and cancel_event.is_set():raise ValueError('已取消预览')
                if sum(path_key(source)==path_key(p) for p in sources)>1:raise ValueError('重复选择或路径大小写别名')
                if paths_overlap(source,e.state_dir):raise ValueError('不能转换应用状态目录')
                target=checked_path((source.parent if mode=='replace' else Path(output_dir))/(source.stem+spec.extension))
                own=mode=='replace' and path_key(target)==path_key(source)
                reserved=(*targets, *(p for p in sources if not (own and path_key(p)==path_key(source))))
                target=allocate_conversion_target(target,reserved=reserved,own_source=source if own else None)
                if paths_overlap(target,e.state_dir):raise ValueError('目标与应用状态目录重叠')
                own=mode=='replace' and path_key(target)==path_key(source)
                if any(paths_overlap(target,p) and not (own and path_key(p)==path_key(source)) for p in sources):raise ValueError('目标与另一个选择的源重叠')
                if any(paths_overlap(target,p) for p in targets):raise ValueError('本批次目标重复或重叠')
                if _existing_collision(target) and not own:raise ValueError('目标在预览期间已被占用，请重新预览')
                validation=inspect(source,spec)
                if cancel_event and cancel_event.is_set():raise ValueError('已取消预览')
                targets.append(target)
                items.append(ImagePreviewItem(source,target,validation))
            except (OSError,ValueError) as exc:items.append(ImagePreviewItem(source,target,error=str(exc)))
        if cancel_event and cancel_event.is_set():raise ValueError('已取消预览')
        preview=ImagePreview(tuple(items),mode,snapshot_config_revision,authority_config_revision)
        self._previews[id(preview)]=preview
        return preview

    def submit_images(self,preview,*,completion=None,progress=None):
        return self.submit(lambda cancel,report:self.execute_images(preview,cancel,report),completion=completion,progress=progress)

    def execute_images(self,preview,cancel,progress):
        if self._previews.get(id(preview)) is not preview:raise ValueError('预览不属于当前图片工作线程；请重新预览')
        outcomes=[];e=self.service.engine;ledger=self.runner.ledger
        for index,item in enumerate(preview.items):
            if cancel.is_set():break
            if item.error:
                outcomes.append(RunOutcome(item.source,error=item.error));continue
            validation=item.conversion_plan;spec=validation.spec
            semantic=hashlib.sha256(json.dumps([asdict(spec),preview.mode,str(item.target)],sort_keys=True).encode()).hexdigest()
            step=PlannedStep('image_convert',item.source,item.target,validation.source_fingerprint,conversion_spec=spec,
                conversion_plan=validation,generates_content=True,replaces_original=preview.mode=='replace')
            plan=RulePlan(item.source,validation.source_fingerprint,'standalone-image',semantic,'standalone-image',
                self.service.reload_templates().revision,datetime.now(timezone.utc),(step,))
            def authority():
                if cancel.is_set():raise ValueError('已取消')
                if self.service._closing:raise ValueError('当前服务正在关闭')
                if config_revision(self.service.config,ignore_paused=True,ignore_theme=True)!=preview.authority_config_revision:raise ValueError('设置已变化，请重新预览')
                self.service.config.validate(e.state_dir)
                if Fingerprint.capture(item.source)!=validation.source_fingerprint:raise ValueError('源在预览后变化，请重新预览')
                checked_path(item.target)
                own=preview.mode=='replace' and path_key(item.source)==path_key(item.target)
                if _existing_collision(item.target) and not own:raise ValueError('目标已被占用，请重新预览')
            try:
                with e.locked():authority()
            except (OSError,ValueError) as exc:
                outcomes.append(RunOutcome(item.source,error=str(exc)));continue
            run=ledger.claim(plan,'图片转换（替换原件）' if preview.mode=='replace' else '图片转换（保留原件）')
            if run is None:
                outcomes.append(RunOutcome(item.source,status='skipped',error='此版本已执行或需要核对历史'));continue
            row=ledger.get(run);ticket=None;committed=False
            def report(value):
                if hasattr(value,'phase'):value={'phase':'committing' if value.phase=='complete' else value.phase,'percent':min(value.percent,99)}
                progress({**value,'index':index,'source':str(item.source)})
            try:
                with e.locked():authority();ledger.update(run,'running')
                ticket=generate_owned(e,item.source,item.target,spec,cancel,report,expected_source=validation.source_fingerprint,
                    expected_capability_digest=validation.capability_digest)
                with e.locked():
                    authority();report({'phase':'committing','percent':99})
                    result=e.publish_generated(item.source,item.target,validation.source_fingerprint,ticket,ticket.output_fingerprint,
                        row['name'],mode=preview.mode,batch_id=row['batch_id'],cancel_event=cancel)
                latest=result.items[-1];committed=latest.ok
                if not committed:raise ValueError(latest.message)
                self.runner.checkpoint('published_before_provenance',run,latest)
                ledger.register(item.target,latest.target_fingerprint,json.loads(row['visited']))
                ledger.update(run,'success',progress=[{'operation_id':latest.operation_id,'state':latest.state}])
                report({'phase':'complete','percent':100,'status':'success'})
                outcomes.append(RunOutcome(item.source,row['batch_id'],'success',steps=(latest,),run_id=run))
            except Exception as exc:
                ledger.update(run,'partial' if committed else 'failed',str(exc));ledger.reconcile()
                outcomes.append(RunOutcome(item.source,row['batch_id'],'partial' if committed else 'failed',str(exc),run_id=run))
            finally:
                if ticket is not None:
                    try:discard_owned(e,ticket)
                    except (OSError,ValueError):pass
        return tuple(outcomes)
