import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import json
import time
import threading
from datetime import datetime, timezone
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.integration import SendQueue
from filehub.ui.app import create_demo, self_test, Runtime, bootstrap, ProgramUseMutex


def settle(app,runtime):
    end=time.monotonic()+10
    while runtime.window.coordinator.pending and time.monotonic()<end:
        app.processEvents();time.sleep(.01)
    app.processEvents();assert not runtime.window.coordinator.pending


def runtime(tmp_path,*,now=10):
    app=QApplication.instance() or QApplication([])
    bundle=bootstrap(tmp_path/'state')
    notices=[];exits=[]
    rt=Runtime(bundle,auto_timers=False,wall_clock=lambda:now,notifier=lambda *x:notices.append(x),exit_callback=lambda:exits.append(True))
    rt._test_notices=notices;rt._test_exits=exits;settle(app,rt)
    return app,rt


def cleanup(app,rt):
    if not rt.quitting:rt.request_quit()
    settle(app,rt)


def test_demo_png_is_valid_and_defaults_remain_unconfigured(tmp_path):
    service,store,paths=create_demo(tmp_path)
    image=QImage(str(paths[0]));assert not image.isNull() and image.width()==32
    assert service.config.paused and not service.config.global_jobs
    normal=bootstrap(tmp_path/'normal')
    assert normal.service.config==Config() and normal.service.config.watch_roots==()
    normal.lease.close()


def test_runtime_claim_is_not_acked_on_show_cancel_is_acked(tmp_path):
    app,rt=runtime(tmp_path);p=tmp_path/'中文 path.png';p.write_bytes(b'data')
    rt.queue.enqueue([p],now=9);rt.poll();settle(app,rt)
    assert rt.active_claim and rt.claim_dialog.isVisible()
    from filehub.ui.file_process_dialog import FileProcessDialog
    assert isinstance(rt.claim_dialog,FileProcessDialog) and not hasattr(rt.claim_dialog,'tag')
    assert SendQueue(rt.state_dir).claim(now=11) is None
    rt.renew_claim();settle(app,rt)
    assert SendQueue(rt.state_dir).claim(now=35) is None
    rt.claim_dialog.reject();settle(app,rt)
    assert not rt.active_claim and SendQueue(rt.state_dir).claim(now=50) is None and p.exists()
    rt.poll();settle(app,rt);assert not rt.claim_dialog
    cleanup(app,rt)


def test_open_dialog_crash_lease_redelivers_on_restart(tmp_path):
    app,rt=runtime(tmp_path);p=tmp_path/'a';p.write_bytes(b'a');rt.queue.enqueue([p],now=9)
    rt.poll();settle(app,rt);first=rt.active_claim
    # Model abrupt exit: no finished/cancel callback, no acknowledge/release.
    rt.poll_timer.stop();rt.lease_timer.stop();rt.tick_timer.stop()
    rt.claim_dialog.finished.disconnect();rt.claim_dialog.reject()
    rt.window.runtime_close_callback=None;rt.window.close()
    rt.window.coordinator.close();rt.lease.close();rt.marker.close()
    queue=SendQueue(rt.state_dir);assert queue.claim(now=20) is None
    retry=queue.claim(now=41);assert retry.paths==(p,) and retry.token!=first.token
    queue.ack(retry.token)


def test_demo_swap_coherent_ownership_and_disabled_integration(tmp_path):
    app,rt=runtime(tmp_path);old_state=rt.state_dir
    rt.window.start_demo();settle(app,rt)
    assert rt.service is rt.window.service and rt.scheduler.service is rt.service
    assert rt.state_dir==rt.service.engine.state_dir==rt.queue.state_dir==rt.lease.state_dir==rt.window.store.state_dir
    assert rt.state_dir!=old_state and '演示' in rt.window.windowTitle()
    assert not rt.window.autostart.isEnabled() and not rt.window.context_menu.isEnabled()
    assert rt.window.paths and not QImage(str(rt.window.paths[0])).isNull()
    SendQueue(old_state).enqueue([tmp_path/'ordinary'],now=10)
    assert rt.queue.claim(now=11) is None
    cleanup(app,rt)

