import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from dataclasses import replace
from threading import Event, get_ident
import json
import pytest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow
from filehub.automation.models import Rule, RuleSet, Predicate, Action, MAX_DOCUMENT_BYTES
from filehub.conversion.models import ConversionSpec


def wait(app, predicate):
    end = time.monotonic() + 10
    while not predicate() and time.monotonic() < end:
        app.processEvents(); time.sleep(.005)
    app.processEvents()
    assert predicate()


def settle(app, window):
    wait(app, lambda: not window.coordinator.pending and not window.automation.jobs)


def png(path):
    image=QImage(24,16,QImage.Format_RGBA8888);image.fill(QColor('#8844FF'))
    assert image.save(str(path),'PNG')


@pytest.fixture
def ui(tmp_path):
    app=QApplication.instance() or QApplication([])
    watch=tmp_path/'观察';watch.mkdir()
    sync=tmp_path/'同步';(sync/'1_工作/项目/261001_XYZ_测试').mkdir(parents=True)
    service=FileHubService(Config(watch_roots=(watch,),sync_root=sync),tmp_path/'state')
    rule=Rule(name='素材重命名',condition=Predicate('name','contains','素材'),actions=(Action('rename',{'pattern':'{stem}_已整理{ext}'}),))
    service.rules.save(RuleSet((rule,)))
    window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    yield app,window,service,watch
    window.automation.retire(lambda:None)
    wait(app,lambda:window.automation.settled);settle(app,window)
    window._close_settled=True;window.close();window.coordinator.close()


def image_preview(app,window,path,fmt='jpeg'):
    page=window.conversion_page;page.set_paths([path]);page.fields.set_value(ConversionSpec(output_format=fmt),mode='replace')
    page._preview();settle(app,window)
    assert page._token is not None
    return page._token


def test_new_navigation_and_worker_loaded_forms(tmp_path):
    app = QApplication.instance() or QApplication([])
    service = FileHubService(Config(), tmp_path/'state')
    window = MainWindow(service, ConfigStore(tmp_path/'state'))
    wait(app, lambda: not window.coordinator.pending)
    assert [button.text() for button in window.nav_buttons] == ['整理', '收件箱', '记录', '设置', '自动规则', '图片转换']
    assert window.rules_tabs.widget(0) is window.rules_page
    assert window.rules_tabs.widget(1) is window.templates_page
    assert window.automation.executor is service._conversions
    assert window.automation.rules_revision == service.rules.load().revision
    window.automation.retire(lambda: None)
    wait(app, lambda: window.automation.settled)
    window.coordinator.close()


def test_rule_store_ack_crud_preview_does_not_execute_then_explicit_execute(ui):
    app,w,s,watch=ui;p=watch/'素材.txt';p.write_text('keep',encoding='utf-8')
    page=w.rules_page;page.name_edit.setText('长中文规则名称与明确动作')
    assert page.dirty
    page.save_button.click();settle(app,w)
    assert not page.dirty and s.rules.load().rules[0].name=='长中文规则名称与明确动作'
    page.set_sample_paths([p]);page.preview_button.click();settle(app,w)
    assert p.exists() and not (watch/'素材_已整理.txt').exists() and page.execute_button.isEnabled()
    assert '重命名' in page.preview_text.toPlainText()
    page.execute_button.click();settle(app,w)
    assert not p.exists() and (watch/'素材_已整理.txt').exists() and w.history_list.count()==1
    assert not page.execute_button.isEnabled()
    page.duplicate_rule();assert not page.value().rules[-1].enabled
    page.save_button.click();settle(app,w)
    page.move_rule(-1);page.delete_rule();page.save_button.click();settle(app,w)
    assert len(s.rules.load().rules)==1


def test_save_failure_and_external_revision_keep_dirty_draft(ui,monkeypatch):
    app,w,s,_=ui;page=w.rules_page
    original=s.rules.save
    def fail(*args,**kwargs):raise OSError('保存磁盘已满')
    monkeypatch.setattr(s.rules,'save',fail)
    page.name_edit.setText('保留这个草稿');page.save_button.click();settle(app,w)
    assert page.dirty and page.name_edit.text()=='保留这个草稿' and '磁盘' in page.error_label.text()
    monkeypatch.setattr(s.rules,'save',original)
    external=replace(s.rules.load().rules[0],name='外部版本');s.rules.save(RuleSet((external,)))
    page.save_button.click();settle(app,w)
    assert page.dirty and page.name_edit.text()=='保留这个草稿' and '变化' in page.error_label.text()
    assert s.rules.load().rules[0].name=='外部版本'


