"""Snapshot-driven rule drafting. Controller acknowledges saves via set_ruleset."""
from dataclasses import replace
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QListWidget, QListWidgetItem, QTextEdit, QPushButton, QScrollArea, QFileDialog)
from ..automation.models import RuleSet, Rule, Predicate, Action, absolute_folder
from .condition_editor import ConditionEditor
from .action_editor import ActionEditor
from .rule_requests import RulePreviewRequest
from .compact_message import CompactMessage


class RulesPage(QWidget):
    saveRequested = Signal(object)
    importRequested = Signal(str)
    exportRequested = Signal(str)
    previewRequested = Signal(object)
    executeRequested = Signal(object)
    checkRequested = Signal()
    cancelRequested = Signal()
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self._ruleset = RuleSet(); self._selected_id = None
        self._loading = False; self._dirty = False; self._generation = 0
        self._preview_token = None; self._can_execute = False; self._busy = False; self._sample_paths = ()
        self._watch_roots = ()
        self._scope_snapshot = ()
        self._cancel_pending = False
        self._cancellable = False
        box = QVBoxLayout(self); box.setContentsMargins(12, 12, 12, 12)
        title = QLabel('自动规则'); title.setObjectName('heading'); box.addWidget(title)
        help_label = QLabel('每项只使用第一条启用且匹配的规则。配置观察文件夹后，显式启用规则并取消暂停；自动检查约每 10 分钟。普通规则无需项目同步目录。')
        help_label.setWordWrap(True); box.addWidget(help_label)
        self.rule_list = QListWidget(); self.rule_list.setFixedHeight(82); box.addWidget(self.rule_list)
        tools = QHBoxLayout(); box.addLayout(tools)
        self.edit_buttons = []
        for text, callback in [('新建', self.new_rule), ('复制', self.duplicate_rule), ('删除', self.delete_rule),
                               ('↑', lambda: self.move_rule(-1)), ('↓', lambda: self.move_rule(1)),
                               ('导入', self._import), ('导出', self._export)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, fn=callback: self._guard(fn))
            tools.addWidget(button); self.edit_buttons.append(button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); box.addWidget(scroll, 1)
        self.editor = QWidget(); contents = QVBoxLayout(self.editor); scroll.setWidget(self.editor)
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText('规则名称'); contents.addWidget(self.name_edit)
        self.enabled_check = QCheckBox('启用此规则（保存后生效）'); contents.addWidget(self.enabled_check)
        enable_help = QLabel('启用并继续自动整理后，已选文件夹中现有和新加入的匹配文件都会处理；只检查最外层。每条规则使用自己的等待条件。')
        enable_help.setWordWrap(True); contents.addWidget(enable_help)
        contents.addWidget(QLabel('观察范围：勾选已配置的文件夹；全部不勾选时使用所有观察文件夹'))
        self.scope_list = QListWidget(); self.scope_list.setMaximumHeight(105); contents.addWidget(self.scope_list)
        self.scope_warning = QLabel(); self.scope_warning.setWordWrap(True); contents.addWidget(self.scope_warning)
        contents.addWidget(QLabel('匹配条件')); self.condition_editor = ConditionEditor(); contents.addWidget(self.condition_editor)
        contents.addWidget(QLabel('执行动作')); self.action_editor = ActionEditor(); contents.addWidget(self.action_editor)
        example = QLabel('示例：类型是图片 + 文件名包含“海报” → 转成 PNG → 移动到所选文件夹。新建、复制、导入规则均默认关闭。')
        example.setWordWrap(True); contents.addWidget(example)
        self.sample_label = QLabel('未选择测试样本'); self.sample_label.setWordWrap(True); contents.addWidget(self.sample_label)
        self.folder_sample_button = QPushButton('添加文件夹样本'); contents.addWidget(self.folder_sample_button)
        self.folder_sample_button.clicked.connect(self._choose_folder_sample)
        self.preview_text = QTextEdit(); self.preview_text.setReadOnly(True); self.preview_text.setMinimumHeight(110); contents.addWidget(self.preview_text)
        contents.addStretch()
        self.error_label = CompactMessage(); self.error_label.setObjectName('error'); box.addWidget(self.error_label)
        self.dirty_label = CompactMessage(); box.addWidget(self.dirty_label)
        buttons = QHBoxLayout(); box.addLayout(buttons)
        self.save_button = QPushButton('保存规则'); self.sample_button = QPushButton('选择样本')
        self.preview_button = QPushButton('测试预览'); self.execute_button = QPushButton('明确执行')
        self.check_button = QPushButton('立即检查（执行启用规则）')
        for button in (self.save_button, self.sample_button, self.preview_button, self.execute_button): buttons.addWidget(button)
        check_row = QHBoxLayout(); box.addLayout(check_row); check_row.addWidget(self.check_button)
        self.cancel_button = QPushButton('取消当前测试/执行'); check_row.addWidget(self.cancel_button)
        self.progress_label = CompactMessage(); box.addWidget(self.progress_label)
        self.cancel_button.clicked.connect(self._cancel)
        self.save_button.clicked.connect(lambda: self._guard(self._save))
        self.sample_button.clicked.connect(self._choose_samples); self.preview_button.clicked.connect(lambda: self._guard(self._preview))
        self.execute_button.clicked.connect(self._execute); self.check_button.clicked.connect(self.checkRequested)
        self.rule_list.currentRowChanged.connect(self._select)
        self.scope_list.itemChanged.connect(self._scope_edited)
        for signal in (self.name_edit.textChanged, self.enabled_check.toggled,
                       self.condition_editor.changed, self.action_editor.changed): signal.connect(self._edited)
        self.set_ruleset(self._ruleset)

    @property
    def generation(self): return self._generation

    @property
    def dirty(self): return self._dirty

    @property
    def selected_id(self): return self._selected_id

    def _guard(self, fn):
        try: fn()
        except (ValueError, KeyError) as exc: self.show_error(str(exc))

    def _edited(self):
        if self._loading: return
        self._dirty = True; self.dirty_label.setText('有未保存修改；请保存后测试')
        self.invalidate_preview(); self.changed.emit()

    def invalidate_preview(self):
        self._generation += 1; self._preview_token = None; self._can_execute = False
        self.execute_button.setEnabled(False); self.preview_text.clear()

    def _current_rule(self):
        original = next((rule for rule in self._ruleset.rules if rule.id == self._selected_id), None)
        if original is None: return None
        return replace(original, name=self.name_edit.text(), enabled=self.enabled_check.isChecked(),
            scope=self._scope_values(),
            condition=self.condition_editor.value(), actions=self.action_editor.value())

    def value(self):
        rule = self._current_rule()
        snapshot = self._ruleset.with_rule(rule) if rule else self._ruleset
        # Includes document size/schema validation without store access.
        return RuleSet.from_document(snapshot.to_document())

    def set_ruleset(self, snapshot):
        if not isinstance(snapshot, RuleSet): raise ValueError('必须提供已验证的规则快照')
        wanted = self._selected_id; self._ruleset = snapshot; self._dirty = False
        self._selected_id = None; self.dirty_label.clear(); self.error_label.clear(); self.invalidate_preview()
        self._rebuild(wanted)

    def _rebuild(self, wanted=None):
        self._loading = True; self.rule_list.blockSignals(True); self.rule_list.clear()
        for rule in self._ruleset.rules: self.rule_list.addItem(('已启用 · ' if rule.enabled else '已关闭 · ') + rule.name)
        index = next((i for i, rule in enumerate(self._ruleset.rules) if rule.id == wanted), 0 if self._ruleset.rules else -1)
        self.rule_list.setCurrentRow(index); self.rule_list.blockSignals(False); self._loading = False
        self._selected_id = None; self._select(index)

    def _select(self, index):
        if self._loading: return
        if self._selected_id is not None:
            try: self._ruleset = self.value()
            except ValueError as exc:
                self.show_error('请先修正当前规则：' + str(exc)); self.rule_list.blockSignals(True)
                self.rule_list.setCurrentRow(next(i for i, r in enumerate(self._ruleset.rules) if r.id == self._selected_id))
                self.rule_list.blockSignals(False); return
        self.invalidate_preview(); self._loading = True
        self._selected_id = self._ruleset.rules[index].id if index >= 0 else None
        self.editor.setEnabled(index >= 0 and not self._busy)
        if index >= 0:
            rule = self._ruleset.rules[index]; self.name_edit.setText(rule.name); self.enabled_check.setChecked(rule.enabled)
            self._fill_scope(rule.scope); self.condition_editor.set_value(rule.condition); self.action_editor.set_value(rule.actions)
        else: self.name_edit.clear(); self._fill_scope(()); self.preview_text.clear()
        self._loading = False; self._buttons()

    def new_rule(self):
        self._ruleset = self.value().with_rule(Rule(condition=Predicate('kind', 'equals', 'image'),
            actions=(Action('rename', {'pattern': '{stem}{ext}'}),)))
        wanted = self._ruleset.rules[-1].id; self._rebuild(wanted); self._edited()

    def duplicate_rule(self):
        if not self._selected_id: return
        self._ruleset = self.value().duplicate(self._selected_id); self._rebuild(self._ruleset.rules[-1].id); self._edited()

    def delete_rule(self):
        if not self._selected_id: return
        self._ruleset = self.value().delete(self._selected_id); self._rebuild(); self._edited()

    def move_rule(self, delta):
        if not self._selected_id: return
        snapshot = self.value(); ids = [rule.id for rule in snapshot.rules]; index = ids.index(self._selected_id); target = index + delta
        if not 0 <= target < len(ids): return
        ids[index], ids[target] = ids[target], ids[index]; self._ruleset = snapshot.reorder(ids)
        self._rebuild(self._selected_id); self._edited()

    def set_sample_paths(self, paths):
        self._sample_paths = tuple(str(path) for path in paths); self.sample_label.setText('测试样本：\n' + '\n'.join(self._sample_paths))
        self.invalidate_preview(); self.changed.emit()

    def set_watch_roots(self, paths):
        roots = tuple(absolute_folder(str(path)) for path in paths)
        if len({path.casefold() for path in roots}) != len(roots): raise ValueError('观察文件夹不能重复')
        selected = self._scope_values(); self._watch_roots = roots; self._fill_scope(selected)
        self.invalidate_preview(); self.changed.emit()

    def _scope_values(self):
        checked = tuple(self.scope_list.item(index).data(Qt.UserRole) for index in range(self.scope_list.count())
                        if self.scope_list.item(index).checkState() == Qt.Checked)
        keys = {path.casefold() for path in checked}; old = {path.casefold() for path in self._scope_snapshot}
        return tuple(path for path in self._scope_snapshot if path.casefold() in keys) + tuple(path for path in checked if path.casefold() not in old)

    def _fill_scope(self, selected):
        self._scope_snapshot = tuple(selected)
        self.scope_list.blockSignals(True); self.scope_list.clear()
        roots = {path.casefold() for path in self._watch_roots}; chosen = {path.casefold() for path in selected}
        original = {path.casefold(): path for path in selected}
        for root in (*self._watch_roots, *(path for path in selected if path.casefold() not in roots)):
            path = original.get(root.casefold(), root)
            item = QListWidgetItem(path if path.casefold() in roots else '未配置 · ' + path)
            item.setData(Qt.UserRole, path); item.setToolTip(path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if path.casefold() in chosen else Qt.Unchecked)
            self.scope_list.addItem(item)
        self.scope_list.blockSignals(False); self._scope_warning()

    def _scope_warning(self):
        roots = {path.casefold() for path in self._watch_roots}
        unknown = [path for path in self._scope_values() if path.casefold() not in roots]
        self.scope_warning.setText('存在未配置的观察文件夹，请先在设置中添加或取消此范围：\n' + '\n'.join(unknown) if unknown else
                                   '未配置观察文件夹；请先在设置中选择。' if not self._watch_roots else '')

    def _scope_edited(self): self._scope_warning(); self._edited()

    def _validate_scope(self):
        roots = {path.casefold() for path in self._watch_roots}
        if any(path.casefold() not in roots for path in self._scope_values()): raise ValueError('规则包含未配置的观察文件夹，请先配置或取消勾选')

    def _save(self): self._validate_scope(); self.saveRequested.emit(self.value())

    def _choose_samples(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择只用于测试预览的样本')
        if paths: self.set_sample_paths(paths)

    def _choose_folder_sample(self):
        path = QFileDialog.getExistingDirectory(self, '添加文件夹测试样本（预览不会执行）')
        if path: self.set_sample_paths((*self._sample_paths, path))

    def _preview(self):
        self._validate_scope()
        if self._dirty: raise ValueError('请先保存修改，再测试当前显示的规则')
        if not self._selected_id or not self._sample_paths: raise ValueError('请选择规则和测试样本')
        self.invalidate_preview(); self.error_label.clear()
        self.previewRequested.emit(RulePreviewRequest(self._selected_id, self._sample_paths, self._ruleset.revision, self.generation))

    def set_preview(self, text, token=None, can_execute=False):
        self.preview_text.setPlainText(str(text)); self._preview_token = token
        self._can_execute = bool(can_execute and token is not None and not self._dirty); self._buttons()

    def _execute(self):
        if not self._busy and self._can_execute and self._preview_token is not None:
            token = self._preview_token; self._preview_token = None; self._can_execute = False
            self._buttons(); self.executeRequested.emit(token)

    def _buttons(self):
        self.execute_button.setEnabled(not self._busy and self._can_execute and not self._dirty and self._preview_token is not None)
        for button in (*self.edit_buttons, self.save_button, self.sample_button, self.check_button): button.setEnabled(not self._busy)
        self.preview_button.setEnabled(not self._busy and self._selected_id is not None)
        self.rule_list.setEnabled(not self._busy)
        self.cancel_button.setEnabled(self._busy and self._cancellable and not self._cancel_pending)

    def set_busy(self, busy, *, cancellable=False):
        self._cancellable = bool(busy and cancellable)
        self._busy = bool(busy); self.editor.setEnabled(not busy and self._selected_id is not None); self._buttons()
        if not busy: self.set_cancel_pending(False)

    def _cancel(self):
        if self._busy and self._cancellable and not self._cancel_pending:
            self.set_cancel_pending(True); self.cancelRequested.emit()

    def set_cancel_pending(self, pending=True):
        if self._cancel_pending and not pending: self.progress_label.clear()
        self._cancel_pending = bool(pending)
        if pending: self.progress_label.setText('正在请求取消；当前处理会先安全完成或恢复。已完成的项目保留。')
        self._buttons()

    def show_error(self, message): self.error_label.setText(str(message))

    def _import(self):
        if self._dirty: raise ValueError('请先保存当前草稿，再导入规则')
        path, _ = QFileDialog.getOpenFileName(self, '导入规则（全部默认关闭）', '', '规则定义 (*.json)')
        if path: self.invalidate_preview(); self.importRequested.emit(path)

    def _export(self):
        if self._dirty: raise ValueError('请先保存当前草稿，再导出规则')
        path, _ = QFileDialog.getSaveFileName(self, '导出规则定义（不含记录）', '', '规则定义 (*.json)')
        if path: self.exportRequested.emit(path)
