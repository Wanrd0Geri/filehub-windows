from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
import pytest
from filehub.config import Config
from filehub.service import FileHubService
from filehub.scheduler import Scheduler
from test_rulefiles_protocol import document

NOW = datetime.now(timezone.utc) + timedelta(days=40)


def install(service, doc, values):
    snapshot = service.catalog.load()
    snapshot = service.catalog.import_package(json.dumps(doc).encode(), expected_revision=snapshot.revision)
    return service.catalog.bind(doc['id'], values, expected_revision=snapshot.revision)


def test_new_user_old_flags_no_hidden_legacy_jobs(tmp_path):
    root = tmp_path/'sync'; root.mkdir(); watch = tmp_path/'watch'; watch.mkdir()
    source = watch/'x.txt'; source.write_bytes(b'x')
    junk = watch/'.baiduyun.uploading.cfg'; junk.write_bytes(b'junk')
    bad = root/'bad😀'; bad.mkdir()
    service = FileHubService(Config(sync_root=root, watch_roots=(watch,), paused=False, global_jobs=True, sweep_days=0), tmp_path/'state')
    scheduler = Scheduler(service)
    assert scheduler.tick(NOW) == []
    assert scheduler.tick(NOW+timedelta(days=10)) == []
    assert source.exists() and junk.exists() and bad.exists()
    assert not (root/'0_收件箱').exists()


def test_manual_scope_without_watch_and_no_old_template_dependency(tmp_path):
    incoming = tmp_path/'in'; incoming.mkdir(); source = incoming/'a.txt'; source.write_bytes(b'a')
    other = tmp_path/'other'; other.mkdir(); outside = other/'a.txt'; outside.write_bytes(b'a')
    service = FileHubService(Config(), tmp_path/'state')
    (service.engine.state_dir/'templates.json').write_text('corrupt', encoding='utf-8')
    doc = document(); doc['rules'][0]['condition'] = {'field':'name','operator':'glob','value':'*'}
    doc['rules'][0]['actions'] = [{'kind':'copy','options':{'destination':{'binding':'output','relative':''}}}]
    snap = install(service, doc, {'input':incoming,'output':tmp_path/'out'})
    rid = snap.runtime_ids['images']['convert']
    preview = service.automation.preview([source], rid)
    assert not preview.errors and preview.plans[0].ok
    assert service.automation.preview([outside],rid).errors
    preview = service.automation.preview([source], rid)
    assert service.automation.execute(preview)[0].ok
    assert (tmp_path/'out/a.txt').read_bytes() == b'a'
    assert service.config.watch_roots == ()


def test_archive_requires_explicit_profile(tmp_path):
    root = tmp_path/'sync'; root.mkdir(); source = tmp_path/'x.txt'; source.write_bytes(b'x')
    service = FileHubService(Config(sync_root=root), tmp_path/'state')
    assert service.preview([source], '通用测试').items[0].error
    assert source.exists() and not list(root.iterdir())


def test_generic_ignores_unused_legacy_sync_overlap_and_invalid_templates(tmp_path):
    service = FileHubService(Config(sync_root=tmp_path/'state'), tmp_path/'state')
    assert service.migration_error
    assert not service.reload_templates().templates
    (service.engine.state_dir/'templates.json').write_bytes(b'broken')
    service = FileHubService(service.config, service.engine.state_dir)
    assert 'templates.json' in service.migration_error
    assert not service.reload_templates().templates


def test_generic_ignores_unused_legacy_sync_junction(tmp_path):
    import subprocess
    root=tmp_path/'old-root';root.mkdir();link=tmp_path/'old-link'
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(root)],capture_output=True)
    if result.returncode:pytest.skip('owned junction fixture unavailable')
    service=FileHubService(Config(sync_root=link),tmp_path/'state')
    assert service.migration_error and not service.reload_templates().templates