def test_busy_quit_retains_marker_and_lease_until_worker_finishes(tmp_path):
    app,rt=runtime(tmp_path);entered=threading.Event();release=threading.Event()
    rt.window.coordinator.submit(lambda:(entered.set(),release.wait(5)),lambda _:None)
    assert entered.wait(2)
    rt.request_quit();assert rt.quitting and not rt.closed and rt.marker.handle and rt.lease.file
    release.set();settle(app,rt)
    assert rt.closed and rt.marker.handle is None and rt.lease.file is None and rt._test_exits==[True]


def test_claim_execute_ack_only_after_persisted_result(tmp_path):
    app,rt=runtime(tmp_path);rt.window.start_demo();settle(app,rt)
    p=rt.window.paths[0];rt.queue.enqueue([p],now=9);rt.poll();settle(app,rt)
    dialog=rt.claim_dialog;rt.window.transfer_archive(dialog);settle(app,rt);dialog=rt.claim_dialog;assert rt.active_claim and rt.queue.claim(now=11) is None
    dialog.tag.setText('DEMO020822');dialog.request_preview();settle(app,rt);assert dialog.preview
    dialog.execute();settle(app,rt)
    assert not rt.active_claim and rt.service.history()[0].ok and not p.exists()
    assert rt.queue.claim(now=50) is None
    cleanup(app,rt)


def test_claim_execute_exception_retains_unacked_request(tmp_path):
    app,rt=runtime(tmp_path);rt.window.start_demo();settle(app,rt)
    p=rt.window.paths[0];rt.queue.enqueue([p],now=9);rt.poll();settle(app,rt)
    dialog=rt.claim_dialog;rt.window.transfer_archive(dialog);settle(app,rt);dialog=rt.claim_dialog;dialog.tag.setText('DEMO020822');dialog.request_preview();settle(app,rt)
    def fail(preview):raise OSError('before persistent result')
    rt.service.execute=fail;dialog.execute();settle(app,rt)
    assert rt.active_claim and dialog.isVisible() and p.exists() and not rt.service.history()
    rt.request_quit();settle(app,rt)
    redelivered=SendQueue(rt.state_dir).claim(now=11);assert redelivered.paths==(p,)
    SendQueue(rt.state_dir).ack(redelivered.token)

def test_generic_claim_preview_and_durable_execution_ack(tmp_path):
    from rulefile_fixtures import install_rules
    from filehub.automation.models import Rule,Predicate,Action
    app,rt=runtime(tmp_path)
    rule=Rule(name='一般重命名',condition=Predicate('extension','equals','.txt'),actions=(Action('rename',{'pattern':'{stem}_done{ext}'}),))
    install_rules(rt.service,rule);rt.window.automation.load();settle(app,rt)
    source=tmp_path/'queued.txt';source.write_text('queue');rt.queue.enqueue([source],now=9);rt.poll();settle(app,rt)
    dialog=rt.claim_dialog;dialog.panel.rule_choice.setCurrentIndex(1);dialog.panel.request_preview();settle(app,rt)
    assert rt.active_claim and source.exists() and dialog.panel.execute_button.isEnabled()
    dialog.panel.execute();settle(app,rt)
    assert rt.active_claim is None and not source.exists() and source.with_name('queued_done.txt').exists()
    assert rt.queue.claim(now=50) is None and rt.service.history()[0].ok
    cleanup(app,rt)