def test_import_export_bounded_duplicate_keys_and_disabled_ids(ui,tmp_path):
    app,w,s,_=ui;original=s.rules.load().rules[0]
    incoming=tmp_path/'导入.json';incoming.write_text(json.dumps(RuleSet((replace(original,enabled=True),)).to_document()),encoding='utf-8')
    w.automation.import_rules(str(incoming));settle(app,w)
    imported=s.rules.load().rules[-1];assert not imported.enabled and imported.id!=original.id
    exported=tmp_path/'导出.json';w.automation.export_rules(str(exported));settle(app,w)
    assert len(json.loads(exported.read_text(encoding='utf-8'))['rules'])==2
    incoming.write_text('{"schema_version":1,"schema_version":1,"rules":[]}',encoding='utf-8')
    w.automation.import_rules(str(incoming));settle(app,w)
    assert '重复' in w.rules_page.error_label.text() and len(s.rules.load().rules)==2
    incoming.write_bytes(b' '*(MAX_DOCUMENT_BYTES+1));w.automation.import_rules(str(incoming));settle(app,w)
    assert '2 MB' in w.rules_page.error_label.text() and len(s.rules.load().rules)==2


def test_template_store_ack_and_dirty_failure(ui,monkeypatch):
    app,w,s,_=ui;page=w.templates_page;page.copy_template('角色项目模板');page.name_edit.setText('明确保存模板')
    page.save_button.click();settle(app,w)
    assert not page.dirty and page.selected_id in s.reload_templates().templates
    revision=w.automation.template_revision
    monkeypatch.setattr(s.templates,'save',lambda *a,**k:(_ for _ in ()).throw(OSError('模板无法写入')))
    page.name_edit.setText('不能丢弃');page.save_button.click();settle(app,w)
    assert page.dirty and page.name_edit.text()=='不能丢弃' and w.automation.template_revision==revision


def test_real_image_replace_final_progress_history_backup_and_undo(ui):
    app,w,s,watch=ui;p=watch/'原图.png';png(p)
    token=image_preview(app,w,p)
    assert token.preview.items[0].target==watch/'原图.jpg' and p.exists()
    page=w.conversion_page;page.execute_button.click();settle(app,w)
    assert page.results.item(0,2).text()=='已完成' and not p.exists() and (watch/'原图.jpg').exists()
    w.history_list.setCurrentRow(0);w.show_history_details(0)
    assert '图片转换/替换' in w.history_details.toPlainText() and '原图备份' in w.history_details.toPlainText()
    w.undo_button.click();settle(app,w)
    assert p.exists() and not (watch/'原图.jpg').exists()


def test_image_preview_decode_is_independent_archive_and_direct_cancel(ui,monkeypatch):
    import filehub.automation.executor as module
    app,w,s,watch=ui;p=watch/'image.png';png(p);archive=watch/'普通素材.txt';archive.write_text('archive')
    entered,release=Event(),Event();original=module.inspect;threads=[]
    def slow(*args):
        threads.append(get_ident());entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(module,'inspect',slow)
    page=w.conversion_page;page.set_paths([p]);page.fields.set_value(ConversionSpec(),mode='replace');page._preview()
    wait(app,entered.is_set)
    w.set_paths([archive]);w.tag.setText('XYZ020822');w.request_preview()
    wait(app,lambda:not w.coordinator.pending)
    assert w.preview is not None and w.execute_button.isEnabled() and threads[0]!=get_ident()
    w.execute();wait(app,lambda:not w.coordinator.pending)
    assert not archive.exists() and page._busy
    page.cancel_button.click();assert w.automation.jobs['images']['cancel'].is_set() and page.cancel_pending
    release.set();settle(app,w)
    assert p.exists() and not (watch/'image.jpg').exists() and page._token is None


