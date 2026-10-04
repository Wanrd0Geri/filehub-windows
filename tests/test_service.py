from datetime import datetime, timezone
from pathlib import Path
import pytest
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.platform.windows import WindowsPlatform, RecycleOutcome

TIME = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)

@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'sync'
    project = root / '1_工作' / '项目' / '260930_XYZ_测试'
    project.mkdir(parents=True)
    service = FileHubService(Config(sync_root=root), tmp_path/'state', probe=lambda p:1920, source_time=lambda p:TIME)
    def source(name='input.mp4', data=b'video'):
        p = tmp_path/name
        p.write_bytes(data)
        return p
    return service, project, source

def test_preview_execute_version_and_timestamp(setup):
    s,p,make = setup
    a = make()
    preview = s.preview([a], 'XYZ020822')
    assert preview.items[0].source_time == TIME
    assert preview.items[0].targets[0].name == '02_08_22_01_20260930PM_1080p.mp4'
    result = s.execute(preview)
    assert result.ok and result.created and not a.exists()
    b = make('second.mp4', b'different')
    result = s.execute(s.preview([b], 'XYZ020822'))
    assert result.outcomes[0].targets[0].name.startswith('02_08_22_02_')
    assert s.history()[0].created == result.created

def test_two_shot_copy_move_undo(setup):
    s,p,make=setup
    a=make()
    r=s.execute(s.preview([a],'XYZ020822+23'))
    assert r.ok and [i.kind for i in r.items] == ['copy','move']
    assert len(r.outcomes[0].targets)==2
    assert s.undo(r.batch_id).ok and a.exists()
    assert all(not t.exists() for t in r.outcomes[0].targets)

@pytest.mark.parametrize('tag',['XYZ020822+23','XYZ020822+23+24'])
def test_duplicate_merged_recycle_once(setup,tag):
    s,p,make=setup
    existing=p/'existing.mp4';existing.write_bytes(b'video')
    calls=[]
    class Fake(WindowsPlatform):
        def recycle(self,path):
            calls.append(path);path.unlink();return RecycleOutcome('recycled','test')
    s.engine.platform=Fake()
    a=make()
    r=s.execute(s.preview([a],tag))
    assert r.ok and len(calls)==1 and [i.kind for i in r.items]==['recycle']
    assert r.outcomes[0].duplicate == existing
    assert list(p.rglob('*.mp4'))==[existing]

def test_changed_and_collision(setup):
    s,p,make=setup
    a=make();pr=s.preview([a],'XYZ020822');a.write_bytes(b'changed')
    assert not s.execute(pr).ok and a.exists()
    pr=s.preview([a],'XYZ020822');t=pr.items[0].targets[0]
    t.parent.mkdir(parents=True);t.write_bytes(b'occupied')
    r=s.execute(pr)
    assert r.ok and r.outcomes[0].reallocated
    assert t.read_bytes()==b'occupied'

def test_invalid_partial_notifications_and_warning(setup):
    s,p,make=setup
    a=make();bad=s.preview([a],'unknown')
    assert bad.items[0].error and bad.items[0].notify
    assert not s.preview([a],'unknown').items[0].notify
    assert not s.execute(bad).ok and a.exists()
    assert not s.execute(s.preview([],'XYZ020822')).ok
    pr=s.preview([a,a.parent/'missing.mp4'],'XYZ020822+23+24')
    assert pr.items[0].warnings
    r=s.execute(pr)
    assert not r.ok and r.status=='partial' and len(r.outcomes)==2
    assert s.history()[0].outcomes[1].error

def test_probe_scope(setup):
    s,p,make=setup
    def fail(path): raise ValueError('视频探测失败')
    s.probe=fail;a=make()
    assert s.preview([a],'XYZ020822').items[0].error
    assert s.execute(s.preview([a],'XYZ剧本')).ok

