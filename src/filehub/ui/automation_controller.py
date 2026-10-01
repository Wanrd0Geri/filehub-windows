"""GUI adapter for frozen stores/runners; all filesystem work stays on workers."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
import json
from PySide6.QtCore import QObject, Signal
from ..automation.models import MAX_DOCUMENT_BYTES, _unique_object
from ..automation.runner import config_revision
from ..rules import discover_projects
from ..models import checked_path


@dataclass(frozen=True)
class PreviewToken:
    service: object
    state_generation: int
    effective_generation: int
    page_generation: int
    preview: object
    images: bool


class AutomationController(QObject):
    delivered = Signal(object, object, object)
    progressed = Signal(object, object)
    settlement = Signal(object)
    background = Signal(object, object, object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window; self.executor = None; self.accepting = True; self.settled = False
        self.state_generation = 0; self.rule_generation = 0; self.image_generation = 0; self.template_generation = 0
        self.rules_revision = None; self.template_revision = None; self.rules_snapshot = None
        self.jobs = {}; self._retire_callbacks = []
        self.delivered.connect(self._finished); self.progressed.connect(self._progress)
        self.settlement.connect(self._settled)
        self.background.connect(self._background)
        rules, templates, images = window.rules_page, window.templates_page, window.conversion_page
        rules.saveRequested.connect(self.save_rules); rules.importRequested.connect(self.import_rules)
        rules.exportRequested.connect(self.export_rules); rules.previewRequested.connect(self.preview_rule)
        rules.executeRequested.connect(lambda token: self.execute('rules', token))
        rules.cancelRequested.connect(lambda: self.cancel('rules'))
        rules.changed.connect(self.rules_edited)
        templates.saveRequested.connect(self.save_templates); templates.changed.connect(self.templates_edited)
        images.previewRequested.connect(self.preview_images)
        images.executeRequested.connect(lambda token: self.execute('images', token))
        images.cancelRequested.connect(lambda: self.cancel('images'))
        images.changed.connect(lambda: self.cancel('images'))
        self.load()

    def _page(self, kind):
        return self.window.rules_page if kind == 'rules' else self.window.conversion_page

    def _generation(self, kind):
        return self.rule_generation if kind == 'rules' else self.image_generation

    def _bound(self, kind, preview=None, images=False):
        return PreviewToken(self.window.service, self.state_generation, self._generation(kind),
                            self._page(kind).generation, preview, images)

    def _current(self, kind, binding):
        return (binding.service is self.window.service and binding.state_generation == self.state_generation
                and binding.effective_generation == self._generation(kind)
                and binding.page_generation == self._page(kind).generation)

    def load(self):
        service = self.window.service; generation = self.state_generation
        self.window.rules_page.set_busy(True); self.window.templates_page.set_busy(True)
        def read():
            # Lazy executor construction performs recovery/state IO; never on GUI.
            executor = service.conversions
            return service.rules.load(), service.reload_templates(), (
                discover_projects(service.config.sync_root) if service.config.sync_root else {}), executor
        def ready(value):
            if service is not self.window.service or generation != self.state_generation: return
            rules, library, projects, self.executor = value
            self.rules_snapshot = rules; self.rules_revision = rules.revision; self.template_revision = library.revision
            self.window.rules_page.set_watch_roots(service.config.watch_roots)
            self.window.rules_page.set_ruleset(rules); self.window.templates_page.set_library(library)
            self.window.templates_page.set_projects(projects)
            self.window.rules_page.set_busy(False); self.window.templates_page.set_busy(False)
        def failed(message):
            if service is not self.window.service or generation != self.state_generation: return
            self.window.rules_page.show_error(message); self.window.templates_page.show_error(message); self.window.show_error(message)
        self.window.coordinator.submit(read, ready, failed)

    def _store_work(self, kind, work, acknowledged):
        if not self.accepting: return
        service = self.window.service; state = self.state_generation
        page = self.window.rules_page if kind == 'rules' else self.window.templates_page
        page_generation = page.generation if kind == 'rules' else self.template_generation
        page.set_busy(True)
        def ready(value):
            if service is not self.window.service or state != self.state_generation: return
            page.set_busy(False)
            current = page.generation if kind == 'rules' else self.template_generation
            if current != page_generation:
                # Persisted revision advances, but a newer draft is never overwritten.
                if hasattr(value, 'revision'):
                    if kind == 'rules': self.rules_revision = value.revision; self.rules_snapshot = value
                    else: self.template_revision = value.revision
                return
            acknowledged(value)
        def failed(message):
            if service is not self.window.service or state != self.state_generation: return
            page.set_busy(False); page.show_error(message)
        self.window.coordinator.submit(work, ready, failed)

    def _rules_saved(self, snapshot):
        self.rules_snapshot = snapshot; self.rules_revision = snapshot.revision
        self.window.rules_page.set_ruleset(snapshot)
        self.window.status.setText('规则已保存；只有启用且取消暂停的规则会自动执行。')

    def save_rules(self, snapshot):
        service, revision = self.window.service, self.rules_revision
        self.rules_edited()
        self._store_work('rules', lambda: service.rules.save(snapshot, expected_revision=revision), self._rules_saved)

    def import_rules(self, path):
        service, revision = self.window.service, self.rules_revision
        self.rules_edited()
        def read():
            source = checked_path(path)
            if source.stat().st_size > MAX_DOCUMENT_BYTES: raise ValueError('规则文件超过 2 MB 限制')
            with source.open('rb') as stream: data = stream.read(MAX_DOCUMENT_BYTES + 1)
            if len(data) > MAX_DOCUMENT_BYTES: raise ValueError('规则文件超过 2 MB 限制')
            try: document = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object)
            except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
                raise ValueError('规则文件损坏或嵌套过深；当前草稿保持不变') from exc
            return service.rules.import_document(document, expected_revision=revision)
        self._store_work('rules', read, self._rules_saved)

    def export_rules(self, path):
        service = self.window.service
        def write():
            data = json.dumps(service.rules.export_document(), ensure_ascii=False, indent=2, allow_nan=False)
            checked_path(path).write_text(data, encoding='utf-8')
        self._store_work('rules', write, lambda _: self.window.status.setText('规则定义已导出（不含执行记录）。'))

    def save_templates(self, library):
        service, revision = self.window.service, self.template_revision
        self.templates_edited()
        def saved(value):
            self.template_revision = value.revision; self.window.templates_page.set_library(value)
            self.window.status.setText('项目模板已保存。')
        self._store_work('templates', lambda: service.templates.save(library, expected_revision=revision), saved)

    def rules_edited(self):
        self.rule_generation += 1; self.cancel('rules')

    def templates_edited(self):
        self.template_generation += 1
        self.rules_edited(); self.window.rules_page.invalidate_preview(); self.window.invalidate_preview()
        for dialog in self.window.dialogs: dialog.invalidate()

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
        roots = self.window.service.config.watch_roots
        if tuple(map(str, roots)) != self.window.rules_page._watch_roots:
            self.window.rules_page.set_watch_roots(roots)
        service, state = self.window.service, self.state_generation
        self.window.coordinator.submit(lambda: discover_projects(service.config.sync_root) if service.config.sync_root else {},
            lambda projects: self.window.templates_page.set_projects(projects) if service is self.window.service and state == self.state_generation else None,
            self.window.show_error)

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

    def preview_rule(self, request):
        if not self.accepting or self.rules_snapshot is None: return
        if request.generation != self.window.rules_page.generation: return
        rule = next((rule for rule in self.rules_snapshot.rules if rule.id == request.rule_id), None)
        if rule is None or request.ruleset_revision != self.rules_revision:
            self.window.rules_page.show_error('规则已变化，请保存或重新载入后测试'); return
        images = any(action.kind == 'image_convert' for action in rule.actions)
        binding = self._bound('rules', images=images)
        self._start('rules', binding, 'preview',
            lambda completion, progress: self.executor.submit_rule_preview(request.paths, request.rule_id, completion=completion, progress=progress),
            None if images else lambda cancel, progress: binding.service.automation.preview(request.paths, request.rule_id, cancel_event=cancel))

    def preview_images(self, request):
        if not self.accepting or self.executor is None: return
        if request.generation != self.window.conversion_page.generation: return
        binding = self._bound('images', images=True)
        self._start('images', binding, 'preview', lambda completion, progress: self.executor.submit_image_preview(
            request.paths, request.spec, mode=request.mode, output_dir=request.output_dir, completion=completion, progress=progress))

    def execute(self, kind, token):
        if not self.accepting or not isinstance(token, PreviewToken) or not self._current(kind, token):
            self._page(kind).show_error('预览已失效，请重新预览'); return
        submit = (lambda completion, progress: self.executor.submit_images(token.preview, completion=completion, progress=progress)) if kind == 'images' else (
            lambda completion, progress: self.executor.submit_rule(token.preview, completion=completion, progress=progress))
        ordinary = None if token.images else lambda cancel, progress: token.service.automation.execute(token.preview, cancel_event=cancel, progress=progress)
        self._start(kind, token, 'execute', submit, ordinary)

    def _start(self, kind, binding, action, submit, ordinary=None):
        if kind in self.jobs: return
        page = self._page(kind)
        if kind == 'rules': page.set_busy(True, cancellable=True)
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
            self.window.rules_page.progress_label.setText(f"第 {index+1} 项 · {action} · {labels.get(value.get('phase'), '处理')}\n当前对象：{value.get('source', '')}")

    def _finished(self, key, result, error):
        kind, job = key
        if self.jobs.get(kind) is not job: return
        self.jobs.pop(kind); page = self._page(kind); page.set_busy(False)
        if not self._current(kind, job['binding']): return
        if error:
            page.show_error(error); self.window.show_error(error); return
        token = job['binding']
        if job['action'] == 'preview':
            token = PreviewToken(token.service, token.state_generation, token.effective_generation, token.page_generation, result, token.images)
            if kind == 'images':
                rows = [{'source': str(item.source), 'target': str(item.target or ''), 'status': 'error' if item.error else 'ready',
                         'message': item.error or ('原图备份后替换；可从记录撤销' if result.mode == 'replace' else '生成新文件，保留原图')} for item in result.items]
                page.set_preview(rows, token, any(not item.error for item in result.items))
            else: page.set_preview(self.rule_preview_text(result), token, any(plan.ok for plan in result.plans))
        else:
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
        if not self.accepting: return
        self.accepting = False
        self.cancel('rules'); self.cancel('images')
        service = self.window.service
        service.close_conversions(lambda: self.settlement.emit(service))

    def _settled(self, service):
        if service is not self.window.service: return
        self.settled = True
        callbacks, self._retire_callbacks = self._retire_callbacks, []
        for callback in callbacks: callback()

    def rebind(self):
        self.state_generation += 1; self.rule_generation += 1; self.image_generation += 1
        self.executor = None; self.accepting = True; self.settled = False; self.jobs.clear()
        self.window.rules_page.invalidate_preview(); self.window.conversion_page.invalidate_preview(); self.load()
