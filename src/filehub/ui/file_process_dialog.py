"""Generic manual processing uses opaque worker preview authority."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QTextEdit,QFileDialog,QLayout
from .compact_message import CompactMessage
from .rule_requests import RulePreviewRequest
from .theme import apply_theme

class FileProcessWidget(QWidget):
    previewRequested=Signal(object)
    executeRequested=Signal(object)
    cancelRequested=Signal()
    changed=Signal()
    execution_persisted=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self._generation=0;self._token=None;self._sample_paths=();self._busy=False;self._can_execute=False;self._ruleset=None
        box=QVBoxLayout(self);box.setContentsMargins(12,12,12,12);box.setSizeConstraint(QLayout.SetMinimumSize)
        self.sample_label=QLabel('选择文件或文件夹；先预览，再明确执行。');self.sample_label.setWordWrap(True);box.addWidget(self.sample_label)
        row=QHBoxLayout();self.sample_button=QPushButton('选择文件');self.folder_sample_button=QPushButton('选择文件夹')
        row.addWidget(self.sample_button);row.addWidget(self.folder_sample_button);box.addLayout(row)
        self.rule_choice=QComboBox();box.addWidget(self.rule_choice)
        self.preview_text=QTextEdit();self.preview_text.setReadOnly(True);self.preview_text.setMinimumHeight(110);box.addWidget(self.preview_text,1)
        self.error_label=CompactMessage();self.error_label.setObjectName('error');box.addWidget(self.error_label)
        self.progress_label=CompactMessage();box.addWidget(self.progress_label)
        row=QHBoxLayout();self.preview_button=QPushButton('预览');self.execute_button=QPushButton('开始处理');self.execute_button.setObjectName('primary');self.cancel_button=QPushButton('取消当前任务')
        for button in (self.preview_button,self.execute_button,self.cancel_button):row.addWidget(button)
        box.addLayout(row)
        self.sample_button.clicked.connect(self._choose_samples);self.folder_sample_button.clicked.connect(self._choose_folder_sample)
        self.rule_choice.currentIndexChanged.connect(self._changed);self.preview_button.clicked.connect(self._preview)
        self.execute_button.clicked.connect(self._execute);self.cancel_button.clicked.connect(self.cancelRequested);self._buttons()
    @property
    def generation(self):return self._generation
    @property
    def selected_id(self):return self.rule_choice.currentData()
    def set_ruleset(self,snapshot):
        wanted=self.selected_id;self._ruleset=snapshot;self.rule_choice.blockSignals(True);self.rule_choice.clear();self.rule_choice.addItem('匹配已启用规则',None)
        for rule in snapshot.rules:self.rule_choice.addItem(('已启用 · ' if rule.enabled else '手动 · ')+rule.name,rule.id)
        self.rule_choice.setCurrentIndex(max(0,self.rule_choice.findData(wanted)));self.rule_choice.blockSignals(False);self.invalidate_preview();self._buttons()
    def set_sample_paths(self,paths):
        from pathlib import Path
        self._sample_paths=tuple(str(p) for p in paths)
        summary='、'.join(Path(p).name[:36] for p in self._sample_paths[:2])
        self.sample_label.setText('已选择 '+str(len(self._sample_paths))+' 项'+(' · '+summary+('…' if len(self._sample_paths)>2 else '') if summary else '；请选择文件或文件夹'))
        self.sample_label.setToolTip('\n'.join(self._sample_paths));self._changed()
    set_paths=set_sample_paths
    def _choose_samples(self):
        paths,_=QFileDialog.getOpenFileNames(self,'选择文件')
        if paths:self.set_sample_paths(paths)
    def _choose_folder_sample(self):
        path=QFileDialog.getExistingDirectory(self,'选择文件夹')
        if path:self.set_sample_paths([path])
    def _changed(self,*args):self.invalidate_preview();self.changed.emit()
    def invalidate_preview(self):self._generation+=1;self._token=None;self._can_execute=False;self.preview_text.clear();self._buttons()
    invalidate=invalidate_preview
    def _preview(self):
        try:
            if self._ruleset is None:raise ValueError('请先导入规则文件并绑定所需目录')
            self.previewRequested.emit(RulePreviewRequest(self.selected_id,self._sample_paths,self._ruleset.revision,self.generation))
        except ValueError as exc:self.show_error(str(exc))
    request_preview=_preview
    def _execute(self):
        if self._token is not None and self._can_execute and not self._busy:self.executeRequested.emit(self._token)
    execute=_execute
    def set_preview(self,text,token,can_execute):self.preview_text.setPlainText(text);self._token=token;self._can_execute=can_execute;self.error_label.clear();self._buttons()
    def show_error(self,message):
        translations={'Package installed; use replace':'此规则文件已安装，请使用“替换”。','Enabled rule unavailable':'所需目录未绑定或规则不可用，请先核对绑定。','Catalogue changed; reload required':'规则文件已变化，请重新载入并预览。','Active catalogue missing; explicit restore required':'规则目录缺失，请明确选择备份恢复。'}
        self.error_label.setText(translations.get(message,message));self.error_label.setToolTip(message);self.invalidate_preview()
    def set_busy(self,busy,*,cancellable=True):self._busy=busy;self._buttons()
    def set_cancel_pending(self,pending):self.progress_label.setText('正在安全结束当前任务…' if pending else '')
    def _buttons(self):
        if not hasattr(self,'preview_button'):return
        self.preview_button.setEnabled(not self._busy and bool(self._sample_paths) and self._ruleset is not None)
        self.execute_button.setEnabled(not self._busy and self._can_execute and self._token is not None);self.cancel_button.setEnabled(self._busy)
        for control in (self.sample_button,self.folder_sample_button,self.rule_choice):control.setEnabled(not self._busy)

class FileProcessDialog(QDialog):
    execution_persisted=Signal(object)
    transferRequested=Signal(object)
    def __init__(self,window,paths):
        super().__init__(window);self.window=window;self.paths=tuple(paths);self.setWindowTitle('文件处理');self.resize(600,480);self.transferred=False
        box=QVBoxLayout(self);self.panel=FileProcessWidget();box.addWidget(self.panel);self.kind='dialog-'+str(id(self));window.automation.register_panel(self.panel,self.kind)
        if window.automation.rules_snapshot:self.panel.set_ruleset(window.automation.rules_snapshot)
        self.panel.set_sample_paths(paths);self.panel.execution_persisted.connect(self._persisted)
        self.finished.connect(lambda _:window.automation.panels.pop(self.kind,None))
        row=QHBoxLayout();self.compatibility_button=QPushButton('个人项目归档…');row.addWidget(self.compatibility_button);self.dismiss_button=QPushButton('取消');self.dismiss_button.clicked.connect(self.reject);row.addWidget(self.dismiss_button);box.addLayout(row)
        self.compatibility_button.clicked.connect(lambda:self.transferRequested.emit(self));snapshot=window.automation.catalog_snapshot
        self.compatibility_button.setVisible(bool(snapshot and snapshot.compatibility_selection and 'manual_archive' in snapshot.compatibility_permissions));apply_theme(self,window.service.config.theme)
    def invalidate(self):self.panel.invalidate_preview()
    def _persisted(self,result):self.execution_persisted.emit(result);self.accept()
    def reject(self):
        if self.kind in self.window.automation.jobs:self.window.automation.cancel(self.kind);return
        super().reject()