def test_obsolete_image_preview_canceled_and_stale_callback_not_installed(ui,monkeypatch):
    import filehub.automation.executor as module
    app,w,_,watch=ui;p=watch/'old.png';png(p);new=watch/'new.png';png(new)
    entered,release=Event(),Event();original=module.inspect
    def slow(*args):entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(module,'inspect',slow)
    page=w.conversion_page;page.set_paths([p]);page.fields.set_value(ConversionSpec(),mode='replace');page._preview();wait(app,entered.is_set)
    event=w.automation.jobs['images']['cancel'];page.set_paths([new]);assert event.is_set()
    release.set();settle(app,w)
    assert page._token is None and page.results.rowCount()==0 and not page.error_label.text()


def test_encoding_cancel_pending_ordinary_archive_stays_responsive(ui,monkeypatch):
    import filehub.automation.executor as module
    app,w,_,watch=ui;p=watch/'编码.png';png(p);image_preview(app,w,p)
    entered,release=Event(),Event();original=module.generate_owned
    def slow(*args,**kwargs):entered.set();assert release.wait(5);return original(*args,**kwargs)
    monkeypatch.setattr(module,'generate_owned',slow)
    page=w.conversion_page;page.execute_button.click();wait(app,entered.is_set)
    assert w.preview_button.isEnabled()
    page.cancel_button.click();assert page.cancel_pending and w.automation.jobs['images']['cancel'].is_set()
    release.set();settle(app,w)
    assert p.exists() and not (watch/'编码.jpg').exists() and '取消' in page.results.item(0,3).text()


def test_pause_cancels_automatic_only_theme_preserves_explicit(ui,monkeypatch):
    import filehub.automation.executor as module
    app,w,s,watch=ui;p=watch/'继续转换.png';png(p);image_preview(app,w,p)
    entered,release=Event(),Event();original=module.generate_owned;automatic=[]
    def slow(*args,**kwargs):entered.set();assert release.wait(5);return original(*args,**kwargs)
    monkeypatch.setattr(module,'generate_owned',slow)
    original_cancel=w.automation.executor.cancel_automatic
    monkeypatch.setattr(w.automation.executor,'cancel_automatic',lambda:(automatic.append(True),original_cancel()))
    page=w.conversion_page;page.execute_button.click();wait(app,entered.is_set)
    event=w.automation.jobs['images']['cancel'];w.appearance.setCurrentIndex(1);w.save_settings();wait(app,lambda:not w.coordinator.pending)
    assert not event.is_set() and s.config.theme=='light'
    w.toggle_pause();wait(app,lambda:not w.coordinator.pending);assert not s.config.paused
    w.toggle_pause();wait(app,lambda:not w.coordinator.pending)
    assert s.config.paused and automatic==[True] and not event.is_set()
    release.set();settle(app,w)
    assert page.results.item(0,2).text()=='已完成' and not p.exists()


def test_progress_item_index_and_committing_never_final_success(ui):
    app,w,_,watch=ui;page=w.conversion_page
    page.set_preview([{'source':'a','target':'b'},{'source':'c','target':'d'}])
    job={'binding':w.automation._bound('images'),'action':'execute','cancel':Event()};w.automation.jobs['images']=job
    w.automation._progress(('images',job),{'index':1,'phase':'committing','percent':99,'status':'success'})
    assert page.results.item(0,2).text()=='待执行' and page.results.item(1,2).text()=='正在保存/替换'
    w.automation.jobs.clear()


def test_manual_check_executes_enabled_generic_rule_without_sync(ui):
    app,w,s,watch=ui;p=watch/'素材.txt';p.write_text('generic')
    enabled=replace(s.rules.load().rules[0],enabled=True)
    s.rules.save(RuleSet((enabled,)))
    with s.engine.locked():s.config=replace(s.config,paused=False,sync_root=None)
    w.rules_page.check_button.click();settle(app,w)
    assert not p.exists() and (watch/'素材_已整理.txt').exists() and w.history_list.count()==1