def test_config_defaults_atomic_and_overlap(tmp_path):
    store=ConfigStore(tmp_path/'state')
    cfg=store.load()
    assert cfg.sync_root is None and cfg.paused and not cfg.global_jobs and not cfg.watch_roots
    assert cfg.theme=='dark' and cfg.sweep_days==cfg.inbox_days==3
    root=tmp_path/'sync';root.mkdir()
    cfg=Config(sync_root=root)
    store.save(cfg);assert store.load()==cfg
    with pytest.raises(ValueError):store.save(Config(sync_root=root,watch_roots=(root/'watch',)))
    with pytest.raises(ValueError):ConfigStore(root/'state').save(cfg)

def test_state_inside_source_rejected(setup):
    s,p,make=setup
    a=s.engine.state_dir/'input.mp4';a.write_bytes(b'a')
    assert s.preview([a],'XYZ020822').items[0].error

def test_dated_preview_respects_existing_names(setup):
    s,p,make=setup
    a=make();dest=p/'_测试'/'260930';dest.mkdir(parents=True)
    (dest/a.name).write_bytes(b'other')
    pr=s.preview([a],'XYZ测试')
    assert pr.items[0].targets[0].name=='input 2.mp4'


def test_named_versions_preview_and_execution_reallocate_same_series(setup):
    s,p,make=setup
    dest=p/'3_制作'/'PV';dest.mkdir(parents=True)
    unrelated=dest/'PV_决战打斗_260930-5_480p.mp4';unrelated.write_bytes(b'unrelated')
    previous=dest/'PV_打斗去雪_260929-3_480p.mp4';previous.write_bytes(b'previous')
    a=make(data=b'new video')
    pr=s.preview([a],'XYZPV打斗去雪')
    assert pr.items[0].targets[0].name=='PV_打斗去雪_260930-4_1080p.mp4'
    raced=dest/'PV_打斗去雪_260929-4_4K.mp4';raced.write_bytes(b'another version')
    r=s.execute(pr)
    assert r.ok and r.outcomes[0].reallocated
    assert r.outcomes[0].targets[0].name=='PV_打斗去雪_260930-5_1080p.mp4'
    assert r.outcomes[0].targets[0].read_bytes()==b'new video'
    assert previous.read_bytes()==b'previous' and raced.read_bytes()==b'another version'
    assert unrelated.read_bytes()==b'unrelated'


def test_named_versions_batch_reserves_independent_next_versions(setup):
    s,p,make=setup
    dest=p/'3_制作'/'PV';dest.mkdir(parents=True)
    (dest/'PV_决战打斗_260930-5_480p.mp4').write_bytes(b'unrelated')
    pr=s.preview([make('a.mp4',b'a'),make('b.mp4',b'b')],'XYZPV打斗去雪-1')
    assert [i.targets[0].name for i in pr.items]==[
        'PV_打斗去雪-1_260930-1_1080p.mp4',
        'PV_打斗去雪-1_260930-2_1080p.mp4']

def test_locked_duplicate_survivor_and_ads_ignored(setup):
    s,p,make=setup
    existing=p/'existing.mp4';existing.write_bytes(b'video')
    Path(str(existing)+':Zone.Identifier').write_bytes(b'zone')
    attempted=[]
    class Fake(WindowsPlatform):
        def recycle(self,path):
            with pytest.raises(OSError):existing.write_bytes(b'changed')
            with pytest.raises(OSError):existing.unlink()
            attempted.append(True);path.unlink();return RecycleOutcome('recycled','test')
    s.engine.platform=Fake();a=make()
    r=s.execute(s.preview([a],'XYZ020822'))
    assert r.ok and attempted and existing.read_bytes()==b'video'

def test_candidate_changes_before_guard_is_not_duplicate(setup):
    s,p,make=setup
    existing=p/'existing.mp4';existing.write_bytes(b'video')
    class Race(WindowsPlatform):
        def guard(self,path,*args,**kwargs):
            if path==existing:existing.write_bytes(b'other')
            return super().guard(path,*args,**kwargs)
    s.engine.platform=Race();a=make()
    r=s.execute(s.preview([a],'XYZ020822'))
    assert r.ok and not r.outcomes[0].duplicate and r.items[0].kind=='move'

