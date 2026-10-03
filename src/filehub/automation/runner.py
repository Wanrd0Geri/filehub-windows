"""Fingerprint-bound ordered rule runs over the existing transaction engine."""
from dataclasses import dataclass, replace, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, current_thread
import hashlib
import json
from weakref import WeakValueDictionary

from ..models import Fingerprint, Operation, checked_path
from ..conversion.images import inspect
from ..generated import generate_owned, discard_owned
from .models import RuleStore
from .conditions import FileFacts, first_match
from .planner import plan_rule, RulePlan, PlanReservations, path_key, _existing_collision
from .ledger import AutomationLedger, ACTIVE_STATES


def config_revision(config,*,ignore_paused=False,ignore_theme=False):
    data=asdict(config)
    if ignore_paused:data.pop('paused')
    if ignore_theme:data.pop('theme')
    return hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class RulePreview:
    plans: tuple
    matching: tuple
    errors: tuple
    ruleset_revision: str
    template_revision: str
    config_revision: str
    image_capabilities: tuple = ()
    authority_config_revision: str = ''


class AuthorityChanged(ValueError):
    """A bound queued job lost permission before a material boundary."""


@dataclass(frozen=True)
class RunOutcome:
    source: Path
    batch_id: str = ''
    status: str = 'failed'
    error: str = ''
    steps: tuple = ()
    run_id: str = ''

    @property
    def ok(self):return self.status=='success'