def test_image_rule_preview_worker_cancel_and_progress_subject(ui,monkeypatch):
    import filehub.automation.runner as module
    app,w,s,watch=ui;p=watch/'素材.png';png(p)
    rule=replace(s.rules.load().rules[0],actions=(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),Action('rename',{'pattern':'{stem}_交付{ext}'})))
    w.automation.save_rules(RuleSet((rule,)));settle(app,w)
    entered,release=Event(),Event();original=module.inspect;threads=[]
    def slow(*args):threads.append(get_ident());entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(module,'inspect',slow)
    page=w.rules_page;page.set_sample_paths([p]);page.preview_button.click();wait(app,entered.is_set)
    assert w.preview_button.isEnabled() and threads[0]!=get_ident()
    page.cancel_button.click();assert page._cancel_pending and w.automation.jobs['rules']['cancel'].is_set()
    release.set();settle(app,w);assert p.exists() and not page.execute_button.isEnabled()
    monkeypatch.setattr(module,'inspect',original)
    page.preview_button.click();settle(app,w)
    assert '备份原图后替换' in page.preview_text.toPlainText() and p.exists()
    page.execute_button.click();settle(app,w)
    assert not p.exists() and (watch/'素材_交付.jpg').exists() and '已完成' in page.progress_label.text()


def test_demo_waits_for_actual_critical_commit_then_rebind_rejects_old(ui,tmp_path):
    from filehub.platform.windows import WindowsPlatform
    app,w,s,watch=ui;p=watch/'关键.png';second=watch/'剩余.png';png(p);png(second)
    entered,release=Event(),Event();calls=[]
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    s.engine.platform=Block();page=w.conversion_page
    page.set_paths([p,second]);page.fields.set_value(ConversionSpec(),mode='replace');page._preview();settle(app,w)
    token=page._token;page.execute_button.click();wait(app,entered.is_set)
    newstate=tmp_path/'newstate'
    def demo():
        calls.append(True);service=FileHubService(Config(),newstate);return service,ConfigStore(newstate),()
    w.demo_callback=demo;old_generation=w.automation.state_generation
    start=time.monotonic();w.start_demo();assert time.monotonic()-start<.2
    app.processEvents();assert w.service is s and not calls and not w.automation.settled
    release.set();settle(app,w)
    assert calls==[True] and w.service is not s and w.automation.state_generation==old_generation+1
    assert not p.exists() and (watch/'关键.jpg').exists() and second.exists()
    assert s.history()[0].ok
    w.automation.execute('images',token);assert '失效' in page.error_label.text()
    old_hook=w.automation.completion_hook(s,old_generation)
    from concurrent.futures import Future
    from filehub.automation.runner import RunOutcome
    future=Future();future.set_result((RunOutcome(p,error='旧服务错误不得显示'),))
    old_hook(future);app.processEvents();assert '旧服务错误' not in w.status.text()


def test_structural_settings_waits_engine_authority_and_critical_outcome_truth(ui,tmp_path):
    from filehub.platform.windows import WindowsPlatform
    app,w,s,watch=ui;p=watch/'关键设置.png';png(p);image_preview(app,w,p)
    entered,release=Event(),Event()
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    s.engine.platform=Block();w.conversion_page.execute_button.click();wait(app,entered.is_set)
    replacement=tmp_path/'新观察';replacement.mkdir();w.watch_list.clear();w.watch_list.addItem(str(replacement))
    start=time.monotonic();w.save_settings();assert time.monotonic()-start<.2
    app.processEvents();assert s.config.watch_roots==(watch,) and w.coordinator.pending
    release.set();settle(app,w)
    assert s.config.watch_roots==(replacement,) and not p.exists() and (watch/'关键设置.jpg').exists()
    assert w.history_list.count()==1 and s.history()[0].ok


def test_runtime_quit_retains_owned_lease_marker_until_critical_settlement(tmp_path):
    from filehub.ui.app import Runtime,bootstrap
    from filehub.platform.windows import WindowsPlatform
    app=QApplication.instance() or QApplication([])
    bundle=bootstrap(tmp_path/'state');exits=[]
    class Marker:
        handle=True
        def close(self):self.handle=None
    marker=Marker();rt=Runtime(bundle,auto_timers=False,notifier=lambda *args:None,exit_callback=lambda:exits.append(True),marker=marker)
    w=rt.window;settle(app,w);p=tmp_path/'关闭.png';png(p);image_preview(app,w,p)
    entered,release=Event(),Event()
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    bundle.service.engine.platform=Block();w.conversion_page.execute_button.click();wait(app,entered.is_set)
    start=time.monotonic();rt.request_quit();assert time.monotonic()-start<.2
    app.processEvents();assert not rt.closed and rt.lease.file is not None and marker.handle
    release.set();wait(app,lambda:rt.closed)
    assert rt.lease.file is None and marker.handle is None and exits==[True]
    assert not p.exists() and p.with_suffix('.jpg').exists() and bundle.service.history()[0].ok


