import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtWidgets import QApplication
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow
import pytest

def settle(app, window):
    from time import monotonic, sleep
    end = monotonic() + 10
    while window.coordinator.pending and monotonic() < end:
        app.processEvents(); sleep(.01)
    app.processEvents()
    assert not window.coordinator.pending

@pytest.mark.parametrize('recycled',[True,False])
def test_duplicate_result_and_history_show_existing_copy_and_recycle_status(tmp_path,recycled):
    from filehub.platform.windows import WindowsPlatform,RecycleOutcome
    root=tmp_path/'sync';project=root/'1_工作'/'项目'/'261001_XYZ_测试';project.mkdir(parents=True)
    existing=project/'已有副本.png';existing.write_bytes(b'image')
    source=tmp_path/'素材.png';source.write_bytes(b'image');bin_dir=tmp_path/'fake-bin';bin_dir.mkdir()
    class FakeRecycle(WindowsPlatform):
        def recycle(self,path):
            if recycled:path.rename(bin_dir/path.name);return RecycleOutcome('recycled',message='fake recycled')
            return RecycleOutcome('failed',message='fake failed')
    service=FileHubService(Config(sync_root=root),tmp_path/'state',platform=FakeRecycle())
    result=service.execute(service.preview([source],'XYZ020822'))
    assert result.outcomes[0].duplicate==existing
    app=QApplication.instance() or QApplication([])
    window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    window.show_result(result);settle(app,window)
    window.show_history_details(0)
    for text in (window.status.text(),window.history_details.toPlainText()):
        assert '重复' in text and str(existing) in text
        assert ('来源已回收' if recycled else '来源回收未完成') in text
    assert existing.read_bytes()==b'image' and source.exists()!=recycled
    window.close();window.coordinator.close()

def test_controls_archive_history_undo_and_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path/'sync'
    (root/'1_工作'/'项目'/'260930_XYZ_测试').mkdir(parents=True)
    source = tmp_path/'素材.png'; source.write_bytes(b'image')
    service = FileHubService(Config(sync_root=root), tmp_path/'state', source_time=lambda p:datetime.now(timezone.utc))
    window = MainWindow(service, ConfigStore(tmp_path/'state'))
    window.show(); settle(app, window)
    window.set_paths([source]); window.tag.setText('XYZ020822')
    window.preview_button.click(); settle(app, window)
    assert window.preview is not None and window.execute_button.isEnabled()
    window.execute_button.click(); settle(app, window)
    assert not source.exists() and window.history_list.count() == 1
    window.history_list.setCurrentRow(0); window.undo_button.click(); settle(app, window)
    assert source.exists()
    window.appearance.setCurrentIndex(1); window.save_button.click(); settle(app, window)
    assert ConfigStore(tmp_path/'state').load().theme == 'light'
    window.close(); window.coordinator.close()

def test_first_run_demo_callback_and_tabs(tmp_path):
    app = QApplication.instance() or QApplication([])
    called = []
    window = MainWindow(FileHubService(Config(),tmp_path/'state'),ConfigStore(tmp_path/'state'),demo_callback=lambda:called.append(True))
    settle(app,window)
    assert window.first_run.isVisibleTo(window)
    window.demo_button.click(); settle(app,window)
    assert called == [True]
    for index,button in enumerate(window.nav_buttons):
        button.click(); assert window.pages.currentIndex() == index
    window.coordinator.close()

def test_system_theme_uses_platform_scheme():
    from filehub.ui.theme import resolved_theme
    from PySide6.QtCore import Qt
    assert resolved_theme('system',Qt.ColorScheme.Dark)=='dark'
    assert resolved_theme('system',Qt.ColorScheme.Light)=='light'
    assert resolved_theme('light',Qt.ColorScheme.Dark)=='light'