def profile_document():
    from filehub.templates import ProjectTemplate
    doc={'format':'filehub.rules','version':1,'id':'archive','name':'Archive','bindings':{'root':{'label':'Root'}},'variables':{},'rules':[]}
    reference=lambda relative:{'binding':'root','relative':relative}
    doc['compatibility']={'format':'filehub.archive.v1','root':reference(''),
        'projects':{'XYZ':reference('arbitrary folder')},'templates':[ProjectTemplate().to_document()],
        'assignments':{},'default_template':'default','general_test':reference('tests'),
        'policies':{'inbox_root':reference('incoming'),'categories':{'image':'images','video':'videos','other':'other'},
            'arrival_delay_seconds':86400,'expiry_delay_seconds':86400,'disposable_filenames':['.residual.cfg'],
            'sanitization_roots':[reference('')]}}
    return doc


def activate(service,doc,root,permissions):
    snapshot=install(service,doc,{'root':root})
    return service.catalog.set_compatibility(doc['id'],frozenset(permissions),expected_revision=snapshot.revision)


def test_complete_profile_arbitrary_projects_permissions_and_late_occupation(tmp_path):
    root=tmp_path/'archive-root'; (root/'arbitrary folder').mkdir(parents=True)
    source=tmp_path/'a.txt';source.write_bytes(b'a')
    service=FileHubService(Config(),tmp_path/'state')
    doc=profile_document();activate(service,doc,root,())
    assert service.preview([source],'XYZ参考').items[0].error
    snap=service.catalog.load()
    service.catalog.set_compatibility('archive',frozenset({'manual_archive'}),expected_revision=snap.revision)
    preview=service.preview([source],'XYZ参考')
    assert not preview.items[0].error
    target=preview.items[0].targets[0];target.parent.mkdir(parents=True);target.write_bytes(b'occupied')
    outcome=service.execute(preview)
    assert not outcome.ok and source.exists() and target.read_bytes()==b'occupied'
    target.write_bytes(source.read_bytes())
    # A newly occupied approved target is still forbidden even if dedup matches.
    outcome=service.execute(preview)
    assert not outcome.ok and source.exists()
    (root/'new-project').mkdir()
    assert service.preview([source],'NEW参考').items[0].error


def test_cleanup_is_separate_from_inbox_and_observation_clock(tmp_path):
    root=tmp_path/'archive-root';root.mkdir();watch=tmp_path/'watch';watch.mkdir()
    source=watch/'a.txt';source.write_bytes(b'a');junk=watch/'.residual.cfg';junk.write_bytes(b'junk')
    service=FileHubService(Config(watch_roots=(watch,),paused=False),tmp_path/'state')
    activate(service,profile_document(),root,{'unmatched_inbox'})
    scheduler=Scheduler(service)
    assert scheduler.tick(NOW)==[]
    result=scheduler.tick(NOW+timedelta(days=1))
    assert result and not source.exists() and junk.exists()
    # New cleanup authority starts a fresh readiness interval, never backdates.
    snapshot=service.catalog.load()
    service.catalog.set_compatibility('archive',frozenset({'cleanup'}),expected_revision=snapshot.revision)
    normal=watch/'leave.txt';normal.write_bytes(b'leave')
    from filehub.platform.windows import WindowsPlatform,RecycleOutcome
    bin_dir=tmp_path/'bin';bin_dir.mkdir()
    class OwnedRecycle(WindowsPlatform):
        def recycle(self,path):path.rename(bin_dir/path.name);return RecycleOutcome('recycled')
    service.engine.platform=OwnedRecycle()
    assert scheduler.tick(NOW+timedelta(days=2))==[]
    assert junk.exists() and normal.exists()
    assert scheduler.tick(NOW+timedelta(days=3))
    assert not junk.exists() and normal.exists()


