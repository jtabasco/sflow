import math
import logging
from enum import Enum
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QFont, QPen
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

BAR_COUNT = 5

# Border colors per state
BORDER = {
    "idle":       QColor(130, 80, 255),   # violet
    "recording":  QColor(255, 60,  60),   # red
    "processing": QColor(255, 180,  0),   # amber
    "error":      QColor(255, 60,  60),
}


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
        self._anim_phase = 0.0
        self._dot_count = 0
        self._drag_pos = None

        self._setup_window()
        self._restore_position()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(40)  # 25 fps

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(120, 26)

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
        if state != PillState.RECORDING:
            self._rms = 0.0
        self.update()

    def set_rms(self, value: float):
        self._rms = min(value * 6, 1.0)

    def _tick_animation(self):
        self._anim_phase += 0.18

        if self._state == PillState.RECORDING:
            for i in range(BAR_COUNT):
                phase_offset = i * (math.pi * 2 / BAR_COUNT)
                wave = (math.sin(self._anim_phase + phase_offset) + 1) / 2
                # Always show visible wave; amplify with real audio level
                base = 0.25 + wave * 0.35
                rms_boost = self._rms * wave * 1.2
                target = min(1.0, base + rms_boost)
                self._bars[i] += (target - self._bars[i]) * 0.35
        else:
            for i in range(BAR_COUNT):
                self._bars[i] += (0.0 - self._bars[i]) * 0.3

        self._dot_count = int(self._anim_phase / 0.6) % 3
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bw = 1.5          # border width
        r = h / 2 - bw   # inner radius

        # Background (inset by border)
        inner = QRectF(bw, bw, w - bw * 2, h - bw * 2)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(inner, r, r)

        if self._state == PillState.ERROR:
            bg = QColor(100, 15, 15, 245)
        elif self._state == PillState.RECORDING:
            bg = QColor(15, 12, 20, 250)
        else:
            bg = QColor(20, 18, 28, 230)

        painter.fillPath(bg_path, bg)

        # Glowing border
        border_color = BORDER[self._state.value]
        pen = QPen(border_color, bw)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRoundedRect(inner, r, r)

        rect = QRect(0, 0, w, h)

        if self._state == PillState.IDLE:
            painter.setPen(QColor(200, 185, 255))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "🎙  sflow")

        elif self._state == PillState.RECORDING:
            self._draw_bars(painter)

        elif self._state == PillState.PROCESSING:
            painter.setPen(QColor(255, 200, 80))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            dots = "•" * (self._dot_count + 1)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"Procesando {dots}")

        elif self._state == PillState.ERROR:
            painter.setPen(QColor(255, 190, 190))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "⚠  Error")

    def _draw_bars(self, painter):
        bar_w = 4
        gap = 4
        total_w = BAR_COUNT * bar_w + (BAR_COUNT - 1) * gap
        x_start = (self.width() - total_w) // 2
        max_h = self.height() - 8

        for i, level in enumerate(self._bars):
            h = max(2, int(level * max_h))
            x = x_start + i * (bar_w + gap)
            y = (self.height() - h) // 2

            # Red → orange as level rises
            r = 255
            g = int(60 + level * 140)
            painter.fillRect(x, y, bar_w, h, QColor(r, g, 60))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._save_position()
