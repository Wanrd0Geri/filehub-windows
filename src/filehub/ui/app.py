"""Primary runtime, isolated demo and headless packaged acceptance entry."""
from dataclasses import dataclass, replace, field
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import ctypes
from ctypes import wintypes
import json
import os
import sqlite3
import struct
import sys
import zlib
from PySide6.QtCore import QObject, QTimer, Signal, QByteArray
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.models import checked_path
from filehub.scheduler import Scheduler, TICK_INTERVAL_SECONDS
from filehub.integration import (SendQueue, InstanceLease, parse_runtime_args, HKCURegistry,
    OWNER, MENU_KEYS, RUN_KEY, install_context_menu, remove_context_menu, set_autostart, known_folders)
from filehub.platform.windows import process_lock
from filehub.media import probe_width
from .main_window import MainWindow
from .theme import icon


def valid_png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+bytes([216,189,101,255])*32 for _ in range(32))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


def create_demo(base_dir):
    base=checked_path(base_dir)/'demo'/uuid4().hex
    sync=base/'同步空间';watch=base/'示例下载'
    (sync/'1_工作'/'项目'/'261001_DEMO_示例项目').mkdir(parents=True)
    watch.mkdir();source=watch/'镜头素材.png';source.write_bytes(valid_png())
    config=Config(sync_root=sync,watch_roots=(watch,),paused=True,global_jobs=False)
    store=ConfigStore(base/'state');store.save(config)
    (store.state_dir/'demo.marker').write_text('FileHub isolated demo',encoding='utf-8')
    return runtime_service(config,store.state_dir),store,(source,)


class ProgramUseMutex:
    name=r'Local\FileHub.Windows.v1.ProgramInUse'
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];self.kernel.CreateMutexW.restype=wintypes.HANDLE
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateMutexW(None,False,self.name)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


class IntegrationController:
    def __init__(self,exe,registry=None):self.exe=Path(exe);self.registry=registry if registry is not None else HKCURegistry()
    def status(self):
        r=self.registry;command=f'"{self.exe}" --send "%1"';startup=f'"{self.exe}" --background'
        return {'autostart':r.get(RUN_KEY,'FileHub')==startup,
                'context_menu':all(r.get(k,'FileHubOwner')==OWNER and r.get(k+'\\command','')==command for k in MENU_KEYS)}
    def apply(self,autostart,context_menu):
        current=self.status()
        if current['autostart']!=autostart:set_autostart(self.exe,autostart,registry=self.registry)
        if current['context_menu']!=context_menu:
            if context_menu:install_context_menu(self.exe,registry=self.registry)
            else:remove_context_menu(registry=self.registry)
        return self.status()


class OpenRequests:
    """Secondary plain launch asks the primary to reveal its existing window."""
    def __init__(self,state_dir):
        self.state_dir=checked_path(state_dir);self.state_dir.mkdir(parents=True,exist_ok=True)
        self.path=self.state_dir/'runtime.sqlite';self.lock=process_lock(self.state_dir)
    def put(self):
        with self.lock.acquire():
            db=sqlite3.connect(self.path)
            try:
                with db:db.execute('CREATE TABLE IF NOT EXISTS show_requests(id TEXT PRIMARY KEY)');db.execute('INSERT INTO show_requests VALUES(?)',(uuid4().hex,))
            finally:db.close()
    def take(self):
        with self.lock.acquire():
            db=sqlite3.connect(self.path)
            try:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS show_requests(id TEXT PRIMARY KEY)')
                    exists=db.execute('SELECT 1 FROM show_requests').fetchone() is not None
                    db.execute('DELETE FROM show_requests');return exists
            finally:db.close()

@dataclass
class Startup:
    service: FileHubService | None
    store: ConfigStore | None
    queue: SendQueue
    lease: InstanceLease
    demo_paths: tuple=()
    demo: bool=False
    primary: bool=True
    font_data: tuple=()
    proposals: dict=field(default_factory=dict)


def bootstrap(state_dir,*,demo=False,send=(),background=False,proposal_resolver=None):
    state=checked_path(state_dir)
    if demo:
        service,store,paths=create_demo(state);state=store.state_dir
    else:service=store=None;paths=()
    queue=SendQueue(state)
    if send:queue.enqueue(send)
    lease=InstanceLease(state)
    if not lease.try_acquire():
        if not send and not background:OpenRequests(state).put()
        return Startup(None,None,queue,lease,primary=False)
    try:
        if service is None:
            store=ConfigStore(state);service=runtime_service(store.load(),state)
        service.engine.recover()
        fonts=resource_base()/'resources'/'fonts'
        font_data=tuple(p.read_bytes() for p in fonts.glob('*.ttf')) if fonts.is_dir() else ()
        is_demo=demo or (state/'demo.marker').is_file()
        if is_demo:
            proposals={role:service.config.watch_roots[0] for role in ('desktop','downloads')} if service.config.watch_roots else {}
        else:
            try:proposals=known_folders(resolver=proposal_resolver)
            except OSError:proposals={}
        return Startup(service,store,queue,lease,paths,is_demo,font_data=font_data,proposals=proposals)
    except BaseException:lease.close();raise


