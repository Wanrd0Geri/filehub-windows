"""Subordinate project-template editor, using only immutable library snapshots."""
from uuid import uuid4
from dataclasses import replace
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy)
from ..templates import TemplateLibrary
from ..naming import NAMING_TOKENS, render_pattern
from .compact_message import CompactMessage


class _MappingTable(QWidget):
    changed = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent); box = QVBoxLayout(self); box.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2); self.table.setHorizontalHeaderLabels(labels)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.setMinimumHeight(115); self.table.setMaximumHeight(190)
        box.addWidget(self.table); row = QHBoxLayout(); box.addLayout(row)
        add = QPushButton('+ 添加'); remove = QPushButton('删除所选行'); row.addWidget(add); row.addWidget(remove)
        add.clicked.connect(lambda: self.add_row('', '')); remove.clicked.connect(self.remove_selected)
        self.table.cellChanged.connect(self.changed)

    def set_value(self, mapping):
        self.table.blockSignals(True); self.table.setRowCount(0)
        for key, value in mapping.items(): self.add_row(key, value)
        self.table.blockSignals(False)

    def add_row(self, key='', value=''):
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key)); self.table.setItem(row, 1, QTableWidgetItem(value))
        self.changed.emit()

    def remove_selected(self):
        row = self.table.currentRow()
        if row >= 0: self.table.removeRow(row); self.changed.emit()

    def value(self):
        result = {}
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ''
            value = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else ''
            if not key or not value: raise ValueError('每行都需要完整的口令和相对目录')
            if key.casefold() in {word.casefold() for word in result}: raise ValueError('口令不能重复')
            result[key] = value
        return result