def test_runtime_automatic_image_completion_and_failure_notices(tmp_path,monkeypatch):
    from filehub.ui.app import Runtime,bootstrap
    from datetime import datetime,timezone
    app=QApplication.instance() or QApplication([]);watch=tmp_path/'watch';watch.mkdir()
    cfg=Config(watch_roots=(watch,),paused=False);ConfigStore(tmp_path/'state').save(cfg)
    bundle=bootstrap(tmp_path/'state');rule=Rule(name='自动图片替换',enabled=True,condition=Predicate('extension','equals','.png'),actions=(Action('image_convert',{'output_format':'jpeg','mode':'replace'}),))
    bundle.service.rules.save(RuleSet((rule,)));notices=[]
    class Marker:
        handle=True
        def close(self):self.handle=None
    rt=Runtime(bundle,auto_timers=False,notifier=lambda *args:notices.append(args),exit_callback=lambda:None,marker=Marker())
    w=rt.window;settle(app,w);p=watch/'自动.png';png(p)
    rt.schedule_tick();wait(app,lambda:not w.coordinator.pending)
    idle=Event();w.automation.executor.when_idle(idle.set);wait(app,idle.is_set);settle(app,w)
    assert not p.exists() and p.with_suffix('.jpg').exists() and w.history_list.count()==1
    assert any('已完成' in title for title,message in notices)
    bad=watch/'失败.png';png(bad)
    import filehub.automation.runner as module
    def fail(*a,**k):raise ValueError('明确的自动编码失败')
    monkeypatch.setattr(module,'generate_owned',fail)
    rt.schedule_tick();wait(app,lambda:not w.coordinator.pending)
    idle.clear();w.automation.executor.when_idle(idle.set);wait(app,idle.is_set);settle(app,w)
    assert bad.exists() and any('失败' in message for title,message in notices)
    rt.request_quit();wait(app,lambda:rt.closed)


def test_save_ack_does_not_discard_later_programmatic_draft(ui,monkeypatch):
    app,w,s,_=ui;entered,release=Event(),Event();original=s.rules.save
    def delayed(*a,**k):entered.set();assert release.wait(5);return original(*a,**k)
    monkeypatch.setattr(s.rules,'save',delayed)
    page=w.rules_page;page.name_edit.setText('保存这个版本');page.save_button.click();wait(app,entered.is_set)
    page.name_edit.setText('后来的草稿');release.set();settle(app,w)
    assert page.dirty and page.name_edit.text()=='后来的草稿' and s.rules.load().rules[0].name=='保存这个版本'
    assert w.automation.rules_revision==s.rules.load().revision


def test_native_small_templates_columns_and_empty_feedback_space(ui):
    app,w,_,watch=ui;w.resize(800,620);w.navigate(4);w.rules_tabs.setCurrentIndex(1);w.show();app.processEvents()
    table=w.templates_page.categories.table
    assert table.columnWidth(0)+table.columnWidth(1)<=table.viewport().width()+2
    assert w.templates_page.editor.width()<w.rules_tabs.width()
    assert not w.rules_page.error_label.isVisible() and not w.rules_page.dirty_label.isVisible() and not w.rules_page.progress_label.isVisible()


def test_rule_preview_exact_backend_nested_nonmatch_and_unavailable_reasons(ui):
    from filehub.automation.models import ConditionGroup
    app,w,s,watch=ui;p=watch/'素材.txt';p.write_text('sample')
    rule=replace(s.rules.load().rules[0],condition=ConditionGroup('all',(
        Predicate('name','contains','不匹配'),Predicate('first_seen_age_seconds','ge',3600))))
    w.automation.save_rules(RuleSet((rule,)));settle(app,w)
    page=w.rules_page;page.set_sample_paths([p]);page.preview_button.click();settle(app,w)
    text=page.preview_text.toPlainText()
    assert '全部条件：不满足' in text and '实际为 素材.txt' in text and '不匹配' in text
    assert '不可用' in text and '3600' in text and not page.execute_button.isEnabled() and p.exists()


