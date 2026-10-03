import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import json
import pytest
from threading import Event,get_ident
from PySide6.QtWidgets import QApplication
from filehub.config import Config,ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow

def settle(app,window):
    end=time.monotonic()+10
    while (window.coordinator.pending or window.automation.jobs) and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    app.processEvents();assert not window.coordinator.pending and not window.automation.jobs

def test_normal_navigation_and_no_authors(tmp_path):
    app=QApplication.instance() or QApplication([])
    service=FileHubService(Config(),tmp_path/'state');window=MainWindow(service,ConfigStore(tmp_path/'state'))
    try:
        settle(app,window)
        assert [b.text() for b in window.nav_buttons]==['文件处理','规则文件','图片转换','记录','设置']
        assert not hasattr(window,'templates_page') and not hasattr(window.rules_page,'condition_editor')
        assert not hasattr(window,'demo_button') and not hasattr(window,'tag')
    finally:
        window.automation.retire(lambda:None)
        end=time.monotonic()+5
        while not window.automation.settled and time.monotonic()<end:app.processEvents();time.sleep(.005)
        window._close_settled=True;window.close();window.coordinator.close()

@pytest.fixture
def ui(tmp_path):
    app=QApplication.instance() or QApplication([]);service=FileHubService(Config(),tmp_path/'state');window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    yield app,window,service
    for dialog in tuple(window.dialogs):dialog.reject()
    window.automation.retire(lambda:None)
    end=time.monotonic()+10
    while not window.automation.settled and time.monotonic()<end:app.processEvents();time.sleep(.005)
    settle(app,window);window._close_settled=True;window.close();window.coordinator.close()

def package():
    return dict(format='filehub.rules',version=1,id='sample',name='图片整理',bindings={'input':{'label':'输入'},'output':{'label':'输出'}},variables={},rules=[dict(id='one',name='移动素材',scope=[{'binding':'input','relative':''}],condition={'field':'extension','operator':'equals','value':'.txt'},actions=[{'kind':'move','options':{'destination':{'binding':'output','relative':''}}}])])

def import_fixture(app,window,tmp_path):
    path=tmp_path/'rules.json';path.write_text(json.dumps(package()),encoding='utf-8');window.automation.manage(('import',None,str(path)));settle(app,window);return path

def test_import_bind_manual_scope_preview_execute_and_undo(ui,tmp_path):
    app,w,s=ui;import_fixture(app,w,tmp_path)
    snapshot=s.catalog.load();assert not snapshot.enabled['sample'] and s.config.watch_roots==()
    assert '未绑定' in w.rules_page.summary.toPlainText()
    incoming=tmp_path/'input';incoming.mkdir();out=tmp_path/'output';source=incoming/'sample.txt';source.write_text('content')
    w.automation.manage(('bind','sample',None));dialog=w.automation.review_dialog
    dialog.fields['input'].setText(str(incoming));dialog.fields['output'].setText(str(out));dialog.accept();settle(app,w)
    assert not out.exists() and not s.catalog.load().enabled['sample'] and not s.config.watch_roots
    w.set_paths([source]);w.home_panel.rule_choice.setCurrentIndex(1);w.request_preview();settle(app,w)
    assert source.exists() and w.home_panel.execute_button.isEnabled() and '移动' in w.home_panel.preview_text.toPlainText()
    w.execute();settle(app,w);assert not source.exists() and (out/'sample.txt').read_text()=='content'
    assert not w.home_panel.execute_button.isEnabled()
    w.history_list.setCurrentRow(0);w.undo();settle(app,w);assert source.exists()
    outside=tmp_path/'outside.txt';outside.write_text('outside');w.set_paths([outside]);w.request_preview();settle(app,w)
    assert not w.home_panel.execute_button.isEnabled() and outside.exists()

