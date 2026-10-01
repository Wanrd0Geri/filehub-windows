from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit
from .theme import apply_theme

class ArchiveDialog(QDialog):
    def __init__(self, window, paths):
        super().__init__(window)
        self.setWindowTitle('送进项目');self.setMinimumWidth(438)
        self.window=window;self.paths=tuple(paths);self.preview=None;self.generation=0
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        title=QLabel('送进项目');title.setObjectName('heading');layout.addWidget(title)
        layout.addWidget(QLabel(f'已选择 {len(paths)} 项 · 先预览，再归档'))
        layout.addWidget(QLabel('项目代码与目的地'))
        self.tag=QLineEdit();self.tag.setObjectName('tag');self.tag.setPlaceholderText('例如 LYX020822');layout.addWidget(self.tag)
        self.details=QTextEdit();self.details.setReadOnly(True);self.details.setMinimumHeight(140);layout.addWidget(self.details)
        buttons=QHBoxLayout();cancel=QPushButton('取消');cancel.clicked.connect(self.reject);buttons.addWidget(cancel)
        self.preview_button=QPushButton('预览');buttons.addWidget(self.preview_button)
        self.execute_button=QPushButton('送进项目');self.execute_button.setObjectName('primary');self.execute_button.setEnabled(False);buttons.addWidget(self.execute_button);layout.addLayout(buttons)
        self.tag.textChanged.connect(self.invalidate)
        self.preview_button.clicked.connect(self.request_preview)
        self.execute_button.clicked.connect(self.execute)
        self.window.coordinator.busy.connect(self.busy_changed)
        apply_theme(self,window.service.config.theme)

    def busy_changed(self,busy):
        self.preview_button.setEnabled(not busy)
        self.execute_button.setEnabled(not busy and self.preview is not None and any(not i.error for i in self.preview.items))

    def invalidate(self):
        self.generation+=1;self.preview=None;self.execute_button.setEnabled(False)

    def request_preview(self):
        tag,generation=self.tag.text(),self.generation
        self.window.coordinator.submit(lambda:self.window.service.preview(self.paths,tag),lambda p:self.show_preview(p) if generation==self.generation else None,self.details.setPlainText)

    def show_preview(self,preview):
        self.preview=preview;self.details.setPlainText(self.window.preview_text(preview));self.execute_button.setEnabled(not self.window.coordinator.pending and any(not i.error for i in preview.items))

    def execute(self):
        preview=self.preview
        if preview:
            self.execute_button.setEnabled(False)
            self.window.coordinator.submit(lambda:self.window.service.execute(preview),self.finished_result,self.details.setPlainText)

    def finished_result(self,result):
        self.window.show_result(result);self.accept()
