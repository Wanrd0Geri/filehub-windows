"""Draw original FileHub icon; standard ICO with a 256px PNG frame."""
from pathlib import Path
import struct
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
p = QPainter(image)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QColor("#20211f"))
p.drawRoundedRect(QRectF(4, 4, 248, 248), 56, 56)
p.setPen(QPen(QColor("#e9be65"), 15, Qt.PenStyle.SolidLine,
              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
p.setBrush(Qt.BrushStyle.NoBrush)
tray = QPainterPath()
tray.moveTo(54, 122); tray.lineTo(42, 192); tray.lineTo(214, 192)
tray.lineTo(202, 122); tray.lineTo(165, 122); tray.lineTo(153, 145)
tray.lineTo(103, 145); tray.lineTo(91, 122); tray.closeSubpath()
p.drawPath(tray)
p.drawLine(128, 57, 128, 109)
p.drawLine(105, 88, 128, 111); p.drawLine(128, 111, 151, 88)
p.end()
data = QByteArray()
buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
assert image.save(buffer, "PNG")
png = bytes(data)
output = Path(__file__).resolve().parents[1] / "resources" / "app.ico"
output.write_bytes(struct.pack("<HHH", 0, 1, 1) +
                   struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)
print(output)