def test_replace_exact_bytes_cancel_and_stale_cas(ui,tmp_path):
    app,w,s=ui;path=import_fixture(app,w,tmp_path);old=s.catalog.load().revision
    incoming=package();incoming['name']='已审版本';path.write_text(json.dumps(incoming),encoding='utf-8')
    w.automation.manage(('replace','sample',str(path)));settle(app,w);review=w.automation.review_dialog
    assert '图片整理 → 已审版本' in review.details.toPlainText();review.reject();assert s.catalog.load().revision==old
    w.automation.manage(('replace','sample',str(path)));settle(app,w);review=w.automation.review_dialog
    incoming['name']='未审改动';path.write_text(json.dumps(incoming),encoding='utf-8');review.accept();settle(app,w)
    assert s.catalog.load().packages['sample'].name=='已审版本'
    w.automation.manage(('reload','sample',None));settle(app,w);review=w.automation.review_dialog
    current=s.catalog.load();s.catalog.reorder(current.order,expected_revision=current.revision)
    review.accept();settle(app,w)
    assert '变化' in w.rules_page.error_label.text() and s.catalog.load().packages['sample'].name=='已审版本'

def test_recovery_review_works_after_load_failure(ui,tmp_path):
    app,w,s=ui;import_fixture(app,w,tmp_path);snapshot=s.catalog.load();s.catalog.replace_package('sample',json.dumps(package()).encode(),expected_revision=snapshot.revision)
    s.catalog.path.write_bytes(b'{corrupt');w.automation.load();settle(app,w);assert w.automation.catalog_snapshot is None
    w.automation.manage(('restore',None,None));settle(app,w);dialog=w.automation.review_dialog
    assert '移动素材' in dialog.details.toPlainText();dialog.accept();settle(app,w)
    assert not s.catalog.load().enabled['sample'] and w.automation.catalog_snapshot is not None

def test_management_waits_image_idle_and_ordinary_barrier(ui,tmp_path):
    app,w,s=ui;import_fixture(app,w,tmp_path);entered=Event();release=Event();mutations=[]
    handle=w.automation.executor.submit(lambda cancel,progress:(entered.set(),release.wait(5)))
    assert entered.wait(2)
    old=s.catalog.load().revision
    w.automation.mutate(lambda:(mutations.append(get_ident()),s.catalog.reorder(('sample',),expected_revision=old))[1])
    app.processEvents();assert mutations==[] and not w.automation.accepting and w.capture_work_authority() is None
    release.set();settle(app,w);assert mutations and mutations[0]!=get_ident() and w.automation.accepting

def test_stale_read_failures_and_compact_selection(ui,tmp_path):
    app,w,s=ui;entered=Event();release=Event()
    def work():entered.set();release.wait(5);raise ValueError('旧状态错误')
    w.automation._read_work(work,lambda value:None);assert entered.wait(2)
    w.automation.state_generation+=1;release.set();settle(app,w);assert '旧状态错误' not in w.rules_page.error_label.text()
    w.home_panel.set_sample_paths([tmp_path/('长路径'*50)/('文件'+str(i)+'.txt') for i in range(100)])
    assert len(w.home_panel.sample_label.text())<120 and len(w.home_panel.sample_label.toolTip().splitlines())==100

def test_binding_many_roles_keeps_actions_outside_scroll(ui):
    from filehub.ui.rulefile_dialogs import BindingDialog
    from filehub.rulefiles.protocol import parse_package
    app,w,s=ui;doc=package();doc['bindings'].update({str(i):{'label':'角色'+str(i)} for i in range(98)})
    dialog=BindingDialog(w,parse_package(json.dumps(doc).encode()),{});dialog.show();app.processEvents()
    from PySide6.QtWidgets import QScrollArea
    scroll=dialog.findChild(QScrollArea);assert scroll.verticalScrollBar().maximum()>0 and dialog.height()<=560
    dialog.reject()

def test_help_open_failure_shows_copyable_local_path(ui,monkeypatch):
    import filehub.ui.automation_controller as module
    app,w,s=ui;monkeypatch.setattr(module.QDesktopServices,'openUrl',lambda url:False)
    w.automation.open_help();settle(app,w);dialog=w.automation.review_dialog
    assert 'AI规则编写指南.md' in dialog.details.toPlainText() and dialog.details.isReadOnly()
    dialog.reject()