@pytest.mark.parametrize('failure',[None,ValueError('演示目录无法创建')])
def test_demo_failure_reconstructs_settled_same_state_and_remains_usable(ui,failure):
    app,w,s,watch=ui;p=watch/'素材.txt';p.write_text('old state')
    def demo():
        if failure:raise failure
        return None
    w.demo_callback=demo;generation=w.automation.state_generation;w.start_demo();settle(app,w)
    assert w.service is not s and w.service.engine.state_dir==s.engine.state_dir and s._closing
    assert w.automation.accepting and w.automation.state_generation==generation+1 and w.demo_button.isEnabled()
    assert '未进入演示' in w.status.text() and '原状态已恢复' in w.status.text() and not w.is_demo
    w.rules_page.set_sample_paths([p]);w.rules_page.preview_button.click();settle(app,w)
    w.rules_page.execute_button.click();settle(app,w)
    assert not p.exists() and (watch/'素材_已整理.txt').exists()


def test_runtime_demo_failure_rebinds_service_scheduler_keeps_original_lease(tmp_path,monkeypatch):
    import filehub.ui.app as module
    app=QApplication.instance() or QApplication([]);bundle=module.bootstrap(tmp_path/'state')
    class Marker:
        handle=True
        def close(self):self.handle=None
    rt=module.Runtime(bundle,auto_timers=False,notifier=lambda *a:None,exit_callback=lambda:None,marker=Marker())
    w=rt.window;settle(app,w);old=rt.service;lease=rt.lease;state=rt.state_dir
    monkeypatch.setattr(module,'create_demo',lambda *a:(_ for _ in ()).throw(OSError('隔离演示失败')))
    w.start_demo();settle(app,w)
    assert rt.service is w.service and rt.service is not old and rt.scheduler.service is rt.service
    assert rt.lease is lease and lease.file is not None and rt.state_dir==state and not rt.demo
    rt.schedule_tick();settle(app,w);rt.request_quit();wait(app,lambda:rt.closed)


def test_stale_request_generations_never_submit(ui):
    from filehub.ui.rule_requests import RulePreviewRequest
    app,w,_,watch=ui;p=watch/'素材.png';png(p)
    page=w.conversion_page;page.set_paths([p]);page.fields.set_value(ConversionSpec(),mode='replace');request=page.value()
    page.set_paths([p]);w.automation.preview_images(request)
    rules=w.rules_page;rules.set_sample_paths([p]);request=RulePreviewRequest(rules.selected_id,(str(p),),w.automation.rules_revision,rules.generation)
    rules.set_sample_paths([p]);w.automation.preview_rule(request)
    assert not w.automation.jobs and not w.coordinator.pending


def test_all_future_results_and_image_submission_stay_off_gui(ui,monkeypatch):
    from concurrent.futures import Future
    app,w,_,watch=ui;p=watch/'快速.png';png(p)
    gui=get_ident();threads=[];original=Future.result
    def result(future,*args,**kwargs):
        threads.append(get_ident());assert get_ident()!=gui
        return original(future,*args,**kwargs)
    monkeypatch.setattr(Future,'result',result)
    image_preview(app,w,p);w.conversion_page.execute_button.click();settle(app,w)
    assert threads and p.with_suffix('.jpg').exists()


def test_demo_reopen_failure_has_explicit_restart_state(ui):
    app,w,_,_=ui
    w.demo_callback=lambda:None
    w.service_reopen_callback=lambda old:(_ for _ in ()).throw(OSError('无法重新打开状态'))
    w.start_demo();settle(app,w)
    assert not w.automation.accepting and w.automation.settled and not w.demo_button.isEnabled()
    assert '请安全退出后重新打开' in w.status.text() and '原任务已安全结束' in w.status.text()


