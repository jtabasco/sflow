import sys
import logging
import os
from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal as Signal, QTimer

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class TranscribeWorker(QThread):
    done = Signal(str, float)   # text, duration_seconds
    failed = Signal(str)        # error message

    def __init__(self, transcriber):
        super().__init__()
        self._transcriber = transcriber
        self.audio_bytes: bytes = b""
        self.duration: float = 0.0

    def run(self):
        from transcriber import TranscriptionError
        try:
            text = self._transcriber.transcribe(self.audio_bytes)
            if text:
                self.done.emit(text, self.duration)
            else:
                self.failed.emit("Sin texto detectado")
        except TranscriptionError as e:
            self.failed.emit(str(e))


def main():
    from db import Database
    from audio_recorder import AudioRecorder
    from transcriber import Transcriber
    from clipboard_paster import ClipboardPaster
    from hotkey_manager import HotkeyManager
    from pill_ui import PillUI, PillState
    from tray_icon import TrayIcon
    from dashboard.server import create_dashboard

    api_key = os.getenv("GROQ_API_KEY", "")
    port = int(os.getenv("DASHBOARD_PORT", "5678"))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    db = Database()
    recorder = AudioRecorder()
    transcriber = Transcriber(api_key=api_key)
    paster = ClipboardPaster(qt_app=app)
    pill = PillUI(db=db)
    tray = TrayIcon(db=db, dashboard_port=port)
    hotkey_mgr = HotkeyManager()
    worker = TranscribeWorker(transcriber)

    create_dashboard(db, port)

    if not api_key:
        logger.warning("GROQ_API_KEY not set — configure via tray icon")
        tray.notify("API key no configurada. Usa el ícono de la bandeja para configurarla.")

    if not hotkey_mgr.register():
        tray.notify("No se pudo registrar el hotkey (¿ya está en uso?)")

    app.installNativeEventFilter(hotkey_mgr)

    _target_hwnd: list[int] = [0]

    def on_hotkey_pressed():
        import win32gui
        _target_hwnd[0] = win32gui.GetForegroundWindow()
        recorder.start()
        pill.set_state(PillState.RECORDING)
        logger.info("Recording started")

    def on_hotkey_released():
        recorder.stop()
        result = recorder.get_wav_if_long_enough()
        if result is None:
            pill.set_state(PillState.IDLE)
            logger.info("Recording too short, discarded")
            return
        if worker.isRunning():
            logger.warning("Previous transcription still in progress, discarding")
            pill.set_state(PillState.IDLE)
            return
        wav, duration = result
        pill.set_state(PillState.PROCESSING)
        worker.audio_bytes = wav
        worker.duration = duration
        worker.start()

    def on_rms(value: float):
        pill.set_rms(value)

    def on_transcription_done(text: str, duration: float):
        paster.paste(text, hwnd=_target_hwnd[0])
        db.save_transcription(text, duration)
        pill.set_state(PillState.IDLE)
        logger.info(f"Transcribed ({duration:.1f}s): {text[:60]}")

    def on_transcription_failed(message: str):
        pill.set_state(PillState.ERROR)
        tray.notify(message)
        QTimer.singleShot(3000, lambda: pill.set_state(PillState.IDLE))
        logger.warning(f"Transcription failed: {message}")

    hotkey_mgr.hotkey_pressed.connect(on_hotkey_pressed)
    hotkey_mgr.hotkey_released.connect(on_hotkey_released)
    recorder.rms_signal.connect(on_rms)
    worker.done.connect(on_transcription_done)
    worker.failed.connect(on_transcription_failed)

    pill.show()
    tray.show()

    logger.info(f"sflow started — Ctrl+Alt+Space to dictate | dashboard: http://localhost:{port}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
