from PySide6.QtWidgets import QLabel, QSizePolicy


class CompactMessage(QLabel):
    """Empty feedback does not consume editor space; full text remains in tooltip."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True); self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMaximumHeight(66); self.hide()

    def setText(self, text):
        super().setText(text); self.setToolTip(text); self.setVisible(bool(text))

    def clear(self): self.setText('')
