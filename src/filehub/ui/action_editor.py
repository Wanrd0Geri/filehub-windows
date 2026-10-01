"""Ordered action forms and shared image settings; no runtime/store access."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QSpinBox, QCheckBox, QLabel, QPushButton, QGroupBox, QFileDialog, QColorDialog)
from PySide6.QtGui import QColor
from ..automation.models import Action, absolute_folder
from ..conversion.models import ConversionSpec
from ..naming import NAMING_TOKENS
from .condition_editor import combo

ACTION_NAMES = {'rename': '重命名', 'move': '移动', 'copy': '复制', 'subfolder': '移入子文件夹',
                'image_convert': '转换图片', 'project_route': '送进项目（最后一步）'}


class ConversionFields(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); form = QFormLayout(self); self._form = form
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.mode = combo({'keep': '保留原图另存', 'replace': '原地替换（可撤销）'})
        self.output_format = combo({'jpeg': 'JPG / JPEG', 'png': 'PNG（无损）', 'webp': 'WebP'})
        self.quality = QSpinBox(); self.quality.setRange(0, 100); self.quality.setValue(90)
        self.lossless = QCheckBox('WebP 无损（不使用质量值）')
        self.background_choice = combo({'#FFFFFF': '白色', '#000000': '黑色', 'custom': '自定义颜色'})
        self.background = QLineEdit('#FFFFFF'); self.background.setPlaceholderText('#RRGGBB，例如 #FAF0E6')
        self.background_box = QWidget(); color_row = QHBoxLayout(self.background_box); color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(self.background); self.color_button = QPushButton('选择颜色'); color_row.addWidget(self.color_button)
        self.color_button.clicked.connect(self._choose_color)
        self.destination = QLineEdit(); self.destination.setPlaceholderText('明确选择输出文件夹')
        self.destination_box = QWidget(); row = QHBoxLayout(self.destination_box); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.destination); choose = QPushButton('选择文件夹'); row.addWidget(choose)
        choose.clicked.connect(self._choose_folder)
        self.destination_label = QLabel('输出文件夹')
        for label, widget in [('处理方式', self.mode), ('目标格式', self.output_format), ('质量（0–100）', self.quality),
                              ('无损', self.lossless), ('JPEG 透明背景', self.background_choice), ('自定义背景', self.background_box)]:
            form.addRow(label, widget)
        form.addRow(self.destination_label, self.destination_box)
        self.mode_help = QLabel(); self.mode_help.setWordWrap(True); self.mode_help.setObjectName('muted'); form.addRow(self.mode_help)
        help_label = QLabel('保持像素尺寸；最多 4000 万像素。拍摄日期、色彩信息等元数据可能丢失。取消会在当前图片处理结束后生效；正在替换时会先完成或恢复原文件。')
        help_label.setWordWrap(True); help_label.setObjectName('muted'); form.addRow(help_label)
        self._timeout = 60; self._max_pixels = 40000000
        self.mode.currentIndexChanged.connect(self._refresh)
        self.output_format.currentIndexChanged.connect(self._refresh); self.lossless.toggled.connect(self._refresh)
        self.background_choice.currentIndexChanged.connect(self._background_choice_changed)
        self.background.textChanged.connect(self._background_text_changed)
        for signal in (self.mode.currentIndexChanged, self.output_format.currentIndexChanged, self.quality.valueChanged,
                       self.lossless.toggled, self.background.textChanged, self.destination.textChanged): signal.connect(self.changed)
        self._refresh()

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '选择输出文件夹')
        if path: self.destination.setText(path)

    def _choose_color(self):
        color = QColorDialog.getColor(QColor(self.background.text()), self, '选择 JPEG 透明区域背景')
        if color.isValid(): self.background.setText(color.name().upper())

    def _background_choice_changed(self):
        color = self.background_choice.currentData()
        if color != 'custom': self.background.setText(color)
        self._refresh()

    def _background_text_changed(self):
        index = self.background_choice.findData(self.background.text().upper())
        self.background_choice.blockSignals(True); self.background_choice.setCurrentIndex(index if index >= 0 else 2)
        self.background_choice.blockSignals(False)
        self._refresh()

    def _refresh(self):
        keep = self.mode.currentData() == 'keep'; fmt = self.output_format.currentData()
        self.destination_box.setVisible(keep); self.destination_label.setVisible(keep)
        self.destination.setEnabled(keep); self.destination_box.setEnabled(keep)
        self.mode_help.setText('生成新文件，保留原图。请选择输出文件夹。' if keep else
            '原图备份后替换，可从记录撤销。输出在原文件夹；扩展名按目标格式改变，同格式则替换同名文件。')
        self.quality.setEnabled(fmt == 'jpeg' or (fmt == 'webp' and not self.lossless.isChecked()))
        self.lossless.setEnabled(fmt == 'webp'); self.background_choice.setEnabled(fmt == 'jpeg')
        self.background.setEnabled(fmt == 'jpeg' and self.background_choice.currentData() == 'custom')
        self.color_button.setEnabled(fmt == 'jpeg')
        self._form.setRowVisible(self.quality, fmt in ('jpeg', 'webp'))
        self._form.setRowVisible(self.lossless, fmt == 'webp')
        self._form.setRowVisible(self.background_choice, fmt == 'jpeg')
        self._form.setRowVisible(self.background_box, fmt == 'jpeg' and self.background_choice.currentData() == 'custom')

    def set_value(self, spec, mode='keep', destination=None):
        if not isinstance(spec, ConversionSpec): raise ValueError('图片设置必须通过验证')
        if mode not in ('keep', 'replace'): raise ValueError('请选择保留或替换模式')
        self._timeout = spec.timeout_seconds; self._max_pixels = spec.max_pixels
        self.output_format.setCurrentIndex(self.output_format.findData(spec.output_format))
        self.mode.setCurrentIndex(self.mode.findData(mode)); self.quality.setValue(spec.quality)
        self.lossless.setChecked(spec.lossless); self.background.setText(spec.background)
        self.destination.setText(destination or ''); self._refresh(); self.changed.emit()

    def value(self):
        spec = ConversionSpec(output_format=self.output_format.currentData(), quality=self.quality.value(),
            lossless=self.lossless.isChecked(), background=self.background.text(),
            timeout_seconds=self._timeout, max_pixels=self._max_pixels)
        mode = self.mode.currentData()
        return spec, mode, absolute_folder(self.destination.text()) if mode == 'keep' else None


class _ActionRow(QGroupBox):
    def __init__(self, editor, action=None, kind='rename'):
        super().__init__(); self.editor = editor
        box = QVBoxLayout(self); top = QHBoxLayout(); box.addLayout(top)
        self.kind = combo(ACTION_NAMES); top.addWidget(self.kind)
        for text, callback in [('↑', lambda: editor.move_action(editor.rows.index(self), -1)),
                               ('↓', lambda: editor.move_action(editor.rows.index(self), 1)),
                               ('删除', lambda: editor.remove_action(editor.rows.index(self)))]:
            button = QPushButton(text); button.clicked.connect(callback); top.addWidget(button)
        self.option = QLineEdit(); box.addWidget(self.option)
        self.choose = QPushButton('选择目标文件夹'); box.addWidget(self.choose); self.choose.clicked.connect(self._choose)
        self.conversion = ConversionFields(); box.addWidget(self.conversion)
        self.kind.setCurrentIndex(self.kind.findData(action.kind if action else kind))
        self.kind.currentIndexChanged.connect(self._refresh); self.kind.currentIndexChanged.connect(editor.changed)
        self.option.textChanged.connect(editor.changed); self.conversion.changed.connect(editor.changed)
        if action:
            if action.kind == 'image_convert': self.conversion.set_value(action.conversion_spec, action.options['mode'], action.options.get('destination'))
            else: self.option.setText(next(iter(action.options.values())))
        elif kind == 'rename': self.option.setText('{stem}{ext}')
        self._refresh()

    def _choose(self):
        path = QFileDialog.getExistingDirectory(self, '选择目标文件夹')
        if path: self.option.setText(path)

    def _refresh(self):
        kind = self.kind.currentData(); self.conversion.setVisible(kind == 'image_convert')
        self.option.setVisible(kind != 'image_convert'); self.choose.setVisible(kind in ('move', 'copy'))
        self.option.setPlaceholderText({'rename': '例如 {stem}_{sequence}{ext}', 'move': '明确选择绝对目标文件夹',
            'copy': '明确选择绝对目标文件夹', 'subfolder': '相对子目录，例如 素材/图片', 'project_route': '项目口令，例如 LYX角色龙'}.get(kind, ''))

    def value(self):
        kind = self.kind.currentData()
        if kind == 'image_convert':
            spec, mode, destination = self.conversion.value(); options = {**vars(spec), 'mode': mode}
            if destination is not None: options['destination'] = destination
        else: options = {{'rename': 'pattern', 'move': 'destination', 'copy': 'destination',
                         'subfolder': 'path', 'project_route': 'tag'}[kind]: self.option.text()}
        return Action(kind, options)


class ActionEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self.rows = []; self.box = QVBoxLayout(self); self.box.setContentsMargins(0, 0, 0, 0)
        help_label = QLabel('动作按顺序执行（最多 20 步）。复制后以副本继续；图片转换后以新图片继续。项目路由必须放在最后。')
        help_label.setWordWrap(True); self.box.addWidget(help_label)
        tokens = QLabel('重命名可用：' + ' '.join('{' + token + '}' for token in sorted(NAMING_TOKENS)))
        tokens.setWordWrap(True); self.box.addWidget(tokens)
        bottom = QHBoxLayout(); self.add_kind = combo(ACTION_NAMES); bottom.addWidget(self.add_kind)
        self.add_button = QPushButton('+ 添加动作'); bottom.addWidget(self.add_button); self.box.addLayout(bottom)
        self.add_button.clicked.connect(lambda: self.add_action(self.add_kind.currentData()))

    def set_value(self, actions):
        for row in self.rows: self.box.removeWidget(row); row.deleteLater()
        self.rows = []
        for action in actions: self._append(action=action)
        self.changed.emit()

    def _append(self, action=None, kind='rename'):
        row = _ActionRow(self, action, kind); self.rows.append(row); self.box.insertWidget(self.box.count() - 1, row)
        self.add_button.setEnabled(len(self.rows) < 20)

    def add_action(self, kind='rename'):
        if len(self.rows) >= 20: raise ValueError('动作最多 20 步')
        if kind not in ACTION_NAMES: raise ValueError('不支持此动作')
        self._append(kind=kind); self.changed.emit()

    def remove_action(self, index):
        row = self.rows.pop(index); self.box.removeWidget(row); row.deleteLater()
        self.add_button.setEnabled(True); self.changed.emit()

    def move_action(self, index, delta):
        target = index + delta
        if not 0 <= target < len(self.rows): return
        row = self.rows.pop(index); self.rows.insert(target, row); self.box.removeWidget(row); self.box.insertWidget(target + 2, row)
        self.changed.emit()

    def value(self):
        if not 1 <= len(self.rows) <= 20: raise ValueError('请添加 1–20 个动作')
        actions = tuple(row.value() for row in self.rows)
        if any(action.kind == 'project_route' for action in actions[:-1]): raise ValueError('项目路由必须放在最后')
        return actions
