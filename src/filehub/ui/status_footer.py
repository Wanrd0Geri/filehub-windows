"""A bounded status area retaining selectable, scrollable full messages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy


class StatusLabel(QLabel):
    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)
        if hasattr(self, 'footer'):self.footer.fit_message()


class StatusFooter(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('statusFooter')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.label = StatusLabel('')
        self.label.setObjectName('statusMessage')
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.footer = self
        self.setWidget(self.label)
        self.fit_message()

    def fit_message(self):
        if not self.label.text():
            self.setFixedHeight(0)
            self.label.setMinimumHeight(0)
            return
        width = max(100, self.viewport().width() - 20)
        natural = max(36, self.label.heightForWidth(width))
        self.label.setMinimumHeight(natural)
        self.setFixedHeight(min(natural, 144))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_message()
