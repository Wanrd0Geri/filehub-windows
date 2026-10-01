"""Structured bounded condition tree; only finite model validation occurs here."""
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from PySide6.QtCore import Signal, QDateTime, QDate, QTime, QTimeZone
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QLineEdit, QDateTimeEdit, QLabel, QPushButton, QGroupBox)
from ..automation.models import Predicate, ConditionGroup

FIELDS = {'kind': '类型', 'extension': '扩展名', 'name': '文件名', 'size_bytes': '大小',
          'created': '创建日期', 'modified': '修改日期', 'first_seen_age_seconds': '首次看到至今',
          'stable_age_seconds': '保持不变时间'}
KINDS = {'file': '文件（所有类型）', 'folder': '文件夹', 'image': '图片', 'video': '视频',
         'audio': '音频', 'document': '文档', 'other': '其他'}
TEXT_OPS = {'equals': '等于', 'contains': '包含', 'starts_with': '开头是', 'ends_with': '结尾是', 'glob': '通配匹配（* ?）'}
ORDER_OPS = {'eq': '等于', 'lt': '小于 / 早于', 'le': '小于等于', 'gt': '大于 / 晚于', 'ge': '大于等于'}
MODES = {'all': '全部满足', 'any': '任一满足', 'none': '全部不满足'}


def combo(values):
    widget = QComboBox()
    for key, label in values.items(): widget.addItem(label, key)
    return widget


