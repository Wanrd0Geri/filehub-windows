from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

def resolved_theme(appearance,scheme):
    if appearance!='system':return appearance
    return 'dark' if scheme==Qt.ColorScheme.Dark else 'light'

def icon(kind,color='#d8bd65'):
    pixmap = QPixmap(24,24); pixmap.fill(Qt.transparent)
    p=QPainter(pixmap); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color),1.5))
    if kind in ('整理','文件处理','FileHub'):
        p.drawRoundedRect(3,7,18,14,2,2); p.drawLine(3,7,3,4);p.drawLine(3,4,10,4);p.drawLine(10,4,13,7)
    elif kind=='收件箱':
        p.drawRect(3,5,18,16);p.drawLine(3,14,9,14);p.drawLine(9,14,9,17);p.drawLine(9,17,15,17);p.drawLine(15,17,15,14);p.drawLine(15,14,21,14)
    elif kind=='记录':
        p.drawEllipse(4,4,16,16);p.drawLine(12,7,12,12);p.drawLine(12,12,17,14)
    elif kind=='规则文件':
        p.drawRoundedRect(5,3,14,18,2,2)
        for y in (8,12,16):p.drawLine(8,y,16,y)
    elif kind=='图片转换':
        p.drawRoundedRect(3,4,18,16,2,2);p.drawEllipse(6,7,3,3);p.drawLine(4,18,10,12);p.drawLine(10,12,14,16);p.drawLine(14,16,18,10);p.drawLine(18,10,20,13)
    else:
        for y,x in ((6,8),(12,16),(18,10)):
            p.drawLine(3,y,21,y);p.drawEllipse(x-2,y-2,4,4)
    p.end();return QIcon(pixmap)

def apply_theme(widget, appearance='dark'):
    appearance=resolved_theme(appearance,QApplication.styleHints().colorScheme())
    light=appearance=='light'
    bg,side,surface,top,text,muted,line,gold=('#f7f7f5','#eeeeeb','#ffffff','#ffffff','#242422','#73736b','#deded7','#927216') if light else ('#19191b','#111113','#202022','#252527','#ececea','#969693','#303032','#d8bd65')
    scroll_handle,scroll_hover=('#c7c7bf','#aaa99f') if light else ('#47474b','#626267')
    QFont.insertSubstitutions('Inter',['Noto Sans SC','Microsoft YaHei UI'])
    font=QFont();font.setFamilies(['Inter','Noto Sans SC','Segoe UI','Microsoft YaHei UI']);font.setPixelSize(13);widget.setFont(font)
    QApplication.instance().setFont(font)
    if hasattr(widget,'nav_buttons'):
        for button in widget.nav_buttons:button.setIcon(icon(button.text(),gold))
    widget.setStyleSheet(f'''
    QWidget {{ background:{bg}; color:{text}; font-family:"Inter","Noto Sans SC","Microsoft YaHei UI"; font-size:13px; }}
    QLabel,QCheckBox {{background:transparent;}}
    QWidget#sidebar {{ background:{side}; border-right:1px solid {line}; }}
    QLabel#brand {{font-size:20px; font-weight:600; padding:8px;}}
    QLabel#heading {{font-size:25px; font-weight:500;}}
    QLabel#muted {{color:{muted}; font-size:11px;}}
    QLabel#firstRun {{background:{surface};border:1px solid {line};border-radius:10px;padding:18px;}}
    QFrame#card {{background:{surface};border:1px solid {line};border-radius:10px;}}
    QPushButton {{background:{surface};border:1px solid {line};border-radius:7px;padding:8px 12px;}}
    QPushButton:hover {{background:{top};border-color:{gold};}}
    QPushButton:focus,QLineEdit:focus,QComboBox:focus {{border:1px solid {gold};}}
    QPushButton:disabled {{color:{muted};}}
    QPushButton#primary {{background:{text};color:{bg};font-weight:500;}}
    QPushButton#primary:disabled {{background:{surface};color:{muted};border-color:{line};}}
    QPushButton#nav {{background:transparent;border:1px solid transparent;text-align:left;padding:10px;}}
    QPushButton#nav:checked {{background:{top};border:1px solid {line};border-right:2px solid {gold};}}
    QLineEdit,QComboBox,QSpinBox {{background:{surface};border:1px solid {line};border-radius:7px;padding:8px;selection-background-color:{gold};}}
    QLineEdit#tag {{font-size:19px;}}
    QListWidget,QTextEdit {{background:{surface};border:1px solid {line};border-radius:9px;padding:4px;}}
    QListWidget::item {{padding:12px 9px;border-bottom:1px solid {line};}}
    QListWidget#conversionSources::item {{padding:2px 8px;}}
    QListWidget::item:selected {{background:{top};color:{text};}}
    QCheckBox {{spacing:8px;}}
    QScrollArea {{border:0;}}
    QScrollBar:vertical {{background:transparent;border:0;width:8px;margin:0;}}
    QScrollBar:horizontal {{background:transparent;border:0;height:8px;margin:0;}}
    QScrollBar::handle:vertical {{background:{scroll_handle};border-radius:4px;min-height:24px;}}
    QScrollBar::handle:horizontal {{background:{scroll_handle};border-radius:4px;min-width:24px;}}
    QScrollBar::handle:hover {{background:{scroll_hover};}}
    QScrollBar::add-line,QScrollBar::sub-line {{background:transparent;border:0;width:0;height:0;}}
    QScrollBar::up-arrow,QScrollBar::down-arrow,QScrollBar::left-arrow,QScrollBar::right-arrow {{width:0;height:0;}}
    QScrollBar::add-page,QScrollBar::sub-page {{background:transparent;}}
    QStatusBar#appStatusBar {{background:{side};border-top:1px solid {line};padding:0;}}
    QStatusBar#appStatusBar::item {{border:0;}}
    QScrollArea#statusFooter,QScrollArea#statusFooter QWidget {{background:{side};border:0;}}
    QScrollArea#statusFooter QScrollBar {{background:transparent;}}
    QScrollArea#statusFooter QScrollBar::handle {{background:{scroll_handle};}}
    QScrollArea#statusFooter QScrollBar::handle:hover {{background:{scroll_hover};}}
    QLabel#statusMessage {{background:{side};padding:8px 16px;}}
    QPushButton#historyClear {{background:transparent;border:0;color:{muted};padding:1px 4px;font-size:11px;}}
    QWidget#historyChip {{background:{surface};border:1px solid {line};border-radius:6px;}}
    QPushButton#historyTag {{background:transparent;border:0;color:{gold};padding:5px 8px;}}
    QPushButton#historyRemove {{background:transparent;border:0;color:{muted};padding:5px 4px;}}
    QPushButton#historyRemove:hover {{color:{text};}}
    QLabel#historyError {{color:{gold};font-size:11px;}}
    QToolTip {{background:{surface};color:{text};border:1px solid {line};}}
    ''')
