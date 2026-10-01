from pathlib import Path
import pytest
from filehub.models import Fingerprint, Operation
from filehub.operations import OperationEngine
from filehub.platform.windows import WindowsPlatform


def tree(tmp_path):
    p=tmp_path/'源 目录';(p/'空').mkdir(parents=True);(p/'nested').mkdir()
    (p/'nested'/'文件.txt').write_bytes(b'original')
    return p


def test_directory_move_and_restart_undo(tmp_path):
    s=tree(tmp_path);t=tmp_path/'目标';fp=Fingerprint.capture(s)
    e=OperationEngine(tmp_path/'state');r=e.execute([Operation('move',s,t,fp)],'tree')
    assert r.ok and not s.exists() and (t/'空').is_dir()
    assert (t/'nested'/'文件.txt').read_bytes()==b'original'
    assert OperationEngine(tmp_path/'state').undo(r.batch_id).ok
    assert (s/'nested'/'文件.txt').read_bytes()==b'original' and (s/'空').is_dir() and not t.exists()


def test_added_after_capture_survives(tmp_path):
    s=tree(tmp_path);fp=Fingerprint.capture(s);t=tmp_path/'target'
    class Race(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='tree_before_entry':(s/'新到.txt').write_bytes(b'new')
    r=OperationEngine(tmp_path/'state',Race()).execute([Operation('move',s,t,fp)],'tree')
    assert not r.ok and r.status=='partial'
    assert (s/'新到.txt').read_bytes()==b'new'
    assert (t/'nested'/'文件.txt').read_bytes()==b'original'
    assert r.items[0].state=='conflict'


def test_changed_entry_survives(tmp_path):
    s=tree(tmp_path);fp=Fingerprint.capture(s);t=tmp_path/'target'
    class Race(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='tree_before_entry':(s/'nested'/'文件.txt').write_bytes(b'changed')
    r=OperationEngine(tmp_path/'state',Race()).execute([Operation('move',s,t,fp)],'tree')
    assert not r.ok and (s/'nested'/'文件.txt').read_bytes()==b'changed'


def test_undo_altered_tree_refuses_all_children(tmp_path):
    s=tree(tmp_path);t=tmp_path/'target';e=OperationEngine(tmp_path/'state')
    r=e.execute([Operation('move',s,t,Fingerprint.capture(s))],'tree')
    (t/'new.txt').write_bytes(b'external')
    result=e.undo(r.batch_id)
    assert not result.ok and not s.exists()
    assert (t/'new.txt').read_bytes()==b'external' and (t/'nested'/'文件.txt').read_bytes()==b'original'


def test_directory_capture_rejects_junction(tmp_path):
    import subprocess
    s=tree(tmp_path);outside=tmp_path/'outside';outside.mkdir()
    subprocess.run(['cmd','/c','mklink','/J',str(s/'junction'),str(outside)],check=True,capture_output=True)
    with pytest.raises(ValueError):Fingerprint.capture(s)

def test_tree_preserves_file_times_and_named_streams(tmp_path):
    s=tree(tmp_path);f=s/'nested'/'文件.txt';Path(str(f)+':Zone.Identifier').write_bytes(b'zone')
    before=Fingerprint.capture(f);t=tmp_path/'target'
    r=OperationEngine(tmp_path/'state').execute([Operation('move',s,t,Fingerprint.capture(s))],'tree')
    assert r.ok
    after=Fingerprint.capture(t/'nested'/'文件.txt')
    assert before.same_content(after) and before.creation_ns==after.creation_ns and before.mtime_ns==after.mtime_ns


def test_tree_copy_fault_and_recovery_preserve_original(tmp_path):
    s=tree(tmp_path);t=tmp_path/'target'
    class Crash(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='copy_chunk':raise KeyboardInterrupt('crash')
    e=OperationEngine(tmp_path/'state',Crash())
    with pytest.raises(KeyboardInterrupt):e.execute([Operation('move',s,t,Fingerprint.capture(s))],'tree')
    recovered=OperationEngine(tmp_path/'state').recover()
    assert any(i.state=='conflict' for i in recovered)
    assert (s/'nested'/'文件.txt').read_bytes()==b'original'
    assert any(p.read_bytes()==b'original' for p in t.rglob('*.tmp'))


def test_tree_recycle_captured_only_new_file_survives(tmp_path):
    from filehub.platform.windows import RecycleOutcome
    s=tree(tmp_path);bin=tmp_path/'fake-bin';bin.mkdir()
    class Fake(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='tree_before_entry':(s/'fresh').write_bytes(b'new')
        def recycle(self,path):
            path.rename(bin/path.name);return RecycleOutcome('recycled')
    r=OperationEngine(tmp_path/'state',Fake()).execute([Operation('recycle',s,None,Fingerprint.capture(s))],'tree')
    assert not r.ok and (s/'fresh').read_bytes()==b'new'
    assert not list(bin.iterdir())
    assert (r.items[0].staging/'nested'/'文件.txt').read_bytes()==b'original'


def test_directory_service_never_probes_and_undo(tmp_path):
    from filehub.config import Config
    from filehub.service import FileHubService
    sync=tmp_path/'sync';project=sync/'1_工作'/'项目'/'260930_XYZ_测试';project.mkdir(parents=True)
    s=tree(tmp_path);renamed=s.with_name('folder.mp4');s.rename(renamed)
    def probe(p):raise AssertionError('folder must not probe')
    service=FileHubService(Config(sync_root=sync),tmp_path/'state',probe=probe)
    preview=service.preview([renamed],'XYZ020822')
    assert not preview.items[0].error and preview.items[0].targets[0].name=='folder.mp4'
    r=service.execute(preview);assert r.ok and not renamed.exists()
    assert service.undo(r.batch_id).ok and renamed.exists()

def test_tree_recycle_restart_undo_reports_child_manual_restore(tmp_path):
    from filehub.platform.windows import RecycleOutcome
    s=tree(tmp_path);bin=tmp_path/'bin';bin.mkdir()
    class Fake(WindowsPlatform):
        def recycle(self,path):path.rename(bin/path.name);return RecycleOutcome('recycled')
    e=OperationEngine(tmp_path/'state',Fake());r=e.execute([Operation('recycle',s,None,Fingerprint.capture(s))],'tree')
    assert r.ok and not s.exists()
    restored=OperationEngine(tmp_path/'state').undo(r.batch_id)
    assert restored.items[0].state=='manual_restore' and '整个目录' in restored.items[0].message
    assert all(i.parent_operation_id==restored.items[0].operation_id for i in restored.items[1:])
    assert all(i.state=='committed' for i in restored.items[1:]) and e.history()[0].items

def test_whole_tree_recycle_once_preserves_empty_dirs_and_failure(tmp_path):
    from filehub.platform.windows import RecycleOutcome
    s=tree(tmp_path);seen=[]
    class Fake(WindowsPlatform):
        def recycle(self,path):
            seen.append(path)
            assert (path/'空').is_dir() and (path/'nested'/'文件.txt').read_bytes()==b'original'
            return RecycleOutcome('failed',message='offline bin')
    e=OperationEngine(tmp_path/'state',Fake());r=e.execute([Operation('recycle',s,None,Fingerprint.capture(s))],'tree')
    assert not r.ok and len(seen)==1
    assert (r.items[0].staging/'nested'/'文件.txt').read_bytes()==b'original'
    assert e.history()[0].items[0].state=='conflict'

def test_external_identical_replacement_is_not_restore_lineage(tmp_path):
    s=tree(tmp_path);t=tmp_path/'target';e=OperationEngine(tmp_path/'state')
    r=e.execute([Operation('move',s,t,Fingerprint.capture(s))],'tree')
    p=t/'nested'/'文件.txt';old=Fingerprint.capture(p);p.unlink();p.write_bytes(b'original')
    from filehub.platform.metadata import set_times
    import ctypes
    from filehub.platform.windows import kernel
    from filehub.platform.metadata import winpath
    handle=kernel.CreateFileW(winpath(p),0x100,3,None,3,0x80,None)
    try:set_times(handle,old.creation_ns,old.mtime_ns)
    finally:kernel.CloseHandle(handle)
    assert not e.undo(r.batch_id).ok and not s.exists() and p.read_bytes()==b'original'

def test_manual_archive_prunes_only_empty_inbox_day(tmp_path):
    from filehub.config import Config
    from filehub.service import FileHubService
    sync=tmp_path/'sync';project=sync/'1_工作'/'项目'/'260930_XYZ_测试';project.mkdir(parents=True)
    day=sync/'0_收件箱'/'其他'/'260930';sub=day/'sub';sub.mkdir(parents=True);f=sub/'a.txt';f.write_bytes(b'a')
    svc=FileHubService(Config(sync_root=sync),tmp_path/'state')
    r=svc.execute(svc.preview([f],'XYZ参考'))
    assert r.ok and not day.exists() and day.parent.exists()


def test_manual_archive_day_sibling_arrival_survives(tmp_path):
    from filehub.config import Config
    from filehub.service import FileHubService
    sync=tmp_path/'sync';project=sync/'1_工作'/'项目'/'260930_XYZ_测试';project.mkdir(parents=True)
    day=sync/'0_收件箱'/'其他'/'260930';day.mkdir(parents=True);f=day/'a.txt';f.write_bytes(b'a')
    class Race(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_source_remove':(day/'new.txt').write_bytes(b'new')
    svc=FileHubService(Config(sync_root=sync),tmp_path/'state',platform=Race())
    assert svc.execute(svc.preview([f],'XYZ参考')).ok
    assert (day/'new.txt').read_bytes()==b'new'


def test_default_probe_uses_updated_config(tmp_path,monkeypatch):
    from dataclasses import replace
    from filehub.config import Config
    from filehub.service import FileHubService
    import filehub.service as module
    paths=[];monkeypatch.setattr(module,'probe_width',lambda p,exe:paths.append(exe) or 64)
    svc=FileHubService(Config(),tmp_path/'state');svc.config=replace(svc.config,ffprobe_path='new.exe')
    assert svc.probe(tmp_path/'a.mp4')==64 and paths==['new.exe']

def test_target_new_arrival_is_partial_and_preserved(tmp_path):
    s=tree(tmp_path);t=tmp_path/'target'
    class Race(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='copy_verified':(t/'external').write_bytes(b'external')
    r=OperationEngine(tmp_path/'state',Race()).execute([Operation('move',s,t,Fingerprint.capture(s))],'tree')
    assert not r.ok and r.status=='partial' and (t/'external').read_bytes()==b'external'

def test_directory_ads_rejected_and_empty_day_ads_preserved(tmp_path):
    from filehub.config import Config
    from filehub.service import FileHubService
    s=tree(tmp_path);Path(str(s)+':UserData').write_bytes(b'directory-data')
    with pytest.raises(ValueError):Fingerprint.capture(s)
    sync=tmp_path/'sync';project=sync/'1_工作'/'项目'/'260930_XYZ_测试';project.mkdir(parents=True)
    day=sync/'0_收件箱'/'其他'/'260930';day.mkdir(parents=True);p=day/'a.txt';p.write_bytes(b'a')
    Path(str(day)+':UserData').write_bytes(b'keep-dir-metadata')
    svc=FileHubService(Config(sync_root=sync),tmp_path/'state');assert svc.execute(svc.preview([p],'XYZ参考')).ok
    assert day.is_dir() and Path(str(day)+':UserData').read_bytes()==b'keep-dir-metadata'


def test_whole_tree_recycle_crash_recovery_unknown_keeps_manual_bin(tmp_path):
    s=tree(tmp_path);bin=tmp_path/'bin';bin.mkdir()
    class Crash(WindowsPlatform):
        def recycle(self,path):path.rename(bin/path.name);raise KeyboardInterrupt('after native delete')
    e=OperationEngine(tmp_path/'state',Crash())
    with pytest.raises(KeyboardInterrupt):e.execute([Operation('recycle',s,None,Fingerprint.capture(s))],'tree')
    restarted=OperationEngine(tmp_path/'state');recovered=restarted.recover()
    assert any(i.state=='recycle_unknown' for i in recovered)
    r=restarted.history()[0];assert r.items[0].staging is not None
    assert (next(bin.iterdir())/'nested'/'文件.txt').read_bytes()==b'original'
    after=restarted.undo(r.batch_id)
    assert after.items[0].state=='recycle_unknown' and not s.exists()


def test_child_junction_added_after_capture_survives_no_external_mutation(tmp_path):
    import subprocess
    s=tree(tmp_path);fp=Fingerprint.capture(s);external=tmp_path/'external';external.mkdir();outside=external/'outside';outside.write_bytes(b'external')
    class Race(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='tree_before_entry':subprocess.run(['cmd','/c','mklink','/J',str(s/'new-junction'),str(external)],check=True,capture_output=True)
    r=OperationEngine(tmp_path/'state',Race()).execute([Operation('move',s,tmp_path/'target',fp)],'tree')
    assert not r.ok and outside.read_bytes()==b'external' and (s/'new-junction').exists()

def test_ancestor_undo_never_rebinds_preexisting_external_replacement(tmp_path):
    from filehub.platform.metadata import set_times, winpath
    from filehub.platform.windows import kernel
    original=tmp_path/'input';original.write_bytes(b'a');folder=tmp_path/'folder';folder.mkdir();p=folder/'a'
    e=OperationEngine(tmp_path/'state');first=e.execute([Operation('move',original,p,Fingerprint.capture(original))],'first')
    expected=Fingerprint.capture(p);p.unlink();p.write_bytes(b'a')
    handle=kernel.CreateFileW(winpath(p),0x100,3,None,3,0x80,None)
    try:set_times(handle,expected.creation_ns,expected.mtime_ns)
    finally:kernel.CloseHandle(handle)
    ancestor=e.execute([Operation('move',folder,tmp_path/'moved',Fingerprint.capture(folder))],'ancestor')
    assert ancestor.ok and e.undo(ancestor.batch_id).ok
    assert not e.undo(first.batch_id).ok and p.read_bytes()==b'a' and not original.exists()

@pytest.mark.parametrize('external_child',[False,True])
def test_undo_recreated_original_root_blocks_every_child(tmp_path,external_child):
    s=tree(tmp_path);t=tmp_path/'target';e=OperationEngine(tmp_path/'state')
    r=e.execute([Operation('move',s,t,Fingerprint.capture(s))],'tree');assert r.ok
    s.mkdir()
    if external_child:(s/'external').write_bytes(b'keep')
    after=e.undo(r.batch_id)
    assert not after.ok and (t/'nested'/'文件.txt').read_bytes()==b'original'
    assert not (s/'nested').exists()
    if external_child:assert (s/'external').read_bytes()==b'keep'
    assert not e.undo(r.batch_id).ok and (t/'nested'/'文件.txt').read_bytes()==b'original'

@pytest.mark.parametrize('extra_source',[False,True])
def test_owned_inverse_root_restart_accepts_only_exact_restored_children(tmp_path,extra_source):
    s=tree(tmp_path);(s/'second.txt').write_bytes(b'second');t=tmp_path/'target'
    class Crash(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='undo_target_removed':raise KeyboardInterrupt('partial inverse')
    e=OperationEngine(tmp_path/'state',Crash());r=e.execute([Operation('move',s,t,Fingerprint.capture(s))],'tree');assert r.ok
    with pytest.raises(KeyboardInterrupt):e.undo(r.batch_id)
    restarted=OperationEngine(tmp_path/'state');restarted.recover()
    pending=[c for c in restarted.history()[0].items if c.parent_operation_id and c.state=='committed']
    assert pending and s.is_dir()
    if extra_source:(s/'external').write_bytes(b'keep')
    result=restarted.undo(r.batch_id)
    if extra_source:
        assert not result.ok and (s/'external').read_bytes()==b'keep'
        assert all(c.target.exists() for c in pending)
    else:
        assert result.ok and (s/'second.txt').read_bytes()==b'second'
        assert (s/'nested'/'文件.txt').read_bytes()==b'original' and not t.exists()

@pytest.mark.parametrize('kind',['recycle','move'])
def test_conflicted_tree_undo_blocks_children_when_original_root_reoccupied(tmp_path,kind):
    from filehub.platform.windows import RecycleOutcome
    s=tree(tmp_path);t=tmp_path/'target'
    class Partial(WindowsPlatform):
        def recycle(self,path):return RecycleOutcome('failed',message='isolated failure')
        def checkpoint(self,stage,item):
            if kind=='move' and stage=='copy_verified':(t/'external-target.txt').write_bytes(b'keep-target')
    engine=OperationEngine(tmp_path/'state',Partial())
    result=engine.execute([Operation(kind,s,t if kind=='move' else None,Fingerprint.capture(s))],'partial-tree')
    root=result.items[0];assert root.state=='conflict' and not s.exists()
    destination=t if kind=='move' else root.staging
    s.mkdir();external=s/'external.txt';external.write_bytes(b'keep-source')
    after=engine.undo(result.batch_id)
    assert external.read_bytes()==b'keep-source' and not (s/'nested').exists()
    assert (destination/'nested'/'文件.txt').read_bytes()==b'original'
    assert all(c.state=='committed' for c in after.items if c.parent_operation_id)
    assert str(destination) in after.items[0].message
    again=engine.undo(result.batch_id)
    assert all(c.state=='committed' for c in again.items if c.parent_operation_id)


@pytest.mark.parametrize('kind',['move','copy'])
@pytest.mark.parametrize('failed_tail',[False,True])
@pytest.mark.parametrize('empty_tree',[False,True])
def test_same_batch_directory_chain_restores_prior_subject_before_undo(tmp_path,kind,failed_tail,empty_tree):
    s=tmp_path/'源 目录'
    if empty_tree:(s/'空').mkdir(parents=True)
    else:s=tree(tmp_path)
    t=tmp_path/'intermediate';renamed=tmp_path/'renamed'
    engine=OperationEngine(tmp_path/'state')
    first=engine.execute([Operation(kind,s,t,Fingerprint.capture(s))],'chain');assert first.ok
    second=engine.execute([Operation('move',t,renamed,Fingerprint.capture(t))],'chain',batch_id=first.batch_id)
    assert second.ok and not t.exists()
    if failed_tail:
        occupied=tmp_path/'occupied';occupied.mkdir();(occupied/'external').write_bytes(b'keep')
        failed=engine.execute([Operation('move',renamed,occupied,Fingerprint.capture(renamed))],'chain',batch_id=first.batch_id)
        assert not failed.ok and failed.items[-1].state=='failed'
    result=OperationEngine(tmp_path/'state').undo(first.batch_id)
    committed=[i for i in result.items if i.state!='failed']
    assert committed and all(i.state=='undone' for i in committed)
    assert (s/'空').is_dir()
    if not empty_tree:assert (s/'nested'/'文件.txt').read_bytes()==b'original'
    assert not t.exists() and not renamed.exists()
    if failed_tail:assert (occupied/'external').read_bytes()==b'keep'
    else:assert result.ok


@pytest.mark.parametrize('change',['added','changed','identical_replacement'])
def test_directory_chain_external_change_blocks_whole_later_group(tmp_path,change):
    s=tree(tmp_path);(s/'second.txt').write_bytes(b'second')
    t=tmp_path/'intermediate';renamed=tmp_path/'renamed'
    engine=OperationEngine(tmp_path/'state')
    first=engine.execute([Operation('move',s,t,Fingerprint.capture(s))],'chain');assert first.ok
    second=engine.execute([Operation('move',t,renamed,Fingerprint.capture(t))],'chain',batch_id=first.batch_id)
    assert second.ok
    child=renamed/'nested'/'文件.txt'
    if change=='added':(renamed/'external.txt').write_bytes(b'external')
    elif change=='changed':child.write_bytes(b'changed')
    else:
        from filehub.platform.metadata import set_times, winpath
        from filehub.platform.windows import kernel
        old=Fingerprint.capture(child);held=child.with_name('held-original');child.rename(held)
        child.write_bytes(b'original')
        handle=kernel.CreateFileW(winpath(child),0x100,3,None,3,0x80,None)
        try:set_times(handle,old.creation_ns,old.mtime_ns)
        finally:kernel.CloseHandle(handle)
        held.unlink()
        assert Fingerprint.capture(child).file_id!=old.file_id
    before=Fingerprint.capture(renamed)
    after=engine.undo(first.batch_id)
    assert not after.ok and not s.exists() and not t.exists()
    assert Fingerprint.capture(renamed)==before
    assert all(i.state=='committed' for i in after.items if i.parent_operation_id)
    again=engine.undo(first.batch_id)
    assert not again.ok and Fingerprint.capture(renamed)==before


def test_directory_batch_with_noncontiguous_parent_children_undo(tmp_path):
    s=tree(tmp_path/'one');other=tree(tmp_path/'two')
    t=tmp_path/'first-target';u=tmp_path/'second-target'
    engine=OperationEngine(tmp_path/'state')
    result=engine.execute([Operation('move',s,t,Fingerprint.capture(s)),
                           Operation('move',other,u,Fingerprint.capture(other))],'two roots')
    assert result.ok
    assert all(i.parent_operation_id is None for i in result.items[:2])
    assert all(i.parent_operation_id is not None for i in result.items[2:])
    after=OperationEngine(tmp_path/'state').undo(result.batch_id)
    assert after.ok and not t.exists() and not u.exists()
    assert (s/'nested'/'文件.txt').read_bytes()==b'original'
    assert (other/'nested'/'文件.txt').read_bytes()==b'original'


def test_same_batch_directory_inverse_cannot_rebind_external_predecessor(tmp_path):
    from filehub.platform.metadata import set_times, winpath
    from filehub.platform.windows import kernel
    s=tree(tmp_path);t=tmp_path/'intermediate';renamed=tmp_path/'renamed'
    engine=OperationEngine(tmp_path/'state')
    first=engine.execute([Operation('move',s,t,Fingerprint.capture(s))],'chain');assert first.ok
    p=t/'nested'/'文件.txt';old=Fingerprint.capture(p);held=tmp_path/'held-original'
    p.rename(held);p.write_bytes(b'original')
    handle=kernel.CreateFileW(winpath(p),0x100,3,None,3,0x80,None)
    try:set_times(handle,old.creation_ns,old.mtime_ns)
    finally:kernel.CloseHandle(handle)
    held.unlink()
    assert Fingerprint.capture(p).file_id!=old.file_id
    second=engine.execute([Operation('move',t,renamed,Fingerprint.capture(t))],'chain',batch_id=first.batch_id)
    assert second.ok
    after=engine.undo(first.batch_id)
    assert not after.ok and after.items[0].state=='conflict' and not s.exists()
    assert p.read_bytes()==b'original' and not renamed.exists()
    assert all(c.state=='committed' for c in after.items if c.parent_operation_id==first.items[0].operation_id)
    with engine.journal.connection() as db:
        assert db.execute('SELECT 1 FROM tree_lineage WHERE previous_operation=?',(first.items[0].operation_id,)).fetchone() is None
