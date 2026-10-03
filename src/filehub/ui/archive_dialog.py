from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QMessageBox
from .theme import apply_theme
from PySide6.QtCore import Signal
from .tag_history import HistoryChips

class ArchiveDialog(QDialog):
    execution_persisted=Signal(object)
    def __init__(self, window, paths, *, entry=None):
        super().__init__(window)
        self.setWindowTitle('手动标签');self.setMinimumWidth(438)
        self.window=window;self.paths=tuple(paths);self.preview=None;self.generation=0
        self.executing=False;self.closed=False;self.binding=window.capture_work_authority()
        self.service=self.binding[0];self.recovery_dialog=None;self._recovery_token=None
        self.entry=entry or self.service.manual_archive_entry(window.automation.catalog_snapshot)
        self.finished.connect(self._closed)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        title=QLabel('手动标签');title.setObjectName('heading');layout.addWidget(title)
        layout.addWidget(QLabel(f'已选择 {len(paths)} 项 · 先预览，再归档'))
        layout.addWidget(QLabel('项目代码与目的地'))
        self.tag=QLineEdit();self.tag.setObjectName('tag');self.tag.setPlaceholderText('例如 LYX020822');layout.addWidget(self.tag)
        self.history_chips=HistoryChips(window.tag_history,self.fill_history_tag);layout.addWidget(self.history_chips)
        self.recovery_notice=QLabel('先恢复手动标签归档，再预览目的地。此操作只允许手动归档，不会启用自动整理。')
        self.recovery_notice.setWordWrap(True);layout.addWidget(self.recovery_notice)
        self.profile_choice=QComboBox();self.profile_choice.addItem('请选择归档方案',None)
        for key,name in self.entry[2]:self.profile_choice.addItem(name,key)
        if len(self.entry[2])==1:self.profile_choice.setCurrentIndex(1)
        layout.addWidget(self.profile_choice)
        self.recovery_button=QPushButton('恢复手动标签归档');self.recovery_button.clicked.connect(self.request_recovery);layout.addWidget(self.recovery_button)
        self.details=QTextEdit();self.details.setReadOnly(True);self.details.setMinimumHeight(140);layout.addWidget(self.details)
        buttons=QHBoxLayout();self.cancel_button=QPushButton('取消');self.cancel_button.clicked.connect(self.reject);buttons.addWidget(self.cancel_button)
        self.preview_button=QPushButton('预览');buttons.addWidget(self.preview_button)
        self.execute_button=QPushButton('送进项目');self.execute_button.setObjectName('primary');self.execute_button.setEnabled(False);buttons.addWidget(self.execute_button);layout.addLayout(buttons)
        self.tag.textChanged.connect(self.invalidate)
        self.preview_button.clicked.connect(self.request_preview)
        self.execute_button.clicked.connect(self.execute)
        self.window.coordinator.busy.connect(self.busy_changed)
        self._show_recovery()
        apply_theme(self,window.service.config.theme)

    def _live(self):
        return (not self.closed and self.service is self.window.service and not self.service._closing
            and self.binding[1]==self.window.automation.state_generation)

    def _closed(self,_):
        self.closed=True;self.invalidate();self._recovery_token=None
        if self.recovery_dialog is not None:self.recovery_dialog.reject()

    def _authorized(self):
        snapshot=self.entry[0]
        return self.entry[1] is None and snapshot.compatibility_selection is not None and 'manual_archive' in snapshot.compatibility_permissions

    def _show_recovery(self):
        needs=not self._authorized()
        self.recovery_notice.setVisible(needs);self.recovery_button.setVisible(needs)
        self.profile_choice.setVisible(needs and len(self.entry[2])>1)
        self.busy_changed(bool(self.window.coordinator.pending))

    def request_recovery(self):
        if not self._live() or not self.window.admit_work() or self._authorized() or self._recovery_token is not None:return
        key=self.profile_choice.currentData()
        if key is None:self.details.setPlainText('请选择要恢复的归档方案。');return
        token=self._recovery_token=object();effective=self.window.automation.rule_generation
        snapshot=self.entry[0];selected=snapshot.compatibility_selection
        name='原来的项目设置' if self.entry[1] is not None else dict(self.entry[2])[key]
        message=f'确认恢复“{name}”的手动标签归档？旧定义会保留；自动规则、观察目录和自动整理设置不会因此启用。'
        if selected==key:message=f'“{name}”仅新增手动标签权限，现有设置保持。确认恢复？'
        elif selected is not None:
            message=f'归档方案将从“{snapshot.packages[selected].name}”切换到“{dict(self.entry[2])[key]}”。\n原方案的送进项目规则将关闭；新方案仅允许手动标签归档。确认切换？'
        review=QMessageBox(QMessageBox.Question,'恢复手动标签归档',message,
            QMessageBox.Yes|QMessageBox.No,self)
        review.setDefaultButton(QMessageBox.No);review.button(QMessageBox.Yes).setText('确认恢复');review.button(QMessageBox.No).setText('取消')
        self.recovery_dialog=review
        def current():return self._live() and self._recovery_token is token
        def finished(_):
            if (not current() or effective!=self.window.automation.rule_generation
                    or review.standardButton(review.clickedButton())!=QMessageBox.Yes):
                if self._recovery_token is token:self._recovery_token=None
                return
            service=self.service;entry=self.entry
            def work():
                if not current():raise ValueError('标签窗口已关闭；未恢复手动归档。')
                self.window.assert_work_authority(self.binding)
                return service.restore_manual_archive(key,entry)
            def ready(snapshot):
                if not current() or effective+1!=self.window.automation.rule_generation:return
                self._recovery_token=None;self.entry=service.manual_archive_entry(snapshot);self._show_recovery()
                self.details.setPlainText('手动标签归档已恢复。请预览目的地后再归档。')
            def failed(message):
                if current():self._recovery_token=None;self.details.setPlainText(message);self._show_recovery()
            self.window.automation.mutate(work,service=service,state_generation=self.binding[1],on_complete=ready,on_error=failed)
        review.finished.connect(finished);review.open()

    def busy_changed(self,busy):
        live=self._live()
        self.recovery_button.setEnabled(live and not busy and self._recovery_token is None)
        self.preview_button.setEnabled(live and not busy and self._authorized())
        self.execute_button.setEnabled(live and not busy and not self.executing and self.preview is not None and any(not i.error for i in self.preview.items))

    def invalidate(self):
        self.generation+=1;self.preview=None;self.execute_button.setEnabled(False)

    def fill_history_tag(self,tag):
        self.tag.setText(tag);self.invalidate();self.tag.setFocus()

    def request_preview(self):
        if not self._live() or not self._authorized() or not self.window.admit_work():return
        tag,generation=self.tag.text(),self.generation
        effective=self.window.automation.rule_generation
        service,history_token=self.service,self.window.tag_history.token
        def ready(preview):
            if not self._live() or generation!=self.generation or effective!=self.window.automation.rule_generation:return
            self.show_preview(preview)
            if any(not item.error for item in preview.items):self.window.tag_history.remember(tag,history_token)
        self.window.coordinator.submit(lambda:service.preview(self.paths,tag),ready,
            lambda message:self.details.setPlainText(message) if self._live() and generation==self.generation else None)

    def show_preview(self,preview):
        self.preview=preview;self.details.setPlainText(self.window.preview_text(preview));self.execute_button.setEnabled(not self.window.coordinator.pending and any(not i.error for i in preview.items))

    def execute(self):
        if not self._live() or not self.window.admit_work():return
        preview=self.preview
        if preview:
            self.executing=True;self.execute_button.setEnabled(False);self.cancel_button.setEnabled(False);self.tag.setEnabled(False)
            service=self.service
            self.window.coordinator.submit(lambda:service.execute(preview),self.finished_result,self.execution_failed)

    def finished_result(self,result):
        self.executing=False
        if not self._live():return
        self.execution_persisted.emit(result);self.window.show_result(result);self.accept()

    def execution_failed(self,message):
        if not self._live():return
        self.executing=False;self.cancel_button.setEnabled(True);self.tag.setEnabled(True);self.details.setPlainText(message)

    def reject(self):
        if not self.executing:super().reject()
