"""Run once to generate the tray icon: python make_icon.py"""
import sys
import os
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
pm = QPixmap(32, 32)
pm.fill(Qt.GlobalColor.transparent)
p = QPainter(pm)
p.setBrush(QColor(80, 160, 255))
p.setPen(Qt.PenStyle.NoPen)
p.drawEllipse(4, 4, 24, 24)
p.end()
os.makedirs("assets", exist_ok=True)
pm.save("assets/icon.png")
print("assets/icon.png saved")
