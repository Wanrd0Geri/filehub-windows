"""Actual Runtime/manual recovery acceptance in an explicit UUID-owned fixture."""
from pathlib import Path
import json
import sys
import time
from PySide6.QtWidgets import QApplication, QMessageBox
from .config import Config, ConfigStore
from .tag_history import TagHistory


def extend_report(fixture,report):
    from .ui.app import Runtime, bootstrap
    from .ui.archive_dialog import ArchiveDialog
    work=Path(fixture)/'release031';work.mkdir()
    root=work/'sync';(root/'1_工作/项目/261001_XYZ_自检').mkdir(parents=True)
    state=work/'state';config=Config(sync_root=root,paused=False,global_jobs=False)
    ConfigStore(state).save(config);TagHistory(state).remember('XYZ020821')
    from .automation.models import Rule,RuleSet,Predicate,Action
    legacy_rule=Rule(id='old-enabled',name='Owned enabled legacy rule',enabled=True,
        condition=Predicate('extension','equals','.txt'),actions=(Action('rename',{'pattern':'{stem}_old{ext}'}),))
    (state/'automation-rules.json').write_text(json.dumps(RuleSet((legacy_rule,)).to_document()),encoding='utf-8')
    sources=tuple(work/f'owned-{n}.png' for n in range(2))
    for n,source in enumerate(sources):source.write_bytes(b'owned manual acceptance '+str(n).encode())
    originals=tuple(p.read_bytes() for p in sources)
    app=QApplication.instance()
    if not isinstance(app,QApplication):raise ValueError('Manual acceptance requires QApplication')
    checks=report['checks'];details={'work_dir':str(work),'runtime_frozen':bool(getattr(sys,'frozen',False))}
    report['release031']=details
    class Marker:
        def close(self):pass
    rt=None
    def require(value,message):
        if not value:raise ValueError('0.3.1 manual acceptance: '+message)
    def settle():
        end=time.monotonic()+15
        while rt.window.coordinator.pending and time.monotonic()<end:
            app.processEvents();time.sleep(.005)
        app.processEvents();require(not rt.window.coordinator.pending,'worker did not settle')
    try:
        rt=Runtime(bootstrap(state),background=True,auto_timers=False,marker=Marker(),
            wall_clock=lambda:10,notifier=lambda *args:None,exit_callback=lambda:None)
        settle();rt.queue.enqueue(sources,now=9);rt.poll();settle();dialog=rt.claim_dialog
        require(isinstance(dialog,ArchiveDialog) and dialog.paths==sources and not rt.service.catalog.path.exists(),'legacy send tag entry')
        checks['manual_legacy_send_tag_entry']=True
        details.update(dispatch_dialog=type(dialog).__name__,selected_paths=[str(p) for p in sources])
        dialog.tag.setText('XYZ020822');dialog.request_preview();settle()
        require(dialog.preview is None and not rt.service.catalog.path.exists(),'preview granted authority')
        dialog.recovery_button.click();app.processEvents();review=dialog.recovery_dialog
        require(review is not None,'confirmation missing');review.button(QMessageBox.No).click();settle()
        require(not rt.service.catalog.path.exists(),'cancel migrated')
        dialog.recovery_button.click();app.processEvents();dialog.recovery_dialog.button(QMessageBox.Yes).click();settle()
        snapshot=rt.service.catalog.load()
        require(snapshot.compatibility_permissions==frozenset({'manual_archive'}) and len(snapshot.compiled.rules)==1 and not any(snapshot.enabled.values())
            and rt.service.config==config,'manual-only restoration')
        checks['manual_restore_confirmation_only']=True
        details.update(permissions=sorted(snapshot.compatibility_permissions),ordinary_enabled={k:sorted(v) for k,v in snapshot.enabled.items()},config_unchanged=rt.service.config==config)
        require(dialog.tag.text()=='XYZ020822' and dialog.paths==sources and dialog.history_chips.tags==('XYZ020821',),'lost entry/history')
        checks['manual_restore_preserves_history']=True
        details['history_before_preview']=list(dialog.history_chips.tags)
        dialog.request_preview();settle();require(dialog.preview is not None and all(not i.error for i in dialog.preview.items),'real preview')
        require(rt.active_claim is not None and rt.queue.claim(now=11) is None,'ack before commit')
        dialog.execute();settle();batch=rt.service.history()[0]
        require(batch.ok and all(not p.exists() for p in sources) and rt.active_claim is None and rt.queue.claim(now=50) is None,'durable archive/ack')
        checks['manual_real_archive_durable_ack']=True
        details.update(durable_ack=rt.active_claim is None,archive_targets=[str(i.target) for i in batch.items if i.target is not None])
        rt.window.coordinator.submit(lambda:rt.service.undo(batch.batch_id),lambda result:details.update(undo_ok=result.ok))
        settle();require(details.get('undo_ok') and tuple(p.read_bytes() for p in sources)==originals,'undo bytes')
        require(TagHistory(state).list()==('XYZ020822','XYZ020821'),'history not retained')
        details.update(batch_id=batch.batch_id,restored_files=len(sources),history_after_undo=list(TagHistory(state).list()))
        checks['manual_archive_undo']=True
    finally:
        if rt is not None:
            rt.request_quit();settle();require(rt.closed,'owned Runtime did not close')
