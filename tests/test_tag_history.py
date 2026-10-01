import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import threading
import time
import pytest
from PySide6.QtWidgets import QApplication
from filehub.tag_history import TagHistory
from filehub.config import Config,ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow


def settle(app,w):
    until=time.monotonic()+10
    while w.coordinator.pending and time.monotonic()<until:app.processEvents();time.sleep(.01)
    app.processEvents();assert not w.coordinator.pending


def test_store_restart_exact_dedup_order_delete_clear_and_lazy_init(tmp_path):
    state=tmp_path/'state';s=TagHistory(state);assert not state.exists()
    assert s.remember(' XYZ020822 ')==('XYZ020822',)
    for n in range(55):s.remember('XYZ角色'+str(n))
    s.remember('XYZ020822');s.remember('xyz020822')
    restarted=TagHistory(state);tags=restarted.list();assert len(tags)==57 and tags[:2]==('xyz020822','XYZ020822')
    assert 'XYZ角色0' in tags
    assert 'XYZ020822' not in restarted.remove('XYZ020822')
    assert restarted.clear()==() and TagHistory(state).list()==()


@pytest.fixture
def ui(tmp_path):
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作/项目/261001_XYZ_测试').mkdir(parents=True)
    p=tmp_path/'source.png';p.write_bytes(b'image')
    state=tmp_path/'state';s=FileHubService(Config(sync_root=root),state)
    w=MainWindow(s,ConfigStore(state));settle(app,w);w.set_paths([p]);w.show()
    yield app,w,p
    for d in tuple(w.dialogs):d.reject()
    settle(app,w);w.close();w.coordinator.close()


def test_valid_preview_remember_invalid_empty_and_partial_typing_do_not(ui):
    app,w,p=ui;w.tag.setText('XYZ02');settle(app,w);assert w.tag_history.tags==()
    w.request_preview();settle(app,w);assert w.tag_history.tags==()
    w.tag.setText('XYZ020822');w.request_preview();settle(app,w);assert w.tag_history.tags==('XYZ020822',)
    w.set_paths([]);w.tag.setText('XYZ020823');w.request_preview();settle(app,w);assert w.tag_history.tags==('XYZ020822',)
    assert p.read_bytes()==b'image' and not w.service.history()


def test_chip_click_only_fills_and_invalidates_then_deletes_sync_no_file_or_journal_change(ui):
    app,w,p=ui;d=w.open_archive_dialog([p]);w.tag.setText('XYZ020822');w.request_preview();settle(app,w)
    assert d.history_chips.tags==w.history_chips.tags==('XYZ020822',)
    d.history_chips.tag_buttons['XYZ020822'].click();assert d.tag.text()=='XYZ020822' and d.preview is None
    assert p.read_bytes()==b'image' and not w.service.history()
    d.tag.setText('XYZ020823');d.request_preview();settle(app,w);assert w.history_chips.tags[0]=='XYZ020823'
    w.history_chips.remove_buttons['XYZ020822'].click();settle(app,w);assert d.history_chips.tags==('XYZ020823',)
    journal=w.service.engine.journal.path.read_bytes()
    d.history_chips.clear_button.click();settle(app,w);assert w.history_chips.tags==d.history_chips.tags==()
    assert w.service.engine.journal.path.read_bytes()==journal and p.read_bytes()==b'image'


@pytest.mark.parametrize('dialog',[False,True])
def test_stale_preview_is_not_remembered(ui,dialog):
    app,w,p=ui;editor=w.open_archive_dialog([p]) if dialog else w;entered=threading.Event();release=threading.Event();original=w.service.preview
    def delayed(paths,tag):entered.set();release.wait(5);return original(paths,tag)
    w.service.preview=delayed;editor.tag.setText('XYZ020822');editor.request_preview();assert entered.wait(2)
    editor.tag.setText('XYZ020823');release.set();settle(app,w)
    assert w.tag_history.tags==() and editor.preview is None


def test_history_io_error_visible_without_losing_valid_preview(ui):
    app,w,p=ui
    def fail(tag):raise OSError('history disk full')
    w.tag_history.store.remember=fail;w.tag.setText('XYZ020822');w.request_preview();settle(app,w)
    assert w.preview and w.execute_button.isEnabled() and 'history disk full' in w.history_chips.error_label.text()


