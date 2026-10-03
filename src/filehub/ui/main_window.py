from dataclasses import replace
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QStackedWidget,QListWidget,QListWidgetItem,QLineEdit,QTextEdit,QFileDialog,QFrame,QComboBox,QSpinBox,QCheckBox,QScrollArea,QLayout,QTabWidget)
from .coordinator import Coordinator
from .theme import apply_theme, icon
from .archive_dialog import ArchiveDialog
from .tag_history import HistoryController, HistoryChips
from .status_footer import StatusFooter
from .rules_page import RulesPage
from .file_process_dialog import FileProcessWidget, FileProcessDialog
from .conversion_page import ConversionPage
from .automation_controller import AutomationController

class MainWindow(QMainWindow):
    configuration_changed = Signal(object)
    demo_activated = Signal()
    result_ready = Signal(object)
    outcomes_ready = Signal(object, object)
    check_requested = Signal()
    automation_error = Signal(str)
    service_rebound = Signal(object)
    def __init__(self,service,store,*,demo_callback=None,pause_callback=None,integration_callback=None,integration_status_callback=None,inbox_provider=None):
        super().__init__();self.service=service;self.store=store
        self.demo_callback=demo_callback;self.pause_callback=pause_callback;self.integration_callback=integration_callback;self.inbox_provider=inbox_provider
        self.integration_status_callback=integration_status_callback;self.integration_status_ready=integration_status_callback is None;self.runtime_close_callback=None;self.is_demo=False
        self.paths=();self.preview=None;self.preview_generation=0;self.batches=[];self.dialogs=[];self.generated_details={}
        self.known_folder_proposals={};self._close_settled=False;self._close_requested=False;self._quit_requested=False;self.manual_check_callback=None;self.service_reopen_callback=None
        self.coordinator=Coordinator(self);self.setWindowTitle('FileHub');self.resize(1000,700);self.setMinimumSize(800,620);self.setAcceptDrops(True)
        self.tag_history=HistoryController(self.coordinator,store.state_dir,self)
        shell=QWidget();self.setCentralWidget(shell);outer=QHBoxLayout(shell);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(180);nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,22,12,17);nav.setSpacing(5)
        brand_row=QHBoxLayout();brand_row.setSpacing(10);brand_icon=QLabel();brand_icon.setFixedWidth(30);brand_icon.setPixmap(icon('FileHub').pixmap(30,30));brand_row.addWidget(brand_icon);brand=QLabel('FileHub');brand.setObjectName('brand');brand_row.addWidget(brand);nav.addLayout(brand_row);nav.addSpacing(18)
        self.pages=QStackedWidget();self.nav_buttons=[]
        for n,name in enumerate(('文件处理','规则文件','图片转换','记录','设置')):
            button=QPushButton(icon(name),name);button.setObjectName('nav');button.setCheckable(True);button.clicked.connect(lambda checked=False,i=n:self.navigate(i));nav.addWidget(button);self.nav_buttons.append(button)
        nav.addStretch();self.running=QLabel();self.running.setObjectName('muted');nav.addWidget(self.running);nav.addWidget(self.muted('本机 · Windows'))
        outer.addWidget(sidebar);outer.addWidget(self.pages,1)
        self.build_home();self.rules_page=RulesPage();self.rules_scroll=QScrollArea();self.rules_scroll.setWidgetResizable(True);self.rules_scroll.setWidget(self.rules_page);self.pages.addWidget(self.rules_scroll)
        self.conversion_page=ConversionPage(can_accept_paths=lambda:self.capture_work_authority() is not None);self.pages.addWidget(self.conversion_page)
        self.build_history();self.build_settings()
        self.status_footer=StatusFooter(self);self.status=self.status_footer.label
        self.statusBar().setObjectName('appStatusBar');self.statusBar().setSizeGripEnabled(False);self.statusBar().addWidget(self.status_footer,1)
        self.coordinator.busy.connect(self.busy_changed)
        self.outcomes_ready.connect(self._show_outcome_batches)
        self.rules_page.checkRequested.connect(self.manual_check)
        self.automation=AutomationController(self)
        self.load_config_controls();self.navigate(0);apply_theme(self,service.config.theme);self.refresh();self.tag_history.refresh()
        QApplication.styleHints().colorSchemeChanged.connect(self.system_theme_changed)

    def system_theme_changed(self,scheme):
        if self.service.config.theme=='system':apply_theme(self,'system')

    def capture_work_authority(self):
        adapter=getattr(self,'automation',None)
        if self._quit_requested or self._close_requested or (adapter is not None and not adapter.accepting):return None
        return self.service,adapter.state_generation if adapter is not None else 0

    def assert_work_authority(self,binding):
        service,generation=binding;adapter=getattr(self,'automation',None)
        current=adapter.state_generation if adapter is not None else 0
        if service is not self.service or generation!=current or service._closing:
            raise ValueError('操作所属状态已结束；未写入旧状态。')

    def admit_work(self):
        if self.capture_work_authority() is not None:return True
        self.show_error('正在切换状态或退出；未接受新的操作。');return False

    @staticmethod
    def muted(text):
        label=QLabel(text);label.setObjectName('muted');label.setWordWrap(True);return label

    def page(self,title,subtitle):
        widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(26,25,26,17);layout.setSpacing(14)
        heading=QLabel(title);heading.setObjectName('heading')
        if title=='文件，各归其位。':
            header=QHBoxLayout();header.addWidget(heading);header.addStretch();header.addWidget(self.button('送进项目',self.choose_files,True));layout.addLayout(header)
        else:layout.addWidget(heading)
        layout.addWidget(self.muted(subtitle));self.pages.addWidget(widget);return layout

    def button(self,text,action,primary=False):
        b=QPushButton(text);b.clicked.connect(action)
        if primary:b.setObjectName('primary')
        return b

    def build_home(self):
        layout=self.page('文件处理','选择文件，核对预览，再明确执行。')
        self.first_run=QLabel('导入外部规则文件并绑定所需目录，即可手动预览。自动处理还需启用规则、配置观察目录并取消暂停。');self.first_run.setWordWrap(True);self.first_run.setObjectName('firstRun');layout.addWidget(self.first_run)
        row=QHBoxLayout();row.addWidget(self.button('管理规则文件',lambda:self.navigate(1)));self.archive_button=self.button('个人项目归档…',self.choose_archive);self.archive_button.hide();row.addWidget(self.archive_button);row.addStretch();layout.addLayout(row)
        self.home_panel=FileProcessWidget();layout.addWidget(self.home_panel,1)
        self.recent_list=QListWidget();self.recent_list.setMaximumHeight(90);layout.addWidget(self.recent_list)
        self.pause_button=self.button('继续整理',self.toggle_pause);layout.addWidget(self.pause_button,alignment=Qt.AlignRight)
        home=layout.parentWidget();layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.pages.removeWidget(home);self.home_scroll=QScrollArea();self.home_scroll.setWidgetResizable(True);self.home_scroll.setWidget(home);self.pages.addWidget(self.home_scroll)

    def choose_archive(self):
        if not self.admit_work():return
        service=self.service
        def ready(_):
            if service is not self.service:return
            paths,_=QFileDialog.getOpenFileNames(self,'个人项目归档')
            if paths:self.open_archive_dialog(paths)
        self.coordinator.submit(lambda:service.archive_context(),ready,self.show_error)

    def build_history(self):
        layout=self.page('整理记录','每次归档都有迹可循。撤销会保护修改后的文件。')
        self.history_list=QListWidget();layout.addWidget(self.history_list,1);self.history_list.currentRowChanged.connect(self.show_history_details)
        self.history_details=QTextEdit();self.history_details.setReadOnly(True);self.history_details.setMaximumHeight(210);layout.addWidget(self.history_details)
        row=QHBoxLayout();row.addWidget(self.button('刷新',self.refresh));row.addStretch();row.addWidget(self.button('打开回收站',lambda:QDesktopServices.openUrl(QUrl('shell:RecycleBinFolder'))));self.undo_button=self.button('撤销所选批次',self.undo);row.addWidget(self.undo_button);layout.addLayout(row)

    def build_settings(self):
        layout=self.page('设置','观察目录需要明确选择；导入或绑定规则不会添加目录。')
        layout.addWidget(QLabel('观察目录 · 只处理最外层'))
        self.watch_list=QListWidget();layout.addWidget(self.watch_list,1)
        row=QHBoxLayout();row.addWidget(self.button('添加目录',lambda:self.choose_watch()));row.addWidget(self.button('桌面…',lambda:self.choose_watch('desktop')));row.addWidget(self.button('下载…',lambda:self.choose_watch('downloads')));row.addWidget(self.button('移除所选',lambda:self.watch_list.takeItem(self.watch_list.currentRow())));layout.addLayout(row)
        self.paused=QCheckBox('暂停自动处理（仍可手动预览和执行）');layout.addWidget(self.paused)
        row=QHBoxLayout();row.addWidget(QLabel('外观'));self.appearance=QComboBox();self.appearance.addItems(['深色','浅色','跟随系统']);row.addWidget(self.appearance);row.addStretch();layout.addLayout(row)
        layout.addWidget(self.muted('个人归档与清理需在规则文件页选择完整兼容定义并单独授权。'))
        self.autostart=QCheckBox('登录后自动运行');self.context_menu=QCheckBox('文件右键菜单：用 FileHub 处理…');layout.addWidget(self.autostart);layout.addWidget(self.context_menu)
        self.autostart.setEnabled(self.integration_callback is not None);self.context_menu.setEnabled(self.integration_callback is not None)
        self.save_button=self.button('保存设置',self.save_settings,True);layout.addWidget(self.save_button,alignment=Qt.AlignRight)

    def navigate(self,index):
        self.pages.setCurrentIndex(index)
        for n,b in enumerate(self.nav_buttons):b.setChecked(index==n)


    def load_config_controls(self):
        c=self.service.config;self.watch_list.clear();self.watch_list.addItems([str(p) for p in c.watch_roots]);self.appearance.setCurrentIndex(['dark','light','system'].index(c.theme));self.paused.setChecked(c.paused)
        self.running.setText('自动处理已暂停' if c.paused else '自动处理运行中');self.pause_button.setText('继续处理' if c.paused else '暂停处理')
        self.setWindowTitle('FileHub · 工程演示' if self.is_demo else 'FileHub')

    def choose_watch(self,role='downloads'):
        path=QFileDialog.getExistingDirectory(self,'选择自动整理目录',str(self.known_folder_proposals.get(role,'')))
        if path:self.watch_list.addItem(path)

    def choose_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'选择要归档的文件')
        if paths:self.set_paths(paths)

    def choose_source_folder(self):
        path=QFileDialog.getExistingDirectory(self,'选择要归档的文件夹')
        if path:self.set_paths([path])

    def set_paths(self,paths):
        self.paths=tuple(dict.fromkeys(Path(p) for p in paths));self.home_panel.set_sample_paths(self.paths)

    def dragEnterEvent(self,event):
        if self.pages.currentWidget() is self.conversion_page:
            self.conversion_page.dragEnterEvent(event);return
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()

    def dropEvent(self,event):
        if self.pages.currentWidget() is self.conversion_page:
            self.conversion_page.dropEvent(event);return
        self.set_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]);self.navigate(0);event.acceptProposedAction()

    def dragMoveEvent(self,event):
        if self.pages.currentWidget() is self.conversion_page:
            self.conversion_page.dragMoveEvent(event);return
        super().dragMoveEvent(event)

    def invalidate_preview(self):
        self.preview_generation+=1;self.preview=None
        if hasattr(self,'home_panel'):self.home_panel.invalidate_preview()

    def preview_text(self,preview):
        rows=[]
        for i in preview.items:
            destinations=[]
            for target in i.targets:
                try:destination=str(target.parent.relative_to(self.service.config.sync_root))
                except (ValueError,TypeError):destination=str(target.parent)
                destinations.append(f'新文件名：{target.name}\n目的地：{destination}')
            rows.append('来源：'+i.source.name+'\n'+('\n'.join(destinations) or '无可执行目的地')+('\n问题：'+i.error if i.error else '')+('\n提示：'+'；'.join(i.warnings) if i.warnings else ''))
        return '\n\n'.join(rows)

    def request_preview(self):self.home_panel._preview()
    def execute(self):self.home_panel._execute()

    def show_result(self,result):
        summary={'success':'已完成，可在记录中撤销。','partial':'部分完成，请查看记录中的问题。','failed':'未完成，请查看记录。'}[result.status]
        details=self.duplicate_details(result)
        self.status.setText(summary+('\n'+'\n'.join(details) if details else ''));self.refresh()
        if result.ok:self.set_paths([])
        self.result_ready.emit(result)

    def show_run_outcomes(self,outcomes,service=None,generation=None):
        service=service or self.service
        generation=self.automation.state_generation if generation is None else generation
        ids={outcome.batch_id for outcome in outcomes if outcome.batch_id}
        def read():return tuple(batch for batch in service.history() if batch.batch_id in ids)
        self.coordinator.submit(read,lambda batches:self.outcomes_ready.emit((service,generation,tuple(outcomes)),batches),self.show_error,lifecycle=True)

    def _show_outcome_batches(self,binding,batches):
        service,generation,outcomes=binding
        if service is not self.service or generation!=self.automation.state_generation:return
        for batch in batches:self.show_result(batch)
        errors=[outcome.error for outcome in outcomes if outcome.error]
        if errors:self.show_error('；'.join(errors[:3]))
        elif not outcomes:self.status.setText('已取消，未开始剩余项目。')

    def manual_check(self):
        if not self.admit_work():return
        if self.manual_check_callback:self.manual_check_callback();return
        from ..scheduler import Scheduler
        service,generation=self.service,self.automation.state_generation
        def check():
            scheduler=Scheduler(service,automatic_completion=self.automation.completion_hook(service,generation))
            return scheduler.tick(datetime.now().astimezone()),scheduler.last_errors
        def ready(value):
            if service is not self.service or generation!=self.automation.state_generation:return
            results,errors=value
            for result in results:
                if hasattr(result,'items'):self.show_result(result)
                else:self.show_run_outcomes((result,),service,generation)
            if errors:self.show_error('；'.join(errors[:3]))
            if not results and not errors:self.status.setText('立即检查已完成；图片任务如已排队会在完成后更新记录。')
        self.coordinator.submit(check,ready,self.show_error)

    def show_error(self,message):self.status.setText('操作未完成：'+message)

    @staticmethod
    def duplicate_details(batch):
        lines=[]
        for outcome in batch.outcomes:
            if not outcome.duplicate:continue
            recycled=any(i.source==outcome.source and i.kind=='recycle' and i.state in {'recycled','manual_restore'} for i in batch.items)
            state='来源已回收' if recycled else '来源回收未完成，请核对原位置、暂存或回收站'
            lines.append(f'重复文件：{outcome.source}\n原因：项目中已有相同内容的副本\n已有副本完整路径：{outcome.duplicate}\n{state}')
        return lines

    def busy_changed(self,busy):
        self.save_button.setEnabled(not busy);self.undo_button.setEnabled(not busy)
        self.pause_button.setEnabled(not busy and self.capture_work_authority() is not None)

    def refresh(self):
        service=self.service;generation=self.automation.state_generation
        def read():
            with service.engine.locked():
                batches=service.history()
                details={item.operation_id:service.engine.journal.generated(item.operation_id) for batch in batches for item in batch.items if item.kind=='convert'}
                return batches,details
        def ready(value):
            if service is not self.service or generation!=self.automation.state_generation:return
            batches,self.generated_details=value;self.show_history(batches)
        self.coordinator.submit(read,ready,lambda message:self.show_error(message) if service is self.service and generation==self.automation.state_generation else None,lifecycle=True)

    def show_history(self,batches):
        self.batches=batches;self.history_list.clear();self.recent_list.clear()
        self.recent_list.setVisible(bool(batches))
        for n,b in enumerate(batches):
            states={'success':'完成','partial':'部分完成','failed':'需要查看'}
            try:local=datetime.fromisoformat(b.created.replace('Z','+00:00')).astimezone().strftime('%m月%d日 %H:%M')
            except ValueError:local=b.created
            text=f'{b.label}  ·  {states[b.status]}\n{local}'
            item=QListWidgetItem(text);item.setToolTip(b.created);self.history_list.addItem(item)
            if n<3:
                roots=[i for i in b.items if not getattr(i,'parent_operation_id',None)]
                target=(roots[0].target or roots[0].source) if roots else None
                if target:
                    try:destination=str(target.parent.relative_to(self.service.config.sync_root))
                    except (ValueError,TypeError):destination=str(target.parent)
                    text=f'{target.name}'+(f' +其余 {len(roots)-1} 项' if len(roots)>1 else '')+f' · {local}\n{destination}'
                item=QListWidgetItem(text);item.setToolTip(b.label+'\n'+b.created);self.recent_list.addItem(item)
        if not batches:self.recent_list.addItem('暂无处理记录 · 选择文件并预览开始')
        self.recent_list.setFixedHeight(max(1,min(3,len(batches)))*70+10)

    def show_history_details(self,index):
        if not 0<=index<len(self.batches):self.history_details.clear();return
        batch=self.batches[index];lines=[]
        for item in batch.items:
            action={'move':'移动','copy':'复制','recycle':'移到回收站','convert':'图片转换/替换'}.get(item.kind,item.kind)
            state={'committed':'已完成','undone':'已撤销','recycled':'已回收','manual_restore':'需手动还原','conflict':'存在冲突','failed':'未完成','pending':'等待处理','planned':'等待处理'}.get(item.state,'需要查看')
            lines.append(f'{action} · {state}\n原位置：{item.source}\n目标位置：{item.target or "—"}\n说明：{item.message or "—"}')
            if item.kind=='convert':
                generated=self.generated_details.get(item.operation_id)
                if generated:
                    if generated.backup:lines.append('原图备份：'+str(generated.backup))
                    if generated.swap:lines.append('原图暂存：'+str(generated.swap))
                    if generated.undo_stage:lines.append('恢复暂存：'+str(generated.undo_stage))
                    if generated.undo_swap:lines.append('恢复交换位置：'+str(generated.undo_swap))
            if item.state=='manual_restore':
                staging=str(item.staging or item.recycle_identity or '记录未提供回收名称')
                lines.append(f'需要手动恢复\n回收暂存名称：{staging}\n原文件名：{item.source.name}\n原完整路径：{item.source}\n打开回收站恢复后，可能得到 .filehub 暂存名称，请改回原文件名。')
        lines.extend(str(o.source)+'\n'+o.error for o in batch.outcomes if o.error)
        lines.extend(self.duplicate_details(batch))
        self.history_details.setPlainText('\n\n'.join(lines))

    def undo(self):
        if not self.admit_work():return
        index=self.history_list.currentRow()
        if 0<=index<len(self.batches):
            batch_id=self.batches[index].batch_id;service=self.service
            self.coordinator.submit(lambda:service.undo(batch_id),self.show_result,self.show_error)

    def save_settings(self):
        if not self.admit_work():return
        if self.integration_status_callback and not self.integration_status_ready:
            self.show_error('正在读取 Windows 集成设置，请稍候。');return
        self.invalidate_preview()
        for dialog in self.dialogs:dialog.invalidate()
        config=replace(self.service.config,watch_roots=tuple(Path(self.watch_list.item(i).text()) for i in range(self.watch_list.count())),paused=self.paused.isChecked(),theme=['dark','light','system'][self.appearance.currentIndex()])
        integration=(self.autostart.isChecked(),self.context_menu.isChecked());integration_callback=self.integration_callback
        service,store,generation=self.service,self.store,self.automation.state_generation
        self.automation.config_requested(service.config,config)
        def save():
            with service.engine.locked():
                store.save(config);service.config=config
            if integration_callback:
                try:integration_callback(*integration)
                except Exception as exc:raise RuntimeError('设置已保存，但 Windows 集成未完成：'+str(exc)) from exc
            return config
        self.coordinator.submit(save,lambda value:self.saved(value) if service is self.service and generation==self.automation.state_generation else None,
            lambda message:self.settings_failed(message) if service is self.service and generation==self.automation.state_generation else None)

    def saved(self,config):
        self.invalidate_preview()
        for dialog in self.dialogs:dialog.invalidate()
        self.load_config_controls();apply_theme(self,config.theme);self.configuration_changed.emit(config);self.status.setText('设置已保存。')
        self.refresh_integration()
        self.automation.config_saved()
        self.refresh()

    def settings_failed(self,message):
        self.load_config_controls();apply_theme(self,self.service.config.theme);self.configuration_changed.emit(self.service.config)
        self.refresh_integration();self.show_error(message)

    def refresh_integration(self):
        if self.integration_status_callback:
            self.integration_status_ready=False;self.autostart.setEnabled(False);self.context_menu.setEnabled(False)
            self.coordinator.submit(self.integration_status_callback,self.show_integration_status,self.show_error)

    def show_integration_status(self,status):
        self.integration_status_ready=True;self.autostart.setEnabled(True);self.context_menu.setEnabled(True)
        self.autostart.setChecked(status['autostart']);self.context_menu.setChecked(status['context_menu'])

    def toggle_pause(self):
        if not self.admit_work():return
        config=replace(self.service.config,paused=not self.service.config.paused)
        service,store,generation=self.service,self.store,self.automation.state_generation
        self.automation.config_requested(service.config,config)
        def change():
            with service.engine.locked():store.save(config);service.config=config
            if self.pause_callback:self.pause_callback(config.paused)
            return config
        self.coordinator.submit(change,lambda value:self.saved(value) if service is self.service and generation==self.automation.state_generation else None,self.show_error)

    def start_demo(self):
        if not self.admit_work():return
        if self.coordinator.pending or self.dialogs:
            self.show_error('请先完成当前操作或关闭归档窗口，再进入演示。');return
        if self.demo_callback:
            self.status.setText('正在取消图片任务；安全完成当前替换后进入演示。')
            self.coordinator.begin_wait()
            def settled():
                if not self._quit_requested:
                    self.coordinator.submit(self.demo_callback,self.demo_ready,self.demo_failed,lifecycle=True)
                self.coordinator.end_wait()
            self.automation.retire(settled)
        else:self.status.setText('演示将在应用启动器接入后启用。')

    def demo_ready(self,result):
        if not result:
            self.demo_failed('没有创建演示状态；已请求恢复原状态。');return
        if result:
            self.invalidate_preview()
            for dialog in self.dialogs:dialog.invalidate()
            self.service,self.store,paths=result;self.automation.rebind();self.tag_history.switch_state(self.store.state_dir);self.is_demo=True;self.load_config_controls();self.set_paths(paths);self.refresh();self.demo_activated.emit()
        self.status.setText('演示只使用独立示例目录，可尝试归档与撤销。')

    def demo_failed(self,message):
        # The old executor is already settled and retired. Reconstruct the same
        # state through a new service; never reset an executor's closing latch.
        old=self.service
        def reopen():
            if self.service_reopen_callback:return self.service_reopen_callback(old)
            from ..service import FileHubService
            return FileHubService(old.config,old.engine.state_dir,platform=old.engine.platform,probe=old.probe,source_time=old.source_time)
        def ready(service):
            self.service=service;self.automation.rebind();self.load_config_controls();self.refresh()
            self.service_rebound.emit(service)
            self.show_error('未进入演示，原状态已恢复：'+message)
        def failed(error):
            self.show_error('未进入演示；恢复原状态失败，请安全退出后重新打开。原任务已安全结束：'+message+'；'+error)
        self.coordinator.submit(reopen,ready,failed,lifecycle=True)

    def open_archive_dialog(self,paths,*,entry=None):
        if not self.admit_work():return None
        dialog=ArchiveDialog(self,paths,entry=entry);self.dialogs.append(dialog);dialog.finished.connect(lambda _:self.dialogs.remove(dialog) if dialog in self.dialogs else None);dialog.show();dialog.raise_();dialog.activateWindow();return dialog

    def open_file_dialog(self,paths):
        if not self.admit_work():return None
        dialog=FileProcessDialog(self,paths);self.dialogs.append(dialog)
        dialog.finished.connect(lambda _:self.dialogs.remove(dialog) if dialog in self.dialogs else None)
        dialog.transferRequested.connect(self.transfer_archive)
        dialog.show();dialog.raise_();dialog.activateWindow();return dialog

    def transfer_archive(self,dialog):
        if (getattr(self,'_archive_transfer',None) is not None or dialog not in self.dialogs
                or not isinstance(dialog,FileProcessDialog) or dialog.kind in self.automation.jobs or not self.admit_work()):return
        service=self.service;adapter=self.automation;panel=dialog.panel
        runtime=getattr(self,'runtime',None)
        claim=getattr(runtime,'active_claim',None) if runtime and runtime.claim_dialog is dialog else None
        queue=getattr(runtime,'claim_queue',None) if claim else None
        request=object();self._archive_transfer=request
        state,effective,page=adapter.state_generation,adapter.rule_generation,panel.generation
        panel.set_transfer_pending(True);dialog.compatibility_button.setEnabled(False)
        def current():
            return (self._archive_transfer is request and service is self.service
                and state==adapter.state_generation and effective==adapter.rule_generation
                and dialog in self.dialogs and adapter.panels.get(dialog.kind) is panel
                and panel.generation==page and dialog.kind not in adapter.jobs
                and (claim is None or (runtime.claim_dialog is dialog and runtime.active_claim is claim and runtime.claim_queue is queue)))
        def finish():
            valid=current()
            if self._archive_transfer is request:self._archive_transfer=None
            if dialog in self.dialogs and adapter.panels.get(dialog.kind) is panel:
                panel.set_transfer_pending(False);dialog.compatibility_button.setEnabled(True)
            return valid
        def canceled(_):
            if self._archive_transfer is request:self._archive_transfer=None
        dialog.finished.connect(canceled)
        def ready(_):
            if not finish():return
            replacement=self.open_archive_dialog(dialog.panel._sample_paths)
            if replacement is None:return
            if claim is not None:
                runtime.bind_claim_dialog(replacement)
            dialog.transferred=True;dialog.accept()
        def failed(message):
            if finish():self.show_error(message)
        self.coordinator.submit(lambda:service.archive_context(),ready,failed)

    def closeEvent(self,event):
        if self.runtime_close_callback:
            if not self.runtime_close_callback():event.ignore()
            else:event.accept()
        elif self._close_settled:event.accept()
        else:
            event.ignore()
            if self._close_requested:return
            self._close_requested=True
            def closed():self._close_settled=True;self.close()
            self.automation.retire(closed)