def test_catalogue_change_during_critical_queue_commit_keeps_durable_ack(tmp_path):
    from rulefile_fixtures import install_rules
    from filehub.automation.models import Rule,Predicate,Action
    from filehub.platform.windows import WindowsPlatform
    app,rt=runtime(tmp_path);w=rt.window;entered=threading.Event();release=threading.Event()
    def wait_for(predicate):
        end=time.monotonic()+5
        while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.005)
        app.processEvents();assert predicate()
    rule=Rule(name='图片原地替换',condition=Predicate('extension','equals','.png'),actions=(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),))
    install_rules(rt.service,rule);w.automation.load();settle(app,rt)
    source=tmp_path/'critical.png';image=QImage(24,16,QImage.Format_RGBA8888);image.fill(0xffddbb66);assert image.save(str(source),'PNG')
    rt.queue.enqueue([source],now=9);rt.poll();settle(app,rt);dialog=rt.claim_dialog
    dialog.panel.rule_choice.setCurrentIndex(1);dialog.panel.request_preview();wait_for(lambda:dialog.panel._token is not None)
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    rt.service.engine.platform=Block();dialog.panel.execute();wait_for(entered.is_set)
    snapshot=w.automation.catalog_snapshot
    w.automation.mutate(lambda:rt.service.catalog.reorder(snapshot.order,expected_revision=snapshot.revision))
    assert rt.active_claim and not w.automation.accepting
    release.set();wait_for(lambda:rt.active_claim is None and not w.coordinator.pending and not w.automation.jobs)
    assert not source.exists() and source.with_suffix('.jpg').exists() and rt.queue.claim(now=50) is None
    assert rt.service.history()[0].ok and w.automation.accepting
    cleanup(app,rt)


def test_selftest_writes_json_without_stdout_and_actual_probe(tmp_path,monkeypatch):
    import filehub.ui.app as module
    monkeypatch.setattr(module.sys,'stdout',None)
    assert module.run(['--self-test','--state-dir',str(tmp_path/'selftest')])==0
    report=json.loads((tmp_path/'selftest'/'self-test.json').read_text(encoding='utf-8'))
    assert report['ok'] and all(report['checks'].values()) and report['probe']['width']==64
    assert Path(report['probe']['path']).is_relative_to(Path.cwd())
    assert Path(report['state_dir']).is_relative_to(tmp_path/'selftest')


def test_selftest_archives_two_distinct_real_1920_videos_and_undo(tmp_path):
    report=self_test(tmp_path/'selftest-1920')
    assert report['ok'] and report['checks']['video_1920_archive_naming']
    assert report['checks']['video_1920_distinct_sequence']
    assert report['checks']['video_1920_undo']
    videos=report['videos']
    assert [item['width'] for item in videos]==[1920,1920]
    assert [item['sequence'] for item in videos]==['01','02']
    assert all(item['target_name']==item['expected_name'] and item['target_name'].endswith('_1080p.mp4') for item in videos)
    assert all(Path(item['source']).is_file() and not Path(item['target']).exists() for item in videos)
    assert Path(videos[0]['source']).read_bytes()!=Path(videos[1]['source']).read_bytes()


def test_multiple_invocations_aggregate_one_dialog_and_plain_launch_reveals(tmp_path):
    app,rt=runtime(tmp_path);state=rt.state_dir
    paths=[tmp_path/f'素材 {n}.txt' for n in range(3)]
    for p in paths:p.write_bytes(b'a')
    for p in paths:
        secondary=bootstrap(state,send=[p]);assert not secondary.primary
    rt.wall_clock=lambda:time.time()+1;rt.poll();settle(app,rt)
    assert rt.claim_dialog.paths==tuple(paths)
    rt.claim_dialog.reject();settle(app,rt)
    rt.window.hide();secondary=bootstrap(state);assert not secondary.primary
    rt.poll();settle(app,rt);assert rt.window.isVisible()
    cleanup(app,rt)


def test_slow_demo_swap_never_claims_original_queue(tmp_path,monkeypatch):
    import filehub.ui.app as module
    app,rt=runtime(tmp_path);old=rt.state_dir;entered=threading.Event();release=threading.Event();original=module.create_demo
    def slow(base):entered.set();assert release.wait(3);return original(base)
    monkeypatch.setattr(module,'create_demo',slow)
    rt.window.start_demo()
    end=time.monotonic()+2
    while not entered.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert entered.is_set()
    path=tmp_path/'ordinary';SendQueue(old).enqueue([path],now=9)
    rt.poll();rt.schedule_tick()
    release.set();settle(app,rt)
    assert rt.state_dir!=old and rt.active_claim is None
    preserved=SendQueue(old).claim(now=11);assert preserved.paths==(path,)
    SendQueue(old).ack(preserved.token);cleanup(app,rt)

