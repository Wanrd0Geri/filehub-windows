"""Installed file management; portable definitions are read-only."""
import json
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QTextEdit,QFileDialog
from .file_process_dialog import FileProcessWidget

def condition_summary(node):
    if 'children' in node:
        return {'all':'全部满足','any':'任一满足','none':'全部不满足'}.get(node.get('mode'),node.get('mode','条件组'))+'（'+'；'.join(condition_summary(child) for child in node['children'])+'）'
    fields={'name':'文件名','extension':'扩展名','kind':'文件类型','size':'大小','size_bytes':'大小','first_seen_age_seconds':'首次观察时长','mtime_age_seconds':'修改时长','width':'宽度','height':'高度'}
    operators={'equals':'等于','contains':'包含','glob':'匹配','ge':'至少','le':'至多','gt':'大于','lt':'小于','ne':'不等于','in':'属于','regex':'正则匹配'}
    return fields.get(node.get('field'),node.get('field','条件'))+' '+operators.get(node.get('operator'),node.get('operator',''))+' '+str(node.get('value',''))

def rule_summary(rule,package,enabled):
    def reference(ref):
        if hasattr(ref,'to_document'):ref=ref.to_document()
        return package.bindings[ref['binding']]['label']+(' / '+ref['relative'] if ref['relative'] else '')
    rows=[rule.name+' · '+('已启用' if enabled else '已关闭'),'范围：'+('所有已配置观察目录；手动可选择文件' if not rule.scope else '、'.join(reference(p) for p in rule.scope)), '条件：'+condition_summary(rule.condition.to_document())]
    labels={'rename':'重命名','move':'移动','copy':'复制','subfolder':'放入子文件夹','image_convert':'图片转换','project_route':'个人项目归档'}
    for index,action in enumerate(rule.actions,1):
        options=action['options'];kind=action['kind'];detail=''
        if kind in ('move','copy'):detail=' → '+reference(options['destination'])
        elif kind=='rename':detail='：'+options['pattern']
        elif kind=='subfolder':detail='：'+options['path']
        elif kind=='image_convert':detail='：'+str(options.get('output_format',''))+' · '+('备份后替换原件' if options.get('mode')=='replace' else '保留原件')+(' → '+reference(options['destination']) if options.get('destination') else '')
        rows.append(str(index)+'. '+labels.get(kind,kind)+detail)
    return '\n'.join(rows)

class RulesPage(FileProcessWidget):
    managementRequested=Signal(object)
    checkRequested=Signal()
    helpRequested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.snapshot=None;self._watch_roots=()
        box=self.layout();title=QLabel('规则文件');title.setObjectName('heading');box.insertWidget(0,title)
        self.notice=QLabel('导入外部 JSON；所有规则默认关闭。绑定目录不会增加观察目录。');self.notice.setWordWrap(True);box.insertWidget(1,self.notice)
        self.package_list=QListWidget();self.package_list.setMaximumHeight(95);box.insertWidget(2,self.package_list)
        self.summary=QTextEdit();self.summary.setReadOnly(True);self.summary.setMaximumHeight(115);box.insertWidget(3,self.summary)
        tools=QWidget();rows=QVBoxLayout(tools);rows.setContentsMargins(0,0,0,0);self.manage_buttons=[]
        for actions in [(('导入',self._import),('替换',self._replace),('重新载入',lambda:self._emit('reload')),('导出',self._export),('绑定目录',lambda:self._emit('bind'))),
                        (('启用/关闭',lambda:self._emit('toggle')),('前移',lambda:self._emit('order',-1)),('后移',lambda:self._emit('order',1)),('移除',lambda:self._emit('remove')),('恢复备份',lambda:self._emit('restore'))),
                        (('AI 编写指南',self.helpRequested.emit),('迁移旧设置',lambda:self._emit('migration')),('兼容权限',lambda:self._emit('compatibility')),('立即检查',self.checkRequested.emit))]:
            row=QHBoxLayout();rows.addLayout(row)
            for name,fn in actions:
                button=QPushButton(name);button.clicked.connect(lambda checked=False,f=fn:f());row.addWidget(button);self.manage_buttons.append(button)
        box.insertWidget(4,tools);self.package_list.currentRowChanged.connect(self._selection)
    @property
    def package_id(self):
        item=self.package_list.currentItem();return item.data(Qt.UserRole) if item else None
    def _emit(self,operation,value=None):self.managementRequested.emit((operation,self.package_id,value))
    def _import(self):
        path,_=QFileDialog.getOpenFileName(self,'导入规则文件','','JSON (*.json)')
        if path:self._emit('import',path)
    def _replace(self):
        path,_=QFileDialog.getOpenFileName(self,'选择替换文件','','JSON (*.json)')
        if path:self._emit('replace',path)
    def _export(self):
        path,_=QFileDialog.getSaveFileName(self,'导出可移植规则','','JSON (*.json)')
        if path:self._emit('export',path)
    def set_catalog(self,snapshot):
        self.snapshot=snapshot;wanted=self.package_id;self.package_list.blockSignals(True);self.package_list.clear()
        for key,package in snapshot.packages.items():
            missing=set(package.bindings)-set(snapshot.bindings[key]);text=package.name+' · '+str(len(package.rules))+' 条'+(' · 未绑定 '+str(len(missing)) if missing else ' · 已绑定')
            item=QListWidgetItem(text);item.setData(Qt.UserRole,key);self.package_list.addItem(item)
        index=next((i for i in range(self.package_list.count()) if self.package_list.item(i).data(Qt.UserRole)==wanted),0 if self.package_list.count() else -1)
        self.package_list.setCurrentRow(index);self.package_list.blockSignals(False);self._selection(index)
    def _selection(self,index):
        if self.snapshot is None:return
        key=self.package_id
        if key is None:self.summary.setPlainText('没有已安装规则；可导入外部规则文件。');return
        package=self.snapshot.packages[key];bindings=self.snapshot.bindings[key];rows=[package.name+' · ID '+key]
        rows.extend(k+' ('+v['label']+')：'+str(bindings.get(k,'未绑定')) for k,v in package.bindings.items())
        rows.extend(rule_summary(r,package,r.id in self.snapshot.enabled[key]) for r in package.rules)
        self.summary.setPlainText('\n'.join(rows));self.set_ruleset(self.snapshot.compiled)
        first=next((self.rule_choice.findData(self.snapshot.runtime_ids[key][r.id]) for r in package.rules if self.rule_choice.findData(self.snapshot.runtime_ids[key][r.id])>=0),0);self.rule_choice.setCurrentIndex(first)
    def set_watch_roots(self,paths):self._watch_roots=tuple(map(str,paths))
    def set_busy(self,busy,*,cancellable=True):
        super().set_busy(busy,cancellable=cancellable)
        if hasattr(self,'manage_buttons'):
            for button in self.manage_buttons:button.setEnabled(not busy)
            self.package_list.setEnabled(not busy)
