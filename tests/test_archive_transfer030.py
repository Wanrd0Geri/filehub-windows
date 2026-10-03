import time
from threading import Event
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow
from rulefile_fixtures import install_rules
from filehub.automation.models import Rule, Predicate, Action

def pump(app,w):
    end=time.monotonic()+10
    while w.coordinator.pending and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    app.processEvents()
    assert not w.coordinator.pending

def test_transfer_callback_must_not_reopen_dismissed_dialog(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'archive';root.mkdir()
    s=FileHubService(Config(sync_root=root),tmp_path/'state')
    install_rules(s,Rule(id='copy',name='Copy',condition=Predicate('name','glob','*'),actions=(Action('copy',{'destination':str(tmp_path/'out')}),)))
    w=MainWindow(s,ConfigStore(s.engine.state_dir));pump(app,w)
    source=tmp_path/'source.txt';source.write_text('owned fixture')
    dialog=w.open_file_dialog([source])
    entered=Event();release=Event();original=s.archive_context
    def delayed(*args,**kwargs):
        result=original(*args,**kwargs);entered.set();release.wait(3);return result
    monkeypatch.setattr(s,'archive_context',delayed)
    try:
        w.transfer_archive(dialog);assert entered.wait(2)
        dialog.reject();assert dialog not in w.dialogs
        release.set();pump(app,w)
        assert not w.dialogs, 'Canceled generic dialog was reopened as archive by stale transfer callback'
    finally:
        release.set();pump(app,w)
        for d in tuple(w.dialogs):d.reject()
        w.automation.retire(lambda:None)
        end=time.monotonic()+5
        while not w.automation.settled and time.monotonic()<end:app.processEvents();time.sleep(.005)
        pump(app,w);w._close_settled=True;w.close();w.coordinator.close()

def test_transfer_must_not_remove_panel_with_new_execution(tmp_path,monkeypatch):
    import sys
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'archive';root.mkdir()
    s=FileHubService(Config(sync_root=root),tmp_path/'state')
    install_rules(s,Rule(id='copy',name='Copy',condition=Predicate('name','glob','*'),actions=(Action('copy',{'destination':str(tmp_path/'out')}),)))
    w=MainWindow(s,ConfigStore(s.engine.state_dir));pump(app,w)
    source=tmp_path/'source.txt';source.write_text('owned fixture')
    dialog=w.open_file_dialog([source]);dialog.panel.rule_choice.setCurrentIndex(1)
    dialog.panel._preview();pump(app,w);assert dialog.panel.execute_button.isEnabled()
    entered=Event();release=Event();original=s.archive_context;errors=[]
    def delayed(*args,**kwargs):
        result=original(*args,**kwargs);entered.set();release.wait(3);return result
    monkeypatch.setattr(s,'archive_context',delayed)
    monkeypatch.setattr(sys,'excepthook',lambda typ,value,trace:errors.append((typ.__name__,str(value))))
    try:
        w.transfer_archive(dialog);assert entered.wait(2)
        assert not dialog.panel.execute_button.isEnabled()
        assert not dialog.panel.preview_button.isEnabled()
        dialog.panel._execute();assert dialog.kind not in w.automation.jobs
        dialog.panel._preview();assert dialog.kind not in w.automation.jobs
        w.transfer_archive(dialog)  # Duplicate request is ignored.
        release.set();pump(app,w)
        assert source.read_text()=='owned fixture' and not (tmp_path/'out/source.txt').exists()
        assert not errors, 'Committed execution callback failed after transfer removed its panel: '+repr(errors)
    finally:
        release.set();pump(app,w)
        for d in tuple(w.dialogs):d.reject()
        w.automation.retire(lambda:None)
        end=time.monotonic()+5
        while not w.automation.settled and time.monotonic()<end:app.processEvents();time.sleep(.005)
        pump(app,w);w._close_settled=True;w.close();w.coordinator.close()


def test_committed_result_survives_detached_panel_but_not_old_state(tmp_path, monkeypatch):
    app=QApplication.instance() or QApplication([])
    s=FileHubService(Config(),tmp_path/'state')
    install_rules(s,Rule(id='copy',name='Copy',condition=Predicate('name','glob','*'),
        actions=(Action('copy',{'destination':str(tmp_path/'out')}),)))
    w=MainWindow(s,ConfigStore(s.engine.state_dir));pump(app,w)
    source=tmp_path/'source.txt';source.write_text('owned durable fixture')
    dialog=w.open_file_dialog([source]);kind=dialog.kind
    preview=s.automation.preview([source], 'copy')
    binding=w.automation._bound(kind,preview)
    result=s.automation.execute(preview)
    assert result[0].ok and result[0].batch_id
    delivered=[]
    monkeypatch.setattr(w,'show_run_outcomes',lambda *args:delivered.append(args))
    try:
        dialog.reject();assert kind not in w.automation.panels
        job={'binding':binding,'action':'execute'};w.automation.jobs[kind]=job
        w.automation._finished((kind,job),result,None)
        assert len(delivered)==1
        w.automation.state_generation+=1
        w.automation.jobs[kind]=job
        w.automation._finished((kind,job),result,None)
        assert len(delivered)==1
    finally:
        w.automation.retire(lambda:None)
        end=time.monotonic()+5
        while not w.automation.settled and time.monotonic()<end:app.processEvents();time.sleep(.005)
        pump(app,w);w._close_settled=True;w.close();w.coordinator.close()
