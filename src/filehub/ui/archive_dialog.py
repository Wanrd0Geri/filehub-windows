from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit
from .theme import apply_theme
from PySide6.QtCore import Signal
from .tag_history import HistoryChips

class ArchiveDialog(QDialog):
    execution_persisted=Signal(object)
    def __init__(self, window, paths):
        super().__init__(window)
        self.setWindowTitle('送进项目');self.setMinimumWidth(438)
        self.window=window;self.paths=tuple(paths);self.preview=None;self.generation=0
        self.executing=False
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        title=QLabel('送进项目');title.setObjectName('heading');layout.addWidget(title)
        layout.addWidget(QLabel(f'已选择 {len(paths)} 项 · 先预览，再归档'))
        layout.addWidget(QLabel('项目代码与目的地'))
        self.tag=QLineEdit();self.tag.setObjectName('tag');self.tag.setPlaceholderText('例如 LYX020822');layout.addWidget(self.tag)
        self.history_chips=HistoryChips(window.tag_history,self.fill_history_tag);layout.addWidget(self.history_chips)
        self.details=QTextEdit();self.details.setReadOnly(True);self.details.setMinimumHeight(140);layout.addWidget(self.details)
        buttons=QHBoxLayout();self.cancel_button=QPushButton('取消');self.cancel_button.clicked.connect(self.reject);buttons.addWidget(self.cancel_button)
        self.preview_button=QPushButton('预览');buttons.addWidget(self.preview_button)
        self.execute_button=QPushButton('送进项目');self.execute_button.setObjectName('primary');self.execute_button.setEnabled(False);buttons.addWidget(self.execute_button);layout.addLayout(buttons)
        self.tag.textChanged.connect(self.invalidate)
        self.preview_button.clicked.connect(self.request_preview)
        self.execute_button.clicked.connect(self.execute)
        self.window.coordinator.busy.connect(self.busy_changed)
        apply_theme(self,window.service.config.theme)

    def busy_changed(self,busy):
        self.preview_button.setEnabled(not busy)
        self.execute_button.setEnabled(not busy and not self.executing and self.preview is not None and any(not i.error for i in self.preview.items))

    def invalidate(self):
        self.generation+=1;self.preview=None;self.execute_button.setEnabled(False)

    def fill_history_tag(self,tag):
        self.tag.setText(tag);self.invalidate();self.tag.setFocus()

    def request_preview(self):
        tag,generation=self.tag.text(),self.generation
        service,history_token=self.window.service,self.window.tag_history.token
        def ready(preview):
            if generation!=self.generation or service is not self.window.service:return
            self.show_preview(preview)
            if any(not item.error for item in preview.items):self.window.tag_history.remember(tag,history_token)
        self.window.coordinator.submit(lambda:service.preview(self.paths,tag),ready,self.details.setPlainText)

    def show_preview(self,preview):
        self.preview=preview;self.details.setPlainText(self.window.preview_text(preview));self.execute_button.setEnabled(not self.window.coordinator.pending and any(not i.error for i in preview.items))

    def execute(self):
        preview=self.preview
        if preview:
            self.executing=True;self.execute_button.setEnabled(False);self.cancel_button.setEnabled(False);self.tag.setEnabled(False)
            service=self.window.service
            self.window.coordinator.submit(lambda:service.execute(preview),self.finished_result,self.execution_failed)

    def finished_result(self,result):
        self.executing=False;self.execution_persisted.emit(result);self.window.show_result(result);self.accept()

    def execution_failed(self,message):
        self.executing=False;self.cancel_button.setEnabled(True);self.tag.setEnabled(True);self.details.setPlainText(message)

    def reject(self):
        if not self.executing:super().reject()