def test_timestamp_not_recaptured_and_history_restart(setup):
    s,p,make=setup
    pr=s.preview([make()],'XYZ020822')
    s.source_time=lambda p: (_ for _ in ()).throw(AssertionError('recaptured'))
    r=s.execute(pr)
    fresh=FileHubService(s.config,s.engine.state_dir)
    assert fresh.history()[0]==r

def test_config_save_failure_visible_preserves_old(tmp_path,monkeypatch):
    import filehub.config as module
    store=ConfigStore(tmp_path/'state');store.save(Config())
    def fail(*args):raise OSError('disk failure')
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError):store.save(Config(theme='light'))
    assert store.load().theme=='dark'

def test_media_invocation_and_errors(tmp_path,monkeypatch):
    from filehub.media import probe_width
    import filehub.media as media
    import subprocess
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return subprocess.CompletedProcess(args,0,'{"streams":[{"width":1920}]}','')
    monkeypatch.setattr(media.subprocess,'run',run)
    assert probe_width(tmp_path/'a b.mp4','bin/ffprobe.exe',base_dir=tmp_path)==1920
    args,kwargs=calls[0]
    assert args[0]==str(tmp_path/'bin/ffprobe.exe') and kwargs['shell'] is False
    assert kwargs['timeout']==15 and kwargs['creationflags']==subprocess.CREATE_NO_WINDOW
    monkeypatch.setattr(media.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess([],0,'{"streams":[]}',''))
    with pytest.raises(ValueError,match='视频探测失败'):probe_width(tmp_path/'bad.mp4')

def test_same_content_batch_one_move_one_recycle(setup):
    s,p,make=setup;calls=[]
    class Fake(WindowsPlatform):
        def recycle(self,path):calls.append(path);path.unlink();return RecycleOutcome('recycled','test')
    s.engine.platform=Fake();a=make();b=make('b.mp4')
    r=s.execute(s.preview([a,b],'XYZ020822'))
    assert r.ok and [i.kind for i in r.items]==['move','recycle'] and len(calls)==1
    assert len(s.history())==1

def test_selected_project_sources_not_held_as_survivors(setup):
    s,p,make=setup
    a=p/'a.mp4';b=p/'b.mp4';a.write_bytes(b'video');b.write_bytes(b'video')
    class Fake(WindowsPlatform):
        def recycle(self,path):path.unlink();return RecycleOutcome('recycled','test')
    s.engine.platform=Fake()
    r=s.execute(s.preview([a,b],'XYZ020822'))
    assert r.ok and [i.kind for i in r.items]==['move','recycle']

def test_selection_restart_undo_one_batch(setup):
    s,p,make=setup
    class Fake(WindowsPlatform):
        def recycle(self,path):path.unlink();return RecycleOutcome('recycled','test')
    s.engine.platform=Fake()
    a,b,c=make(),make('b.mp4',b'other'),make('c.mp4')
    r=s.execute(s.preview([a,b,c],'XYZ020822'))
    fresh=FileHubService(s.config,s.engine.state_dir)
    history=fresh.history()
    assert len(history)==1 and history[0]==r and len(r.outcomes)==3
    undone=fresh.undo(r.batch_id)
    assert a.read_bytes()==b'video' and b.read_bytes()==b'other' and not c.exists()
    assert [i.state for i in undone.items]==['undone','undone','manual_restore']

def test_failed_first_move_does_not_recycle_later(setup):
    s,p,make=setup
    a,b=make(),make('b.mp4')
    class FailFirst(WindowsPlatform):
        def checkpoint(self,stage,item):
            if item.source==a and stage=='before_target_create':raise OSError('injected failure')
    s.engine.platform=FailFirst()
    r=s.execute(s.preview([a,b],'XYZ020822'))
    assert not r.ok and r.status=='partial' and a.exists() and not b.exists()
    assert [i.kind for i in r.items]==['move','move']
    assert r.outcomes[0].error and not r.outcomes[1].error