class Runtime(QObject):
    def __init__(self,bundle,*,background=False,auto_timers=True,wall_clock=None,notifier=None,exit_callback=None,integration=None,marker=None):
        super().__init__()
        import time
        self.service=bundle.service;self.store=bundle.store;self.queue=bundle.queue;self.lease=bundle.lease;self.state_dir=self.queue.state_dir
        self.wall_clock=wall_clock or time.time;self.notifier=notifier;self.exit_callback=exit_callback or QApplication.instance().quit
        self.marker=marker or ProgramUseMutex();self.integration=integration;self.demo=bundle.demo
        self.scheduler=None;self.active_claim=None;self.claim_dialog=None;self.claim_handled=False
        self.generation=0;self.claim_queue=None
        self.poll_pending=False;self.renew_pending=False;self.tick_pending=False;self.quitting=False;self.closed=False
        self.window=MainWindow(self.service,self.store,demo_callback=self._demo_worker,
            integration_callback=integration.apply if integration and not self.demo else None,
            integration_status_callback=integration.status if integration and not self.demo else None)
        self.window.runtime_close_callback=self.close_to_tray
        self.window.known_folder_proposals=bundle.proposals
        self.window.is_demo=self.demo;self.window.load_config_controls()
        self.window.demo_activated.connect(self._demo_ready)
        self.window.service_reopen_callback=lambda old:runtime_service(old.config,old.engine.state_dir)
        self.window.service_rebound.connect(self._service_rebound)
        self.window.configuration_changed.connect(self.config_changed)
        self.window.coordinator.busy.connect(self.busy_changed)
        self.window.result_ready.connect(self.result_notification)
        self.window.manual_check_callback=self.schedule_tick
        self.window.automation_error.connect(lambda message:self.notify('FileHub · 图片自动整理未完成',message))
        self.tray=QSystemTrayIcon(icon('FileHub'),self);self.tray.setToolTip('FileHub · 自动整理已暂停')
        menu=QMenu();self.open_action=QAction('打开 FileHub',menu);self.open_action.triggered.connect(self.show_window);menu.addAction(self.open_action)
        self.pause_action=QAction('继续整理',menu);self.pause_action.triggered.connect(self.window.toggle_pause);menu.addAction(self.pause_action)
        menu.addSeparator();self.quit_action=QAction('退出 FileHub',menu);self.quit_action.triggered.connect(self.request_quit);menu.addAction(self.quit_action)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.show_window() if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self.poll_timer=QTimer(self);self.poll_timer.setInterval(200);self.poll_timer.timeout.connect(self.poll)
        self.lease_timer=QTimer(self);self.lease_timer.setInterval(5000);self.lease_timer.timeout.connect(self.renew_claim)
        self.tick_timer=QTimer(self);self.tick_timer.setInterval(TICK_INTERVAL_SECONDS*1000);self.tick_timer.timeout.connect(self.schedule_tick)
        service=self.service;generation=self.window.automation.state_generation
        self.window.coordinator.submit(lambda:Scheduler(service,automatic_completion=self.window.automation.completion_hook(service,generation)),self._scheduler_ready,self.window.show_error)
        self.window.refresh_integration()
        self.config_changed(self.service.config)
        if bundle.demo_paths:self.window.set_paths(bundle.demo_paths);self.window.tag.setText('DEMO020822')
        if auto_timers:self.poll_timer.start();self.lease_timer.start();self.tick_timer.start()
        if not background:self.window.show()
        elif self.service.config.sync_root is None:
            self.notify('FileHub 已在托盘运行','自动整理已暂停；选择观察文件夹、保存并启用规则后继续。普通规则无需同步空间。' if self.service.config.paused else '自动规则约每 10 分钟检查已选文件夹；送进项目和旧收件箱整理另外需要同步空间。')

    def _scheduler_ready(self,scheduler):self.scheduler=scheduler
    def notify(self,title,message):
        if self.notifier:self.notifier(title,message)
        else:self.tray.showMessage(title,message,QSystemTrayIcon.Information,5000)
    def result_notification(self,result):
        if result.items:
            details=self.window.duplicate_details(result)
            message=details[0] if details else f'“{result.label}”已记录；打开 FileHub 查看或撤销。'
            if len(details)>1:message+=f'\n另有 {len(details)-1} 项重复文件；完整结果请查看记录。'
            self.notify('FileHub · '+{'success':'已完成','partial':'部分完成','failed':'需要查看'}.get(result.status,'需要查看'),message)
    def show_window(self):self.window.showNormal();self.window.raise_();self.window.activateWindow()
    def close_to_tray(self):
        if self.closed:return True
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.request_quit();return False
        self.window.hide();self.notify('FileHub 仍在托盘运行','关闭窗口不会退出；请从托盘菜单选择“退出 FileHub”。');return False
    def config_changed(self,config):
        self.pause_action.setText('继续整理' if config.paused else '暂停整理')
        self.tray.setToolTip(('FileHub · 演示 · ' if self.demo else 'FileHub · ')+('自动整理已暂停' if config.paused else '自动整理运行中'))
    def busy_changed(self,busy):
        self.pause_action.setEnabled(not busy and not self.quitting)
        self.window.demo_button.setEnabled(not busy and not self.active_claim and not self.quitting and self.window.automation.accepting)
        if self.quitting and not busy:self._finish_quit()
    def poll(self):
        if self.quitting or self.poll_pending or self.active_claim or self.window.coordinator.pending:return
        self.poll_pending=True;queue=self.queue;state=self.state_dir;now=self.wall_clock();generation=self.generation
        self.window.coordinator.submit(lambda:(OpenRequests(state).take(),queue.claim(now=now)),lambda value:self._poll_done(value,queue,generation),self._poll_error)
    def _poll_error(self,message):self.poll_pending=False;self.window.show_error(message)
    def _poll_done(self,value,queue,generation):
        self.poll_pending=False;show,batch=value
        if generation!=self.generation:
            if batch:self.window.coordinator.submit(lambda:queue.release(batch.token),lambda _:None,self.window.show_error)
            return
        if show:self.show_window()
        if batch is None:return
        self.active_claim=batch;self.claim_handled=False;self.claim_queue=queue
        if self.quitting:return
        self.claim_dialog=self.window.open_archive_dialog(batch.paths)
        self.claim_dialog.execution_persisted.connect(self._claim_executed)
        self.claim_dialog.finished.connect(self._claim_finished)
        self.window.demo_button.setEnabled(False)
        if self.demo:self.claim_dialog.tag.setText('DEMO020822')
    def renew_claim(self):
        if not self.active_claim or self.renew_pending or self.quitting:return
        self.renew_pending=True;queue=self.claim_queue;token=self.active_claim.token;now=self.wall_clock()
        self.window.coordinator.submit(lambda:queue.renew(token,now=now,lease_seconds=30),lambda _:self._renew_done(),self._renew_error)
    def _renew_done(self):self.renew_pending=False
    def _renew_error(self,message):self.renew_pending=False;self.window.show_error('多选请求租约未续期：'+message)
    def _claim_executed(self,result):self.claim_handled=True
    def _claim_finished(self,code):
        if not self.active_claim:return
        batch=self.active_claim;queue=self.claim_queue
        # A user Cancel is explicit dismissal. Acceptance requires durable result.
        handled=self.claim_handled or code==0
        self.claim_dialog=None
        def finish():
            if handled:queue.ack(batch.token)
            else:queue.release(batch.token)
        def done(_):
            self.active_claim=None;self.claim_handled=False;self.claim_queue=None
            self.window.demo_button.setEnabled(not self.window.coordinator.pending and not self.quitting)
        self.window.coordinator.submit(finish,done,lambda error:(done(None),self.window.show_error(error)))
    def schedule_tick(self):
        if self.quitting or self.tick_pending or self.scheduler is None or self.window.coordinator.pending or not self.window.automation.accepting:return
        self.tick_pending=True;scheduler=self.scheduler;now=datetime.now().astimezone();generation=self.generation
        completion=self.window.automation.completion_hook(self.service,self.window.automation.state_generation)
        effective_generation=self.window.automation.rule_generation
        def tick():
            scheduler.automatic_completion=completion
            return scheduler.tick(now),scheduler.last_errors
        self.window.coordinator.submit(tick,lambda value:self._tick_done(value,generation,effective_generation),lambda message:self._tick_error(message) if generation==self.generation and effective_generation==self.window.automation.rule_generation else None)
    def _tick_error(self,message):self.tick_pending=False;self.window.show_error(message);self.notify('FileHub · 后台整理未完成',message)
    def _tick_done(self,value,generation=None,effective_generation=None):
        self.tick_pending=False;results,errors=value
        if generation is not None and generation!=self.generation:return
        if effective_generation is not None and effective_generation!=self.window.automation.rule_generation:
            self.window.refresh();return
        outcomes=[]
        for result in results:
            if hasattr(result,'items'):self.window.show_result(result)
            else:outcomes.append(result)
        if outcomes:self.window.show_run_outcomes(outcomes)
        if errors:self.window.show_error('；'.join(errors[:3]))
    def _demo_worker(self):
        service,store,paths=create_demo(self.state_dir);queue=SendQueue(store.state_dir);lease=InstanceLease(store.state_dir)
        if not lease.try_acquire():raise RuntimeError('演示状态已由另一进程使用')
        generation=self.window.automation.state_generation+1
        try:scheduler=Scheduler(service,automatic_completion=self.window.automation.completion_hook(service,generation))
        except BaseException:lease.close();service.close_conversions();raise
        old_lease=self.lease
        self.service=service;self.store=store;self.scheduler=scheduler;self.queue=queue;self.lease=lease;self.state_dir=store.state_dir;self.demo=True;self.generation+=1
        old_lease.close();return service,store,paths

    def _service_rebound(self,service):
        self.service=service;self.generation+=1
        generation=self.window.automation.state_generation
        self.scheduler=None
        self.window.coordinator.submit(lambda:Scheduler(service,automatic_completion=self.window.automation.completion_hook(service,generation)),self._scheduler_ready,self.window.show_error)
        self.config_changed(service.config)
    def _demo_ready(self):
        self.window.known_folder_proposals={role:self.service.config.watch_roots[0] for role in ('desktop','downloads')} if self.service.config.watch_roots else {}
        self.window.integration_callback=None;self.window.integration_status_callback=None
        self.window.autostart.setChecked(False);self.window.context_menu.setChecked(False)
        self.window.autostart.setEnabled(False);self.window.context_menu.setEnabled(False)
        self.config_changed(self.service.config)
    def request_quit(self):
        if self.closed or self.quitting:return
        self.quitting=True;self.poll_timer.stop();self.tick_timer.stop()
        self.window.setEnabled(False);self.quit_action.setEnabled(False)
        self.window.coordinator.begin_wait()
        self.window.automation.retire(self.window.coordinator.end_wait)
        if self.window.coordinator.pending:
            self.window.status.setText('正在完成当前操作，完成后安全退出。');return
        self._finish_quit()
    def _finish_quit(self):
        if self.closed or self.window.coordinator.pending or not self.window.automation.settled:return
        if self.active_claim:
            batch=self.active_claim;queue=self.claim_queue
            self.active_claim=None
            # Quit is not a user cancellation of an unhandled selection.
            self.window.coordinator.submit(lambda:queue.release(batch.token),lambda _:None,self.window.show_error)
            return
        self.closed=True;self.lease_timer.stop();self.window.coordinator.close()
        for dialog in tuple(self.window.dialogs):dialog.reject()
        self.window.runtime_close_callback=None;self.window._close_settled=True;self.window.close();self.tray.hide();self.lease.close();self.marker.close();self.exit_callback()


