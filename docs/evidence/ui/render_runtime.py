"""Native Windows runtime evidence using isolated demo fixtures."""
from pathlib import Path
from time import monotonic, sleep
from PySide6.QtWidgets import QApplication
from filehub.ui.app import bootstrap, Runtime

app=QApplication([])
base=Path('sandbox/task5-runtime-render').absolute()
evidence=Path(__file__).parent
bundle=bootstrap(base,demo=True)
runtime=Runtime(bundle,auto_timers=False,notifier=lambda *args:None,exit_callback=lambda:None)
def settle():
    end=monotonic()+10
    while runtime.window.coordinator.pending and monotonic()<end:
        app.processEvents();sleep(.01)
    for _ in range(10):app.processEvents();sleep(.02)
    assert not runtime.window.coordinator.pending
settle()
runtime.window.grab().save(str(evidence/'runtime-demo.png'))
runtime.window.navigate(3);settle()
runtime.window.grab().save(str(evidence/'runtime-settings.png'))
runtime.window.navigate(0)
runtime.queue.enqueue(bundle.demo_paths,now=runtime.wall_clock()-1)
runtime.poll();settle()
assert runtime.claim_dialog and runtime.active_claim
runtime.claim_dialog.tag.setText('DEMO020822')
runtime.claim_dialog.preview_button.click();settle()
runtime.claim_dialog.grab().save(str(evidence/'runtime-claimed-dialog.png'))
(evidence/'runtime-state.txt').write_text(
    f'platform={app.platformName()}\ndemo={runtime.demo}\npaused={runtime.service.config.paused}\n'
    f'tray_tooltip={runtime.tray.toolTip()}\nclaim_unacked={bool(runtime.active_claim)}\n',encoding='utf-8')
runtime.request_quit();settle()
assert runtime.closed
