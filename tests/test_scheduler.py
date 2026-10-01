from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import pytest
from filehub.config import Config
from filehub.service import FileHubService
from filehub.scheduler import Scheduler
from filehub.models import Fingerprint
from filehub.platform.windows import WindowsPlatform, RecycleOutcome

# Explicit simulated clock: sources born today are old relative to this future clock.
NOW=datetime.now(timezone.utc)+timedelta(days=40)

@pytest.fixture
def setup(tmp_path):
    root=tmp_path/'sync';root.mkdir();watch=tmp_path/'watch';watch.mkdir()
    service=FileHubService(Config(sync_root=root,watch_roots=(watch,),paused=False),tmp_path/'state')
    return service,watch,root


def test_first_seen_old_source_restart_full_grace(setup):
    s,w,root=setup;p=w/'图片.png';p.write_bytes(b'old');os.utime(p,(NOW.timestamp()-30*86400,)*2)
    assert Scheduler(s).tick(NOW)==[] and p.exists()
    assert Scheduler(s).tick(NOW+timedelta(days=2))==[] and p.exists()
    result=Scheduler(s).tick(NOW+timedelta(days=3))
    assert result and result[0].ok and not p.exists()
    target=root/'0_收件箱'/'图片'/(NOW+timedelta(days=3)).strftime('%y%m%d')/'图片.png'
    assert target.read_bytes()==b'old'


def test_paused_never_mutates_resume_resets_first_seen(setup):
    s,w,root=setup;p=w/'a.txt';p.write_bytes(b'a');q=Scheduler(s);q.tick(NOW)
    s.config=replace(s.config,paused=True);assert q.tick(NOW+timedelta(days=8))==[] and p.exists()
    p2=w/'unseen.txt';p2.write_bytes(b'new');s.config=replace(s.config,paused=False)
    assert q.tick(NOW+timedelta(days=10))==[] and p.exists() and p2.exists()
    assert q.tick(NOW+timedelta(days=12))==[]


def test_changes_with_restored_mtime_reset_idle(setup):
    s,w,_=setup;p=w/'a.txt';p.write_bytes(b'aaa');stamp=p.stat().st_mtime_ns
    q=Scheduler(s);q.tick(NOW);p.write_bytes(b'bbb');os.utime(p,ns=(stamp,stamp))
    assert q.tick(NOW+timedelta(days=3))==[] and p.exists()
    assert q.tick(NOW+timedelta(days=5))==[]
    assert q.tick(NOW+timedelta(days=6))[0].ok


def test_replacement_resets_arrival_and_disappearance_removes_observation(setup):
    s,w,_=setup;p=w/'a.txt';p.write_bytes(b'a');q=Scheduler(s);q.tick(NOW)
    p.unlink();q.tick(NOW+timedelta(days=2));p.write_bytes(b'a')
    assert q.tick(NOW+timedelta(days=4))==[]
    assert q.tick(NOW+timedelta(days=6))==[]


@pytest.mark.parametrize('name',['x.crdownload','x.part','x.partial','x.tmp','~$office.docx','.hidden'])
def test_partial_office_hidden_never_swept(setup,name):
    s,w,_=setup;p=w/name;p.write_bytes(b'x');q=Scheduler(s);q.tick(NOW)
    assert q.tick(NOW+timedelta(days=10))==[] and p.exists()


def test_only_explicit_top_level_watch_and_directories_other(setup):
    s,w,root=setup;outside=w.parent/'outside';outside.write_bytes(b'leave')
    folder=w/'movie.mp4';folder.mkdir();(folder/'child.png').write_bytes(b'c')
    q=Scheduler(s);q.tick(NOW);r=q.tick(NOW+timedelta(days=3))
    assert r and r[0].ok and outside.exists()
    assert (root/'0_收件箱'/'其他'/(NOW+timedelta(days=3)).strftime('%y%m%d')/'movie.mp4'/'child.png').exists()


def test_global_false_never_expires_or_sanitizes(setup):
    s,w,root=setup;day=root/'0_收件箱'/'其他'/'260101';day.mkdir(parents=True);(day/'old.txt').write_bytes(b'old')
    bad=root/'1_工作'/'项目'/'260101_XYZ_项目😀';bad.mkdir(parents=True)
    q=Scheduler(s);q.tick(NOW);assert q.tick(NOW+timedelta(days=10))==[]
    assert day.exists() and bad.exists()