def resource_base():return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[3]))


def runtime_service(config,state):
    # Approved media.probe_width resolves bundled relative paths against
    # _MEIPASS already. Source runs use the licensed development bundle for
    # only the default setting; custom executable settings remain respected.
    service=FileHubService(config,state)
    def probe(path):
        executable=service.config.ffprobe_path
        if executable=='resources/ffprobe/ffprobe.exe' and not getattr(sys,'frozen',False):
            executable=resource_base()/'third_party'/'ffprobe'/'bin'/'ffprobe.exe'
        return probe_width(path,executable)
    service.probe=probe;return service


def self_test(state_parent,*,asset_root=None,probe_binary=None):
    if state_parent is None:raise ValueError('--self-test 必须显式提供 --state-dir 隔离目录')
    parent=checked_path(state_parent);parent.mkdir(parents=True,exist_ok=True)
    fixture=parent/('self-test-'+uuid4().hex);fixture.mkdir()
    report={'schema_version':1,'ok':False,'checks':{},'fixture_dir':str(fixture),'state_dir':None,'probe':{},'error':''}
    try:
        default=ConfigStore(fixture/'unconfigured-state').load()
        report['checks']['default_unconfigured_paused']=default==Config()
        service,store,paths=create_demo(fixture);report['state_dir']=str(store.state_dir)
        original=paths[0].read_bytes();report['checks']['valid_png']=original.startswith(b'\x89PNG\r\n\x1a\n')
        result=service.execute(service.preview(paths,'DEMO020822'))
        report['checks']['png_archive']=result.ok and not paths[0].exists()
        inverse=service.undo(result.batch_id)
        report['checks']['png_undo']=inverse.ok and paths[0].read_bytes()==original
        root=Path(asset_root) if asset_root else resource_base()
        binary=Path(probe_binary) if probe_binary else root/('resources/ffprobe/ffprobe.exe' if getattr(sys,'frozen',False) else 'third_party/ffprobe/bin/ffprobe.exe')
        sample=root/'resources'/'selftest'/'tiny.mp4'
        video=paths[0].with_name('探测样例.mp4');video.write_bytes(sample.read_bytes())
        width=probe_width(video,binary);report['probe']={'path':str(binary),'fixture':str(sample),'width':width}
        report['checks']['bundled_probe_width_64']=width==64
        report['checks']['paused_no_source_mutation']=Scheduler(service).tick(datetime.now().astimezone())==[] and video.exists()
        # Fixed bundled media exercise the real service/default probe resolver,
        # independently of the 64px probe smoke check and ordinary user state.
        project=service.config.sync_root/'1_工作'/'项目'/'261001_LYX_验收项目'
        project.mkdir()
        report['videos']=[];video_results=[];originals=[]
        for color,sequence in (('yellow','01'),('blue','02')):
            source=paths[0].with_name('真实1920-'+color+'.mp4')
            content=(root/'resources'/'selftest'/('tiny-1920-'+color+'.mp4')).read_bytes()
            source.write_bytes(content);originals.append(content)
            preview=service.preview([source],'LYX020822');item=preview.items[0]
            stamp=item.source_time.strftime('%Y%m%d')+('AM' if item.source_time.hour<12 else 'PM')
            expected='02_08_22_'+sequence+'_'+stamp+'_1080p.mp4'
            result=service.execute(preview);video_results.append(result)
            target=result.outcomes[0].targets[0] if result.outcomes and result.outcomes[0].targets else item.targets[0]
            report['videos'].append({'source':str(source),'target':str(target),
                'target_name':target.name,'expected_name':expected,'sequence':sequence,
                'width':item.video_width,'batch_id':result.batch_id})
        report['checks']['video_1920_distinct_content']=originals[0]!=originals[1]
        report['checks']['video_1920_archive_naming']=all(result.ok for result in video_results) and all(
            item['width']==1920 and item['target_name']==item['expected_name'] and
            Path(item['target']).is_relative_to(project/'3_制作'/'E02'/'S08') and
            Path(item['target']).is_file() and not Path(item['source']).exists() for item in report['videos'])
        report['checks']['video_1920_distinct_sequence']=len({item['target'] for item in report['videos']})==2
        inverse_ok=all(service.undo(result.batch_id).ok for result in reversed(video_results))
        report['checks']['video_1920_undo']=inverse_ok and all(
            Path(item['source']).read_bytes()==content and not Path(item['target']).exists()
            for item,content in zip(report['videos'],originals))
        report['ok']=all(report['checks'].values())
    except Exception as exc:report['error']=str(exc)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    (parent/'self-test.json').write_text(encoded,encoding='utf-8')
    return report


