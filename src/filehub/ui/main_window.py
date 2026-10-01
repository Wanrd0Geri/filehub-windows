from dataclasses import replace
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QStackedWidget,QListWidget,QListWidgetItem,QLineEdit,QTextEdit,QFileDialog,QFrame,QComboBox,QSpinBox,QCheckBox,QScrollArea)
from .coordinator import Coordinator
from .theme import apply_theme, icon
from .archive_dialog import ArchiveDialog

class MainWindow(QMainWindow):
    configuration_changed = Signal(object)
    demo_activated = Signal()
    result_ready = Signal(object)
    def __init__(self,service,store,*,demo_callback=None,pause_callback=None,integration_callback=None,integration_status_callback=None,inbox_provider=None):
        super().__init__();self.service=service;self.store=store
        self.demo_callback=demo_callback;self.pause_callback=pause_callback;self.integration_callback=integration_callback;self.inbox_provider=inbox_provider
        self.integration_status_callback=integration_status_callback;self.integration_status_ready=integration_status_callback is None;self.runtime_close_callback=None;self.is_demo=False
        self.paths=();self.preview=None;self.preview_generation=0;self.batches=[];self.dialogs=[]
        self.known_folder_proposals={}
        self.coordinator=Coordinator(self);self.setWindowTitle('FileHub');self.resize(1000,700);self.setMinimumSize(800,620);self.setAcceptDrops(True)
        shell=QWidget();self.setCentralWidget(shell);outer=QHBoxLayout(shell);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(180);nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,22,12,17);nav.setSpacing(5)
        brand_row=QHBoxLayout();brand_row.setSpacing(10);brand_icon=QLabel();brand_icon.setFixedWidth(30);brand_icon.setPixmap(icon('FileHub').pixmap(30,30));brand_row.addWidget(brand_icon);brand=QLabel('FileHub');brand.setObjectName('brand');brand_row.addWidget(brand);nav.addLayout(brand_row);nav.addSpacing(18)
        self.pages=QStackedWidget();self.nav_buttons=[]
        for n,name in enumerate(('整理','收件箱','记录','设置')):
            button=QPushButton(icon(name),name);button.setObjectName('nav');button.setCheckable(True);button.clicked.connect(lambda checked=False,i=n:self.navigate(i));nav.addWidget(button);self.nav_buttons.append(button)
        nav.addStretch();self.running=QLabel();self.running.setObjectName('muted');nav.addWidget(self.running);nav.addWidget(self.muted('本机 · Windows'))
        outer.addWidget(sidebar);outer.addWidget(self.pages,1)
        self.build_home();self.build_inbox();self.build_history();self.build_settings()
        self.status=QLabel('');self.status.setWordWrap(True);self.statusBar().addWidget(self.status,1)
        self.coordinator.busy.connect(self.busy_changed)
        self.load_config_controls();self.navigate(0);apply_theme(self,service.config.theme);self.refresh()
        QApplication.styleHints().colorSchemeChanged.connect(self.system_theme_changed)

    def system_theme_changed(self,scheme):
        if self.service.config.theme=='system':apply_theme(self,'system')

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
        layout=self.page('文件，各归其位。','留下需要的，其余交给 FileHub。')
        self.first_run=QLabel('欢迎使用 FileHub\n先选择同步空间，再选择要自动整理的目录。\n新发现的文件会完整等待 3 天；首次启动保持暂停。');self.first_run.setObjectName('firstRun');self.first_run.setWordWrap(True);layout.addWidget(self.first_run)
        self.demo_notice=self.muted('演示 · 当前文件和同步空间均为独立示例。普通启动会返回原设置。');self.demo_notice.hide();layout.addWidget(self.demo_notice)
        row=QHBoxLayout();row.addWidget(self.button('选择文件',self.choose_files));row.addWidget(self.button('选择文件夹',self.choose_source_folder));self.first_sync_button=self.button('选择同步空间',self.first_choose_sync);row.addWidget(self.first_sync_button);row.addStretch();self.demo_button=self.button('演示',self.start_demo);row.addWidget(self.demo_button);layout.addLayout(row)
        self.selection=QLabel('将文件拖到这里，或选择多个文件。');self.selection.setWordWrap(True);layout.addWidget(self.selection)
        self.source_cards=[];self.source_titles=[];cards=QHBoxLayout()
        for name in ('桌面','下载'):
            card=QFrame();card.setObjectName('card');box=QVBoxLayout(card);box.setContentsMargins(16,14,16,14);title=QLabel(name);self.source_titles.append(title);card_head=QHBoxLayout();mark=QLabel();mark.setPixmap(icon('整理').pixmap(22,22));card_head.addWidget(mark);card_head.addWidget(title);card_head.addStretch();box.addLayout(card_head);status=self.muted('未选择目录 · 已暂停');box.addWidget(status);self.source_cards.append(status);cards.addWidget(card)
        layout.addLayout(cards)
        self.editor=QWidget();editor_layout=QVBoxLayout(self.editor);editor_layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.tag=QLineEdit();self.tag.setPlaceholderText('项目代码与目的地，例如 LYX020822');row.addWidget(self.tag,1);self.preview_button=self.button('预览',self.request_preview);row.addWidget(self.preview_button);self.execute_button=self.button('送进项目',self.execute,True);row.addWidget(self.execute_button);editor_layout.addLayout(row)
        self.preview_details=QTextEdit();self.preview_details.setReadOnly(True);self.preview_details.setPlaceholderText('预览将显示每项的目的地、警告与问题。');self.preview_details.setMaximumHeight(160);editor_layout.addWidget(self.preview_details);layout.addWidget(self.editor);self.editor.hide()
        self.tag.textChanged.connect(self.invalidate_preview)
        layout.addWidget(self.muted('最近整理'));self.recent_list=QListWidget();layout.addWidget(self.recent_list);layout.addStretch(1)
        self.pause_button=self.button('继续整理',self.toggle_pause);layout.addWidget(self.pause_button,alignment=Qt.AlignRight)

    def build_inbox(self):
        layout=self.page('收件箱','暂时没有归属的文件，在这里留一会儿。')
        self.inbox_list=QListWidget();self.inbox_list.setSelectionMode(QListWidget.ExtendedSelection);layout.addWidget(self.inbox_list)
        row=QHBoxLayout();row.addWidget(self.button('刷新',self.refresh_inbox));row.addWidget(self.button('送进项目',self.archive_inbox));row.addWidget(self.button('打开所选位置',self.open_inbox));layout.addLayout(row)
        layout.addWidget(self.muted('共享到期清理默认由 Mac 管理，Windows 已关闭。'))

    def build_history(self):
        layout=self.page('整理记录','每次归档都有迹可循。撤销会保护修改后的文件。')
        self.history_list=QListWidget();layout.addWidget(self.history_list,1);self.history_list.currentRowChanged.connect(self.show_history_details)
        self.history_details=QTextEdit();self.history_details.setReadOnly(True);self.history_details.setMaximumHeight(210);layout.addWidget(self.history_details)
        row=QHBoxLayout();row.addWidget(self.button('刷新',self.refresh));row.addStretch();row.addWidget(self.button('打开回收站',lambda:QDesktopServices.openUrl(QUrl('shell:RecycleBinFolder'))));self.undo_button=self.button('撤销所选批次',self.undo);row.addWidget(self.undo_button);layout.addLayout(row)

    def build_settings(self):
        layout=self.page('设置','按你的习惯，安静地运行。')
        self.sync_path=QLineEdit();self.sync_path.setReadOnly(True);row=QHBoxLayout();row.addWidget(self.sync_path,1);row.addWidget(self.button('选择同步空间',self.choose_sync));layout.addWidget(QLabel('同步空间'));layout.addLayout(row)
        layout.addWidget(QLabel('自动整理目录 · 明确选择后才生效'));self.watch_list=QListWidget();self.watch_list.setMinimumHeight(92);self.watch_list.setMaximumHeight(130);layout.addWidget(self.watch_list)
        row=QHBoxLayout();row.addWidget(self.button('添加目录',lambda:self.choose_watch()));row.addWidget(self.button('桌面…',lambda:self.choose_watch('desktop')));row.addWidget(self.button('下载…',lambda:self.choose_watch('downloads')));row.addWidget(self.button('移除所选',lambda:self.watch_list.takeItem(self.watch_list.currentRow())));layout.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel('首次发现后等待'));self.sweep_days=QSpinBox();self.sweep_days.setRange(1,365);self.sweep_days.setSuffix(' 天');row.addWidget(self.sweep_days);row.addStretch();row.addWidget(QLabel('外观'));self.appearance=QComboBox();self.appearance.addItems(['深色','浅色','跟随系统']);row.addWidget(self.appearance);layout.addLayout(row)
        self.paused=QCheckBox('暂停自动整理（仍可手动归档）');layout.addWidget(self.paused)
        self.global_jobs=QCheckBox('由这台电脑管理共享任务（高级）');layout.addWidget(self.global_jobs)
        layout.addWidget(self.muted('共享收件箱到期清理 + 同步空间不合规文件名修正（包括已有项目）。\n仅一台电脑开启；默认由 Mac 管理 / 关闭。普通文件名和项目路由不变。'))
        row=QHBoxLayout();row.addWidget(QLabel('共享收件箱保留'));self.inbox_days=QSpinBox();self.inbox_days.setRange(1,365);self.inbox_days.setSuffix(' 天');row.addWidget(self.inbox_days);row.addStretch();layout.addLayout(row)
        self.autostart=QCheckBox('登录后自动运行');self.context_menu=QCheckBox('文件右键菜单：送进项目');layout.addWidget(self.autostart);layout.addWidget(self.context_menu)
        self.autostart.setEnabled(self.integration_callback is not None);self.context_menu.setEnabled(self.integration_callback is not None)
        layout.addStretch();self.save_button=self.button('保存设置',self.save_settings,True);layout.addWidget(self.save_button,alignment=Qt.AlignRight)
        settings=layout.parentWidget();settings.setMinimumHeight(680)
        self.pages.removeWidget(settings);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(settings);self.pages.addWidget(scroll)

    def navigate(self,index):
        self.pages.setCurrentIndex(index)
        for n,b in enumerate(self.nav_buttons):b.setChecked(index==n)
        if index==1:self.refresh_inbox()

    def load_config_controls(self):
        c=self.service.config;self.sync_path.setText(str(c.sync_root or ''));self.watch_list.clear();self.watch_list.addItems([str(p) for p in c.watch_roots]);self.sweep_days.setValue(c.sweep_days);self.inbox_days.setValue(c.inbox_days);self.appearance.setCurrentIndex(['dark','light','system'].index(c.theme));self.paused.setChecked(c.paused);self.global_jobs.setChecked(c.global_jobs)
        self.first_run.setVisible(c.sync_root is None);self.running.setText('自动整理已暂停' if c.paused else '自动整理运行中');self.pause_button.setText('继续整理' if c.paused else '暂停整理')
        self.first_sync_button.setVisible(c.sync_root is None)
        self.setWindowTitle('FileHub · 演示' if self.is_demo else 'FileHub')
        self.demo_notice.setVisible(self.is_demo)
        if self.is_demo:self.running.setText('演示 · '+self.running.text())
        for n,label in enumerate(self.source_cards):
            text=str(c.watch_roots[n]) if n<len(c.watch_roots) else '未选择目录'
            self.source_titles[n].setText(c.watch_roots[n].name if n<len(c.watch_roots) else ('桌面','下载')[n])
            label.setText(('已选择目录' if n<len(c.watch_roots) else text)+' · '+('已暂停' if c.paused else f'首次发现 {c.sweep_days} 天后送入收件箱'));label.setToolTip(text)

    def choose_sync(self):
        path=QFileDialog.getExistingDirectory(self,'选择同步空间')
        if path:self.sync_path.setText(path)

    def first_choose_sync(self):
        self.navigate(3);self.choose_sync()

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
        self.paths=tuple(dict.fromkeys(Path(p) for p in paths));self.selection.setText(f'已选择 {len(self.paths)} 项 · '+ '、'.join(p.name for p in self.paths) if self.paths else '将文件拖到这里，或选择多个文件。');self.selection.setToolTip('\n'.join(map(str,self.paths)));self.invalidate_preview()
        self.editor.setVisible(bool(self.paths))

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()

    def dropEvent(self,event):
        self.set_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]);self.navigate(0);event.acceptProposedAction()

    def invalidate_preview(self):
        self.preview_generation+=1;self.preview=None;self.execute_button.setEnabled(False)

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

    def request_preview(self):
        paths,tag,generation=self.paths,self.tag.text(),self.preview_generation
        self.coordinator.submit(lambda:self.service.preview(paths,tag),lambda p:self.show_preview(p) if generation==self.preview_generation else None,self.show_error)

    def show_preview(self,preview):
        self.preview=preview;self.preview_details.setPlainText(self.preview_text(preview));self.preview_details.setToolTip('\n'.join(str(i.source)+'\n'+'\n'.join(map(str,i.targets)) for i in preview.items));self.execute_button.setEnabled(any(not i.error for i in preview.items))

    def execute(self):
        preview=self.preview
        if preview:self.invalidate_preview();self.coordinator.submit(lambda:self.service.execute(preview),self.show_result,self.show_error)

    def show_result(self,result):
        summary={'success':'已完成，可在记录中撤销。','partial':'部分完成，请查看记录中的问题。','failed':'未完成，请查看记录。'}[result.status]
        details=self.duplicate_details(result)
        self.status.setText(summary+('\n'+'\n'.join(details) if details else ''));self.refresh()
        if result.ok:self.set_paths([])
        self.result_ready.emit(result)

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
        self.preview_button.setEnabled(not busy);self.save_button.setEnabled(not busy);self.undo_button.setEnabled(not busy)
        self.execute_button.setEnabled(not busy and self.preview is not None and any(not i.error for i in self.preview.items))

    def refresh(self):self.coordinator.submit(self.service.history,self.show_history,self.show_error)

    def show_history(self,batches):
        self.batches=batches;self.history_list.clear();self.recent_list.clear()
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
        if not batches:self.recent_list.addItem('暂无整理记录 · 选择文件开始，或试试演示')
        self.recent_list.setFixedHeight(max(1,min(3,len(batches)))*70+10)

    def show_history_details(self,index):
        if not 0<=index<len(self.batches):self.history_details.clear();return
        batch=self.batches[index];lines=[]
        for item in batch.items:
            action={'move':'移动','copy':'复制','recycle':'移到回收站'}.get(item.kind,item.kind)
            state={'committed':'已完成','undone':'已撤销','recycled':'已回收','manual_restore':'需手动还原','conflict':'存在冲突','failed':'未完成','pending':'等待处理','planned':'等待处理'}.get(item.state,'需要查看')
            lines.append(f'{action} · {state}\n原位置：{item.source}\n目标位置：{item.target or "—"}\n说明：{item.message or "—"}')
            if item.state=='manual_restore':
                staging=str(item.staging or item.recycle_identity or '记录未提供回收名称')
                lines.append(f'需要手动恢复\n回收暂存名称：{staging}\n原文件名：{item.source.name}\n原完整路径：{item.source}\n打开回收站恢复后，可能得到 .filehub 暂存名称，请改回原文件名。')
        lines.extend(str(o.source)+'\n'+o.error for o in batch.outcomes if o.error)
        lines.extend(self.duplicate_details(batch))
        self.history_details.setPlainText('\n\n'.join(lines))

    def undo(self):
        index=self.history_list.currentRow()
        if 0<=index<len(self.batches):
            batch_id=self.batches[index].batch_id;self.coordinator.submit(lambda:self.service.undo(batch_id),self.show_result,self.show_error)

    def save_settings(self):
        if self.integration_status_callback and not self.integration_status_ready:
            self.show_error('正在读取 Windows 集成设置，请稍候。');return
        self.invalidate_preview()
        for dialog in self.dialogs:dialog.invalidate()
        config=replace(self.service.config,sync_root=Path(self.sync_path.text()) if self.sync_path.text() else None,watch_roots=tuple(Path(self.watch_list.item(i).text()) for i in range(self.watch_list.count())),paused=self.paused.isChecked(),global_jobs=self.global_jobs.isChecked(),sweep_days=self.sweep_days.value(),inbox_days=self.inbox_days.value(),theme=['dark','light','system'][self.appearance.currentIndex()])
        integration=(self.autostart.isChecked(),self.context_menu.isChecked())
        def save():
            self.store.save(config)
            self.service.config=config
            if self.integration_callback:
                try:self.integration_callback(*integration)
                except Exception as exc:raise RuntimeError('设置已保存，但 Windows 集成未完成：'+str(exc)) from exc
            return config
        self.coordinator.submit(save,self.saved,self.settings_failed)

    def saved(self,config):
        self.invalidate_preview()
        for dialog in self.dialogs:dialog.invalidate()
        self.load_config_controls();apply_theme(self,config.theme);self.configuration_changed.emit(config);self.status.setText('设置已保存。')
        self.refresh_integration()

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
        config=replace(self.service.config,paused=not self.service.config.paused)
        def change():
            self.store.save(config);self.service.config=config
            if self.pause_callback:self.pause_callback(config.paused)
            return config
        self.coordinator.submit(change,self.saved,self.show_error)

    def start_demo(self):
        if self.coordinator.pending or self.dialogs:
            self.show_error('请先完成当前操作或关闭归档窗口，再进入演示。');return
        if self.demo_callback:self.coordinator.submit(self.demo_callback,self.demo_ready,self.show_error)
        else:self.status.setText('演示将在应用启动器接入后启用。')

    def demo_ready(self,result):
        if result:
            self.invalidate_preview()
            for dialog in self.dialogs:dialog.invalidate()
            self.service,self.store,paths=result;self.is_demo=True;self.load_config_controls();self.set_paths(paths);self.tag.setText('DEMO020822');self.refresh();self.demo_activated.emit()
        self.status.setText('演示只使用独立示例目录，可尝试归档与撤销。')

    def refresh_inbox(self):
        def scan():
            if self.inbox_provider:return self.inbox_provider()
            root=self.service.config.sync_root
            if root is None:return []
            from filehub.models import checked_path
            inbox=checked_path(root/'0_收件箱');paths=[]
            if not inbox.is_dir():return paths
            for category in inbox.iterdir():
                checked_path(category)
                if not category.is_dir():continue
                for day in category.iterdir():
                    checked_path(day)
                    if not day.is_dir():continue
                    for path in day.iterdir():checked_path(path);paths.append(path)
            return paths
        self.coordinator.submit(scan,self.show_inbox,self.show_error)

    def show_inbox(self,paths):
        self.inbox_list.clear()
        for path in paths:
            path=Path(path);item=QListWidgetItem(f'{path.name}\n{path.parent.parent.name} / {path.parent.name}');item.setData(Qt.UserRole,str(path));item.setToolTip(str(path));self.inbox_list.addItem(item)

    def archive_inbox(self):
        paths=[Path(i.data(Qt.UserRole)) for i in self.inbox_list.selectedItems()]
        if paths:self.open_archive_dialog(paths)

    def open_inbox(self):
        items=self.inbox_list.selectedItems()
        if items:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(items[0].data(Qt.UserRole)).parent)))

    def open_archive_dialog(self,paths):
        dialog=ArchiveDialog(self,paths);self.dialogs.append(dialog);dialog.finished.connect(lambda _:self.dialogs.remove(dialog));dialog.show();dialog.raise_();dialog.activateWindow();return dialog

    def closeEvent(self,event):
        if self.runtime_close_callback and not self.runtime_close_callback():event.ignore()
        else:event.accept()