class TemplatesPage(QWidget):
    saveRequested = Signal(object)
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self._library = TemplateLibrary(); self._projects = {}
        self._selected_id = None; self._loading = False; self._dirty = False; self._busy = False
        self._saved_assignments = {}
        box = QVBoxLayout(self); box.setContentsMargins(12, 12, 12, 12)
        label = QLabel('项目模板 · 仅用于送进项目；普通自动规则无需配置模板。默认模板只读，请先复制后编辑。')
        label.setWordWrap(True); box.addWidget(label)
        top = QHBoxLayout(); box.addLayout(top)
        self.template_combo = QComboBox(); top.addWidget(self.template_combo, 1)
        self.copy_button = QPushButton('复制为自定义'); top.addWidget(self.copy_button)
        self.delete_button = QPushButton('删除模板'); top.addWidget(self.delete_button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); box.addWidget(scroll, 1)
        self.editor = QWidget(); contents = QVBoxLayout(self.editor); scroll.setWidget(self.editor)
        form = QFormLayout(); contents.addLayout(form)
        self.name_edit = QLineEdit(); form.addRow('模板名称', self.name_edit)
        self.directory_fields = {}
        for key, label in [('production_dir', '制作目录'), ('asset_root', '设定根目录'), ('final_dir', '交付目录'), ('test_dir', '测试目录')]:
            field = QLineEdit(); field.setPlaceholderText('项目内相对目录，例如 制作/镜头')
            form.addRow(label, field); self.directory_fields[key] = field; field.textChanged.connect(self._edited)
        contents.addWidget(QLabel('设定类别：口令 → 设定根目录内的相对目录'))
        self.categories = _MappingTable(['类别口令', '相对目录']); contents.addWidget(self.categories)
        contents.addWidget(QLabel('保留文件名：口令 → 项目内相对目录'))
        self.keep_routes = _MappingTable(['保留名称口令', '相对目录']); contents.addWidget(self.keep_routes)
        contents.addWidget(QLabel('命名规则：留空沿用原有命名；文件夹名称保持不变'))
        patterns = QFormLayout(); contents.addLayout(patterns); self.pattern_fields = {}
        for mode, label in [('shot', '镜头'), ('asset', '设定素材'), ('final', '交付成片')]:
            field = QLineEdit(); field.setPlaceholderText('例如 {stem}_{date}_{sequence}{ext}')
            self.pattern_fields[mode] = field; patterns.addRow(label, field); field.textChanged.connect(self._edited)
        tokens = QLabel('可用占位符：' + ' '.join('{' + token + '}' for token in sorted(NAMING_TOKENS)) +
            '\n{ext} 包含点；{date} 为 YYMMDD；{date_long} 为 YYYYMMDD；编号按十进制显示。')
        tokens.setWordWrap(True); contents.addWidget(tokens)
        self.example_label = QLabel(); self.example_label.setWordWrap(True); contents.addWidget(self.example_label)
        self.example_button = QPushButton('查看命名示例（不读文件）'); contents.addWidget(self.example_button)
        contents.addWidget(QLabel('选择项目并分配模板'))
        assignment_row = QHBoxLayout(); contents.addLayout(assignment_row)
        self.project_combo = QComboBox(); self.assignment_combo = QComboBox()
        for combo in (self.project_combo, self.assignment_combo, self.template_combo):
            combo.setMinimumContentsLength(8); combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumWidth(0); combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.assign_button = QPushButton('应用分配'); assignment_row.addWidget(self.project_combo); assignment_row.addWidget(self.assignment_combo); assignment_row.addWidget(self.assign_button)
        self.assignment_label = QLabel(); self.assignment_label.setWordWrap(True); contents.addWidget(self.assignment_label); contents.addStretch()
        self.error_label = CompactMessage(); self.error_label.setObjectName('error'); box.addWidget(self.error_label)
        self.dirty_label = CompactMessage(); box.addWidget(self.dirty_label)
        self.save_button = QPushButton('保存模板与分配'); box.addWidget(self.save_button)
        self.template_combo.currentIndexChanged.connect(self._select)
        self.copy_button.clicked.connect(lambda: self._guard(self.copy_template)); self.delete_button.clicked.connect(self.delete_template)
        self.save_button.clicked.connect(lambda: self._guard(lambda: self.saveRequested.emit(self.value())))
        self.assign_button.clicked.connect(lambda: self._guard(lambda: self.assign_project(self.project_combo.currentData(), self.assignment_combo.currentData())))
        self.example_button.clicked.connect(lambda: self._guard(self._example))
        for signal in (self.name_edit.textChanged, self.categories.changed, self.keep_routes.changed): signal.connect(self._edited)
        self.set_library(self._library)

    @property
    def dirty(self): return self._dirty

    @property
    def selected_id(self): return self._selected_id

    def _guard(self, fn):
        try: fn()
        except (ValueError, KeyError) as exc: self.show_error(str(exc))

    def _edited(self):
        if self._loading: return
        self._dirty = True; self.dirty_label.setText('有未保存修改'); self.example_label.clear(); self.changed.emit()

    def value(self):
        if self._selected_id is None or self._selected_id == 'default': return self._library
        template = self._library.templates[self._selected_id]
        template = replace(template, name=self.name_edit.text(),
            **{key: field.text() for key, field in self.directory_fields.items()},
            asset_categories=self.categories.value(), keep_name_routes=self.keep_routes.value(),
            naming_patterns={mode: field.text() for mode, field in self.pattern_fields.items() if field.text()})
        return self._library.with_template(template)

    def set_library(self, library):
        if not isinstance(library, TemplateLibrary): raise ValueError('必须提供已验证的模板快照')
        wanted = self._selected_id; self._library = library; self._selected_id = None; self._dirty = False
        self._saved_assignments = dict(library.assignments)
        self.error_label.clear(); self.dirty_label.clear(); self._rebuild(wanted)

    def _rebuild(self, wanted=None):
        self._loading = True; self.template_combo.blockSignals(True); self.template_combo.clear(); self.assignment_combo.clear()
        self.assignment_combo.addItem('默认 / 解除自定义分配', None)
        for identifier, template in self._library.templates.items():
            self.template_combo.addItem(template.name, identifier)
            if identifier != 'default': self.assignment_combo.addItem(template.name, identifier)
        index = self.template_combo.findData(wanted); self.template_combo.setCurrentIndex(max(0, index))
        self.template_combo.blockSignals(False); self._selected_id = None; self._loading = False
        self._select(self.template_combo.currentIndex()); self._assignments_text()

    def _select(self, index):
        if self._loading or index < 0: return
        if self._selected_id:
            try: self._library = self.value()
            except ValueError as exc:
                self.show_error('请先修正当前模板：' + str(exc)); self.template_combo.blockSignals(True)
                self.template_combo.setCurrentIndex(self.template_combo.findData(self._selected_id)); self.template_combo.blockSignals(False); return
        self._selected_id = self.template_combo.itemData(index); template = self._library.templates[self._selected_id]
        self._loading = True; self.name_edit.setText(template.name)
        readonly = self._selected_id == 'default'; self.name_edit.setReadOnly(readonly)
        for key, field in self.directory_fields.items(): field.setText(getattr(template, key)); field.setReadOnly(readonly)
        self.categories.set_value(template.asset_categories); self.keep_routes.set_value(template.keep_name_routes)
        self.categories.setEnabled(not readonly); self.keep_routes.setEnabled(not readonly)
        for mode, field in self.pattern_fields.items(): field.setText(template.naming_patterns.get(mode, '')); field.setReadOnly(readonly)
        self.delete_button.setEnabled(not readonly and not self._busy); self.example_label.clear(); self._loading = False

    def copy_template(self, name=None):
        if not self._selected_id: return
        library = self.value(); identifier = 'custom_' + uuid4().hex
        name = name or library.templates[self._selected_id].name + ' 副本'
        self._library = library.copy_template(self._selected_id, identifier, name); self._rebuild(identifier); self._edited()

    def delete_template(self):
        try:
            if not self._selected_id: return
            if self._selected_id in self._saved_assignments.values(): raise ValueError('请先解除分配并保存，再删除此模板')
            self._library = self.value().delete_template(self._selected_id); self._rebuild('default'); self._edited()
        except ValueError as exc: self.show_error(str(exc))

    def set_projects(self, mapping):
        self._projects = dict(mapping); self.project_combo.clear()
        for code, name in self._projects.items(): self.project_combo.addItem(str(code) + ' · ' + str(name), str(code))

    def assign_project(self, code, identifier):
        if not code or str(code).upper() not in {str(key).upper() for key in self._projects}: raise ValueError('请选择列表中的项目')
        self._library = self.value().assign(str(code), identifier); self._assignments_text(); self._edited()

    def _assignments_text(self):
        self.assignment_label.setText('当前分配：\n' + ('\n'.join(code + ' → ' + self._library.templates[identifier].name
            for code, identifier in self._library.assignments.items()) or '所有项目使用默认模板'))

    def _example(self):
        template = self.value().templates[self._selected_id]
        values = {token: '' for token in NAMING_TOKENS}
        values.update(original='海报.png', stem='海报', ext='.png', prefix='角色龙', date='261001', date_long='20261001',
                      period='AM', episode='2', scene='8', shot='22', sequence=1, resolution='2K', note='定稿')
        self.example_label.setText('\n'.join({'shot': '镜头', 'asset': '素材', 'final': '交付'}[mode] + '：' + render_pattern(pattern, values)
            for mode, pattern in template.naming_patterns.items()) or '沿用原有命名规则；预览真实文件时查看准确名称。')

    def set_busy(self, busy):
        self._busy = bool(busy); self.editor.setEnabled(not busy); self.template_combo.setEnabled(not busy)
        self.copy_button.setEnabled(not busy); self.save_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy and self._selected_id != 'default')

    def show_error(self, message): self.error_label.setText(str(message))