class AutomationRunner:
    def __init__(self,service):
        self.service=service;self.engine=service.engine
        self.ledger=AutomationLedger(self.engine);self._previews=WeakValueDictionary();self._automatic_previews=set()
        # Existing engine recovery only classifies prior intents, never re-encodes.
        with self.engine.locked():
            if path_key(self.engine.state_dir) not in tuple(ACTIVE_STATES.values()):self.engine.recover()
            self.ledger.reconcile()

    def facts(self,path,*,now=None,watch_root=None):
        facts=FileFacts.capture(path)
        observed=self.ledger.observe(path,facts.fingerprint,now,watch_root) if watch_root is not None else self.ledger.observed(path,facts.fingerprint)
        return replace(facts,first_seen=observed[0],stable_since=observed[1])

    def preview(self,paths,rule_id=None,*,inspect_images=False,now=None,automatic=False,watch_root=None,cancel_event=None):
        cancel=cancel_event or Event()
        self._automatic_previews.intersection_update(self._previews.keys())
        if not automatic:
            for key in tuple(self._previews.keys()):
                if key not in self._automatic_previews:self._previews.pop(key,None)
        now=now or datetime.now(timezone.utc);paths=tuple(checked_path(p) for p in paths)
        snapshot_config_revision=config_revision(self.service.config)
        authority_config_revision=config_revision(self.service.config,ignore_theme=True)
        rules=self.service.rules.load();templates=self.service.reload_templates()
        reservations=PlanReservations(paths);plans=[];matching=[];errors=[];capabilities=[]
        for path in paths:
            facts=None;match=None
            try:
                if cancel.is_set():raise ValueError('已取消预览')
                facts=self.facts(path,now=now,watch_root=watch_root if automatic else None)
                match=first_match(rules,facts,now,rule_id=rule_id if not automatic else None,
                    watch_root=watch_root if automatic else None,configured_watch_roots=self.service.config.watch_roots if automatic else None)
                matching.append(match)
                if match.rule is None:raise ValueError('没有匹配的规则')
                suppression=self.ledger.suppression(path,facts.fingerprint,match.rule)
                if suppression:raise ValueError(suppression)
                inspected={}
                if inspect_images:
                    # Future paths must never masquerade as inspected subjects.
                    for index,action in enumerate(match.rule.actions):
                        if action.kind!='image_convert':continue
                        if cancel.is_set():raise ValueError('已取消预览')
                        checked=inspect(path,action.conversion_spec)
                        if cancel.is_set():raise ValueError('已取消预览')
                        if checked.source_fingerprint!=facts.fingerprint:raise ValueError('图片在预览核验时变化')
                        capabilities.append((path_key(path),index,checked.capability_digest))
                        if index==0:inspected[index]=checked
                plan=plan_rule(match.rule,facts,self.service,reservations,ruleset_revision=rules.revision,
                    templates=templates,now=now,conversion_plans=inspected)
                if facts.kind=='video' and any('视频探测失败' in error for error in plan.errors):
                    facts=replace(facts,video_width=self.service.probe(path))
                    plan=plan_rule(match.rule,facts,self.service,reservations,ruleset_revision=rules.revision,
                        templates=templates,now=now,conversion_plans=inspected)
                plans.append(plan)
                if plan.errors:errors.extend(plan.errors)
            except (OSError,ValueError) as exc:
                errors.append(f'{path}：{exc}')
                if facts is not None and match is not None and match.rule is not None:
                    rule=match.rule
                    plans.append(RulePlan(path,facts.fingerprint,rule.id,rule.revision,rules.revision,
                        templates.revision,now,errors=(str(exc),)))
        if cancel.is_set():raise ValueError('已取消预览')
        preview=RulePreview(tuple(plans),tuple(matching),tuple(errors),rules.revision,templates.revision,
            snapshot_config_revision,tuple(capabilities),authority_config_revision)
        self._previews[id(preview)]=preview
        if automatic:self._automatic_previews.add(id(preview))
        return preview

    def _authority(self,preview,plan,automatic,cancel):
        if cancel.is_set():raise AuthorityChanged('已取消；后续动作停止')
        if self.service._closing:raise AuthorityChanged('当前服务正在关闭；后续动作停止')
        s=self.service;s.config.validate(self.engine.state_dir)
        if config_revision(s.config,ignore_theme=True)!=preview.authority_config_revision:raise AuthorityChanged('设置在预览后变化，请重新预览')
        rules=s.rules.load()
        if not preview.ruleset_revision or rules.revision!=preview.ruleset_revision:raise AuthorityChanged('规则在预览后变化，请重新预览')
        rule=next((r for r in rules.rules if r.id==plan.rule_id),None)
        if rule is None or rule.revision!=plan.rule_revision:raise AuthorityChanged('规则语义已变化，请重新预览')
        if s.reload_templates().revision!=preview.template_revision:raise AuthorityChanged('模板已变化，请重新预览')
        if rule.scope and path_key(plan.original_path.parent) not in {path_key(p) for p in rule.scope}:
            raise AuthorityChanged('源已不在规则的顶层目录范围')
        if any(a.kind=='project_route' for a in rule.actions):
            s.archive_context(rule_id=rule.id)
        if automatic:
            if s.config.paused or not rule.enabled:raise AuthorityChanged('自动规则已暂停或禁用')
            roots={path_key(p) for p in s.config.watch_roots}
            if path_key(plan.original_path.parent) not in roots:raise AuthorityChanged('自动源已不在配置的观察目录')
            if rule.scope and path_key(plan.original_path.parent) not in {path_key(p) for p in rule.scope}:raise AuthorityChanged('自动源已不在规则范围')
        return rule

    def _preflight(self,preview,plan,automatic,cancel):
        self._authority(preview,plan,automatic,cancel)
        if not plan.ok:raise ValueError('；'.join(plan.errors) or '计划不可执行')
        if Fingerprint.capture(plan.original_path)!=plan.original_fingerprint:raise ValueError('源已变化，请重新预览')
        for step in plan.steps:
            checked_path(step.target);checked_path(step.source)
            own=(step.replaces_original and path_key(step.target)==path_key(plan.original_path)==path_key(step.source))
            if _existing_collision(step.target) and not own:raise ValueError('计划目标已被占用，请重新预览')

    def claim(self,preview,plan):
        rule=next((m.rule for m in preview.matching if m.rule and m.rule.id==plan.rule_id),None)
        return self.ledger.claim(plan,rule.name if rule else plan.rule_id)

    def execute(self,preview,*,cancel_event=None,progress=None,automatic=False,claims=None):
        if self._previews.get(id(preview)) is not preview:raise ValueError('预览不属于当前服务；请重新预览')
        if any(step.kind=='image_convert' for plan in preview.plans for step in plan.steps) and not current_thread().name.startswith('filehub-images'):
            raise ValueError('图片规则必须提交到独立图片工作线程')
        cancel=cancel_event or Event();outcomes=[]
        for index,plan in enumerate(preview.plans):
            run=(claims or {}).get(index)
            if run is None and not automatic:
                try:
                    with self.engine.locked():
                        if preview.errors:raise ValueError('；'.join(preview.errors))
                        self._preflight(preview,plan,False,cancel)
                except (OSError,ValueError) as exc:
                    outcomes.append(RunOutcome(plan.original_path,error=str(exc)));continue
            if run is None:run=self.claim(preview,plan)
            if run is None:
                outcomes.append(RunOutcome(plan.original_path,status='skipped',error='已领取或已处理；请核对历史'));continue
            row=self.ledger.get(run);batch=row['batch_id'];visited={tuple(p) for p in json.loads(row['visited'])};completed=[]
            try:
                with self.engine.locked():
                    if preview.errors:raise ValueError('；'.join(preview.errors))
                    self._preflight(preview,plan,automatic,cancel)
                    self.ledger.update(run,'running')
                current=plan.original_path;expected=plan.original_fingerprint
                for step_index,step in enumerate(plan.steps):
                    def report(value):
                        if progress:
                            if hasattr(value,'phase'):value={'phase':'committing' if value.phase=='complete' else value.phase,'percent':min(value.percent,99)}
                            progress({**value,'index':index,'step_index':step_index,'source':str(current)})
                    with self.engine.locked():
                        self._authority(preview,plan,automatic,cancel)
                        if path_key(current)!=path_key(step.source) or Fingerprint.capture(current)!=expected:raise ValueError('当前对象与已完成动作的精确指纹不一致')
                    if step.kind=='image_convert':
                        validation=inspect(current,step.conversion_spec)
                        digest=next((d for p,i,d in preview.image_capabilities if p==path_key(plan.original_path) and i==step.action_index),validation.capability_digest)
                        if validation.source_fingerprint!=expected or validation.capability_digest!=digest:raise ValueError('图片或编码能力已变化，请重新预览')
                        ticket=None
                        try:
                            ticket=generate_owned(self.engine,current,step.target,step.conversion_spec,cancel,report,
                                expected_source=expected,expected_capability_digest=digest)
                            with self.engine.locked():
                                self._authority(preview,plan,automatic,cancel)
                                report({'phase':'committing','percent':99})
                                result=self.engine.publish_generated(current,step.target,expected,ticket,ticket.output_fingerprint,
                                    row['name'],mode='replace' if step.replaces_original else 'keep',batch_id=batch,cancel_event=cancel)
                        finally:
                            if ticket is not None:
                                try:discard_owned(self.engine,ticket)
                                except (OSError,ValueError):pass
                    else:
                        with self.engine.locked():
                            self._authority(preview,plan,automatic,cancel)
                            result=self.engine.execute([Operation(step.kind,current,step.target,expected)],row['name'],batch_id=batch)
                    item=next(i for i in reversed(result.items) if i.parent_operation_id is None)
                    if not item.ok:raise ValueError(item.message or '动作失败')
                    completed.append({'index':step_index,'operation_id':item.operation_id,'source':str(current),'target':str(step.target),'state':item.state})
                    self.checkpoint('published_before_provenance',run,item)
                    with self.engine.locked():
                        self.ledger.register(item.target,item.target_fingerprint,visited)
                        if current.exists():
                            original_now=Fingerprint.capture(current)
                            if original_now==expected:self.ledger.register(current,expected,visited)
                        self.ledger.update(run,'running',progress=completed)
                    self.checkpoint('provenance_recorded',run,item)
                    if step.advances_subject:current=step.target;expected=item.target_fingerprint
                self.ledger.update(run,'success','已完成；取消请求将停止其余项目' if cancel.is_set() else '',completed)
                if progress:progress({'index':index,'source':str(plan.original_path),'phase':'complete','percent':100,'status':'success'})
                outcomes.append(RunOutcome(plan.original_path,batch,'success',steps=tuple(completed),run_id=run))
            except Exception as exc:
                status='partial' if completed else 'failed'
                # Journal is authoritative if publication committed before a
                # ledger fault; do not misreport an already completed item.
                items=self.engine.journal.items(batch)
                successful=[i for i in items if i.ok and i.parent_operation_id is None]
                if successful and not completed:status='partial'
                self.ledger.update(run,status,str(exc),completed);self.ledger.reconcile()
                outcomes.append(RunOutcome(plan.original_path,batch,status,str(exc),tuple(completed),run))
            if cancel.is_set():break
        return tuple(outcomes)

    def validate_images(self,preview,*,automatic=False,cancel_event=None):
        """Only called on the serial image worker, before queued material work."""
        if self._previews.get(id(preview)) is not preview:raise ValueError('预览不属于当前服务；请重新预览')
        cancel=cancel_event or Event();caps=list(preview.image_capabilities)
        for plan in preview.plans:
            with self.engine.locked():self._authority(preview,plan,automatic,cancel)
            for step in plan.steps:
                if step.kind!='image_convert':continue
                if any(p==path_key(plan.original_path) and i==step.action_index for p,i,d in caps):continue
                checked=inspect(plan.original_path,step.conversion_spec)
                if cancel.is_set():raise ValueError('已取消图片核验')
                if checked.source_fingerprint!=plan.original_fingerprint:raise ValueError('图片源已变化，请重新预览')
                caps.append((path_key(plan.original_path),step.action_index,checked.capability_digest))
        validated=replace(preview,image_capabilities=tuple(caps));self._previews[id(validated)]=validated
        if automatic:self._automatic_previews.add(id(validated))
        return validated

    def checkpoint(self,phase,run,item):
        """Fault-injection seam after a journal commit, before ledger ancestry."""