class Registry:
    def __init__(self):self.data={}
    def exists(self,key):return key in self.data
    def get(self,key,name):return self.data.get(key,{}).get(name)
    def set(self,key,name,value):self.data.setdefault(key,{})[name]=value
    def delete_value(self,key,name):self.data.get(key,{}).pop(name,None)
    def delete_key_if_empty(self,key):
        if not self.data.get(key) and not any(k.startswith(key+'\\') for k in self.data):self.data.pop(key,None)


def test_existing_owned_registration_read_before_first_save_preserved(tmp_path):
    from filehub.ui.app import IntegrationController
    from filehub.integration import install_context_menu, set_autostart
    app=QApplication.instance() or QApplication([]);reg=Registry();exe=tmp_path/'app.exe'
    install_context_menu(exe,registry=reg);set_autostart(exe,True,registry=reg)
    control=IntegrationController(exe,reg);before={key:dict(v) for key,v in reg.data.items()}
    bundle=bootstrap(tmp_path/'state');rt=Runtime(bundle,auto_timers=False,integration=control,notifier=lambda *x:None,exit_callback=lambda:None)
    assert not rt.window.integration_status_ready and not rt.window.autostart.isEnabled()
    settle(app,rt);assert rt.window.autostart.isChecked() and rt.window.context_menu.isChecked()
    rt.window.appearance.setCurrentIndex(1);rt.window.save_settings();settle(app,rt)
    assert reg.data==before and rt.service.config.theme=='light'
    cleanup(app,rt)


def test_partial_settings_save_keeps_tray_config_and_actual_registration(tmp_path):
    from filehub.ui.app import IntegrationController
    from filehub.integration import install_context_menu, RUN_KEY
    app=QApplication.instance() or QApplication([]);reg=Registry();exe=tmp_path/'app.exe'
    foreign='Software\\Classes\\*\\shell\\FileHub.Send';reg.set(foreign,'','foreign')
    bundle=bootstrap(tmp_path/'state');rt=Runtime(bundle,auto_timers=False,integration=IntegrationController(exe,reg),notifier=lambda *x:None,exit_callback=lambda:None);settle(app,rt)
    rt.window.paused.setChecked(False);rt.window.autostart.setChecked(True);rt.window.context_menu.setChecked(True)
    rt.window.save_settings();settle(app,rt)
    assert not rt.service.config.paused and '运行中' in rt.tray.toolTip()
    assert rt.window.autostart.isChecked() and not rt.window.context_menu.isChecked()
    assert reg.get(RUN_KEY,'FileHub')==f'"{exe}" --background' and reg.get(foreign,'')=='foreign'
    assert '设置已保存' in rt.window.status.text() and '集成未完成' in rt.window.status.text()
    cleanup(app,rt)


def test_arbitrary_cwd_runtime_service_archives_real_video(tmp_path,monkeypatch):
    from filehub.ui.app import runtime_service,resource_base
    root=tmp_path/'sync';(root/'1_工作'/'项目'/'261001_XYZ_测试').mkdir(parents=True)
    source=tmp_path/'video.mp4';source.write_bytes((resource_base()/'resources/selftest/tiny.mp4').read_bytes())
    changed=tmp_path/'different-cwd';changed.mkdir();monkeypatch.chdir(changed)
    service=runtime_service(Config(sync_root=root),tmp_path/'state')
    from rulefile_fixtures import install_archive
    install_archive(service)
    preview=service.preview([source],'XYZ020822');assert preview.items[0].video_width==64 and not preview.items[0].error
    result=service.execute(preview);assert result.ok and not source.exists()
    assert service.undo(result.batch_id).ok and source.exists()
    assert service.config.ffprobe_path=='resources/ffprobe/ffprobe.exe'