def test_profile_and_metadata_changes_invalidate_preview_and_keep_rule_revision(tmp_path):
    root=tmp_path/'archive-root';root.mkdir();service=FileHubService(Config(),tmp_path/'state')
    doc=profile_document();doc['rules']=[{'id':'copy','name':'Copy','scope':[],
        'condition':{'field':'name','operator':'glob','value':'*'},'actions':[{'kind':'copy','options':{'destination':{'binding':'root','relative':'out'}}}]}]
    snapshot=activate(service,doc,root,{'manual_archive'})
    source=tmp_path/'a.txt';source.write_bytes(b'a');rid=snapshot.runtime_ids['archive']['copy']
    preview=service.automation.preview([source],rid);semantic=preview.plans[0].rule_revision
    doc['compatibility']['general_test']['relative']='different'
    snapshot=service.catalog.replace_package('archive',json.dumps(doc).encode(),expected_revision=snapshot.revision)
    assert snapshot.compiled.rules[0].revision==semantic
    assert not service.automation.execute(preview)[0].ok


def test_owning_profile_gate_for_disabled_manual_project_route(tmp_path):
    root=tmp_path/'root';root.mkdir();service=FileHubService(Config(),tmp_path/'state')
    doc=profile_document();doc['rules']=[{'id':'route','name':'Route','scope':[],
        'condition':{'field':'name','operator':'glob','value':'*'},'actions':[{'kind':'project_route','options':{'tag':'通用测试'}}]}]
    snapshot=activate(service,doc,root,{'manual_archive'})
    first_id=snapshot.runtime_ids['archive']['route']
    other=profile_document();other['id']='other'
    activate(service,other,root,{'manual_archive'})
    source=tmp_path/'a.txt';source.write_bytes(b'a')
    preview=service.automation.preview([source],first_id)
    assert preview.errors and not preview.plans[0].ok


