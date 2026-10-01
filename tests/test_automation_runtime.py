from dataclasses import replace
from datetime import datetime, timezone, timedelta
from threading import Event
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from filehub.models import Fingerprint

import pytest
from PySide6.QtGui import QImage, QColor

from filehub.config import Config
from filehub.service import FileHubService
from filehub.scheduler import Scheduler
from filehub.automation.models import Rule, RuleSet, Predicate, Action
from filehub.automation.runner import AutomationRunner
from filehub.automation.executor import ConversionExecutor
from filehub.conversion.models import ConversionSpec

NOW = datetime.now(timezone.utc)+timedelta(days=40)

@pytest.fixture
def setup(tmp_path):
    watch=tmp_path/'watch';watch.mkdir()
    return FileHubService(Config(watch_roots=(watch,),paused=False),tmp_path/'state'),watch

def rule(*actions, extension='.txt', name='规则'):
    return Rule(name=name,enabled=True,condition=Predicate('extension','equals',extension),actions=actions)

def save(s,*rules):s.rules.save(RuleSet(rules))

def png(path):
    image=QImage(8,6,QImage.Format.Format_ARGB32);image.fill(QColor('#f04422'));assert image.save(str(path),'PNG')

def test_basic_without_sync_runs_before_legacy_gate_and_restart_claims_copy(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'hello');dest=w.parent/'out'
    save(s,rule(Action('copy',{'destination':str(dest)})))
    assert Scheduler(s).tick(NOW)[0].ok
    assert p.exists() and (dest/p.name).read_bytes()==b'hello'
    assert Scheduler(FileHubService(s.config,s.engine.state_dir)).tick(NOW+timedelta(days=8))==[]

def test_ordered_copy_rename_move_one_batch_and_undo_suppression(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'hello');copy=w.parent/'copy';dest=w.parent/'dest'
    save(s,rule(Action('copy',{'destination':str(copy)}),Action('rename',{'pattern':'b{ext}'}),Action('move',{'destination':str(dest)})))
    preview=s.automation.preview([p],s.rules.load().rules[0].id)
    outcome=s.automation.execute(preview)[0]
    assert outcome.status=='success' and len(s.engine.journal.items(outcome.batch_id))==3
    assert (dest/'b.txt').read_bytes()==b'hello' and p.exists()
    assert s.undo(outcome.batch_id).ok
    assert Scheduler(FileHubService(s.config,s.engine.state_dir)).tick(NOW)==[]

def test_stale_manual_preview_does_not_claim_unstarted_work(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');dest=w.parent/'out'
    first=rule(Action('copy',{'destination':str(dest)}));second=rule(Action('rename',{'pattern':'later{ext}'}))
    save(s,first,second);preview=s.automation.preview([p],first.id)
    dest.mkdir()
    # Isolate claim semantics from existing ordinary-copy NTFS name tunneling:
    # a vacated target inherits this creation time during subsequent publish.
    from filehub.platform.metadata import set_times
    fp=s.automation.facts(p).fingerprint
    with s.engine.platform.create_target(dest/p.name) as guard:
        guard.stream.write(b'occupied');guard.flush()
        set_times(guard.handle,fp.creation_ns,fp.mtime_ns)
    assert s.automation.execute(preview)[0].status=='failed'
    (dest/p.name).unlink()
    fresh=s.automation.preview([p],first.id)
    assert s.automation.execute(fresh)[0].ok
    assert Scheduler(s).tick(NOW)==[] and p.exists()

@pytest.mark.parametrize('mode',['keep','replace'])
def test_standalone_real_image_preview_run(mode,setup):
    s,w=setup;p=w/'a.png';png(p)
    ex=s.conversions
    preview=ex.submit_image_preview([p],ConversionSpec(output_format='jpeg'),mode=mode,output_dir=w.parent/'out' if mode=='keep' else None).future.result(5)
    result=ex.submit_images(preview).future.result(5)
    assert result[0].status=='success'
    assert preview.items[0].target.exists() and p.exists()==(mode=='keep')
    assert s.undo(result[0].batch_id).ok and p.exists()
    ex.close().wait(5)

def test_rule_real_convert_rename_move_and_undo(setup):
    s,w=setup;p=w/'a.png';png(p);dest=w.parent/'out'
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),Action('rename',{'pattern':'b{ext}'}),Action('move',{'destination':str(dest)}),extension='.png')
    save(s,r);preview=s.conversions.submit_rule_preview([p],r.id).future.result(5)
    outcome=s.conversions.submit_rule(preview).future.result(5)[0]
    assert outcome.status=='success' and (dest/'b.jpg').exists() and not p.exists()
    assert s.undo(outcome.batch_id).ok and p.exists()

