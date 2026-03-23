import logging
import win32api
import win32con
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

# Ctrl+Alt+D — poll via GetAsyncKeyState
VK_CTRL = win32con.VK_CONTROL
VK_ALT = win32con.VK_MENU   # VK_MENU = Alt key
VK_D = ord("D")

POLL_INTERVAL_MS = 30  # check every 30ms


class HotkeyManager(QObject):
    """
    Detects Ctrl+Alt+D via GetAsyncKeyState polling (QTimer).
    Emits hotkey_pressed on key-down, hotkey_released on key-up.
    This gives true push-to-talk behavior (hold = record, release = stop).
    No RegisterHotKey needed — works without admin, no conflicts.
    """
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._held = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def register(self) -> bool:
        self._timer.start(POLL_INTERVAL_MS)
        logger.info("Hotkey Ctrl+Alt+D active (polling mode)")
        return True

    def unregister(self):
        self._timer.stop()

    def _poll(self):
        ctrl = bool(win32api.GetAsyncKeyState(VK_CTRL) & 0x8000)
        alt  = bool(win32api.GetAsyncKeyState(VK_ALT)  & 0x8000)
        d    = bool(win32api.GetAsyncKeyState(VK_D)    & 0x8000)

        pressed = ctrl and alt and d

        if pressed and not self._held:
            self._held = True
            logger.info("Hotkey pressed — recording start")
            self.hotkey_pressed.emit()
        elif not pressed and self._held:
            self._held = False
            logger.info("Hotkey released — recording stop")
            self.hotkey_released.emit()