def test_hidden_duplicate_and_source_hardlink_skipped(setup):
    import os
    s,p,make=setup;a=make()
    hidden=p/'.hidden';hidden.mkdir();(hidden/'same.mp4').write_bytes(b'video')
    os.link(a,p/'alias.mp4')
    r=s.execute(s.preview([a],'XYZ020822'))
    assert r.ok and r.items[0].kind=='move' and not r.outcomes[0].duplicate

def test_standard_name_remark_and_notification_retry(setup):
    s,p,make=setup
    a=make('E02S08_C022_旧备注_260929-3.png')
    pr=s.preview([a],'XYZ020822')
    assert pr.items[0].targets[0].name=='E02S08_C022_旧备注_260929-3.png'
    assert s.execute(pr).ok
    b=make();assert s.preview([b],'bad').items[0].notify
    assert not s.preview([b],'bad').items[0].notify
    b.write_bytes(b'corrected');assert s.preview([b],'bad').items[0].notify
    assert not s.preview([b],'XYZ020822').items[0].error

def test_engine_append_no_reexecute_and_unknown_batch(setup):
    from filehub.models import Operation, Fingerprint
    s,p,make=setup;a=make('a.txt');b=make('b.txt',b'other')
    e=s.engine
    first=e.execute([Operation('move',a,p/'a.txt',Fingerprint.capture(a))],'first')
    second=e.execute([Operation('move',b,p/'b.txt',Fingerprint.capture(b))],'ignored',batch_id=first.batch_id)
    assert second.ok and second.created==first.created and second.label=='first'
    assert len(second.items)==2 and e.undo(second.batch_id).ok
    with pytest.raises(KeyError):e.execute([],'x',batch_id='missing')

def test_real_tiny_video_probe(tmp_path):
    import subprocess
    from filehub.media import probe_width
    ffmpeg=Path('C:/ffmpeg7.1.1/bin/ffmpeg.exe')
    if not ffmpeg.exists():pytest.skip('explicit local dev binary unavailable')
    video=tmp_path/'tiny.mp4'
    subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','color=c=black:s=64x48:d=0.1',
                    '-c:v','mpeg4',str(video)],check=True,capture_output=True,timeout=15,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    assert probe_width(video,ffmpeg.with_name('ffprobe.exe'))==64
    invalid=tmp_path/'invalid.mp4';invalid.write_bytes(b'not video')
    with pytest.raises(ValueError,match='视频探测失败'):probe_width(invalid,ffmpeg.with_name('ffprobe.exe'))

@pytest.mark.parametrize('response',['{"streams":null}','[]'])
def test_probe_malformed_shape_chinese_error(tmp_path,monkeypatch,response):
    import subprocess
    import filehub.media as media
    monkeypatch.setattr(media.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess([],0,response,''))
    with pytest.raises(ValueError,match='视频探测失败'):media.probe_width(tmp_path/'bad.mp4')

@pytest.mark.parametrize('field',['paused','global_jobs'])
def test_config_boolean_type_rejected(tmp_path,field):
    with pytest.raises(ValueError):ConfigStore(tmp_path/'state').save(Config(**{field:'false'}))

def test_documented_config_schema_and_alias(tmp_path):
    import json
    store=ConfigStore(tmp_path/'state');store.save(Config(ffprobe_path='dev/probe.exe'))
    data=json.loads(store.path.read_text(encoding='utf-8'))
    assert data['watch']==[] and data['ffprobe']=='dev/probe.exe' and 'watch_roots' not in data
    store.path.write_text(json.dumps({'watch':[],'ffprobe':'probe.exe'}),encoding='utf-8')
    assert store.load().ffprobe_path=='probe.exe'
    store.path.write_text(json.dumps({'watch_roots':[],'ffprobe_path':'old.exe'}),encoding='utf-8')
    assert store.load().ffprobe_path=='old.exe'

@pytest.mark.parametrize('data',[{'watch':[],'watch_roots':['other']},{'ffprobe':'a','ffprobe_path':'b'}])
def test_config_alias_conflict_visible(tmp_path,data):
    import json
    store=ConfigStore(tmp_path/'state');store.state_dir.mkdir()
    store.path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='冲突'):store.load()
