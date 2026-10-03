"""GUI adapter for frozen stores/runners; all filesystem work stays on workers."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
import json
from PySide6.QtCore import QObject, Signal
from ..automation.models import MAX_DOCUMENT_BYTES, _unique_object
from ..automation.runner import config_revision
from .rulefile_dialogs import ReplacementReview, ReviewDialog, BindingDialog, CompatibilityDialog
from ..rulefiles.protocol import parse_package
from ..rulefiles.catalog import compare_packages
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from dataclasses import replace
import sys
from ..models import checked_path


@dataclass(frozen=True)
class PreviewToken:
    service: object
    state_generation: int
    effective_generation: int
    page_generation: int
    preview: object
    images: bool
    owner: str = ''


class AutomationController(QObject):
    delivered = Signal(object, object, object)
    progressed = Signal(object, object)
    settlement = Signal(object)
    background = Signal(object, object, object)
    management_idle = Signal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window; self.executor = None; self.accepting = True; self.settled = False
        self.state_generation = 0; self.rule_generation = 0; self.image_generation = 0; self.template_generation = 0
        self.rules_revision = None; self.template_revision = None; self.rules_snapshot = None
        self.jobs = {}; self._retire_callbacks = []; self._retirement_started = False
        self.delivered.connect(self._finished); self.progressed.connect(self._progress)
        self.settlement.connect(self._settled)
        self.background.connect(self._background)
        self.catalog_snapshot=None;self.management_busy=False;self.panels={'rules':window.rules_page,'home':window.home_panel,'images':window.conversion_page}
        self.management_idle.connect(self._management_settled)
        for kind in ('rules','home'):self.register_panel(self.panels[kind],kind)
        window.rules_page.managementRequested.connect(self.manage);window.rules_page.helpRequested.connect(self.open_help)
        images=window.conversion_page;images.previewRequested.connect(self.preview_images)
        images.executeRequested.connect(lambda token:self.execute('images',token));images.cancelRequested.connect(lambda:self.cancel('images'));images.changed.connect(lambda:self.cancel('images'))
        self.load()

    def register_panel(self,panel,kind):
        self.panels[kind]=panel
        panel.previewRequested.connect(lambda request:self.preview_rule(request,kind))
        panel.executeRequested.connect(lambda token:self.execute(kind,token));panel.cancelRequested.connect(lambda:self.cancel(kind));panel.changed.connect(lambda:self.cancel(kind))

    def _page(self,kind):return self.panels[kind]

    def _generation(self, kind):
        return self.image_generation if kind == 'images' else self.rule_generation

    def _bound(self, kind, preview=None, images=False):
        return PreviewToken(self.window.service, self.state_generation, self._generation(kind),
                            self._page(kind).generation, preview, images, kind)

    def _current(self, kind, binding):
        return (kind in self.panels and binding.owner==kind and binding.service is self.window.service and binding.state_generation == self.state_generation
                and binding.effective_generation == self._generation(kind)
                and binding.page_generation == self._page(kind).generation)

    def load(self):
        service=self.window.service;state=self.state_generation;self.window.rules_page.set_busy(True)
        def read():
            executor=service.conversions
            try:return executor,service.catalog.load(),None
            except ValueError as exc:return executor,None,str(exc)
        def ready(value):
            if service is not self.window.service or state!=self.state_generation:return
            self.executor,snapshot,error=value;self.window.rules_page.set_busy(False)
            if snapshot is not None:self._rules_saved(snapshot)
            else:
                self.catalog_snapshot=None;self.rules_snapshot=None;self.rules_revision=None
                self.window.rules_page.notice.setText('规则目录需要恢复：'+error);self.window.rules_page.show_error(error)
            notice=service.migration_error or ('检测到旧定义；确认迁移后全部关闭，原始定义保留。' if service.migration_candidate else '')
            if notice:self.window.rules_page.notice.setText(notice)
        def failed(message):
            if service is self.window.service and state==self.state_generation:self.window.rules_page.set_busy(False);self.window.show_error(message)
        self.window.coordinator.submit(read,ready,failed)

    def _rules_saved(self,snapshot):
        self.catalog_snapshot=snapshot;self.rules_snapshot=snapshot.compiled;self.rules_revision=snapshot.revision
        self.window.rules_page.set_ruleset(snapshot.compiled);self.window.rules_page.set_catalog(snapshot)
        self.window.archive_button.setVisible(bool(snapshot.compatibility_selection and 'manual_archive' in snapshot.compatibility_permissions))
        self.window.first_run.setVisible(not snapshot.packages)
        for kind,panel in self.panels.items():
            if kind not in ('rules','images'):panel.set_ruleset(snapshot.compiled)
        self.window.rules_page.notice.setText('规则文件已更新；导入、替换、恢复后全部关闭。绑定不会添加观察目录。')

    def _read_work(self,work,ready):
        service=self.window.service;state=self.state_generation
        def current(value):
            if service is self.window.service and state==self.state_generation:ready(value)
        def failed(message):
            if service is self.window.service and state==self.state_generation:self.window.rules_page.show_error(message)
        self.window.coordinator.submit(work,current,failed)

    def mutate(self,work,*,service=None,state_generation=None,on_complete=None,on_error=None):
        if ((service is not None and service is not self.window.service)
                or (state_generation is not None and state_generation!=self.state_generation)):
            self.window.rules_page.show_error('此管理窗口属于已结束的状态，请关闭后重新操作。');return
        if not self.accepting or self.management_busy:return
        self.management_busy=True;self.accepting=False;self.rule_generation+=1;self.image_generation+=1
        for kind,panel in self.panels.items():self.cancel(kind);panel.invalidate_preview();panel.set_busy(True)
        self.window.invalidate_preview()
        for dialog in tuple(self.window.dialogs):dialog.invalidate()
        self.window.coordinator.begin_wait()
        service=self.window.service;state=self.state_generation
        def barrier():
            if self.executor:self.executor.cancel();self.executor.when_idle(lambda:self.management_idle.emit((service,state,work,on_complete,on_error)))
            else:self.management_idle.emit((service,state,work,on_complete,on_error))
        # Ordinary work before this FIFO barrier finishes first. Image queue has an independent idle barrier.
        self.window.coordinator.submit(barrier,lambda _:None,self.window.show_error,lifecycle=True)

    def _management_settled(self,payload):
        service,state,work,on_complete,on_error=payload
        if service is not self.window.service or state!=self.state_generation or self.window._quit_requested:
            self.window.coordinator.end_wait();return
        def done(snapshot=None,error=None):
            if service is not self.window.service or state!=self.state_generation:
                self.window.coordinator.end_wait();return
            self.management_busy=False;self.accepting=not self.window._quit_requested and not self.window._close_requested
            for panel in self.panels.values():panel.set_busy(False)
            if snapshot is not None:
                self._rules_saved(snapshot);self.window.status.setText('规则文件已更新，请重新预览。')
            if error:self.window.rules_page.show_error(error)
            self.window.coordinator.end_wait()
            if snapshot is not None and on_complete:on_complete(snapshot)
            if error and on_error:on_error(error)
        self.window.coordinator.submit(work,lambda value:done(value),lambda error:done(error=error),lifecycle=True)

    def _read_package(self,path):
        with checked_path(path).open('rb') as stream:data=stream.read(MAX_DOCUMENT_BYTES+1)
        parse_package(data);return data

    def manage(self,intent):
        if not self.accepting:return
        operation,key,value=intent;service=self.window.service;state=self.state_generation;snapshot=self.catalog_snapshot
        commit=lambda work:self.mutate(work,service=service,state_generation=state)
        if operation=='restore':self._read_work(lambda:(service.catalog.list_backups(),service.catalog.recovery_revision()),self._restore_review);return
        if operation=='import':
            if snapshot is None:self.window.rules_page.show_error('请先恢复规则目录');return
            revision=snapshot.revision
            self._read_work(lambda:self._read_package(value),lambda data:commit(lambda:service.catalog.import_package(data,str(value),expected_revision=revision)));return
        if snapshot is None:self.window.rules_page.show_error('请先恢复规则目录');return
        revision=snapshot.revision
        if operation=='migration':
            candidate=service.migration_candidate
            if candidate is None:self.window.rules_page.show_error(service.migration_error or '没有待迁移旧定义');return
            text='将保留旧规则身份、目录绑定与历史。迁移后所有规则关闭；兼容档案未选择、权限关闭。原始文件单独完整备份。\n'+'\n'.join(p.name+' · '+str(len(p.rules))+' 条' for p in candidate.packages)+'\n'+'\n'.join(candidate.warnings)
            dialog=ReviewDialog(self.window,'迁移旧定义',text)
            def adopt():
                def work():
                    result=service.catalog.adopt_legacy(candidate,expected_revision=revision);service.migration_candidate=None;service.migration_error='';return result
                commit(work)
            dialog.accepted.connect(adopt);dialog.show();self.review_dialog=dialog;return
        if operation=='compatibility':
            dialog=CompatibilityDialog(self.window,snapshot)
            def grant():
                selected,permissions=dialog.values()
                def work():
                    if selected is not None and permissions:
                        prospective=replace(snapshot,compatibility_selection=selected,compatibility_permissions=permissions)
                        service.archive_context(permission=None,snapshot=prospective)
                    return service.catalog.set_compatibility(selected,permissions,expected_revision=revision)
                commit(work)
            dialog.accepted.connect(grant);dialog.show();self.review_dialog=dialog;return
        if key is None:self.window.rules_page.show_error('请选择规则文件');return
        if operation in ('replace','reload'):
            path=value if operation=='replace' else snapshot.sources[key]
            if not path:self.window.rules_page.show_error('此文件没有来源路径，请选择替换文件');return
            def prepare():
                data=self._read_package(path);new=parse_package(data)
                return ReplacementReview(key,data,str(path),revision,compare_packages(snapshot.packages[key],new),snapshot.packages[key],new)
            self._read_work(prepare,self._replace_review)
        elif operation=='bind':
            dialog=BindingDialog(self.window,snapshot.packages[key],snapshot.bindings[key])
            def save_binding():
                values=dialog.values()
                commit(lambda:service.catalog.bind(key,values,expected_revision=revision))
            dialog.accepted.connect(save_binding);dialog.show();self.review_dialog=dialog
        elif operation=='toggle':
            runtime_id=self.window.rules_page.selected_id
            external=next((r for r,i in snapshot.runtime_ids[key].items() if i==runtime_id),None)
            if external is None:self.window.rules_page.show_error('请选择此文件中的可用规则');return
            commit(lambda:service.catalog.set_enabled(key,external,external not in snapshot.enabled[key],expected_revision=revision))
        elif operation=='order':
            order=list(snapshot.order);index=order.index(key);target=index+value
            if 0<=target<len(order):order[index],order[target]=order[target],order[index];commit(lambda:service.catalog.reorder(tuple(order),expected_revision=revision))
        elif operation=='remove':
            dialog=ReviewDialog(self.window,'移除规则文件',snapshot.packages[key].name+'\n移除 '+str(len(snapshot.packages[key].rules))+' 条定义；历史、备份与已执行文件保留。')
            dialog.accepted.connect(lambda:commit(lambda:service.catalog.remove(key,expected_revision=revision)));dialog.show();self.review_dialog=dialog
        elif operation=='export':
            self._read_work(lambda:checked_path(value).write_bytes(service.catalog.export_package(key)),lambda _:self.window.status.setText('已导出可移植定义，不含本机路径或执行记录。'))

    def _replace_review(self,review):
        service=self.window.service;state=self.state_generation
        commit=lambda work:self.mutate(work,service=service,state_generation=state)
        dialog=ReviewDialog(self.window,'核对替换规则文件',review.text());dialog.review=review
        dialog.accepted.connect(lambda:commit(lambda:service.catalog.replace_package(review.package_id,review.data,review.source,expected_revision=review.expected_revision)))
        dialog.show();self.review_dialog=dialog

    def _restore_review(self,value):
        backups,revision=value
        if not backups:self.window.rules_page.show_error('没有可验证的目录备份');return
        dialog=ReviewDialog(self.window,'恢复规则定义','仅恢复定义与目录绑定；所有规则和兼容权限关闭，不撤销已执行的文件操作。')
        from PySide6.QtWidgets import QComboBox
        choice=QComboBox();dialog.layout().insertWidget(1,choice)
        for backup in backups:choice.addItem(backup.created+' · '+('、'.join(backup.package_names) or '空目录'),backup.id)
        def selected(index):dialog.details.setPlainText('仅恢复定义与目录绑定，所有规则和兼容权限关闭。\n'+backups[index].summary)
        choice.currentIndexChanged.connect(selected);selected(0)
        service=self.window.service;state=self.state_generation
        commit=lambda work:self.mutate(work,service=service,state_generation=state)
        def restore():
            identifier=choice.currentData()
            commit(lambda:service.catalog.restore(identifier,expected_revision=revision))
        dialog.accepted.connect(restore);dialog.show();self.review_dialog=dialog

    def open_help(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[3]));path=root/('help' if getattr(sys,'frozen',False) else 'docs')/'AI规则编写指南.md'
        def ready(exists):
            if exists and QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):return
            message=('系统未能打开指南，请复制下方本地路径后手动打开。' if exists else '未找到本地指南，请检查安装包中的帮助文件。')+'\n'+str(path)
            dialog=ReviewDialog(self.window,'AI 编写指南',message);dialog.accept_button.setText('关闭');dialog.show();self.review_dialog=dialog
        self._read_work(path.is_file,ready)

    def rules_edited(self):
        self.rule_generation+=1
        for kind in tuple(self.jobs):
            if kind!='images':self.cancel(kind)

    def config_requested(self, old, new):
        structural = config_revision(old, ignore_paused=True, ignore_theme=True) != config_revision(new, ignore_paused=True, ignore_theme=True)
        paused = old.paused != new.paused
        if structural:
            self.rule_generation += 1; self.image_generation += 1
            self.cancel('rules'); self.cancel('images')
            if self.executor: self.executor.cancel()
            self.window.rules_page.invalidate_preview(); self.window.conversion_page.invalidate_preview()
        elif paused:
            self.rule_generation += 1; self.cancel('rules'); self.window.rules_page.invalidate_preview()
            if new.paused and self.executor: self.executor.cancel_automatic()
        # Theme is a diagnostic change only; it does not revoke authority.

    def config_saved(self):
        self.window.rules_page.set_watch_roots(self.window.service.config.watch_roots)
        for kind,panel in self.panels.items():
            if kind!='images':panel.invalidate_preview()

    def cancel(self, kind):
        job = self.jobs.get(kind)
        if job:
            with job['lock']: job['cancel'].set()
            self._page(kind).set_cancel_pending(True)

    def completion_hook(self, service=None, generation=None):
        service = service or self.window.service
        generation = self.state_generation if generation is None else generation
        effective_generation = self.rule_generation
        def complete(future):
            try: result, error = future.result(), None
            except Exception as exc: result, error = (), str(exc)
            self.background.emit((service, generation, effective_generation), result, error)
        return complete

    def _background(self, binding, outcomes, error):
        service, generation, effective_generation = binding
        if service is not self.window.service or generation != self.state_generation: return
        if effective_generation != self.rule_generation:
            # Revoked authority may already have safely committed a critical item.
            # Refresh its durable history, without delivering obsolete result UI.
            self.window.refresh(); return
        if error:
            self.window.show_error(error); self.window.automation_error.emit(error); self.window.refresh()
        else:
            errors = [outcome.error for outcome in outcomes if outcome.error]
            if errors: self.window.automation_error.emit('；'.join(errors[:3]))
            self.window.show_run_outcomes(outcomes, service, generation)

    def preview_rule(self, request, kind="rules"):
        if (not self.accepting or self.rules_snapshot is None or kind not in self.panels
                or getattr(self.panels[kind],'_transfer_pending',False)): return
        if request.generation != self._page(kind).generation: return
        rule = next((rule for rule in self.rules_snapshot.rules if rule.id == request.rule_id), None)
        if (rule is None and request.rule_id is not None) or request.ruleset_revision != self.rules_revision:
            self._page(kind).show_error('规则已变化，请重新载入后测试'); return
        images = any(action.kind == 'image_convert' for item in ([rule] if rule else self.rules_snapshot.rules if self.rules_snapshot else ()) for action in item.actions)
        binding = self._bound(kind, images=images)
        self._start(kind, binding, 'preview',
            lambda completion, progress: self.executor.submit_rule_preview(request.paths, request.rule_id, completion=completion, progress=progress),
            None if images else lambda cancel, progress: binding.service.automation.preview(request.paths, request.rule_id, cancel_event=cancel))

    def preview_images(self, request):
        if not self.accepting or self.executor is None: return
        if request.generation != self.window.conversion_page.generation: return
        binding = self._bound('images', images=True)
        self._start('images', binding, 'preview', lambda completion, progress: self.executor.submit_image_preview(
            request.paths, request.spec, mode=request.mode, output_dir=request.output_dir, completion=completion, progress=progress))

    def execute(self, kind, token):
        if kind in self.panels and getattr(self.panels[kind],'_transfer_pending',False):return
        if not self.accepting or not isinstance(token, PreviewToken) or not self._current(kind, token):
            self.panels.get(kind,self.window.rules_page).show_error('预览已失效，请重新预览'); return
        submit = (lambda completion, progress: self.executor.submit_images(token.preview, completion=completion, progress=progress)) if kind == 'images' else (
            lambda completion, progress: self.executor.submit_rule(token.preview, completion=completion, progress=progress))
        ordinary = None if token.images else lambda cancel, progress: token.service.automation.execute(token.preview, cancel_event=cancel, progress=progress)
        self._start(kind, token, 'execute', submit, ordinary)

    def _start(self, kind, binding, action, submit, ordinary=None):
        if kind in self.jobs: return
        page = self._page(kind)
        if kind != 'images': page.set_busy(True, cancellable=True)
        else: page.set_busy(True)
        job = {'binding': binding, 'action': action, 'cancel': Event(), 'lock': RLock()}; self.jobs[kind] = job
        def progress(value): self.progressed.emit((kind, job), value)
        def completion(future):
            try: result, error = future.result(), None
            except Exception as exc: result, error = None, str(exc)
            self.delivered.emit((kind, job), result, error)
        if ordinary:
            self.window.coordinator.submit(lambda: ordinary(job['cancel'], progress),
                lambda result: self._finished((kind, job), result, None),
                lambda error: self._finished((kind, job), None, error))
        else:
            def enqueue():
                # A very fast Future may invoke its completion synchronously in
                # add_done_callback. Submit on a worker so even that result()
                # stays off the GUI; image work itself remains on its own queue.
                handle = submit(completion, progress)
                with job['lock']:
                    if job['cancel'].is_set(): handle.cancel_event.set()
                    job['cancel'] = handle.cancel_event
            self.window.coordinator.submit(enqueue, lambda _: None,
                lambda message: self._finished((kind, job), None, message))

    def _progress(self, key, value):
        kind, job = key
        if self.jobs.get(kind) is not job or not self._current(kind, job['binding']): return
        if kind == 'images':
            # Only final runner outcomes mark success; even backend whole-item progress is transient.
            data = dict(value); data.pop('status', None); self.window.conversion_page.set_progress(data)
        else:
            labels = {'start': '准备', 'decoded': '读取', 'encoded': '编码', 'verified': '验证', 'committing': '保存/替换', 'complete': '等待最终结果'}
            action = '动作 ' + str(value.get('step_index', 0)+1)
            preview = job['binding'].preview; index = value.get('index', 0); step_index = value.get('step_index', 0)
            if preview and 0 <= index < len(preview.plans):
                plan = preview.plans[index]
                rule = next((rule for rule in self.rules_snapshot.rules if rule.id == plan.rule_id), None)
                if rule and 0 <= step_index < len(plan.steps):
                    kind = rule.actions[plan.steps[step_index].action_index].kind
                    action += ' · ' + {'image_convert':'图片转换','rename':'重命名','move':'移动','copy':'复制','subfolder':'子文件夹','project_route':'送进项目'}.get(kind, '处理')
            self._page(key[0]).progress_label.setText(f"第 {index+1} 项 · {action} · {labels.get(value.get('phase'), '处理')}\n当前对象：{value.get('source', '')}")

    def _finished(self, key, result, error):
        kind, job = key
        if self.jobs.get(kind) is not job: return
        self.jobs.pop(kind); page = self.panels.get(kind)
        if page is not None:page.set_busy(False)
        if not self._current(kind, job['binding']):
            binding=job['binding']
            if (job['action']=='execute' and not error and result and binding.service is self.window.service
                    and binding.state_generation==self.state_generation and any(outcome.batch_id for outcome in result)):
                # Revoking preview authority must not lose a result already committed
                # by the same owned service. No old preview or progress is installed.
                self.window.show_run_outcomes(result,binding.service,binding.state_generation)
                if page is not None and hasattr(page,'execution_persisted'):page.execution_persisted.emit(result)
            return
        if error:
            page.show_error(error); self.window.show_error(error); return
        token = job['binding']
        if job['action'] == 'preview':
            token = PreviewToken(token.service, token.state_generation, token.effective_generation, token.page_generation, result, token.images, token.owner)
            if kind == 'images':
                rows = [{'source': str(item.source), 'target': str(item.target or ''), 'status': 'error' if item.error else 'ready',
                         'message': item.error or ('原图备份后替换；可从记录撤销' if result.mode == 'replace' else '生成新文件，保留原图')} for item in result.items]
                page.set_preview(rows, token, any(not item.error for item in result.items))
            else: page.set_preview(self.rule_preview_text(result), token, any(plan.ok for plan in result.plans))
        else:
            if hasattr(page,'_can_execute'):page._can_execute=False;page._token=None
            if kind == 'images':
                by_source = {str(outcome.source).casefold(): outcome for outcome in result}
                for index, item in enumerate(token.preview.items):
                    outcome = by_source.get(str(item.source).casefold())
                    status = 'success' if outcome and outcome.ok else 'error' if outcome else 'canceled'
                    message = outcome.error if outcome else '已取消，未开始此项'
                    page.set_progress({'index': index, 'status': status, 'message': message})
            else:
                statuses = {'success':'已完成','partial':'部分完成','failed':'未完成','skipped':'已跳过','canceled':'已取消','cancelled':'已取消','review_required':'需要核对记录'}
                page.progress_label.setText('\n'.join(f'{outcome.source}：' + statuses.get(outcome.status,'需要查看') + (' · ' + outcome.error if outcome.error else '') for outcome in result) or '已取消，未开始执行')
            self.window.show_run_outcomes(result, token.service, token.state_generation)
            if hasattr(page,"execution_persisted") and any(outcome.batch_id for outcome in result):page.execution_persisted.emit(result)

    def rule_preview_text(self, preview):
        labels = {'rename': '重命名', 'move': '移动', 'copy': '复制', 'subfolder': '放入子文件夹', 'image_convert': '图片转换', 'project_route': '送进项目'}
        rows = []
        def explanation(node, depth=0):
            lines = [('  ' * depth) + node.reason]
            for child in node.children: lines.extend(explanation(child, depth+1))
            return lines
        # Backend snapshots retain all match/nonmatch/unavailable explanations.
        # Do not evaluate conditions again in the GUI.
        for index, match in enumerate(preview.matching):
            lines = [f'样本 {index+1} · 条件核对']
            for evaluation in match.evaluations:
                lines.append('规则：' + evaluation.rule_name)
                if evaluation.explanation: lines.extend(explanation(evaluation.explanation))
                else: lines.append(evaluation.reason)
            rows.append('\n'.join(lines))
        for plan in preview.plans:
            lines = ['来源：' + str(plan.original_path)]
            if plan.explanation: lines.extend(explanation(plan.explanation))
            rule = next((rule for rule in self.rules_snapshot.rules if rule.id == plan.rule_id), None)
            for step in plan.steps:
                mode = '（备份原图后替换，可撤销）' if step.replaces_original else '（生成新图，保留原图）' if step.generates_content else ''
                kind = rule.actions[step.action_index].kind if rule is not None else step.kind
                lines.append(f'{step.action_index+1}. {labels.get(kind, kind)}{mode}\n{step.source} → {step.target}')
            lines.extend('问题：' + error for error in plan.errors); lines.extend('提示：' + warning for warning in plan.warnings)
            rows.append('\n'.join(lines))
        return '\n\n'.join(rows + list(preview.errors)) or '没有可执行的匹配项。预览不会移动或转换文件。'

    def retire(self, callback):
        self._retire_callbacks.append(callback)
        if self.settled: self._settled(self.window.service); return
        if self._retirement_started: return
        self._retirement_started = True; self.accepting = False
        for kind in tuple(self.jobs):self.cancel(kind)
        service = self.window.service
        service.close_conversions(lambda: self.settlement.emit(service))

    def _settled(self, service):
        if service is not self.window.service: return
        self.settled = True
        callbacks, self._retire_callbacks = self._retire_callbacks, []
        for callback in callbacks: callback()

    def rebind(self):
        self.state_generation += 1; self.rule_generation += 1; self.image_generation += 1
        self.executor = None; self.accepting = not self.window._quit_requested; self.settled = False; self._retirement_started = False; self.jobs.clear()
        self.window.rules_page.invalidate_preview(); self.window.conversion_page.invalidate_preview()
        if self.accepting:self.load()
