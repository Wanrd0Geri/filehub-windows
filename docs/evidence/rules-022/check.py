import sys, time
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSpinBox, QStyle, QStyleOptionSlider
from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.ui.main_window import MainWindow
from filehub.ui.theme import apply_theme
base=Path(sys.argv[1]); app=QApplication([])
w=MainWindow(FileHubService(Config(),base/'state'), ConfigStore(base/'state'))
print('Actual window DPR:',w.devicePixelRatioF())
def settle():
    for _ in range(30): app.processEvents(); time.sleep(.005)
settle(); w.resize(1200,800); w.navigate(3); w.show(); settle()
for spin in (w.sweep_days,w.inbox_days):
    assert spin.buttonSymbols()==QSpinBox.NoButtons
    assert (spin.minimum(),spin.maximum())==(1,365)
    spin.setFocus(); spin.lineEdit().selectAll(); QTest.keyClicks(spin,'12'); QTest.keyClick(spin,Qt.Key_Return)
    assert spin.value()==12
    QTest.keyClick(spin,Qt.Key_Up); assert spin.value()==13
    QTest.keyClick(spin,Qt.Key_Down); assert spin.value()==12
    spin.setValue(365); QTest.keyClick(spin,Qt.Key_Up); assert spin.value()==365
    spin.setValue(1); QTest.keyClick(spin,Qt.Key_Down); assert spin.value()==1
assert w.conversion_page.fields.quality.buttonSymbols()!=QSpinBox.NoButtons
for theme in ('dark','light'):
    apply_theme(w,theme); settle(); w.grab().save(str(base/f'{theme}-settings-dpr{round(w.devicePixelRatioF(),2)}.png'))
    w.resize(960,640); w.navigate(5); settle()
    area=w.conversion_page.findChild(__import__('PySide6.QtWidgets',fromlist=['QScrollArea']).QScrollArea)
    bar=area.verticalScrollBar(); assert bar.maximum()>0
    assert bar.width()==8
    opt=QStyleOptionSlider(); bar.initStyleOption(opt)
    for ctl in (QStyle.SC_ScrollBarAddLine,QStyle.SC_ScrollBarSubLine):
        rect=bar.style().subControlRect(QStyle.CC_ScrollBar,opt,ctl,bar)
        assert rect.isEmpty(),rect
    bar.setValue(0); bar.setFocus(); QTest.keyClick(bar,Qt.Key_Down); assert bar.value()>0
    bar.setValue(0)
    ev=QWheelEvent(QPointF(10,10),QPointF(area.mapToGlobal(QPoint(10,10))),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
    app.sendEvent(area.viewport(),ev); assert bar.value()>0
    bar.setValue(0); settle(); opt=QStyleOptionSlider(); bar.initStyleOption(opt); thumb=bar.style().subControlRect(QStyle.CC_ScrollBar,opt,QStyle.SC_ScrollBarSlider,bar); QTest.mousePress(bar,Qt.LeftButton,Qt.NoModifier,thumb.center()); QTest.mouseMove(bar,thumb.center()+QPoint(0,30)); QTest.mouseRelease(bar,Qt.LeftButton,Qt.NoModifier,thumb.center()+QPoint(0,30)); assert bar.value()>0; bar.setValue(0); settle(); w.grab().save(str(base/f'{theme}-conversion-dpr{round(w.devicePixelRatioF(),2)}.png')); w.resize(1200,800); w.navigate(3); settle()
w.automation.retire(lambda:None); settle(); w._close_settled=True; w.close(); w.coordinator.close()
print('PASS: day spinbox typing/arrows/range; quality arrows preserved; both-theme scrollbar width/no end controls/keyboard/wheel; screenshots',base)
