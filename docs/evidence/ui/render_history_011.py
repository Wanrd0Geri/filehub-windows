"""Native Qt 0.1.1 evidence: owned sandbox only; no Runtime/registry hooks."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from time import monotonic, sleep
from PySide6.QtWidgets import QApplication
from filehub.ui.app import create_demo
from filehub.ui.main_window import MainWindow
from filehub.ui.theme import apply_theme


app = QApplication([])
evidence = Path(__file__).parent
base = Path('sandbox/task011-history-native').absolute()
with ThreadPoolExecutor(max_workers=1) as worker:
    service, store, paths = worker.submit(create_demo, base).result()
w = MainWindow(service, store)
w.is_demo = True;w.load_config_controls();w.set_paths(paths);w.tag.setText('DEMO020822');w.show()


def settle():
    end = monotonic() + 10
    while w.coordinator.pending and monotonic() < end:
        app.processEvents();sleep(.01)
    for _ in range(8):app.processEvents();sleep(.02)
    assert not w.coordinator.pending


def seed():
    for n in range(3):
        source = paths[0].parent / f'记录素材{n}.txt'
        source.write_text(f'owned screenshot fixture {n}', encoding='utf-8')
        assert service.execute(service.preview([source], f'DEMO0208{n+1:03}')).ok
    for n in range(57):
        tag = f'DEMO0208{n+1:03}'
        assert any(not item.error for item in service.preview(paths, tag).items)
        w.tag_history.store.remember(tag)
    w.tag_history.store.remember('DEMO角色文件夹口令示例很长但完整内容仍可通过提示查看')
    return service.history()


settle();w.coordinator.submit(seed,w.show_history,w.show_error);settle()
w.tag_history.refresh();settle();w.request_preview();settle()
metadata = []
for theme in ('dark','light'):
    service.config = replace(service.config, theme=theme)
    apply_theme(w,theme)
    for width,height in ((1000,700),(800,620)):
        w.resize(width,height);w.status.setText('');settle()
        name = f'history-011-{theme}-{width}x{height}.png'
        w.grab().save(str(evidence/name))
        metadata.append(f'{name}: logical={w.width()}x{w.height()} DPR={w.devicePixelRatioF()} tags={len(w.tag_history.tags)} recent={w.recent_list.count()}')
    w.status.setText('操作未完成：存在冲突，请检查完整路径。\n'+'\n'.join('已有副本完整路径：'+str(store.state_dir.parent/'同步空间'/('完整目录名称'*12)/f'文件{n}.png') for n in range(25)))
    w.home_scroll.ensureWidgetVisible(w.history_chips,0,20);settle()
    w.grab().save(str(evidence/f'history-011-small-history-long-footer-{theme}.png'))
    w.home_scroll.verticalScrollBar().setValue(w.home_scroll.verticalScrollBar().maximum());settle()
    w.grab().save(str(evidence/f'history-011-small-recent-long-footer-{theme}.png'))
    w.status.setText('');w.home_scroll.verticalScrollBar().setValue(0);settle()
    d = w.open_archive_dialog(paths);d.tag.setText('DEMO020822');d.request_preview();settle()
    d.grab().save(str(evidence/f'history-011-dialog-{theme}.png'))
    d.reject();settle()
    w.navigate(3);w.status.setText('设置已保存。');settle()
    w.grab().save(str(evidence/f'history-011-settings-footer-{theme}.png'))
    w.status.setText('操作未完成：存在冲突，请检查完整路径。\n'+'\n'.join('已有副本完整路径：'+str(store.state_dir.parent/'同步空间'/('完整目录名称'*12)/f'文件{n}.png') for n in range(25)))
    settle();w.grab().save(str(evidence/f'history-011-long-footer-{theme}.png'))
    metadata.append(f'{theme} footer height={w.status_footer.height()} scroll maximum={w.status_footer.verticalScrollBar().maximum()} chars={len(w.status.text())}')
    w.navigate(0)
(evidence/'history-011-native-state.txt').write_text('platform='+app.platformName()+'\nstate='+str(store.state_dir)+'\n'+'\n'.join(metadata)+'\n',encoding='utf-8')
w.close();w.coordinator.close()