def test_standalone_pause_during_encode_continues_explicit_job(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p);ex=s.conversions
    preview=ex.submit_image_preview([p],ConversionSpec(),mode='replace').future.result(5)
    import filehub.automation.executor as runtime
    original=runtime.generate_owned;started=Event();release=Event()
    def delayed(*a,**kw):started.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(runtime,'generate_owned',delayed)
    job=ex.submit_images(preview);assert started.wait(2)
    with s.engine.locked():s.config=replace(s.config,paused=True)
    ex.cancel_automatic();assert not job.cancel_event.is_set()
    release.set();assert job.future.result(5)[0].ok and (w/'a.jpg').exists()
    ex.close().wait(5)

@pytest.mark.parametrize('change',['enabled','semantic','templates','watch'])
def test_auto_authority_changes_during_codec_prevent_publish(setup,monkeypatch,change):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    original=runtime.generate_owned;started=Event();release=Event()
    def delayed(*a,**kw):started.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(runtime,'generate_owned',delayed)
    Scheduler(s).tick(NOW);assert started.wait(2)
    with s.engine.locked():
        if change=='enabled':save(s,replace(r,enabled=False))
        elif change=='semantic':save(s,replace(r,actions=(Action('image_convert',{'output_format':'webp','mode':'replace'}),)))
        elif change=='templates':
            library=s.reload_templates();s.templates.save(library.copy_template('default','custom','新模板'))
        else:s.config=replace(s.config,watch_roots=())
    release.set();idle(s.conversions)
    assert p.exists() and not (w/'a.jpg').exists()
    assert s.automation.ledger.history()[0]['status']=='failed'
    assert not list(w.glob('.filehub-generated-*'))
    s.conversions.close().wait(5)

