"""Concrete reviews hold immutable input bytes and the displayed authority."""
from dataclasses import dataclass
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTextEdit,QPushButton,QComboBox,QLineEdit,QCheckBox,QFileDialog,QScrollArea,QWidget
from .theme import apply_theme

@dataclass(frozen=True)
class ReplacementReview:
    package_id:str
    data:bytes
    source:str
    expected_revision:str
    delta:object
    old:object
    new:object
    def text(self):
        names={r.id:r.name for r in (*self.old.rules,*self.new.rules)}
        rows=[self.old.name+' → '+self.new.name,'接受后所有规则及兼容权限关闭。']
        for title,ids in [('新增',self.delta.added),('修改',self.delta.changed),('移除',self.delta.removed),('目录角色变化',self.delta.binding_changes)]:rows.append(title+'：'+('、'.join(names.get(i,i) for i in ids) or '无'))
        rows.extend(label+'：'+('有变化' if flag else '无变化') for label,flag in [('名称',self.delta.metadata_changed),('变量',self.delta.variables_changed),('兼容档案',self.delta.compatibility_changed),('规则优先顺序',self.delta.order_changed)])
        return '\n'.join(rows)

class ReviewDialog(QDialog):
    def __init__(self,parent,title,text):
        super().__init__(parent);self.setWindowTitle(title);self.resize(580,400)
        box=QVBoxLayout(self);heading=QLabel(title);heading.setObjectName('heading');box.addWidget(heading)
        self.details=QTextEdit();self.details.setReadOnly(True);self.details.setPlainText(text);box.addWidget(self.details)
        row=QHBoxLayout();self.cancel_button=QPushButton('取消');self.cancel_button.clicked.connect(self.reject);row.addWidget(self.cancel_button)
        self.accept_button=QPushButton('确认');self.accept_button.setObjectName('primary');self.accept_button.clicked.connect(self.accept);row.addWidget(self.accept_button);box.addLayout(row)
        apply_theme(self,parent.service.config.theme)

class BindingDialog(QDialog):
    def __init__(self,parent,package,values):
        super().__init__(parent);self.setWindowTitle('绑定目录');self.resize(560,300);self.fields={}
        self.setMaximumHeight(560)
        box=QVBoxLayout(self);notice=QLabel('绑定不会创建目录、增加观察目录或启用规则。留空可解除绑定。');notice.setWordWrap(True);box.addWidget(notice)
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();fields_box=QVBoxLayout(content);scroll.setWidget(content);box.addWidget(scroll,1)
        for key,declaration in package.bindings.items():
            fields_box.addWidget(QLabel(declaration['label']+' · '+key));row=QHBoxLayout();field=QLineEdit(str(values.get(key,'')));self.fields[key]=field;row.addWidget(field)
            button=QPushButton('选择…');button.clicked.connect(lambda checked=False,f=field:self.choose(f));row.addWidget(button);fields_box.addLayout(row)
        row=QHBoxLayout();cancel=QPushButton('取消');cancel.clicked.connect(self.reject);row.addWidget(cancel);save=QPushButton('保存绑定');save.clicked.connect(self.accept);row.addWidget(save);box.addLayout(row);apply_theme(self,parent.service.config.theme)
    def choose(self,field):
        path=QFileDialog.getExistingDirectory(self,'选择本机目录',field.text())
        if path:field.setText(path)
    def values(self):return {key:field.text() for key,field in self.fields.items() if field.text()}

class CompatibilityDialog(QDialog):
    def __init__(self,parent,snapshot):
        super().__init__(parent);self.setWindowTitle('兼容档案与独立权限');box=QVBoxLayout(self)
        notice=QLabel('选中档案不会自动处理文件。请分别选择所需权限；手动归档仍需先预览。');notice.setWordWrap(True);box.addWidget(notice)
        self.choice=QComboBox();self.choice.addItem('不使用兼容档案',None)
        for key,package in snapshot.packages.items():
            if package.compatibility is not None:self.choice.addItem(package.name,key)
        self.choice.setCurrentIndex(max(0,self.choice.findData(snapshot.compatibility_selection)));box.addWidget(self.choice);self.permissions={}
        for key,label in [('manual_archive','个人项目手动归档'),('unmatched_inbox','未匹配文件进入兼容收件箱'),('cleanup','兼容清理与名称修正')]:
            field=QCheckBox(label);field.setChecked(key in snapshot.compatibility_permissions);box.addWidget(field);self.permissions[key]=field
        row=QHBoxLayout();cancel=QPushButton('取消');cancel.clicked.connect(self.reject);row.addWidget(cancel);save=QPushButton('核对并保存');save.clicked.connect(self.accept);row.addWidget(save);box.addLayout(row);apply_theme(self,parent.service.config.theme)
    def values(self):return self.choice.currentData(),frozenset(key for key,field in self.permissions.items() if field.isChecked())
