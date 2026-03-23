import logging
from enum import Enum
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QFont
from PyQt6.QtWidgets import QWidget, QApplication

logger = logging.getLogger(__name__)

BAR_COUNT = 8


class PillState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


class PillUI(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._state = PillState.IDLE
        self._rms = 0.0
        self._bars = [0.0] * BAR_COUNT
        self._drag_pos = None

        self._setup_window()
        self._restore_position()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(50)  # 20 fps

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 48)

    def _restore_position(self):
        x = int(self._db.get_setting("pill_x", default="100"))
        y = int(self._db.get_setting("pill_y", default="100"))
        self.move(x, y)

    def _save_position(self):
        pos = self.pos()
        self._db.set_setting("pill_x", str(pos.x()))
        self._db.set_setting("pill_y", str(pos.y()))

    def set_state(self, state: PillState):
        self._state = state
        self.update()

    def set_rms(self, value: float):
        self._rms = min(value * 5, 1.0)  # amplify for visual effect

    def _tick_animation(self):
        if self._state == PillState.RECORDING:
            import random
            target = self._rms
            for i in range(BAR_COUNT):
                noise = random.uniform(-0.1, 0.1)
                self._bars[i] = max(0.05, min(1.0, target + noise))
        else:
            self._bars = [0.0] * BAR_COUNT
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 24, 24)

        if self._state == PillState.ERROR:
            bg_color = QColor(180, 40, 40, 220)
        elif self._state == PillState.RECORDING:
            bg_color = QColor(30, 30, 30, 230)
        else:
            bg_color = QColor(30, 30, 30, 200)

        painter.fillPath(path, bg_color)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 11)
        painter.setFont(font)

        if self._state == PillState.IDLE:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🎙️  sflow")
        elif self._state == PillState.RECORDING:
            self._draw_bars(painter)
        elif self._state == PillState.PROCESSING:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⏳  Transcribiendo…")
        elif self._state == PillState.ERROR:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⚠️  Error — ver tray")

    def _draw_bars(self, painter):
        bar_w = 8
        gap = 4
        total_w = BAR_COUNT * bar_w + (BAR_COUNT - 1) * gap
        x_start = (self.width() - total_w) // 2
        max_h = self.height() - 16
        for i, level in enumerate(self._bars):
            h = max(4, int(level * max_h))
            x = x_start + i * (bar_w + gap)
            y = (self.height() - h) // 2
            painter.fillRect(x, y, bar_w, h, QColor(255, 80, 80))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._save_position()