class _Node(QGroupBox):
    def __init__(self, editor, value, depth=0):
        super().__init__(); self.editor = editor; self.depth = depth; self.children = []
        self.layout_box = QVBoxLayout(self); self.layout_box.setContentsMargins(8, 8, 8, 8)
        self.is_group = isinstance(value, ConditionGroup)
        top = QHBoxLayout(); self.layout_box.addLayout(top)
        if self.is_group:
            self.mode = combo(MODES); self.mode.setCurrentIndex(self.mode.findData(value.mode)); top.addWidget(self.mode)
            self.mode.currentIndexChanged.connect(editor.changed)
            add = QPushButton('+ 条件'); add.clicked.connect(lambda: editor._add(self, False)); top.addWidget(add)
            group = QPushButton('+ 条件组'); group.setEnabled(depth < 3)
            group.clicked.connect(lambda: editor._add(self, True)); top.addWidget(group)
            for child in value.children: self._append(child)
        else:
            self.field = combo(FIELDS); top.addWidget(self.field)
            self.operator = QComboBox(); top.addWidget(self.operator)
            self.text_value = QLineEdit(); self.text_value.setPlaceholderText('填写比较值；通配可用 * 和 ?')
            self.kind_value = combo(KINDS)
            self.number_value = QLineEdit('0'); self.number_value.setPlaceholderText('非负数字；可输入小数')
            self.unit = QComboBox(); self.unit.addItem('字节', 1)
            self.date_value = QDateTimeEdit(); self.date_value.setCalendarPopup(True)
            self.date_value.setTimeZone(QTimeZone.utc()); self.date_value.setDisplayFormat("yyyy-MM-dd HH:mm:ss 'UTC'")
            self.date_value.setMinimumDate(QDate(1, 1, 1)); self.date_value.setMaximumDate(QDate(9999, 12, 31))
            self.date_help = QLabel('日期按 UTC（+00:00）显示，可用日历选择。未修改时保留导入日期的原时区和精度。')
            self.date_help.setWordWrap(True); self._date_original = None
            for widget in (self.text_value, self.kind_value, self.number_value, self.unit, self.date_value, self.date_help):
                self.layout_box.addWidget(widget)
            self.field.setCurrentIndex(self.field.findData(value.field)); self._configure()
            self.operator.setCurrentIndex(self.operator.findData(value.operator))
            if value.field == 'kind': self.kind_value.setCurrentIndex(self.kind_value.findData(value.value))
            elif value.field in ('created', 'modified'):
                parsed = datetime.fromisoformat(value.value).astimezone(timezone.utc)
                self.date_value.setDateTime(QDateTime(QDate(parsed.year, parsed.month, parsed.day),
                    QTime(parsed.hour, parsed.minute, parsed.second, parsed.microsecond // 1000), QTimeZone.utc()))
                self._date_original = value.value
            elif value.field in ('size_bytes', 'first_seen_age_seconds', 'stable_age_seconds'): self.number_value.setText(str(value.value))
            else: self.text_value.setText(value.value)
            self.field.currentIndexChanged.connect(self._field_changed)
            for signal in (self.operator.currentIndexChanged, self.text_value.textChanged, self.kind_value.currentIndexChanged,
                           self.number_value.textChanged, self.unit.currentIndexChanged):
                signal.connect(editor.changed)
            self.date_value.dateTimeChanged.connect(self._date_changed)
        remove = QPushButton('删除'); remove.clicked.connect(lambda: editor._remove(self)); top.addWidget(remove)

    def _append(self, value):
        child = _Node(self.editor, value, self.depth + 1); self.children.append(child); self.layout_box.addWidget(child)

    def _configure(self):
        field = self.field.currentData(); number = field in ('size_bytes', 'first_seen_age_seconds', 'stable_age_seconds')
        date = field in ('created', 'modified')
        self.operator.clear()
        for key, label in ({'equals': '是'} if field == 'kind' else ORDER_OPS if number or date else TEXT_OPS).items():
            self.operator.addItem(label, key)
        self.text_value.setVisible(not number and not date and field != 'kind')
        self.kind_value.setVisible(field == 'kind'); self.number_value.setVisible(number); self.unit.setVisible(number)
        self.date_value.setVisible(date); self.date_help.setVisible(date); self.unit.clear()
        for label, factor in ([('字节', 1), ('KB', 1024), ('MB', 1048576), ('GB', 1073741824)] if field == 'size_bytes'
                              else [('秒', 1), ('分钟', 60), ('小时', 3600), ('天', 86400)]):
            self.unit.addItem(label, factor)
        if date and self._date_original is None: self.date_value.setDateTime(QDateTime.currentDateTimeUtc())

    def _field_changed(self): self._configure(); self.editor.changed.emit()

    def _date_changed(self): self._date_original = None; self.editor.changed.emit()

    def _date(self):
        if self._date_original is not None: return self._date_original
        date = self.date_value.date(); time = self.date_value.time()
        return datetime(date.year(), date.month(), date.day(), time.hour(), time.minute(), time.second(),
                        time.msec() * 1000, tzinfo=timezone.utc).isoformat()

    def _number(self):
        try:
            value = Decimal(self.number_value.text()) * self.unit.currentData()
            if not value.is_finite() or not 0 <= value <= 2**63 - 1: raise ValueError('数字必须非负且不超过 9223372036854775807')
            return int(value) if value == value.to_integral_value() else float(value)
        except (DecimalException, OverflowError) as exc: raise ValueError('请输入有效数字，并选择单位') from exc

    def value(self):
        if self.is_group: return ConditionGroup(self.mode.currentData(), tuple(child.value() for child in self.children))
        field = self.field.currentData()
        value = (self.kind_value.currentData() if field == 'kind' else self._date() if field in ('created', 'modified')
                 else self._number() if field in ('size_bytes', 'first_seen_age_seconds', 'stable_age_seconds')
                 else self.text_value.text())
        return Predicate(field, self.operator.currentData(), value)


class ConditionEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self.box = QVBoxLayout(self); self.box.setContentsMargins(0, 0, 0, 0)
        help_label = QLabel('条件组最多 4 层、100 个条件。全部不满足表示每个子条件都不匹配；缺少信息不能通过。')
        help_label.setWordWrap(True); self.box.addWidget(help_label)
        self.root = None; self.set_value(Predicate('kind', 'equals', 'image'))
        button = QPushButton('把当前条件放入条件组'); button.clicked.connect(self.wrap_group); self.box.addWidget(button)

    def value(self): return self.root.value()

    def set_value(self, condition):
        if not isinstance(condition, (Predicate, ConditionGroup)): raise ValueError('请选择有效的条件')
        if self.root is not None: self.box.removeWidget(self.root); self.root.deleteLater()
        self.root = _Node(self, condition); self.box.insertWidget(1, self.root); self.changed.emit()

    def node(self, path=()):
        node = self.root
        for index in path: node = node.children[index]
        return node

    def wrap_group(self):
        try: self.set_value(ConditionGroup('all', (self.value(),)))
        except ValueError as exc: self.setToolTip(str(exc))

    def _add(self, parent, group):
        try:
            path = self._path(parent); self.add_group(path) if group else self.add_condition(path)
        except ValueError as exc: self.setToolTip(str(exc))

    def _path(self, wanted, node=None, path=()):
        node = node or self.root
        if node is wanted: return path
        for index, child in enumerate(node.children):
            result = self._path(wanted, child, (*path, index))
            if result is not None: return result
        return None

    def add_condition(self, path=(), condition=None):
        parent = self.node(path)
        if not parent.is_group: raise ValueError('请先添加条件组')
        child = condition or Predicate('kind', 'equals', 'image')
        # Validate whole tree before mutating controls.
        doc = self.value().to_document(); target = doc
        for index in path: target = target['children'][index]
        target['children'].append(child.to_document())
        from ..automation.models import condition_from_document
        condition_from_document(doc)
        parent._append(child); self.changed.emit()

    def add_group(self, path=(), mode='all'):
        self.add_condition(path, ConditionGroup(mode, (Predicate('kind', 'equals', 'image'),)))

    def _remove(self, node):
        path = self._path(node)
        try: self.remove_node(path)
        except ValueError as exc: self.setToolTip(str(exc))

    def remove_node(self, path):
        if not path: raise ValueError('根条件不能删除；可改为其他条件')
        parent = self.node(path[:-1])
        if len(parent.children) == 1: raise ValueError('条件组至少保留一个条件')
        child = parent.children.pop(path[-1]); parent.layout_box.removeWidget(child); child.deleteLater(); self.changed.emit()