def test_rule_save_busy_does_not_offer_job_cancel(ui,monkeypatch):
    app,w,s,_=ui;entered,release=Event(),Event();original=s.rules.save
    def delayed(*a,**k):entered.set();assert release.wait(5);return original(*a,**k)
    monkeypatch.setattr(s.rules,'save',delayed)
    w.rules_page.name_edit.setText('规则保存');w.rules_page.save_button.click();wait(app,entered.is_set)
    assert not w.rules_page.cancel_button.isEnabled()
    release.set();settle(app,w)


@pytest.fixture
def lifecycle_rt(tmp_path):
    from filehub.ui.app import Runtime,bootstrap
    app=QApplication.instance() or QApplication([]);sync=tmp_path/'同步'
    (sync/'1_工作/项目/261001_XYZ_测试').mkdir(parents=True)
    ConfigStore(tmp_path/'state').save(Config(sync_root=sync))
    bundle=bootstrap(tmp_path/'state');notices=[];exits=[]
    class Marker:
        handle=True
        def close(self):self.handle=None
    rt=Runtime(bundle,auto_timers=False,notifier=lambda *a:notices.append(a),exit_callback=lambda:exits.append(True),marker=Marker())
    rt._test_notices=notices;rt._test_exits=exits;settle(app,rt.window)
    yield app,rt
    if not rt.closed:
        if not rt.quitting:rt.request_quit()
        # Failed RED may strand a rebind. Cleanup after recording the assertion
        # explicitly settles its owned service; this is not acceptance evidence.
        rt.window.automation.retire(lambda:None)
        settle(app,rt.window);wait(app,lambda:rt.window.automation.settled)
        rt._finish_quit();wait(app,lambda:rt.closed)


def test_transition_rejects_direct_home_tray_settings_and_archive_mutations(lifecycle_rt,tmp_path,monkeypatch):
    import filehub.ui.app as module
    app,rt=lifecycle_rt;w=rt.window;old=rt.service;oldstore=w.store;lease=rt.lease
    source=tmp_path/'留在原位置.txt';source.write_text('old authority')
    w.set_paths([source]);w.tag.setText('XYZ020822');w.request_preview();settle(app,w)
    entered,release=Event(),Event();original=module.create_demo;writes=[];archives=[]
    save=oldstore.save;execute=old.execute
    def delayed(base):entered.set();assert release.wait(5);return original(base)
    def recorded(config):writes.append((lease.file is None,rt.demo));return save(config)
    def archive(preview):archives.append(True);return execute(preview)
    monkeypatch.setattr(module,'create_demo',delayed);monkeypatch.setattr(oldstore,'save',recorded);monkeypatch.setattr(old,'execute',archive)
    w.start_demo();wait(app,entered.is_set)
    try:
        w.toggle_pause();w.pause_button.click();rt.pause_action.trigger();w.save_settings();w.execute()
        admitted=w.open_archive_dialog([source])
        pause_enabled=w.pause_button.isEnabled()
    finally:release.set()
    settle(app,w)
    assert writes==[] and archives==[] and source.exists() and old.config.paused
    assert admitted is None and not pause_enabled and rt.demo


@pytest.mark.parametrize('recovery',[False,True])
def test_quit_during_demo_creation_or_recovery_retires_new_service_and_exits(lifecycle_rt,monkeypatch,recovery):
    import filehub.ui.app as module
    app,rt=lifecycle_rt;w=rt.window;entered,release=Event(),Event()
    if recovery:
        monkeypatch.setattr(module,'create_demo',lambda *a:(_ for _ in ()).throw(OSError('演示创建失败')))
        original=w.service_reopen_callback
        def delayed(old):entered.set();assert release.wait(5);return original(old)
        w.service_reopen_callback=delayed
    else:
        original=module.create_demo
        def delayed(base):entered.set();assert release.wait(5);return original(base)
        monkeypatch.setattr(module,'create_demo',delayed)
    w.start_demo();wait(app,entered.is_set)
    try:
        rt.quit_action.trigger();assert rt.quitting and not rt.closed and rt.lease.file is not None
    finally:release.set()
    settle(app,w)
    assert rt.closed and not w.automation.accepting and w.automation.settled
    assert rt.lease.file is None and rt.marker.handle is None and rt._test_exits==[True]