def test_service_calls_serial_worker_and_stale_preview_rejected(tmp_path):
    import threading
    from time import sleep
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作'/'项目'/'261001_XYZ_测试').mkdir(parents=True)
    source=tmp_path/'素材.png';source.write_bytes(b'image')
    service=FileHubService(Config(sync_root=root),tmp_path/'state')
    original=service.preview;threads=[]
    def preview(paths,tag):
        threads.append(threading.get_ident());sleep(.04);return original(paths,tag)
    service.preview=preview
    window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    window.set_paths([source]);window.tag.setText('XYZ020822');window.preview_button.click()
    window.tag.setText('XYZ020823');settle(app,window)
    assert window.preview is None
    assert threads and threads[0]!=threading.get_ident()
    window.coordinator.close()

def test_dialog_generation_settings_invalidation_and_inbox_payloads(tmp_path):
    from PySide6.QtCore import Qt
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作'/'项目'/'261001_XYZ_测试').mkdir(parents=True)
    folder=root/'0_收件箱'/'图片'/'261001';folder.mkdir(parents=True)
    source=folder/'素材.png';source.write_bytes(b'image')
    service=FileHubService(Config(sync_root=root),tmp_path/'state')
    window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    window.refresh_inbox();settle(app,window)
    assert window.inbox_list.count()==1
    assert window.inbox_list.item(0).data(Qt.UserRole)==str(source)
    dialog=window.open_archive_dialog([source]);dialog.tag.setText('XYZ020822');dialog.request_preview();dialog.tag.setText('XYZ020823');settle(app,window)
    assert dialog.preview is None and not dialog.execute_button.isEnabled()
    dialog.request_preview();settle(app,window);assert dialog.preview
    window.set_paths([source]);window.tag.setText('XYZ020822');window.request_preview();settle(app,window)
    new_root=tmp_path/'new-sync';new_root.mkdir();window.sync_path.setText(str(new_root));window.save_settings();settle(app,window)
    assert window.preview is None and dialog.preview is None and source.exists()
    dialog.reject();window.coordinator.close()

def test_config_save_failure_preserves_service(tmp_path):
    app=QApplication.instance() or QApplication([])
    service=FileHubService(Config(),tmp_path/'state');store=ConfigStore(tmp_path/'state')
    def fail(config):raise OSError('disk full')
    store.save=fail
    window=MainWindow(service,store);settle(app,window);window.appearance.setCurrentIndex(1);window.save_button.click();settle(app,window)
    assert service.config.theme=='dark' and 'disk full' in window.status.text()
    window.coordinator.close()

def test_open_dialog_disabled_before_delayed_save_and_integration_failure(tmp_path):
    from time import sleep
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作'/'项目'/'261001_XYZ_测试').mkdir(parents=True)
    source=tmp_path/'素材.png';source.write_bytes(b'image')
    service=FileHubService(Config(sync_root=root),tmp_path/'state');store=ConfigStore(tmp_path/'state')
    original=store.save
    def delayed(config):sleep(.05);original(config)
    store.save=delayed
    def integration(*args):raise OSError('integration unavailable')
    window=MainWindow(service,store,integration_callback=integration);settle(app,window)
    dialog=window.open_archive_dialog([source]);dialog.tag.setText('XYZ020822');dialog.request_preview();settle(app,window)
    assert dialog.execute_button.isEnabled()
    window.appearance.setCurrentIndex(1);window.save_settings()
    assert dialog.preview is None and not dialog.execute_button.isEnabled()
    settle(app,window)
    assert service.config.theme=='light' and dialog.preview is None and source.exists()
    dialog.reject();window.coordinator.close()

def test_dialog_execute_captures_immutable_preview(tmp_path):
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作'/'项目'/'261001_XYZ_测试').mkdir(parents=True)
    source=tmp_path/'素材.png';source.write_bytes(b'image')
    service=FileHubService(Config(sync_root=root),tmp_path/'state')
    window=MainWindow(service,ConfigStore(tmp_path/'state'));settle(app,window)
    dialog=window.open_archive_dialog([source]);dialog.tag.setText('XYZ020822');dialog.request_preview();settle(app,window)
    captured=[];original=window.coordinator.submit
    window.coordinator.submit=lambda action,*args:captured.append(action)
    dialog.execute();dialog.tag.setText('XYZ020823')
    result=captured[0]()
    assert result.ok and result.label=='XYZ020822' and not source.exists()
    window.coordinator.submit=original;dialog.reject();window.coordinator.close()
