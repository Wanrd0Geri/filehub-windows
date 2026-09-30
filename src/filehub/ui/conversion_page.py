"""Independent conversion intentions and progress display, with no image decode."""
from collections.abc import Mapping
import ntpath
from pathlib import Path
from PySide6.QtCore import Signal, Qt, QEvent, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QListWidget, QListWidgetItem)
from .action_editor import ConversionFields
from .rule_requests import ConversionRequest
from .compact_message import CompactMessage

PHASES = {'start': '准备中', 'decoded': '已读取', 'encoded': '已编码', 'verified': '已验证',
          'complete': '正在保存/替换', 'saving': '正在保存/替换', 'replacing': '正在保存/替换', 'committing': '正在保存/替换'}
STATUSES = {'ready': '待执行', 'pending': '等待中', 'running': '处理中', 'success': '已完成',
            'error': '失败', 'canceled': '已取消', 'cancelled': '已取消', 'conflict': '需要处理冲突'}


class ConversionPage(QWidget):
    previewRequested = Signal(object)
    executeRequested = Signal(object)
    cancelRequested = Signal()
    changed = Signal()

    def __init__(self, parent=None, *, can_accept_paths=None):
        super().__init__(parent); self._paths = (); self._generation = 0; self._busy = False
        self._can_accept_paths = can_accept_paths or (lambda: True)
        self._cancel_pending = False; self._token = None; self._can_execute = False
        box = QVBoxLayout(self); box.setContentsMargins(12, 12, 12, 12)
        title = QLabel('图片转换'); title.setObjectName('heading'); box.addWidget(title)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); box.addWidget(scroll, 1)
        self.editor = QWidget(); contents = QVBoxLayout(self.editor); scroll.setWidget(self.editor)
        self.select_button = QPushButton('选择图片（可多选，也可拖入 JPEG / PNG / WebP）'); contents.addWidget(self.select_button)
        self.paths_label = QLabel('未选择图片'); self.paths_label.setWordWrap(True); contents.addWidget(self.paths_label)
        self.sources = QListWidget(); self.sources.setObjectName('conversionSources'); self.sources.setFixedHeight(90); contents.addWidget(self.sources)
        self.fields = ConversionFields(); contents.addWidget(self.fields)
        label = QLabel('先预览确切文件名和冲突，再明确开始。预览会读取图片，但不会转换或替换原图。')
        label.setWordWrap(True); label.setObjectName('muted'); contents.addWidget(label)
        self.results = QTableWidget(0, 4); self.results.setHorizontalHeaderLabels(['原图', '计划目标', '状态', '说明'])
        self.results.setEditTriggers(QTableWidget.NoEditTriggers); self.results.setWordWrap(True)
        self.results.setTextElideMode(Qt.ElideNone)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results.horizontalHeader().sectionResized.connect(lambda *_: self.results.resizeRowsToContents())
        self.results.setMinimumHeight(190); contents.addWidget(self.results); contents.addStretch()
        self.error_label = CompactMessage(); self.error_label.setObjectName('error'); box.addWidget(self.error_label)
        self.status_label = CompactMessage(); box.addWidget(self.status_label)
        buttons = QHBoxLayout(); box.addLayout(buttons)
        self.preview_button = QPushButton('预览转换'); self.execute_button = QPushButton('开始转换'); self.cancel_button = QPushButton('取消')
        self.execute_button.setObjectName('primary')
        for button in (self.preview_button, self.execute_button, self.cancel_button): buttons.addWidget(button)
        self.select_button.clicked.connect(self._choose); self.fields.changed.connect(self.invalidate_preview)
        self.preview_button.clicked.connect(self._preview); self.execute_button.clicked.connect(self._execute)
        self.cancel_button.clicked.connect(self._cancel); self._buttons()
        # Native item-view viewports and editable fields receive drops themselves.
        # Intercept them before they can insert URLs or bubble to archive routing.
        self.setAcceptDrops(True)
        for widget in self.findChildren(QWidget):
            widget.setAcceptDrops(True); widget.installEventFilter(self)

    def _drop_paths(self, mime):
        if self._busy: raise ValueError('正在处理图片，请结束后再添加图片。')
        if not self._can_accept_paths(): raise ValueError('正在切换状态或退出，请稍后再添加图片。')
        urls = mime.urls()
        if not urls: raise ValueError('请拖入本地 JPEG、PNG 或 WebP 图片文件。')
        paths = []
        for url in urls:
            path = url.toLocalFile()
            if not url.isLocalFile() or url.host() not in ('', 'localhost') or path.startswith(('\\\\', '//')):
                raise ValueError('只接受本地图片文件，不支持远程链接或网络路径。')
            candidate = Path(path)
            if candidate.is_dir(): raise ValueError('不支持拖入文件夹；请选择 JPEG、PNG 或 WebP 图片文件。')
            if candidate.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
                raise ValueError('只支持 JPEG、PNG 和 WebP 图片；本次拖入未添加任何文件。')
            if not candidate.is_file(): raise ValueError('请选择存在的本地 JPEG、PNG 或 WebP 图片文件。')
            paths.append(str(candidate))
        return paths

    def _drag_event(self, event):
        if not event.possibleActions() & Qt.CopyAction:
            self.show_error('请以复制方式拖入图片；拖放只添加选择，不移动文件。'); event.ignore(); return
        try: paths = self._drop_paths(event.mimeData())
        except (ValueError, OSError) as exc:
            self.show_error(str(exc)); event.ignore(); return
        if event.type() == QEvent.Drop:
            combined = list(self._paths); known = {ntpath.normcase(ntpath.normpath(path)) for path in combined}
            for path in paths:
                key = ntpath.normcase(ntpath.normpath(path))
                if key not in known: combined.append(path); known.add(key)
            self.error_label.clear()
            if tuple(combined) != self._paths: self.set_paths(combined)
        event.setDropAction(Qt.CopyAction); event.accept()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            self._drag_event(event); return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event): self._drag_event(event)

    def dragMoveEvent(self, event): self._drag_event(event)

    def dropEvent(self, event): self._drag_event(event)

    @property
    def generation(self): return self._generation

    @property
    def cancel_pending(self): return self._cancel_pending

    @property
    def paths(self): return self._paths

    def set_paths(self, paths):
        self._paths = tuple(str(path) for path in paths)
        self.paths_label.setText('已选择 %d 张（完整路径见每项提示）：' % len(self._paths))
        self.sources.clear()
        for path in self._paths:
            item = QListWidgetItem(Path(path).name); item.setToolTip(path)
            item.setSizeHint(QSize(0, self.sources.fontMetrics().height() + 6)); self.sources.addItem(item)
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
                full = str(text)
                item = QTableWidgetItem(Path(full).name if column in (0, 1) and full else full)
                item.setToolTip(full); self.results.setItem(index, column, item)
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