def run(argv=None):
    args=parse_runtime_args(argv)
    if args.self_test:
        try:report=self_test(args.state_dir)
        except Exception as exc:report={'schema_version':1,'ok':False,'checks':{},'error':str(exc)}
        if sys.stdout:sys.stdout.write(json.dumps(report,ensure_ascii=False)+'\n');sys.stdout.flush()
        return 0 if report['ok'] else 1
    state=args.state_dir or Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'FileHub'
    marker=ProgramUseMutex();bundle=rt=None
    try:
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix='filehub-bootstrap') as worker:
            bundle=worker.submit(bootstrap,state,demo=args.demo,send=args.send,background=args.background).result()
        if not bundle.primary:return 0
        app=QApplication.instance() or QApplication(sys.argv[:1]);app.setQuitOnLastWindowClosed(False)
        for data in bundle.font_data:QFontDatabase.addApplicationFontFromData(QByteArray(data))
        integration=IntegrationController(Path(sys.executable)) if getattr(sys,'frozen',False) and not bundle.demo else None
        rt=Runtime(bundle,background=args.background,integration=integration,marker=marker)
        app._filehub_runtime=rt
        return app.exec()
    finally:
        # Even an external event-loop exit must wait for file work before the
        # installer-visible marker and primary lease disappear.
        if rt and not rt.closed:
            rt.service.close_conversions().wait();rt.window.coordinator.close();rt.lease.close()
        elif bundle and bundle.primary and rt is None:bundle.lease.close()
        marker.close()
