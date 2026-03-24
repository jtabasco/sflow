import time
import logging
import win32api
import win32con
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

# Push-to-talk: Ctrl+Shift+Space
# Hands-free:   double-tap Shift (alone), single Shift tap to stop
VK_CTRL  = win32con.VK_CONTROL
VK_SHIFT = win32con.VK_SHIFT
VK_SPACE = win32con.VK_SPACE

POLL_INTERVAL_MS = 30
DOUBLE_TAP_WINDOW = 0.40  # seconds


class HotkeyManager(QObject):
    """
    Two recording modes:
    - Push-to-talk: hold Ctrl+Shift+Space, release to stop
    - Hands-free:   double-tap Shift (alone), single Shift tap to stop
    """
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._held = False          # push-to-talk active
        self._hands_free = False    # hands-free active
        self._shift_was_down = False
        self._shift_last_up = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def register(self) -> bool:
        self._timer.start(POLL_INTERVAL_MS)
        logger.info("Hotkeys active: Ctrl+Shift+Space (push-to-talk) | double-tap Shift (hands-free)")
        return True

    def unregister(self):
        self._timer.stop()

    def _poll(self):
        ctrl  = bool(win32api.GetAsyncKeyState(VK_CTRL)  & 0x8000)
        shift = bool(win32api.GetAsyncKeyState(VK_SHIFT) & 0x8000)
        space = bool(win32api.GetAsyncKeyState(VK_SPACE) & 0x8000)
        now = time.monotonic()

        # --- Push-to-talk: Ctrl+Shift+Space ---
        ptt = ctrl and shift and space
        if ptt and not self._held and not self._hands_free:
            self._held = True
            logger.info("PTT pressed — recording start")
            self.hotkey_pressed.emit()
        elif not ptt and self._held:
            self._held = False
            logger.info("PTT released — recording stop")
            self.hotkey_released.emit()

        # --- Hands-free: double-tap Shift alone (no Ctrl, no Space) ---
        shift_alone = shift and not ctrl and not space

        if not self._held:
            if not self._hands_free:
                # Detect double-tap: Shift down→up→down→up within DOUBLE_TAP_WINDOW
                if shift_alone and not self._shift_was_down:
                    self._shift_was_down = True
                elif not shift_alone and self._shift_was_down:
                    self._shift_was_down = False
                    dt = now - self._shift_last_up
                    if 0.05 < dt < DOUBLE_TAP_WINDOW:
                        # Double-tap confirmed → start hands-free
                        self._hands_free = True
                        self._shift_last_up = 0.0
                        logger.info("Hands-free started — recording start")
                        self.hotkey_pressed.emit()
                    else:
                        self._shift_last_up = now
            else:
                # Hands-free active: next Shift tap stops recording
                if shift_alone and not self._shift_was_down:
                    self._shift_was_down = True
                elif not shift_alone and self._shift_was_down:
                    self._shift_was_down = False
                    self._hands_free = False
                    logger.info("Hands-free stopped — recording stop")
                    self.hotkey_released.emit()
