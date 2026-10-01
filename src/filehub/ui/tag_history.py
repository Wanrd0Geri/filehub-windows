"""Shared async history and compact, horizontally scrollable tag chips."""
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy
from filehub.tag_history import TagHistory


class HistoryController(QObject):
    changed = Signal(object)
    failed = Signal(str)

    def __init__(self, coordinator, state_dir, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.tags = ()
        self.error = ''
        self.generation = 0
        self.revision = 0
        self.store = TagHistory(state_dir)

    def switch_state(self, state_dir):
        self.generation += 1
        self.revision += 1
        self.store = TagHistory(state_dir)
        self.tags = ()
        self.error = ''
        self.changed.emit(self.tags)
        self.failed.emit('')
        self.refresh()

    @property
    def token(self):
        return self.generation, self.revision

    def _submit(self, operation, *, remember_token=None):
        store, generation = self.store, self.generation
        revision = self.revision
        def action():
            # A queued operation must not touch a state that has been replaced.
            if generation != self.generation or (remember_token is not None and remember_token != self.token):
                return None
            return operation(store)
        def ready(tags):
            if generation != self.generation or revision != self.revision or store is not self.store or tags is None:
                return
            self.tags = tags
            self.error = ''
            self.changed.emit(tags)
            self.failed.emit('')
        def failed(message):
            if generation == self.generation and revision == self.revision and store is self.store:
                self.error = '历史口令未更新：' + message
                self.failed.emit(self.error)
        self.coordinator.submit(action, ready, failed)

    def refresh(self):
        self._submit(lambda store: store.list())

    def remember(self, tag, token=None):
        token = self.token if token is None else token
        if token == self.token:
            self._submit(lambda store: store.remember(tag), remember_token=token)

    def remove(self, tag):
        self.revision += 1
        self._submit(lambda store: store.remove(tag))

    def clear(self):
        self.revision += 1
        self._submit(lambda store: store.clear())


class HistoryChips(QWidget):
    def __init__(self, controller, fill, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.fill = fill
        self.tags = ()
        self.tag_buttons = {}
        self.remove_buttons = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        header = QHBoxLayout()
        title = QLabel('最近口令');title.setObjectName('muted')
        header.addWidget(title);header.addStretch()
        self.clear_button = QPushButton('清空全部');self.clear_button.setObjectName('historyClear')
        self.clear_button.setToolTip('仅清空历史口令');self.clear_button.clicked.connect(controller.clear)
        header.addWidget(self.clear_button);content_layout.addLayout(header)
        self.scroll = QScrollArea();self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setFixedHeight(54)
        self.row = QWidget();self.row_layout = QHBoxLayout(self.row)
        self.row_layout.setContentsMargins(0, 0, 0, 0);self.row_layout.setSpacing(6)
        self.scroll.setWidget(self.row);content_layout.addWidget(self.scroll);layout.addWidget(self.content)
        self.error_label = QLabel();self.error_label.setObjectName('historyError');self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        controller.changed.connect(self.show_tags);controller.failed.connect(self.show_error)
        self.show_tags(controller.tags);self.show_error(controller.error)

    def show_tags(self, tags):
        self.tags = tags
        while self.row_layout.count():
            item = self.row_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.tag_buttons = {};self.remove_buttons = {}
        for tag in tags:
            chip = QWidget();chip.setObjectName('historyChip')
            row = QHBoxLayout(chip);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
            button = QPushButton(self.fontMetrics().elidedText(tag, Qt.ElideRight, 160))
            button.setObjectName('historyTag');button.setToolTip(tag);button.setAccessibleName('填入口令：'+tag)
            button.clicked.connect(lambda checked=False, value=tag:self.fill(value))
            remove = QPushButton('×');remove.setObjectName('historyRemove');remove.setFixedWidth(28)
            remove.setToolTip('删除历史口令：'+tag);remove.setAccessibleName('删除历史口令：'+tag)
            remove.clicked.connect(lambda checked=False, value=tag:self.controller.remove(value))
            row.addWidget(button);row.addWidget(remove);self.row_layout.addWidget(chip)
            self.tag_buttons[tag] = button;self.remove_buttons[tag] = remove
        self.row_layout.addStretch()
        self.content.setVisible(bool(tags))
        self.setVisible(bool(tags) or bool(self.controller.error))

    def show_error(self, message):
        self.error_label.setText(message);self.error_label.setVisible(bool(message))
        self.setVisible(bool(self.tags) or bool(message))