def test_failed_generic_evaluation_never_falls_back(tmp_path,monkeypatch):
    root=tmp_path/'archive-root';root.mkdir();watch=tmp_path/'watch';watch.mkdir()
    source=watch/'a.txt';source.write_bytes(b'a')
    service=FileHubService(Config(watch_roots=(watch,),paused=False),tmp_path/'state')
    doc=profile_document();doc['compatibility']['policies']['arrival_delay_seconds']=0
    doc['rules']=[{'id':'generic','name':'Generic','scope':[],
        'condition':{'field':'name','operator':'glob','value':'*'},'actions':[{'kind':'copy','options':{'destination':{'binding':'root','relative':'out'}}}]}]
    snapshot=activate(service,doc,root,{'unmatched_inbox'})
    service.catalog.set_enabled('archive','generic',True,expected_revision=snapshot.revision)
    original=service.automation.facts;calls=[]
    def transient(*args,**kwargs):
        calls.append(True)
        if len(calls)==1:raise ValueError('transient facts failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(service.automation,'facts',transient)
    scheduler=Scheduler(service)
    assert scheduler.tick(NOW)==[] and source.exists()
    assert scheduler.last_errors and not (root/'incoming').exists()


def test_active_profile_policy_roots_cannot_overlap_watches(tmp_path):
    root=tmp_path/'archive-root';root.mkdir();watch=root/'watch';watch.mkdir()
    service=FileHubService(Config(watch_roots=(watch,),paused=False),tmp_path/'state')
    activate(service,profile_document(),root,{'cleanup'})
    with pytest.raises(ValueError,match='观察目录'):service.archive_context(permission=None)
    with pytest.raises(ValueError,match='观察目录'):Scheduler(service).tick(NOW)


def test_real_ledger_survives_metadata_enable_order_replace_and_restore(tmp_path):
    incoming=tmp_path/'in';incoming.mkdir();source=incoming/'a.txt';source.write_bytes(b'a')
    service=FileHubService(Config(),tmp_path/'state')
    doc=document();doc['rules'][0]['condition']={'field':'name','operator':'glob','value':'*'}
    doc['rules'][0]['actions']=[{'kind':'copy','options':{'destination':{'binding':'output','relative':''}}}]
    snapshot=install(service,doc,{'input':incoming,'output':tmp_path/'out'})
    rid=snapshot.runtime_ids['images']['convert'];original=snapshot.compiled.rules[0];bound_revision=snapshot.revision
    preview=service.automation.preview([source],rid)
    assert service.automation.execute(preview)[0].ok
    snapshot=service.catalog.set_enabled('images','convert',True,expected_revision=snapshot.revision)
    assert snapshot.compiled.rules[0].revision==original.revision
    snapshot=service.catalog.reorder(('images',),expected_revision=snapshot.revision)
    doc['name']='New package label';doc['rules'][0]['name']='New rule label'
    snapshot=service.catalog.replace_package('images',json.dumps(doc).encode(),expected_revision=snapshot.revision)
    assert snapshot.compiled.rules[0].revision==original.revision
    assert service.automation.preview([source],rid).errors
    backup=next(item for item in service.catalog.list_backups() if item.revision==bound_revision)
    snapshot=service.catalog.restore(backup.id,expected_revision=snapshot.revision)
    assert snapshot.compiled.rules[0].id==rid and snapshot.compiled.rules[0].revision==original.revision
    assert service.automation.preview([source],rid).errors
    assert len(service.automation.ledger.history())==1


def test_watched_and_manual_only_scope_members_are_independent(tmp_path):
    watched=tmp_path/'watched';watched.mkdir();manual=tmp_path/'manual';manual.mkdir()
    a=watched/'a.txt';a.write_bytes(b'a');b=manual/'b.txt';b.write_bytes(b'b')
    service=FileHubService(Config(watch_roots=(watched,),paused=False),tmp_path/'state')
    doc=document();doc['bindings']['manual']={'label':'Manual'}
    doc['rules'][0]['scope'].append({'binding':'manual','relative':''})
    doc['rules'][0]['condition']={'field':'name','operator':'glob','value':'*'}
    doc['rules'][0]['actions']=[{'kind':'copy','options':{'destination':{'binding':'output','relative':''}}}]
    snapshot=install(service,doc,{'input':watched,'manual':manual,'output':tmp_path/'out'})
    snapshot=service.catalog.set_enabled('images','convert',True,expected_revision=snapshot.revision)
    assert Scheduler(service).tick(NOW)[0].ok
    assert (tmp_path/'out/a.txt').exists() and not (tmp_path/'out/b.txt').exists()
    preview=service.automation.preview([b],snapshot.runtime_ids['images']['convert'])
    assert not preview.errors and preview.plans[0].ok
    assert service.config.watch_roots==(watched,)


def test_enabled_no_match_never_uses_old_flags(tmp_path):
    root=tmp_path/'old-root';root.mkdir();watch=tmp_path/'watch';watch.mkdir()
    source=watch/'leave.txt';source.write_bytes(b'a')
    service=FileHubService(Config(sync_root=root,watch_roots=(watch,),paused=False,global_jobs=True,sweep_days=0),tmp_path/'state')
    doc=document();doc['rules'][0]['scope']=[];doc['rules'][0]['actions']=[{'kind':'rename','options':{'pattern':'new{ext}'}}]
    snapshot=install(service,doc,{})
    service.catalog.set_enabled('images','convert',True,expected_revision=snapshot.revision)
    assert Scheduler(service).tick(NOW)==[] and source.exists()
    assert not list(root.iterdir())


def test_custom_inbox_archive_prunes_only_captured_empty_day(tmp_path):
    root=tmp_path/'archive-root';day=root/'incoming/other/261001';day.mkdir(parents=True)
    source=day/'a.txt';source.write_bytes(b'a')
    service=FileHubService(Config(),tmp_path/'state')
    activate(service,profile_document(),root,{'manual_archive'})
    result=service.execute(service.preview([source],'XYZ参考'))
    assert result.ok and not source.exists() and not day.exists()
    assert day.parent.exists() and (root/'arbitrary folder/_参考/a.txt').read_bytes()==b'a'
