"""Independent conversion intentions and progress display, with no image decode."""
from collections.abc import Mapping
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog)
from .action_editor import ConversionFields
from .rule_requests import ConversionRequest

PHASES = {'start': '准备中', 'decoded': '已读取', 'encoded': '已编码', 'verified': '已验证',
          'complete': '正在保存/替换', 'saving': '正在保存/替换', 'replacing': '正在保存/替换', 'committing': '正在保存/替换'}
STATUSES = {'ready': '待执行', 'pending': '等待中', 'running': '处理中', 'success': '已完成',
            'error': '失败', 'canceled': '已取消', 'cancelled': '已取消', 'conflict': '需要处理冲突'}


class ConversionPage(QWidget):
    previewRequested = Signal(object)
    executeRequested = Signal(object)
    cancelRequested = Signal()
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self._paths = (); self._generation = 0; self._busy = False
        self._cancel_pending = False; self._token = None; self._can_execute = False
        box = QVBoxLayout(self); box.setContentsMargins(12, 12, 12, 12)
        title = QLabel('图片转换'); title.setObjectName('heading'); box.addWidget(title)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); box.addWidget(scroll, 1)
        self.editor = QWidget(); contents = QVBoxLayout(self.editor); scroll.setWidget(self.editor)
        self.select_button = QPushButton('选择图片（可多选）'); contents.addWidget(self.select_button)
        self.paths_label = QLabel('未选择图片'); self.paths_label.setWordWrap(True); contents.addWidget(self.paths_label)
        self.fields = ConversionFields(); contents.addWidget(self.fields)
        label = QLabel('先预览确切文件名和冲突，再明确开始。预览会读取图片，但不会转换或替换原图。')
        label.setWordWrap(True); label.setObjectName('muted'); contents.addWidget(label)
        self.results = QTableWidget(0, 4); self.results.setHorizontalHeaderLabels(['原图', '计划目标', '状态', '说明'])
        self.results.setEditTriggers(QTableWidget.NoEditTriggers); self.results.setWordWrap(True)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.setColumnWidth(0, 165); self.results.setColumnWidth(1, 165); self.results.setColumnWidth(2, 125)
        self.results.setMinimumHeight(190); contents.addWidget(self.results); contents.addStretch()
        self.error_label = QLabel(); self.error_label.setWordWrap(True); self.error_label.setObjectName('error'); box.addWidget(self.error_label)
        self.status_label = QLabel(); self.status_label.setWordWrap(True); box.addWidget(self.status_label)
        buttons = QHBoxLayout(); box.addLayout(buttons)
        self.preview_button = QPushButton('预览转换'); self.execute_button = QPushButton('开始转换'); self.cancel_button = QPushButton('取消')
        self.execute_button.setObjectName('primary')
        for button in (self.preview_button, self.execute_button, self.cancel_button): buttons.addWidget(button)
        self.select_button.clicked.connect(self._choose); self.fields.changed.connect(self.invalidate_preview)
        self.preview_button.clicked.connect(self._preview); self.execute_button.clicked.connect(self._execute)
        self.cancel_button.clicked.connect(self._cancel); self._buttons()

    @property
    def generation(self): return self._generation

    @property
    def cancel_pending(self): return self._cancel_pending

    @property
    def paths(self): return self._paths

    def set_paths(self, paths):
        self._paths = tuple(str(path) for path in paths)
        self.paths_label.setText('已选择 %d 张：\n%s' % (len(self._paths), '\n'.join(self._paths)))
        self.invalidate_preview()

    def _choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择图片', '', '图片 (*.jpg *.jpeg *.png *.webp);;所有文件 (*)')
        if paths: self.set_paths(paths)

    def invalidate_preview(self):
        self._generation += 1; self._token = None; self._can_execute = False
        self.results.setRowCount(0); self._buttons(); self.changed.emit()

    def value(self):
        if not self._paths: raise ValueError('请先选择图片')
        spec, mode, destination = self.fields.value()
        return ConversionRequest(self._paths, spec, mode, destination, self.generation)

    def _preview(self):
        try:
            self.invalidate_preview(); request = self.value(); self.error_label.clear(); self.previewRequested.emit(request)
        except ValueError as exc: self.show_error(str(exc))

    def set_preview(self, rows, token=None, can_execute=True):
        """Rows: mappings source/target/status/message; token is controller-owned."""
        self.results.setRowCount(0)
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping): raise ValueError('预览行必须提供 source/target/status/message 映射')
            self.results.insertRow(index)
            status = row.get('status', 'ready')
            for column, text in enumerate((row.get('source', ''), row.get('target', ''), STATUSES.get(status, str(status)), row.get('message', ''))):
                item = QTableWidgetItem(str(text)); item.setToolTip(str(text)); self.results.setItem(index, column, item)
        self.results.resizeRowsToContents(); self._token = token
        self._can_execute = bool(can_execute and token is not None); self._buttons()

    def set_progress(self, status):
        """Mapping index, phase/percent OR final status/message; final success is explicit."""
        if not isinstance(status, Mapping): raise ValueError('进度必须是映射')
        index = status.get('index')
        if type(index) is not int or not 0 <= index < self.results.rowCount(): return
        if status.get('status') in STATUSES:
            text = STATUSES[status['status']]
        else:
            phase = status.get('phase', 'running'); text = PHASES.get(phase, '处理中')
            if 'percent' in status and phase not in ('complete', 'saving', 'replacing', 'committing'): text += f" {status['percent']}%"
        self.results.setItem(index, 2, QTableWidgetItem(text))
        if 'message' in status:
            item = QTableWidgetItem(str(status['message'])); item.setToolTip(str(status['message'])); self.results.setItem(index, 3, item)
        self.results.resizeRowToContents(index)

    def _execute(self):
        if not self._busy and self._can_execute and self._token is not None:
            token = self._token; self._token = None; self._can_execute = False
            self._buttons(); self.executeRequested.emit(token)

    def _cancel(self):
        if self._busy and not self._cancel_pending:
            self.set_cancel_pending(True); self.cancelRequested.emit()

    def set_cancel_pending(self, pending=True):
        self._cancel_pending = bool(pending)
        self.status_label.setText('正在请求取消；当前图片处理结束后生效，正在替换时会先完成或恢复原文件。已完成的项目保留，剩余项目取消。' if pending else '')
        self._buttons()

    def set_busy(self, busy):
        self._busy = bool(busy); self.fields.setEnabled(not busy); self.select_button.setEnabled(not busy)
        if busy:
            # Token is consumed once a preview/run begins; no repeated execution.
            self._token = None; self._can_execute = False
        else: self.set_cancel_pending(False)
        self._buttons()

    def _buttons(self):
        self.preview_button.setEnabled(not self._busy and bool(self._paths))
        self.execute_button.setEnabled(not self._busy and self._can_execute and self._token is not None)
        self.cancel_button.setEnabled(self._busy and not self._cancel_pending)

    def show_error(self, message): self.error_label.setText(str(message))
