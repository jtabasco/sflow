import logging
import win32con
import win32gui
from PyQt6.QtCore import QObject, pyqtSignal, QAbstractNativeEventFilter

logger = logging.getLogger(__name__)

# Hotkey ID (arbitrary int, must be unique per process)
HOTKEY_ID = 1
# Ctrl+Alt+D  (D for Dictate — less likely to conflict)
MODIFIERS = win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_NOREPEAT
VKEY = ord("D")
WM_HOTKEY = 0x0312


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """
    Registers Ctrl+Shift+Space as a system-wide hotkey via win32 RegisterHotKey.
    Integrates with Qt's event loop via QAbstractNativeEventFilter (no extra thread needed).

    Emits:
        hotkey_pressed  — first press, starts recording
        hotkey_released — second press, stops recording

    v1 behavior: RegisterHotKey fires on key-down only, so true push-to-talk
    (hold=record, release=stop) is not possible with RegisterHotKey alone.
    Instead we use TOGGLE mode: first press starts recording, second press stops it.
    The pill shows a red dot + animated bars while recording so the user always
    knows the current state. True push-to-talk is a v2 enhancement.
    """
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._registered = False
        self._held = False

    def register(self) -> bool:
        """Register hotkey. Returns True on success."""
        try:
            win32gui.RegisterHotKey(None, HOTKEY_ID, MODIFIERS, VKEY)
            self._registered = True
            logger.info("Hotkey Ctrl+Alt+D registered")
            return True
        except Exception as e:
            logger.error(f"Failed to register hotkey: {e}")
            return False

    def unregister(self):
        if self._registered:
            win32gui.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        """Called by Qt event loop for every native Windows message."""
        from ctypes import cast, POINTER
        from ctypes.wintypes import MSG
        msg = cast(int(message), POINTER(MSG)).contents
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            if not self._held:
                self._held = True
                self.hotkey_pressed.emit()
            else:
                self._held = False
                self.hotkey_released.emit()
            return True, 0
        return False, 0