def test_startup_marker_already_exists_during_recovery_and_closes_after_quit(tmp_path,monkeypatch):
    import ctypes
    from ctypes import wintypes
    import filehub.ui.app as module
    from PySide6.QtCore import QTimer
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenMutexW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR];kernel.OpenMutexW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    original=module.bootstrap;seen=[]
    def boot(*args,**kwargs):
        handle=kernel.OpenMutexW(0x100000,False,ProgramUseMutex.name)
        assert handle;kernel.CloseHandle(handle);seen.append(threading.get_ident());return original(*args,**kwargs)
    monkeypatch.setattr(module,'bootstrap',boot)
    original_runtime=module.Runtime
    def make(*args,**kwargs):
        rt=original_runtime(*args,**kwargs);QTimer.singleShot(0,rt.request_quit);return rt
    monkeypatch.setattr(module,'Runtime',make)
    assert module.run(['--background','--state-dir',str(tmp_path/'state')])==0
    assert seen and seen[0]!=threading.get_ident()

def test_sync_drive_root_validation_rejects_before_any_runtime_scan(tmp_path):
    # Unused legacy sync_root is not generic validation authority.
    if True:
        # Pure validation only: a different-volume state path, never created.
        other_state=Path('C:/FileHub_validation_only') if tmp_path.anchor.upper()!='C:\\' else Path('D:/FileHub_validation_only')
        Config(sync_root=Path(tmp_path.anchor)).validate(other_state)

def test_knownfolder_proposals_are_not_watch_roots_and_only_seed_dialog(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    proposed={'desktop':tmp_path/'redirected desktop','downloads':tmp_path/'redirected downloads'}
    seen=[]
    def resolve(guid):return proposed['desktop'] if guid.startswith('B4BF') else proposed['downloads']
    bundle=bootstrap(tmp_path/'state',proposal_resolver=resolve)
    assert bundle.proposals==proposed and bundle.service.config.watch_roots==()
    app=QApplication.instance() or QApplication([]);rt=Runtime(bundle,auto_timers=False,notifier=lambda *x:None,exit_callback=lambda:None);settle(app,rt)
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda parent,title,start:seen.append(start) or '')
    rt.window.choose_watch('desktop');rt.window.choose_watch('downloads')
    assert seen==[str(proposed['desktop']),str(proposed['downloads'])] and rt.window.watch_list.count()==0
    assert not proposed['desktop'].exists() and not proposed['downloads'].exists()
    cleanup(app,rt)

@pytest.mark.parametrize('recycled',[True,False])
def test_background_duplicate_dialog_notifies_existing_copy_and_recycle_status(tmp_path,recycled):
    from filehub.platform.windows import WindowsPlatform,RecycleOutcome
    root=tmp_path/'sync';project=root/'1_工作'/'项目'/'261001_XYZ_测试';project.mkdir(parents=True)
    existing=project/'已有副本.png';existing.write_bytes(b'image')
    source=tmp_path/'素材.png';source.write_bytes(b'image');bin_dir=tmp_path/'fake-bin';bin_dir.mkdir()
    class FakeRecycle(WindowsPlatform):
        def recycle(self,path):
            if recycled:path.rename(bin_dir/path.name);return RecycleOutcome('recycled',message='fake recycled')
            return RecycleOutcome('failed',message='fake failed')
    state=tmp_path/'state';ConfigStore(state).save(Config(sync_root=root))
    bundle=bootstrap(state);bundle.service.engine.platform=FakeRecycle()
    from rulefile_fixtures import install_archive
    install_archive(bundle.service)
    app=QApplication.instance() or QApplication([]);notices=[]
    rt=Runtime(bundle,background=True,auto_timers=False,wall_clock=lambda:10,notifier=lambda *args:notices.append(args),exit_callback=lambda:None)
    settle(app,rt);assert not rt.window.isVisible()
    rt.queue.enqueue([source],now=9);rt.poll();settle(app,rt)
    dialog=rt.claim_dialog;assert dialog and dialog.isVisible()
    rt.window.transfer_archive(dialog);settle(app,rt);dialog=rt.claim_dialog
    dialog.tag.setText('XYZ020822');dialog.preview_button.click();settle(app,rt)
    dialog.execute_button.click();settle(app,rt)
    assert not rt.window.isVisible() and not dialog.isVisible()
    message='\n'.join(str(part) for notice in notices for part in notice)
    assert '重复' in message and '相同内容' in message and str(existing) in message
    assert ('来源已回收' if recycled else '来源回收未完成') in message
    assert existing.read_bytes()==b'image' and source.exists()!=recycled
    cleanup(app,rt)