def test_stale_tick_error_settles_own_token_and_next_check_runs(lifecycle_rt,monkeypatch):
    app,rt=lifecycle_rt;w=rt.window;entered,release=Event(),Event();calls=[]
    def tick(now):
        calls.append(True)
        if len(calls)==1:entered.set();assert release.wait(5);raise OSError('过期检查错误')
        return []
    monkeypatch.setattr(rt.scheduler,'tick',tick)
    rt.schedule_tick();wait(app,entered.is_set)
    try:w.rules_page.new_rule()
    finally:release.set()
    settle(app,w)
    assert not rt.tick_pending and '过期检查错误' not in w.status.text()
    assert not any('过期检查错误' in message for title,message in rt._test_notices)
    rt.schedule_tick();settle(app,w);assert len(calls)==2 and not rt.tick_pending


def test_admitted_config_write_finishes_before_demo_can_release_old_lease(lifecycle_rt,monkeypatch):
    import filehub.ui.app as module
    app,rt=lifecycle_rt;w=rt.window;old=rt.service;lease=rt.lease;entered,release=Event(),Event();writes=[]
    original=w.store.save
    def delayed(config):
        entered.set();assert release.wait(5)
        writes.append((lease.file is None,rt.demo));return original(config)
    monkeypatch.setattr(w.store,'save',delayed)
    w.toggle_pause();wait(app,entered.is_set)
    try:
        w.start_demo();assert not rt.demo and rt.service is old and not old._closing and lease.file is not None
    finally:release.set()
    settle(app,w);assert writes==[(False,False)] and not old.config.paused
    w.start_demo();settle(app,w);assert rt.demo and lease.file is None


def test_queued_worker_guard_rejects_retired_mutation_before_ownership_release(lifecycle_rt,monkeypatch):
    app,rt=lifecycle_rt;w=rt.window;entered,release=Event(),Event();writes=[]
    w.coordinator.submit(lambda:(entered.set(),release.wait(5)),lambda _:None)
    wait(app,entered.is_set)
    monkeypatch.setattr(w.store,'save',lambda config:writes.append(config))
    w.toggle_pause()  # This request is admitted while the earlier ordinary job runs.
    rt.request_quit();assert rt.lease.file is not None
    release.set();settle(app,w)
    assert writes==[] and rt.closed and rt.lease.file is None and rt._test_exits==[True]


def test_tick_error_current_generation_notifies_and_old_token_cannot_clear_new_check(lifecycle_rt,monkeypatch):
    app,rt=lifecycle_rt;w=rt.window;calls=[];entered,release=Event(),Event()
    def tick(now):
        calls.append(True)
        if len(calls)==1:raise OSError('当前检查读取失败')
        entered.set();assert release.wait(5);return []
    monkeypatch.setattr(rt.scheduler,'tick',tick)
    rt.schedule_tick();old=rt._tick_token;settle(app,w)
    assert not rt.tick_pending and any('当前检查读取失败' in message for title,message in rt._test_notices)
    rt.schedule_tick();wait(app,entered.is_set);new=rt._tick_token
    try:
        rt._tick_error('迟到旧错误',rt.generation,w.automation.rule_generation,old)
        rt._tick_done(([],()),rt.generation,w.automation.rule_generation,old)
        assert rt.tick_pending and rt._tick_token is new and '迟到旧错误' not in w.status.text()
    finally:release.set()
    settle(app,w);assert not rt.tick_pending and rt._tick_token is None


def test_quit_before_demo_conversion_settlement_keeps_old_service_until_safe_commit(lifecycle_rt,tmp_path):
    from filehub.platform.windows import WindowsPlatform
    app,rt=lifecycle_rt;w=rt.window;old=rt.service;p=tmp_path/'关键切换.png';png(p);image_preview(app,w,p)
    entered,release=Event(),Event()
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_generated_publish':entered.set();assert release.wait(5)
    old.engine.platform=Block();w.conversion_page.execute_button.click();wait(app,entered.is_set)
    w.start_demo();assert not w.automation.accepting and not w.automation.settled
    rt.request_quit();assert rt.lease.file is not None and not rt.demo
    release.set();settle(app,w)
    assert rt.closed and rt.service is old and not rt.demo and rt.lease.file is None and rt.marker.handle is None
    assert not p.exists() and p.with_suffix('.jpg').exists() and old.history()[0].ok