def test_retained_copy_source_suppression_and_generated_output_new_rule_chain(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x')
    # A copy stays in watched top-level subfolder? Only the original is watched;
    # externally renaming that original is a new exact-path chain.
    r=rule(Action('copy',{'destination':str(w.parent/'out')}));save(s,r)
    assert Scheduler(s).tick(NOW)[0].ok
    p.rename(w/'renamed.txt')
    preview=s.automation.preview([w/'renamed.txt'],r.id)
    assert not preview.errors and s.automation.execute(preview)[0].ok

def test_image_rule_requires_executor_before_any_material_step(setup):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('rename',{'pattern':'renamed{ext}'}),Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    preview=s.automation.preview([p],r.id)
    with pytest.raises(ValueError,match='工作线程'):s.automation.execute(preview)
    assert p.exists() and not (w/'renamed.png').exists()

def test_pause_releases_only_settled_queued_zero_intent_job_then_resume(setup,monkeypatch):
    s,w=setup;first=w/'a.png';png(first);second=w/'b.png';png(second)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    original=runtime.generate_owned;entered=Event();release=Event()
    def delayed(*a,**kw):entered.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(runtime,'generate_owned',delayed)
    q=Scheduler(s);q.tick(NOW);assert entered.wait(2)
    with s.engine.locked():s.config=replace(s.config,paused=True)
    s.conversions.cancel_automatic();release.set();idle(s.conversions)
    rows=s.automation.ledger.history()
    assert {row['status'] for row in rows}=={'failed','canceled_before_start'}
    queued=next(row for row in rows if row['status']=='canceled_before_start')
    assert queued['original']==str(second) and not s.engine.journal.items(queued['batch_id'])
    assert not s.automation.ledger.suppression(second,Fingerprint.capture(second),r)
    with s.engine.locked():s.config=replace(s.config,paused=False)
    q.tick(NOW);idle(s.conversions)
    assert first.exists() and not second.exists() and (w/'b.jpg').exists()
    assert len(s.automation.ledger.history())==3
    s.conversions.close().wait(5)

def test_theme_only_change_during_automatic_encoding_keeps_authority(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    original=runtime.generate_owned;entered=Event();release=Event()
    def delayed(*a,**kw):entered.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(runtime,'generate_owned',delayed)
    Scheduler(s).tick(NOW);assert entered.wait(2)
    with s.engine.locked():s.config=replace(s.config,theme='light')
    release.set();idle(s.conversions)
    assert not p.exists() and (w/'a.jpg').exists() and s.automation.ledger.history()[0]['status']=='success'
    s.conversions.close().wait(5)

def test_invalid_project_route_without_sync_is_claimed_and_blocks_second_rule(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x')
    a=rule(Action('project_route',{'tag':'XYZ参考'}));b=rule(Action('rename',{'pattern':'later{ext}'}));save(s,a,b)
    result=Scheduler(s).tick(NOW)
    assert result[0].status=='failed' and p.exists() and not (w/'later.txt').exists()
    assert Scheduler(s).tick(NOW)==[] and len(s.automation.ledger.history())==1

def test_submit_rule_foreign_or_forged_preview_cannot_promote_owner(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    preview=s.automation.preview([p],r.id)
    other=FileHubService(s.config,s.engine.state_dir);ex=other.conversions
    import filehub.automation.runner as runtime
    monkeypatch.setattr(runtime,'inspect',lambda *a:pytest.fail('foreign preview decoded'))
    with pytest.raises(ValueError,match='预览'):ex.submit_rule(preview).future.result(5)
    with pytest.raises(ValueError,match='预览'):s.conversions.submit_rule(replace(preview)).future.result(5)
    assert p.exists() and not (w/'a.jpg').exists() and not s.automation.ledger.history()
    ex.close().wait(5);s.conversions.close().wait(5)

def test_manual_preview_does_not_invalidate_owned_queued_automatic_preview(setup):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    ex=s.conversions;entered=Event();release=Event()
    ex.submit(lambda cancel,report:(entered.set(),release.wait(5)))
    assert entered.wait(2);Scheduler(s).tick(NOW)
    sample=w.parent/'sample.png';png(sample)
    manual=s.automation.preview([sample],r.id);assert not manual.errors
    release.set();idle(ex)
    assert not p.exists() and (w/'a.jpg').exists() and s.automation.ledger.history()[0]['status']=='success'
    ex.close().wait(5)
    assert Scheduler(FileHubService(s.config,s.engine.state_dir)).tick(NOW)==[]
    s.conversions.close().wait(5)

def test_async_close_cancels_and_settles_before_callback(setup):
    s,w=setup;ex=s.conversions;started=Event();release=Event();settled=Event()
    def work(cancel,progress):started.set();release.wait(5);return cancel.is_set()
    job=ex.submit(work);assert started.wait(2)
    done=ex.close(callback=lambda:settled.set())
    assert not done.is_set() and not settled.is_set()
    release.set();assert done.wait(5) and settled.wait(5) and job.future.result()

def idle(ex):
    done=Event();ex.when_idle(done.set);assert done.wait(10)

def test_two_real_replace_rules_cycle_stops_after_a_b_and_restart(setup):
    s,w=setup;p=w/'a.png';png(p)
    a=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png',name='A')
    b=rule(Action('image_convert',{'output_format':'png','mode':'replace'}),extension='.jpg',name='B')
    save(s,a,b);q=Scheduler(s)
    q.tick(NOW);idle(s.conversions)
    assert (w/'a.jpg').exists() and not p.exists()
    q.tick(NOW);idle(s.conversions)
    assert p.exists() and not (w/'a.jpg').exists()
    assert [r['status'] for r in s.automation.ledger.history()]==['success','success']
    assert q.tick(NOW)==[] and len(s.automation.ledger.history())==2
    s.conversions.close().wait(5)
    restarted=FileHubService(s.config,s.engine.state_dir)
    assert Scheduler(restarted).tick(NOW)==[] and len(restarted.automation.ledger.history())==2

def test_disabled_manual_rule_and_foreign_or_forged_preview(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x')
    r=replace(rule(Action('rename',{'pattern':'done{ext}'})),enabled=False);save(s,r)
    preview=s.automation.preview([p],r.id)
    with pytest.raises(ValueError,match='预览'):s.automation.execute(replace(preview))
    other=FileHubService(s.config,s.engine.state_dir)
    with pytest.raises(ValueError,match='预览'):other.automation.execute(preview)
    assert s.automation.execute(preview)[0].ok and (w/'done.txt').exists()
    assert not s.rules.load().rules[0].enabled

def test_manual_stale_config_fresh_preview_is_eligible(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');r=rule(Action('rename',{'pattern':'done{ext}'}));save(s,r)
    preview=s.automation.preview([p],r.id);s.config=replace(s.config,global_jobs=True)
    assert not s.automation.execute(preview)[0].ok and not s.automation.ledger.history()
    assert s.automation.execute(s.automation.preview([p],r.id))[0].ok

def test_first_matching_invalid_plan_claims_never_falls_through(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');out=w.parent/'out';out.mkdir();(out/'a.txt').write_bytes(b'occupied')
    a=rule(Action('copy',{'destination':str(out)}));b=rule(Action('rename',{'pattern':'later{ext}'}));save(s,a,b)
    q=Scheduler(s);result=q.tick(NOW)
    assert result[0].status=='failed' and p.exists() and not (w/'later.txt').exists()
    assert q.tick(NOW+timedelta(days=10))==[]
    assert s.automation.ledger.history()[0]['rule_id']==a.id

def test_semantic_edits_and_external_content_new_chain_but_name_enable_order_do_not(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');out=w.parent/'out';r=rule(Action('copy',{'destination':str(out)}));save(s,r)
    q=Scheduler(s);assert q.tick(NOW)[0].ok
    save(s,replace(r,name='改名',enabled=False));q.tick(NOW)
    save(s,replace(r,name='改名',enabled=True));assert q.tick(NOW)==[]
    edited=replace(r,actions=(Action('copy',{'destination':str(w.parent/'new')}),));save(s,edited)
    assert q.tick(NOW)[0].ok
    p.write_bytes(b'changed');(w.parent/'new'/'a.txt').rename(w.parent/'new'/'prior.txt')
    result=q.tick(NOW)
    assert result and result[0].ok and len(s.automation.ledger.history())==3

def test_observations_persist_age_and_pause_resets_only_observations(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x')
    from filehub.automation.models import ConditionGroup
    r=replace(rule(Action('rename',{'pattern':'done{ext}'})),condition=ConditionGroup('all',(
        Predicate('extension','equals','.txt'),Predicate('first_seen_age_seconds','ge',3600))))
    save(s,r);q=Scheduler(s);assert q.tick(NOW)==[]
    s2=FileHubService(s.config,s.engine.state_dir);q2=Scheduler(s2)
    assert q2.tick(NOW+timedelta(minutes=30))==[]
    s2.config=replace(s2.config,paused=True);q2.tick(NOW+timedelta(hours=2))
    assert not s2.automation.ledger.observed(p,s2.automation.facts(p).fingerprint)[0]
    s2.config=replace(s2.config,paused=False)
    assert q2.tick(NOW+timedelta(hours=3))==[]
    assert q2.tick(NOW+timedelta(hours=4))[0].ok

def test_move_undo_new_identity_suppressed_after_restart(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');r=rule(Action('move',{'destination':str(w.parent/'out')}));save(s,r)
    result=Scheduler(s).tick(NOW)[0];assert result.ok
    assert s.undo(result.batch_id).ok and p.exists()
    s2=FileHubService(s.config,s.engine.state_dir);assert Scheduler(s2).tick(NOW)==[]
    edited=replace(r,actions=(Action('rename',{'pattern':'eligible{ext}'}),));save(s2,edited)
    assert Scheduler(s2).tick(NOW)[0].ok

def test_claimed_image_is_skipped_without_decode(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p);r=rule(Action('image_convert',{'output_format':'jpeg','mode':'keep','destination':str(w.parent/'out')}),extension='.png');save(s,r)
    q=Scheduler(s);q.tick(NOW);idle(s.conversions)
    import filehub.automation.runner as runtime
    monkeypatch.setattr(runtime,'inspect',lambda *a:pytest.fail('claimed input decoded again'))
    assert q.tick(NOW)==[]
    s.conversions.close().wait(5)

def test_partial_chain_retains_prior_copy_and_durable_suppression(setup,monkeypatch):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');dest=w.parent/'out';r=rule(Action('copy',{'destination':str(dest)}),Action('rename',{'pattern':'later{ext}'}));save(s,r)
    execute=s.engine.execute
    def fail(operations,*a,**kw):
        if operations and operations[0].source==dest/p.name:
            s.engine.journal.append_operations(kw['batch_id'],operations)
            item=s.engine.journal.items(kw['batch_id'])[-1];s.engine.journal.transition(item.operation_id,'failed','injected second step')
            return s.engine.journal.batch(kw['batch_id'])
        return execute(operations,*a,**kw)
    monkeypatch.setattr(s.engine,'execute',fail)
    result=s.automation.execute(s.automation.preview([p],r.id))[0]
    assert result.status=='partial' and len(result.steps)==1 and p.exists() and (dest/p.name).exists()
    assert Scheduler(FileHubService(s.config,s.engine.state_dir)).tick(NOW)==[]
    assert s.undo(result.batch_id).status=='partial'
    assert not (dest/p.name).exists() and p.exists()

def test_directory_move_rename_chain_undo_and_provenance(setup):
    s,w=setup;p=w/'folder';p.mkdir();(p/'child.txt').write_bytes(b'x')
    r=Rule(name='目录',enabled=True,condition=Predicate('kind','equals','folder'),actions=(
        Action('move',{'destination':str(w.parent/'out')}),Action('rename',{'pattern':'renamed'})))
    save(s,r);outcome=Scheduler(s).tick(NOW)[0]
    assert outcome.ok and (w.parent/'out'/'renamed'/'child.txt').exists()
    assert s.undo(outcome.batch_id).ok and (p/'child.txt').exists()
    assert Scheduler(FileHubService(s.config,s.engine.state_dir)).tick(NOW)==[]

def test_preview_cancel_after_decode_returns_no_runnable_token(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p);cancel=Event()
    import filehub.automation.executor as runtime
    original=runtime.inspect
    def canceled(*a):result=original(*a);cancel.set();return result
    monkeypatch.setattr(runtime,'inspect',canceled)
    with pytest.raises(ValueError,match='取消'):s.conversions.preview_images([p],ConversionSpec(),mode='replace',cancel_event=cancel)
    assert not s.conversions._previews
    s.conversions.close().wait(5)

def test_close_before_lazy_submit_retires_service(setup):
    s,_=setup;assert s.close_conversions().is_set()
    with pytest.raises(ValueError,match='关闭'):s.conversions

def test_image_preview_reserves_all_sources_and_duplicate_targets(setup):
    s,w=setup;p=w/'a.png';png(p);other=w/'a.jpg';png(other);ex=s.conversions
    preview=ex.submit_image_preview([p,other],ConversionSpec(),mode='replace').future.result(5)
    assert preview.items[0].error and '重叠' in preview.items[0].error
    dup=ex.submit_image_preview([p,p],ConversionSpec(),mode='replace').future.result(5)
    assert all(item.error for item in dup.items)
    assert all(not r.ok for r in ex.submit_images(dup).future.result(5))
    ex.close().wait(5)

def test_auto_pause_during_codec_prevents_publish_and_archive_remains_responsive(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p);root=w.parent/'sync';root.mkdir();(root/'1_工作'/'项目'/'260101_XYZ_项目').mkdir(parents=True)
    s.config=replace(s.config,sync_root=root)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    original=runtime.generate_owned;started=Event();release=Event()
    def delayed(*a,**kw):started.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(runtime,'generate_owned',delayed)
    Scheduler(s).tick(NOW);assert started.wait(2)
    ordinary=w/'archive.txt';ordinary.write_bytes(b'x')
    with ThreadPoolExecutor(max_workers=1) as worker:
        batch=worker.submit(s.preview,[ordinary],'XYZ参考').result(2)
        assert worker.submit(s.execute,batch).result(2).ok
    s.config=replace(s.config,paused=True);release.set();idle(s.conversions)
    assert p.exists() and not (w/'a.jpg').exists()
    assert s.automation.ledger.history()[0]['status']=='failed'
    s.conversions.close().wait(5)

def test_queued_auto_disable_rechecks_before_decode(setup):
    s,w=setup;p=w/'a.png';png(p);r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    ex=s.conversions;started=Event();release=Event()
    ex.submit(lambda cancel,report:(started.set(),release.wait(5)))
    assert started.wait(2);Scheduler(s).tick(NOW)
    save(s,replace(r,enabled=False));release.set();idle(ex)
    assert p.exists() and not (w/'a.jpg').exists() and s.automation.ledger.history()[0]['status']=='canceled_before_start'
    ex.close().wait(5)

def test_critical_replace_switch_waits_asynchronously_and_reports_actual_commit(setup):
    from filehub.platform.windows import WindowsPlatform
    s,w=setup;p=w/'a.png';png(p);second=w/'second.png';png(second)
    entered=Event();release=Event();switched=Event();order=[]
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    s.engine.platform=Block();ex=s.conversions
    preview=ex.submit_image_preview([p,second],ConversionSpec(),mode='replace').future.result(5)
    job=ex.submit_images(preview,completion=lambda f:order.append('completed'))
    assert entered.wait(2)
    settled=s.close_conversions(callback=lambda:(order.append('switched'),switched.set()))
    assert not switched.is_set() and not settled.is_set()
    release.set();assert settled.wait(5) and switched.wait(5)
    outcomes=job.future.result();assert outcomes[0].ok and len(outcomes)==1
    assert (w/'a.jpg').exists() and not p.exists() and second.exists()
    assert order==['completed','switched']

def crash_runtime(s,w,point,*,generated=False):
    script=w.parent/'crash-runtime.py'
    script.write_text('\n'.join([
        'import os,sys',
        'from pathlib import Path',
        'from datetime import datetime,timezone',
        'from filehub.config import Config',
        'from filehub.service import FileHubService',
        'from filehub.scheduler import Scheduler',
        'from filehub.platform.windows import WindowsPlatform',
        'class Crash(WindowsPlatform):',
        " def checkpoint(self,stage,item):",
        "  if sys.argv[4]=='generated' and stage==sys.argv[3]:os._exit(77)",
        "s=FileHubService(Config(watch_roots=(Path(sys.argv[1]),),paused=False),Path(sys.argv[2]),platform=Crash())",
        'def fault(phase,run,item):',
        " if sys.argv[4]=='runtime' and phase==sys.argv[3]:os._exit(77)",
        's.automation.checkpoint=fault',
        'Scheduler(s).tick(datetime.now(timezone.utc))',
        'from threading import Event',
        'e=Event();s.conversions.when_idle(e.set);e.wait(10)',
    ]),encoding='utf-8')
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    child=subprocess.run([sys.executable,str(script),str(w),str(s.engine.state_dir),point,'generated' if generated else 'runtime'],env=env,capture_output=True,timeout=15)
    assert child.returncode==77,child.stderr.decode(errors='replace')

@pytest.mark.parametrize('point',['published_before_provenance','provenance_recorded'])
def test_actual_process_crash_journal_provenance_gap_restarts_without_replay(setup,point):
    s,w=setup;p=w/'a.png';png(p);r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    crash_runtime(s,w,point)
    restarted=FileHubService(s.config,s.engine.state_dir);assert Scheduler(restarted).tick(NOW)==[]
    assert (w/'a.jpg').exists() and not p.exists()
    assert restarted.automation.ledger.history()[0]['status']=='review_required'

def test_samepath_prebind_crash_blocks_actual_tunneled_output_before_scan(setup):
    s,w=setup;p=w/'a.jpg';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.jpg');save(s,r)
    crash_runtime(s,w,'after_generated_rename_before_binding',generated=True)
    restart=FileHubService(s.config,s.engine.state_dir);assert Scheduler(restart).tick(NOW)==[]
    assert len(restart.automation.ledger.history())==1 and p.exists()
    assert restart.engine.history()[0].items[-1].state=='conflict'
    assert '中断' in restart.automation.ledger.suppression(p,Fingerprint.capture(p),r)
    restart.conversions.close().wait(5)

def test_full_decode_preview_worker_does_not_block_ordinary_work(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p)
    import filehub.automation.executor as runtime
    started=Event();release=Event();original=runtime.inspect
    def inspect_slow(*a):started.set();assert release.wait(5);return original(*a)
    monkeypatch.setattr(runtime,'inspect',inspect_slow)
    ex=s.conversions;job=ex.submit_image_preview([p],ConversionSpec(),mode='replace')
    assert started.wait(2)
    with ThreadPoolExecutor(max_workers=1) as ordinary:
        assert ordinary.submit(s.rules.load).result(2).rules==()
    job.cancel_event.set();release.set()
    with pytest.raises(ValueError,match='取消'):job.future.result(5)
    assert p.exists() and not (w/'a.jpg').exists()
    ex.close().wait(5)

def test_rule_preview_cancel_between_full_decodes(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p);second=w/'b.png';png(second)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    started=Event();release=Event();calls=[];original=runtime.inspect
    def inspect_slow(path,*a):
        calls.append(path);started.set();assert release.wait(5);return original(path,*a)
    monkeypatch.setattr(runtime,'inspect',inspect_slow)
    ex=s.conversions;job=ex.submit_rule_preview([p,second],r.id)
    assert started.wait(2);job.cancel_event.set();release.set()
    with pytest.raises(ValueError,match='取消'):job.future.result(5)
    assert calls==[p]
    ex.close().wait(5)

def test_queued_cancel_finishes_durable_claim_without_stuck_active_run(setup):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    ex=s.conversions;entered=Event();release=Event()
    ex.submit(lambda cancel,report:(entered.set(),release.wait(5)))
    assert entered.wait(2);Scheduler(s).tick(NOW)
    settled=s.close_conversions();release.set();assert settled.wait(5)
    assert s.automation.ledger.history()[0]['status']=='canceled_before_start'
    from filehub.automation.ledger import ACTIVE_RUNS
    assert s.automation.ledger.history()[0]['id'] not in ACTIVE_RUNS

def test_multiple_conversions_each_inspects_actual_generated_subject(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('rename',{'pattern':'start{ext}'}),
        Action('image_convert',{'output_format':'jpeg','mode':'replace'}),
        Action('image_convert',{'output_format':'webp','mode':'replace'}),extension='.png');save(s,r)
    ex=s.conversions;preview=ex.submit_rule_preview([p],r.id).future.result(5)
    import filehub.automation.runner as runtime
    calls=[];original=runtime.inspect
    def traced(path,*a):calls.append(path);return original(path,*a)
    monkeypatch.setattr(runtime,'inspect',traced)
    outcome=ex.submit_rule(preview).future.result(5)[0]
    assert outcome.ok and calls==[w/'start.png',w/'start.jpg']
    assert (w/'start.webp').exists() and not p.exists()
    assert s.undo(outcome.batch_id).ok and p.exists()
    ex.close().wait(5)

def test_standalone_stale_preview_failure_does_not_poison_claim(setup):
    s,w=setup;p=w/'a.png';png(p);ex=s.conversions
    preview=ex.submit_image_preview([p],ConversionSpec(),mode='replace').future.result(5)
    s.config=replace(s.config,global_jobs=True)
    assert not ex.submit_images(preview).future.result(5)[0].ok and not s.automation.ledger.history()
    fresh=ex.submit_image_preview([p],ConversionSpec(),mode='replace').future.result(5)
    assert ex.submit_images(fresh).future.result(5)[0].ok
    ex.close().wait(5)

def test_atomic_manual_automatic_claim_duplicate(setup):
    s,w=setup;p=w/'a.txt';p.write_bytes(b'x');dest=w.parent/'out'
    r=rule(Action('copy',{'destination':str(dest)}));save(s,r)
    runner=s.automation;preview=runner.preview([p],r.id)
    with ThreadPoolExecutor(max_workers=2) as workers:
        manual=workers.submit(runner.execute,preview)
        automatic=workers.submit(Scheduler(s).tick,NOW)
        manual.result(5);automatic.result(5)
    assert len(runner.ledger.history())==1 and (dest/p.name).exists()

def test_video_project_route_existing_probe_and_keep_name_no_probe(setup):
    s,w=setup;root=w.parent/'sync';project=root/'1_工作'/'项目'/'260101_XYZ_项目';project.mkdir(parents=True)
    s.config=replace(s.config,sync_root=root)
    p=w/'one.mp4';p.write_bytes(b'video');calls=[];s.probe=lambda path:(calls.append(path),1920)[1]
    r=rule(Action('project_route',{'tag':'XYZ020822'}),extension='.mp4');save(s,r)
    preview=s.automation.preview([p],r.id)
    assert not preview.errors and calls==[p]
    assert s.automation.execute(preview)[0].ok
    second=w/'second.mp4';second.write_bytes(b'video')
    keep=replace(r,actions=(Action('project_route',{'tag':'XYZ参考'}),));save(s,keep);calls.clear()
    preview=s.automation.preview([second],keep.id)
    assert not preview.errors and calls==[]
    assert s.automation.execute(preview)[0].ok

def test_automatic_image_completion_hook_and_batch_indexed_final_progress(setup):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    callback=Event();values=[]
    q=Scheduler(s,automatic_completion=lambda f:(values.extend(f.result()),callback.set()))
    assert q.tick(NOW)==[] and callback.wait(5) and values[0].ok
    second=w/'b.png';png(second);third=w/'c.png';png(third);progress=[]
    ex=s.conversions;preview=ex.submit_image_preview([second,third],ConversionSpec(),mode='replace').future.result(5)
    assert all(item.ok for item in ex.submit_images(preview,progress=progress.append).future.result(5))
    assert {p['index'] for p in progress}=={0,1}
    for index in (0,1):
        entries=[p for p in progress if p['index']==index]
        assert entries[-1]['phase']=='complete' and entries[-1]['percent']==100
        assert all(p['percent']<100 for p in entries[:-1])
    ex.close().wait(5)

def test_lazy_executor_and_scan_contention_has_consistent_lock_order(setup,monkeypatch):
    s,w=setup;p=w/'a.png';png(p)
    r=rule(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),extension='.png');save(s,r)
    import filehub.automation.runner as runtime
    original=runtime.AutomationRunner.__init__;entered=Event();release=Event()
    def blocked(self,service):entered.set();assert release.wait(5);original(self,service)
    monkeypatch.setattr(runtime.AutomationRunner,'__init__',blocked)
    scheduler=Scheduler(s)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first=workers.submit(lambda:s.conversions)
        assert entered.wait(2)
        second=workers.submit(scheduler.tick,NOW)
        release.set();ex=first.result(5);second.result(5)
    idle(ex);assert (w/'a.jpg').exists();ex.close().wait(5)

def test_terminal_project_route_branch_copy_does_not_advance_subject(setup):
    s,w=setup;root=w.parent/'sync';project=root/'1_工作'/'项目'/'260101_XYZ_项目';project.mkdir(parents=True)
    s.config=replace(s.config,sync_root=root);s.probe=lambda p:1920
    p=w/'one.mp4';p.write_bytes(b'video');r=rule(Action('project_route',{'tag':'XYZ020822+23'}),extension='.mp4');save(s,r)
    preview=s.automation.preview([p],r.id)
    assert preview.plans[0].steps[0].advances_subject is False
    outcome=s.automation.execute(preview)[0]
    assert outcome.ok and len(outcome.steps)==2 and not p.exists()
    assert s.undo(outcome.batch_id).ok and p.exists()
