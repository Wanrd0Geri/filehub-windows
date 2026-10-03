"""Owned Runtime send fixtures for the restored manual tag entry."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from threading import Event
import time
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from filehub.config import Config, ConfigStore
from filehub.integration import SendQueue
from filehub.tag_history import TagHistory
from filehub.ui.app import Runtime, bootstrap
from filehub.ui.archive_dialog import ArchiveDialog
from filehub.ui.file_process_dialog import FileProcessDialog
from rulefile_fixtures import install_archive
from test_app_runtime import settle, cleanup


@pytest.fixture
def legacy(tmp_path):
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'sync';(root/'1_工作/项目/261001_XYZ_测试').mkdir(parents=True)
    state=tmp_path/'state';store=ConfigStore(state)
    config=Config(sync_root=root,paused=False,global_jobs=False)
    store.save(config);TagHistory(state).remember('XYZ020821')
    from filehub.automation.models import Rule,RuleSet,Predicate,Action
    import json
    rule=Rule(id='old-enabled',name='Old enabled rename',enabled=True,
        condition=Predicate('extension','equals','.txt'),actions=(Action('rename',{'pattern':'{stem}_old{ext}'}),))
    (state/'automation-rules.json').write_text(json.dumps(RuleSet((rule,)).to_document()),encoding='utf-8')
    rt=Runtime(bootstrap(state),auto_timers=False,wall_clock=lambda:10,notifier=lambda *args:None,exit_callback=lambda:None)
    settle(app,rt)
    paths=tuple(tmp_path/f'file-{n}.png' for n in range(2))
    for p in paths:p.write_bytes(b'owned image '+p.name.encode())
    yield app,rt,paths,config
    cleanup(app,rt)


def send(app,rt,paths):
    rt.queue.enqueue(paths,now=9);rt.poll();settle(app,rt)
    return rt.claim_dialog


def confirm(app,rt,d):
    d.recovery_button.click();app.processEvents()
    assert d.recovery_dialog is not None
    d.recovery_dialog.button(QMessageBox.Yes).click();settle(app,rt)


def test_legacy_send_opens_tags_then_explicit_recovery_archive_undo(legacy):
    app,rt,paths,config=legacy;d=send(app,rt,paths)
    assert isinstance(d,ArchiveDialog), 'Legacy right click lost manual tag entry'
    assert d.history_chips.tags==('XYZ020821',) and d.paths==paths
    d.tag.setText('XYZ020822');d.request_preview();settle(app,rt)
    assert not rt.service.catalog.path.exists() and d.preview is None
    confirm(app,rt,d)
    snap=rt.service.catalog.load()
    assert snap.compatibility_permissions==frozenset({'manual_archive'})
    assert len(snap.compiled.rules)==1 and not any(snap.enabled.values()) and rt.service.config==config
    assert d.tag.text()=='XYZ020822' and d.paths==paths and d.history_chips.tags==('XYZ020821',)
    d.request_preview();settle(app,rt)
    assert d.preview and all(not item.error for item in d.preview.items)
    assert rt.active_claim and rt.queue.claim(now=11) is None
    d.execute();settle(app,rt)
    assert rt.active_claim is None and rt.queue.claim(now=50) is None
    batch=rt.service.history()[0];assert batch.ok and all(not p.exists() for p in paths)
    assert rt.service.undo(batch.batch_id).ok and all(p.exists() for p in paths)
    assert TagHistory(rt.state_dir).list()==('XYZ020822','XYZ020821')


def test_cancel_tag_window_or_confirmation_never_migrates(legacy):
    app,rt,paths,_=legacy;d=send(app,rt,paths)
    assert isinstance(d,ArchiveDialog)
    d.recovery_button.click();app.processEvents()
    d.recovery_dialog.button(QMessageBox.No).click();settle(app,rt)
    assert not rt.service.catalog.path.exists()
    d.reject();settle(app,rt)
    assert not rt.service.catalog.path.exists() and rt.active_claim is None
    assert all(p.exists() for p in paths) and TagHistory(rt.state_dir).list()==('XYZ020821',)


@pytest.mark.parametrize('permissions',[frozenset(),frozenset({'manual_archive'})])
def test_imported_archive_profile_routes_directly_to_tags(legacy,permissions):
    app,rt,paths,_=legacy;install_archive(rt.service,permissions=permissions)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    assert isinstance(d,ArchiveDialog)
    assert d.recovery_button.isVisible()==(not permissions)
    if not permissions:confirm(app,rt,d)
    d.history_chips.tag_buttons['XYZ020821'].click()
    assert d.tag.text()=='XYZ020821' and d.preview is None
    d.history_chips.remove_buttons['XYZ020821'].click();settle(app,rt)
    assert d.history_chips.tags==()
    rt.window.tag_history.remember('XYZ020822');settle(app,rt)
    d.history_chips.clear_button.click();settle(app,rt)
    assert TagHistory(rt.state_dir).list()==()


def test_old_dialog_signals_cannot_ack_new_claim(legacy):
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt)
    old=send(app,rt,[paths[0]]);old.reject();settle(app,rt)
    new=send(app,rt,[paths[1]])
    old.execution_persisted.emit(object());old.finished.emit(0);settle(app,rt)
    assert rt.claim_dialog is new and rt.active_claim and not rt.claim_handled
    new.accept();settle(app,rt)
    retry=rt.queue.claim(now=11);assert retry and retry.paths==(paths[1],)
    rt.queue.ack(retry.token)


def test_dismissed_preview_callback_does_not_remember_or_resurrect(legacy,monkeypatch):
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    entered=Event();release=Event();original=rt.service.preview
    def delayed(*args):
        result=original(*args);entered.set();release.wait(3);return result
    monkeypatch.setattr(rt.service,'preview',delayed)
    d.tag.setText('XYZ020822');d.request_preview();assert entered.wait(2)
    d.reject();release.set();settle(app,rt)
    assert d.preview is None and TagHistory(rt.state_dir).list()==('XYZ020821',)
    assert not d.isVisible() and rt.active_claim is None


def test_closed_confirmation_cannot_authorize(legacy):
    app,rt,paths,_=legacy;d=send(app,rt,paths)
    assert isinstance(d,ArchiveDialog)
    d.recovery_button.click();app.processEvents();review=d.recovery_dialog
    d.reject();review.button(QMessageBox.Yes).click();settle(app,rt)
    assert not rt.service.catalog.path.exists()


def test_close_after_confirmation_during_barrier_cannot_migrate(legacy):
    app,rt,paths,_=legacy;d=send(app,rt,paths)
    entered=Event();release=Event()
    rt.window.coordinator.submit(lambda:(entered.set(),release.wait(3)),lambda _:None)
    assert entered.wait(2)
    # Request directly to exercise an accepted review waiting behind prior work.
    d.request_recovery();app.processEvents()
    d.recovery_dialog.button(QMessageBox.Yes).click();app.processEvents()
    assert rt.window.automation.management_busy
    d.reject();release.set();settle(app,rt)
    assert not rt.service.catalog.path.exists() and rt.active_claim is None
    assert all(p.exists() for p in paths)


def test_service_rebind_invalidates_old_recovery_and_preview(legacy):
    from filehub.service import FileHubService
    app,rt,paths,_=legacy;d=send(app,rt,paths)
    d.recovery_button.click();app.processEvents();review=d.recovery_dialog;old=rt.service
    new=FileHubService(Config(),old.engine.state_dir/'separate-state')
    rt.window.service=new;rt.window.automation.rebind();rt._service_rebound(new)
    review.button(QMessageBox.Yes).click();settle(app,rt)
    assert not old.catalog.path.exists() and not new.catalog.path.exists()
    assert not d.preview_button.isEnabled() and d.preview is None
    old.close_conversions().wait(5)


def test_same_profile_recovery_preserves_existing_explicit_permissions(legacy):
    app,rt,paths,config=legacy
    install_archive(rt.service,permissions=frozenset({'cleanup'}))
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    confirm(app,rt,d)
    assert rt.service.catalog.load().compatibility_permissions==frozenset({'cleanup','manual_archive'})
    assert rt.service.config==config


def test_multiple_profiles_require_choice_and_explain_switch(legacy):
    import json
    app,rt,paths,_=legacy
    snap=install_archive(rt.service,permissions=frozenset({'cleanup'}))
    doc=snap.packages['legacy-import'].to_document();doc['id']='other-profile';doc['name']='另一个项目方案'
    snap=rt.service.catalog.import_package(json.dumps(doc).encode(),expected_revision=snap.revision)
    snap=rt.service.catalog.bind('other-profile',dict(snap.bindings['legacy-import']),expected_revision=snap.revision)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    assert d.profile_choice.currentData() is None
    d.recovery_button.click();app.processEvents();assert d.recovery_dialog is None
    assert '请选择' in d.details.toPlainText()
    d.profile_choice.setCurrentIndex(2);d.recovery_button.click();app.processEvents()
    assert '另一个项目方案' in d.recovery_dialog.text() and '将关闭' in d.recovery_dialog.text()
    d.recovery_dialog.button(QMessageBox.Yes).click();settle(app,rt)
    snap=rt.service.catalog.load()
    assert snap.compatibility_selection=='other-profile' and snap.compatibility_permissions==frozenset({'manual_archive'})


def test_bound_claim_survives_generic_transfer_and_ignores_old_signals(legacy):
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt);old=send(app,rt,paths)
    generic=rt.window.open_file_dialog(paths);rt.bind_claim_dialog(generic);old.reject()
    rt.window.transfer_archive(generic);settle(app,rt);d=rt.claim_dialog
    assert isinstance(d,ArchiveDialog) and rt.active_claim
    generic.execution_persisted.emit(object());generic.finished.emit(0);settle(app,rt)
    assert rt.claim_dialog is d and rt.active_claim and not rt.claim_handled
    d.reject();settle(app,rt);assert rt.active_claim is None and rt.queue.claim(now=50) is None


def test_plain_open_does_not_read_archive_catalog_and_corrupt_send_falls_back(legacy,monkeypatch):
    from filehub.ui.app import OpenRequests
    app,rt,paths,_=legacy;reads=[];original=rt.service.manual_archive_entry
    def read(*args):reads.append(True);return original(*args)
    monkeypatch.setattr(rt.service,'manual_archive_entry',read)
    rt.window.hide();OpenRequests(rt.state_dir).put();rt.poll();settle(app,rt)
    assert rt.window.isVisible() and reads==[]
    rt.service.catalog.path.write_bytes(b'{broken')
    d=send(app,rt,paths)
    assert isinstance(d,FileProcessDialog) and len(reads)==1 and rt.active_claim
    assert '需要恢复' in rt.window.status.text()
    d.reject();settle(app,rt);assert rt.active_claim is None and all(p.exists() for p in paths)


def test_preview_callback_rejects_effective_authority_change(legacy,monkeypatch):
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    entered=Event();release=Event();original=rt.service.preview
    def delayed(*args):
        result=original(*args);entered.set();release.wait(3);return result
    monkeypatch.setattr(rt.service,'preview',delayed)
    d.tag.setText('XYZ020822');d.request_preview();assert entered.wait(2)
    rt.window.automation.rule_generation+=1
    release.set();settle(app,rt)
    assert d.preview is None and TagHistory(rt.state_dir).list()==('XYZ020821',)


def test_service_change_after_confirmation_waiting_in_barrier_does_not_migrate(legacy):
    from filehub.service import FileHubService
    app,rt,paths,_=legacy;d=send(app,rt,paths);old=rt.service
    entered=Event();release=Event()
    rt.window.coordinator.submit(lambda:(entered.set(),release.wait(3)),lambda _:None)
    assert entered.wait(2)
    d.request_recovery();app.processEvents();d.recovery_dialog.button(QMessageBox.Yes).click();app.processEvents()
    assert rt.window.automation.management_busy
    new=FileHubService(Config(),old.engine.state_dir/'new-state')
    rt.window.service=new;rt.window.automation.rebind();rt._service_rebound(new)
    release.set();settle(app,rt)
    assert not old.catalog.path.exists() and not new.catalog.path.exists() and d.preview is None
    assert not d.isVisible() or not d.preview_button.isEnabled()
    old.close_conversions().wait(5)


def test_quit_after_manual_commit_boundary_retains_durable_ack_without_ui(legacy,monkeypatch):
    from filehub.platform.windows import WindowsPlatform
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,paths)
    d.tag.setText('XYZ020822');d.request_preview();settle(app,rt)
    entered=Event();release=Event();persisted=[];displayed=[];service=rt.service
    class Block(WindowsPlatform):
        def checkpoint(self,stage,item):
            if stage=='before_publish':entered.set();assert release.wait(5)
    service.engine.platform=Block()
    d.execution_persisted.connect(persisted.append)
    monkeypatch.setattr(rt.window,'show_result',displayed.append)
    try:
        d.execute();assert entered.wait(2)
        rt.request_quit();assert service._closing and not rt.closed
        release.set();settle(app,rt)
        assert rt.closed and service.history()[0].ok and all(not p.exists() for p in paths)
        assert len(persisted)==1, 'Quit swallowed the persisted manual result'
        assert rt.queue.claim(now=11) is None, 'Committed archive selection was released for replay'
        assert displayed==[] and not d.isVisible()
    finally:release.set()


def test_partial_restore_reads_actual_catalog_and_allows_explicit_same_window_retry(legacy,monkeypatch):
    app,rt,paths,_=legacy;d=send(app,rt,paths);d.tag.setText('XYZ020822')
    rt.service.migration_error='owned stale migration notice'
    original=rt.service.catalog.set_compatibility;calls=[]
    def fail_once(*args,**kwargs):
        calls.append(True)
        if len(calls)==1:raise OSError('owned injected permission failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(rt.service.catalog,'set_compatibility',fail_once)
    confirm(app,rt,d)
    disk=rt.service.catalog.load()
    assert disk.packages and not disk.compatibility_permissions
    assert rt.window.automation.catalog_snapshot.revision==disk.revision, 'Partial adoption left controller authority stale'
    assert d.entry[0].revision==disk.revision and d.entry[1] is None
    assert rt.service.migration_candidate is None and rt.service.migration_error==''
    assert d.tag.text()=='XYZ020822' and d.paths==paths and d.history_chips.tags==('XYZ020821',)
    assert not d.preview_button.isEnabled() and len(calls)==1
    confirm(app,rt,d)
    assert rt.service.catalog.load().compatibility_permissions==frozenset({'manual_archive'}) and len(calls)==2
    d.request_preview();settle(app,rt);assert d.preview and all(not i.error for i in d.preview.items)


@pytest.mark.parametrize('stale',['service','state'])
def test_durable_manual_callback_from_old_state_cannot_deliver_or_update_ui(legacy,monkeypatch,stale):
    from filehub.service import FileHubService
    app,rt,paths,_=legacy;install_archive(rt.service)
    rt.window.automation.load();settle(app,rt);d=send(app,rt,[paths[0]])
    d.tag.setText('XYZ020822');d.request_preview();settle(app,rt)
    result=rt.service.execute(d.preview);assert result.ok
    persisted=[];displayed=[];d.execution_persisted.connect(persisted.append)
    monkeypatch.setattr(rt.window,'show_result',displayed.append)
    old=rt.service
    if stale=='service':
        new=FileHubService(Config(),rt.state_dir/'different-state');rt.window.service=new
    else:rt.window.automation.state_generation+=1
    try:
        d.finished_result(result)
        assert persisted==displayed==[] and not rt.claim_handled and rt.active_claim is not None
    finally:
        rt.window.service=old
        if stale=='state':rt.window.automation.state_generation-=1
        else:new.close_conversions().wait(5)