def test_global_expiry_respects_first_seen_and_ongoing_day_changes(setup):
    s,w,root=setup;s.config=replace(s.config,global_jobs=True)
    day=root/'0_收件箱'/'图片'/'260101';day.mkdir(parents=True);p=day/'a.png';p.write_bytes(b'a')
    bin=w.parent/'fake-bin';bin.mkdir()
    class Fake(WindowsPlatform):
        def recycle(self,path):path.rename(bin/path.name);return RecycleOutcome('recycled')
    s.engine.platform=Fake();q=Scheduler(s)
    assert q.tick(NOW)==[]
    (day/'new.png').write_bytes(b'n');assert q.tick(NOW+timedelta(days=3))==[]
    r=q.tick(NOW+timedelta(days=6));assert r and r[0].ok and not day.exists() and day.parent.exists()
    assert len(list(bin.iterdir()))==1
    whole=next(bin.iterdir());assert whole.name.startswith('收件箱_图片_260101')
    assert sorted(p.read_bytes() for p in whole.iterdir())==[b'a',b'n']


def test_global_sanitizes_invalid_project_names_and_undo(setup):
    s,w,root=setup;s.config=replace(s.config,global_jobs=True)
    bad=root/'1_工作'/'项目'/'260101_XYZ_项目😀';bad.mkdir(parents=True);f=bad/'name😀.txt';f.write_bytes(b'data')
    q=Scheduler(s);r=q.tick(NOW)
    assert r and all(b.ok for b in r)
    good=bad.with_name('260101_XYZ_项目');assert (good/'name.txt').read_bytes()==b'data'
    for b in reversed(r):assert s.engine.undo(b.batch_id).ok
    assert f.read_bytes()==b'data'


def test_drive_root_watch_rejected(tmp_path):
    with pytest.raises(ValueError):Config(watch_roots=(Path(tmp_path.anchor),)).validate(tmp_path/'state')


def test_junk_recycles_only_after_stable_grace(setup):
    s,w,_=setup;p=w/'download.baiduyun.uploading.cfg';p.write_bytes(b'junk');bin=w.parent/'bin';bin.mkdir()
    class Fake(WindowsPlatform):
        def recycle(self,path):path.rename(bin/path.name);return RecycleOutcome('recycled')
    s.engine.platform=Fake();q=Scheduler(s);assert q.tick(NOW)==[]
    r=q.tick(NOW+timedelta(days=3));assert r and r[0].ok and not p.exists() and list(bin.iterdir())

def test_exact_hidden_baidu_residual_has_stable_grace(setup):
    s,w,_=setup;p=w/'.baiduyun.uploading.cfg';p.write_bytes(b'junk');bin=w.parent/'bin';bin.mkdir()
    class Fake(WindowsPlatform):
        def recycle(self,path):path.rename(bin/path.name);return RecycleOutcome('recycled')
    s.engine.platform=Fake();q=Scheduler(s);assert q.tick(NOW)==[]
    r=q.tick(NOW+timedelta(days=3));assert r and r[0].ok and not p.exists()

def test_locked_writer_is_skipped_until_new_inactive_grace(setup):
    import ctypes
    from filehub.platform.windows import kernel
    from filehub.platform.metadata import winpath
    s,w,_=setup;p=w/'a.txt';p.write_bytes(b'a');q=Scheduler(s);q.tick(NOW)
    handle=kernel.CreateFileW(winpath(p),0x40000000,1,None,3,0x80,None)
    assert handle!=ctypes.c_void_p(-1).value
    try:assert q.tick(NOW+timedelta(days=5))==[] and p.exists()
    finally:kernel.CloseHandle(handle)
    assert q.tick(NOW+timedelta(days=7))==[]
    assert q.tick(NOW+timedelta(days=8))[0].ok


def test_owned_staging_not_swept(setup):
    s,w,_=setup;p=w/'leftover.filehub-12345678';p.mkdir();(p/'a').write_bytes(b'a')
    q=Scheduler(s);q.tick(NOW);assert q.tick(NOW+timedelta(days=10))==[] and p.exists()


def test_nested_bad_directory_names_reverse_without_weakening_identity(setup):
    s,w,root=setup;s.config=replace(s.config,global_jobs=True)
    folder=root/'bad😀'/'child😀';folder.mkdir(parents=True);(folder/'a😀.txt').write_bytes(b'a')
    results=Scheduler(s).tick(NOW);assert len(results)==3 and all(r.ok for r in results)
    for result in reversed(results):assert s.engine.undo(result.batch_id).ok
    assert (folder/'a😀.txt').read_bytes()==b'a'

def test_exact_residual_reparse_skips_and_other_watch_continues(setup):
    import subprocess
    s,w,root=setup;external=w.parent/'external';external.mkdir();(external/'keep').write_bytes(b'keep')
    subprocess.run(['cmd','/c','mklink','/J',str(w/'.baiduyun.uploading.cfg'),str(external)],check=True,capture_output=True)
    p=w/'ordinary.txt';p.write_bytes(b'a');q=Scheduler(s)
    assert q.tick(NOW)==[]
    assert q.last_errors
    result=q.tick(NOW+timedelta(days=3))
    assert result and result[0].ok and (external/'keep').read_bytes()==b'keep'