def test_small_home_geometry_has_no_overlap(ui):
    from PySide6.QtWidgets import QStyleOptionComboBox,QStyle
    app,w,s=ui;w.resize(800,620);w.show();app.processEvents();panel=w.home_panel
    assert panel.preview_text.height()>=110
    assert panel.preview_button.y()>=panel.preview_text.y()+panel.preview_text.height()
    option=QStyleOptionComboBox();panel.rule_choice.initStyleOption(option)
    rect=panel.rule_choice.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxEditField,panel.rule_choice)
    assert rect.height()>=panel.rule_choice.fontMetrics().height()

def test_migration_is_explicit_disabled_and_preserves_source(ui):
    from filehub.automation.models import RuleStore,RuleSet,Rule,Predicate,Action
    from filehub.rulefiles.migration import inspect_legacy
    app,w,s=ui;rule=Rule(name='原身份',condition=Predicate('extension','equals','.txt'),actions=(Action('rename',{'pattern':'{stem}_new{ext}'}),),enabled=True)
    store=RuleStore(s.engine.state_dir);store.save(RuleSet((rule,)));prior=store.path.read_bytes()
    s.migration_candidate=inspect_legacy(s.engine.state_dir,s.config);w.automation.load();settle(app,w)
    assert not s.catalog.load().packages and '旧定义' in w.rules_page.notice.text()
    w.automation.manage(('migration',None,None));dialog=w.automation.review_dialog;assert '原始文件' in dialog.details.toPlainText();dialog.accept();settle(app,w)
    snapshot=s.catalog.load();assert store.path.read_bytes()==prior and not snapshot.compatibility_permissions and snapshot.compatibility_selection is None
    assert all(not value for value in snapshot.enabled.values()) and rule.id in snapshot.runtime_ids['legacy-import'].values()
    assert s.migration_candidate is None

def test_permission_grant_preflights_overlap_and_revocation(ui,tmp_path):
    from dataclasses import replace
    from rulefile_fixtures import install_archive
    app,w,s=ui;root=tmp_path/'sync';(root/'1_工作/项目/261001_XYZ_项目').mkdir(parents=True)
    s.config=replace(s.config,sync_root=root);install_archive(s);w.automation.load();settle(app,w)
    snapshot=s.catalog.load();context=s.archive_context();s.config=replace(s.config,watch_roots=(context.sanitization_roots[0],))
    w.automation.manage(('compatibility',None,None));dialog=w.automation.review_dialog;dialog.permissions['cleanup'].setChecked(True);dialog.accept();settle(app,w)
    assert s.catalog.load().revision==snapshot.revision and '重叠' in w.rules_page.error_label.text()
    w.automation.manage(('compatibility',None,None));dialog=w.automation.review_dialog;dialog.choice.setCurrentIndex(0)
    for field in dialog.permissions.values():field.setChecked(False)
    dialog.accept();settle(app,w);assert s.catalog.load().compatibility_selection is None

def test_preview_owner_and_closed_dialog_tokens_are_rejected(ui,tmp_path):
    app,w,s=ui;import_fixture(app,w,tmp_path);token=w.automation._bound('home')
    assert not w.automation._current('rules',token)
    dialog=w.open_file_dialog([tmp_path/'sample.txt']);kind=dialog.kind;assert kind in w.automation.panels
    dialog.reject();assert kind not in w.automation.panels
    w.automation.execute(kind,token);assert '失效' in w.rules_page.error_label.text()

def test_old_binding_review_after_rebind_cannot_mutate_any_state(ui,tmp_path):
    app,w,old=ui;import_fixture(app,w,tmp_path);prior=old.catalog.load().revision
    w.automation.manage(('bind','sample',None));dialog=w.automation.review_dialog;dialog.fields['input'].setText(str(tmp_path/'input'))
    old.close_conversions().wait()
    new=FileHubService(Config(),tmp_path/'newstate');w.service=new;w.store=ConfigStore(tmp_path/'newstate');w.automation.rebind();settle(app,w)
    current=new.catalog.load().revision;dialog.accept();settle(app,w)
    assert old.catalog.load().revision==prior and new.catalog.load().revision==current
    assert '已结束' in w.rules_page.error_label.text()
