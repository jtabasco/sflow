import logging
import win32api
import win32con
import win32gui
import win32process
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

VK_CONTROL = win32con.VK_CONTROL
VK_V = ord("V")
KEYEVENTF_KEYUP = win32con.KEYEVENTF_KEYUP


class ClipboardPaster:
    def __init__(self, qt_app: QApplication):
        self._app = qt_app

    def paste(self, text: str, hwnd: int):
        """Copy text to clipboard and paste it into the window identified by hwnd."""
        try:
            self._restore_focus(hwnd)
        except Exception as e:
            logger.warning(f"Could not restore focus to hwnd={hwnd}: {e}")

        self._app.clipboard().setText(text)
        self._send_ctrl_v()

    def _restore_focus(self, hwnd: int):
        result = win32process.GetWindowThreadProcessId(hwnd)
        fg_thread = result[0]
        cur_thread = win32api.GetCurrentThreadId()
        win32gui.AttachThreadInput(fg_thread, cur_thread, True)
        try:
            win32gui.SetForegroundWindow(hwnd)
        finally:
            win32gui.AttachThreadInput(fg_thread, cur_thread, False)

    def _send_ctrl_v(self):
        win32api.keybd_event(VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(VK_V, 0, 0, 0)
        win32api.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
