"""Native Qt evidence; run from workspace with its .venv Python."""
from pathlib import Path
from time import monotonic,sleep
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from filehub.ui.main_window import MainWindow
from filehub.ui.app import create_demo
from filehub.ui.theme import apply_theme
from filehub.service import FileHubService
from filehub.config import Config,ConfigStore

app=QApplication([])
base=Path('sandbox/task5-ui-render').absolute();evidence=Path('docs/evidence/ui').absolute()
service,store,paths=create_demo(base)
window=MainWindow(service,store,demo_callback=lambda:create_demo(base));window.show()
def settle():
    end=monotonic()+10
    while window.coordinator.pending and monotonic()<end:app.processEvents();sleep(.01)
    for _ in range(10):app.processEvents();sleep(.02)
def capture(name):
    settle();window.grab().save(str(evidence/(name+'.png')))
settle();window.set_paths(paths);window.tag.setText('DEMO020822');window.preview_button.click();settle()
capture('dark-main')
dialog=window.open_archive_dialog(paths);dialog.tag.setText('DEMO020822');dialog.preview_button.click();settle();dialog.grab().save(str(evidence/'archive-preview.png'));dialog.reject()
window.execute_button.click();settle();capture('dark-main');window.navigate(2);window.history_list.setCurrentRow(0);capture('records')
window.navigate(3);capture('settings')
window.navigate(0);apply_theme(window,'light');capture('light-main')
first=MainWindow(FileHubService(Config(),base/'first-state'),ConfigStore(base/'first-state'));first.show()
while first.coordinator.pending:app.processEvents();sleep(.01)
app.processEvents();first.grab().save(str(evidence/'first-run.png'))
first.close();first.coordinator.close();window.close();window.coordinator.close()