def test_demo_switch_isolated_and_old_history_callback_cannot_leak(ui,tmp_path):
    app,w,p=ui;w.tag.setText('XYZ020822');w.request_preview();settle(app,w);normal=w.store.state_dir
    from filehub.ui.app import create_demo
    service,store,paths=create_demo(tmp_path/'demo-root')
    w.demo_ready((service,store,paths));settle(app,w);assert w.tag_history.tags==()
    w.request_preview();settle(app,w);assert w.tag_history.tags==('DEMO020822',)
    assert TagHistory(normal).list()==('XYZ020822',)


def test_old_store_delivery_ignored_after_switch(ui,tmp_path):
    app,w,p=ui;started=threading.Event();release=threading.Event();old=w.tag_history.store
    def delayed():started.set();release.wait(5);return ('PRIVATE_NORMAL',)
    old.list=delayed;w.tag_history.refresh();assert started.wait(2)
    w.tag_history.switch_state(tmp_path/'new-demo-state');release.set();settle(app,w);assert w.tag_history.tags==()


@pytest.mark.parametrize('dialog,clear',[(False,True),(True,False)])
def test_delete_intent_prevents_inflight_preview_remember(ui,dialog,clear):
    app,w,p=ui;w.tag.setText('XYZ020822');w.request_preview();settle(app,w)
    editor=w.open_archive_dialog([p]) if dialog else w
    entered=threading.Event();release=threading.Event();original=w.service.preview
    def delayed(paths,tag):entered.set();release.wait(5);return original(paths,tag)
    w.service.preview=delayed;editor.tag.setText('XYZ020822');editor.request_preview();assert entered.wait(2)
    if clear:w.tag_history.clear()
    else:w.tag_history.remove('XYZ020822')
    release.set();settle(app,w)
    assert editor.preview is not None and w.tag_history.tags==() and TagHistory(w.store.state_dir).list()==()
    assert p.exists() and not w.service.history()


def test_footer_full_long_message_scrolls_and_empty_stays_compact(ui):
    app,w,p=ui;w.resize(800,620)
    message='操作未完成：存在冲突\n'+'\n'.join('完整路径：'+str(p.parent/('特别长的目录名称'*10)/f'文件{n}.png') for n in range(25))
    w.status.setText(message);app.processEvents()
    assert w.status.text()==message and w.status.hasSelectedText() is False
    assert w.statusBar().objectName()=='appStatusBar' and not w.statusBar().isSizeGripEnabled()
    assert 36<=w.status_footer.height()<=144 and w.status_footer.verticalScrollBar().maximum()>0
    w.status_footer.verticalScrollBar().setValue(w.status_footer.verticalScrollBar().maximum());app.processEvents()
    assert w.status_footer.verticalScrollBar().value()>0
    w.status.setText('');app.processEvents();assert w.status_footer.height()<20


@pytest.mark.parametrize('dialog',[False,True])
def test_click_same_tag_still_requires_new_preview(ui,dialog):
    app,w,p=ui;editor=w.open_archive_dialog([p]) if dialog else w
    editor.tag.setText('XYZ020822');editor.request_preview();settle(app,w)
    assert editor.preview and editor.execute_button.isEnabled()
    editor.history_chips.tag_buttons['XYZ020822'].click()
    assert editor.tag.text()=='XYZ020822' and editor.preview is None and not editor.execute_button.isEnabled()
    assert p.exists() and not w.service.history()


def test_history_io_including_initial_load_and_all_mutations_use_worker(ui):
    app,w,p=ui;threads=[];store=w.tag_history.store
    for method in ('connection',):
        original=getattr(store,method)
        def record(original=original):threads.append(threading.get_ident());return original()
        setattr(store,method,record)
    w.tag_history.refresh();w.tag.setText('XYZ020822');w.request_preview();settle(app,w)
    w.tag_history.remove('XYZ020822');w.tag_history.clear();settle(app,w)
    assert len(threads)==4 and all(t!=threading.get_ident() for t in threads)


def test_small_home_keeps_controls_legible_and_overflow_accessible(ui):
    from PySide6.QtWidgets import QScrollArea
    app,w,p=ui
    for n in range(25):w.tag_history.remember(f'XYZ0208{n+1:03}')
    settle(app,w);w.recent_list.setFixedHeight(220);w.resize(800,620)
    w.status.setText('存在冲突\n'+'\n'.join(str(p)*3 for _ in range(15)));app.processEvents()
    assert isinstance(w.pages.widget(0),QScrollArea)
    assert w.tag.height()>=32 and w.preview_details.height()>=110
    assert w.history_chips.scroll.height()==54 and w.history_chips.scroll.horizontalScrollBar().maximum()>0
    assert w.pages.widget(0).verticalScrollBar().maximum()>0
