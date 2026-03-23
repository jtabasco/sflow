# sflow-windows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows 11 push-to-talk voice-to-text desktop app using PyQt6 + Groq Whisper API that transcribes dictation and pastes it at the cursor.

**Architecture:** A single Python process with a PyQt6 event loop as the main thread. All cross-thread communication uses Qt Signals. The hotkey is captured via `pywin32 RegisterHotKey` through a `QAbstractNativeEventFilter`. Audio is captured with `sounddevice`, encoded to WAV with stdlib `wave`, and sent to Groq's Whisper API. A Flask daemon thread serves the history dashboard.

**Tech Stack:** Python 3.11+, PyQt6 6.6+, sounddevice, numpy, groq SDK, pywin32, Flask, python-dotenv, sqlite3 (stdlib), wave (stdlib)

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Pinned dependencies |
| `.env.example` | Config template |
| `app.manifest` | Windows UAC admin elevation manifest |
| `db.py` | SQLite CRUD — transcriptions + settings, thread-safe |
| `audio_recorder.py` | sounddevice capture, RMS calculation, WAV encoding |
| `transcriber.py` | Groq Whisper API call, returns text or None |
| `clipboard_paster.py` | QClipboard set + win32api Ctrl+V with focus restore |
| `hotkey_manager.py` | pywin32 RegisterHotKey via QAbstractNativeEventFilter |
| `pill_ui.py` | Frameless always-on-top PyQt6 window, 4 states |
| `tray_icon.py` | QSystemTrayIcon with context menu |
| `dashboard/server.py` | Flask app on 127.0.0.1:5678 |
| `dashboard/templates/index.html` | History list with search + pagination |
| `app.py` | Entry point — wires all modules together |
| `tests/test_db.py` | Unit tests for db.py |
| `tests/test_audio_recorder.py` | Unit tests for audio_recorder.py |
| `tests/test_transcriber.py` | Unit tests for transcriber.py (mocked HTTP) |
| `tests/test_clipboard_paster.py` | Unit tests for clipboard_paster.py (mocked win32) |

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app.manifest`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
pyqt6>=6.6.0
sounddevice>=0.4.6
numpy>=1.26.0
groq>=0.9.0
pywin32>=306
flask>=3.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 3: Create .env.example**

```
GROQ_API_KEY=gsk_your_key_here
DASHBOARD_PORT=5678
```

- [ ] **Step 4: Create app.manifest (Windows UAC elevation)**

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
```

- [ ] **Step 5: Create tests/__init__.py (empty)**

- [ ] **Step 6: Copy .env.example to .env and add your real Groq API key**

Get a free key at https://console.groq.com → API Keys.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example app.manifest tests/
git commit -m "chore: project setup — dependencies, config, UAC manifest"
```

---

## Task 2: Database Layer (db.py)

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_db.py`:

```python
import os
import pytest
import tempfile
from db import Database


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    yield database
    database.close()


def test_creates_tables(db):
    # Tables exist if we can insert without error
    db.save_transcription("hello world", 1.5)


def test_save_and_query_transcription(db):
    db.save_transcription("hello world", 2.0)
    results, total = db.get_transcriptions(page=1, search="")
    assert total == 1
    assert results[0]["text"] == "hello world"
    assert results[0]["duration"] == 2.0
    assert "created_at" in results[0]


def test_search_transcription(db):
    db.save_transcription("good morning", 1.0)
    db.save_transcription("good night", 1.0)
    results, total = db.get_transcriptions(page=1, search="morning")
    assert total == 1
    assert results[0]["text"] == "good morning"


def test_pagination(db):
    for i in range(55):
        db.save_transcription(f"text {i}", 1.0)
    results, total = db.get_transcriptions(page=1, search="")
    assert total == 55
    assert len(results) == 50  # page size
    results2, _ = db.get_transcriptions(page=2, search="")
    assert len(results2) == 5


def test_settings_get_set(db):
    db.set_setting("pill_x", "100")
    assert db.get_setting("pill_x") == "100"


def test_settings_default(db):
    assert db.get_setting("missing_key", default="42") == "42"


def test_thread_safety(db):
    import threading
    errors = []
    def worker():
        try:
            db.save_transcription("concurrent", 0.5)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    _, total = db.get_transcriptions(1, "")
    assert total == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement db.py**

```python
import sqlite3
import threading
from datetime import datetime


PAGE_SIZE = 50


class Database:
    def __init__(self, path: str = "sflow.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    text      TEXT NOT NULL,
                    duration  REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            self._conn.commit()

    def save_transcription(self, text: str, duration: float):
        created_at = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO transcriptions (text, duration, created_at) VALUES (?, ?, ?)",
                (text, duration, created_at),
            )
            self._conn.commit()

    def get_transcriptions(self, page: int, search: str) -> tuple[list[dict], int]:
        offset = (page - 1) * PAGE_SIZE
        with self._lock:
            if search:
                pattern = f"%{search}%"
                total = self._conn.execute(
                    "SELECT COUNT(*) FROM transcriptions WHERE text LIKE ?", (pattern,)
                ).fetchone()[0]
                rows = self._conn.execute(
                    "SELECT * FROM transcriptions WHERE text LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (pattern, PAGE_SIZE, offset),
                ).fetchall()
            else:
                total = self._conn.execute(
                    "SELECT COUNT(*) FROM transcriptions"
                ).fetchone()[0]
                rows = self._conn.execute(
                    "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ? OFFSET ?",
                    (PAGE_SIZE, offset),
                ).fetchall()
        return [dict(r) for r in rows], total

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()

    def close(self):
        self._conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: database layer with thread-safe SQLite CRUD"
```

---

## Task 3: Audio Recorder (audio_recorder.py)

**Files:**
- Create: `audio_recorder.py`
- Create: `tests/test_audio_recorder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_audio_recorder.py`:

```python
import io
import wave
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from audio_recorder import AudioRecorder


@pytest.fixture
def recorder():
    r = AudioRecorder(sample_rate=16000)
    yield r
    if r.is_recording:
        r.stop()


def test_initial_state(recorder):
    assert not recorder.is_recording
    assert recorder.sample_rate == 16000


def test_pcm_to_wav_produces_valid_wav(recorder):
    # Feed 1 second of silence as PCM
    samples = np.zeros(16000, dtype=np.float32)
    wav_bytes = recorder._encode_wav(samples)
    assert isinstance(wav_bytes, bytes)
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2  # 16-bit


def test_rms_calculation(recorder):
    silence = np.zeros(1024, dtype=np.float32)
    assert recorder._calc_rms(silence) == pytest.approx(0.0)
    full_signal = np.ones(1024, dtype=np.float32)
    assert recorder._calc_rms(full_signal) == pytest.approx(1.0)


def test_duration_too_short_returns_none(recorder):
    # Simulate 0.1s of audio (below 0.5s minimum)
    samples = np.zeros(1600, dtype=np.float32)  # 0.1s at 16kHz
    recorder._buffer = samples
    recorder._recording_duration = 0.1
    result = recorder.get_wav_if_long_enough()
    assert result is None


def test_duration_ok_returns_bytes(recorder):
    samples = np.zeros(16000, dtype=np.float32)  # 1.0s at 16kHz
    recorder._buffer = samples
    recorder._recording_duration = 1.0
    result = recorder.get_wav_if_long_enough()
    assert isinstance(result, bytes)
    assert len(result) > 44  # at least WAV header size
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_audio_recorder.py -v
```

Expected: `ModuleNotFoundError: No module named 'audio_recorder'`

- [ ] **Step 3: Implement audio_recorder.py**

```python
import io
import wave
import threading
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG


MIN_DURATION_SECONDS = 0.5
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"
CHUNK_SIZE = 1024


class AudioRecorder(QObject):
    rms_signal = pyqtSignal(float)

    def __init__(self, sample_rate: int = SAMPLE_RATE, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.is_recording = False
        self._buffer: np.ndarray = np.array([], dtype=np.float32)
        self._recording_duration: float = 0.0
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        if self.is_recording:
            return
        with self._lock:
            self._buffer = np.array([], dtype=np.float32)
            self._recording_duration = 0.0
        self.is_recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_wav_if_long_enough(self) -> bytes | None:
        with self._lock:
            duration = len(self._buffer) / self.sample_rate
            if duration < MIN_DURATION_SECONDS:
                return None
            return self._encode_wav(self._buffer.copy())

    def _audio_callback(self, indata: np.ndarray, frames: int, time, status):
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        with self._lock:
            self._buffer = np.concatenate([self._buffer, mono])
            self._recording_duration = len(self._buffer) / self.sample_rate
        rms = self._calc_rms(mono)
        QMetaObject.invokeMethod(
            self,
            "_emit_rms",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(float, float(rms)),
        )

    @staticmethod
    def _calc_rms(samples: np.ndarray) -> float:
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples ** 2)))

    def _encode_wav(self, samples: np.ndarray) -> bytes:
        pcm_16 = (samples * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_16.tobytes())
        return buf.getvalue()

    def _emit_rms(self, value: float):
        self.rms_signal.emit(value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_audio_recorder.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add audio_recorder.py tests/test_audio_recorder.py
git commit -m "feat: audio recorder with PCM capture, RMS, and WAV encoding"
```

---

## Task 4: Transcriber (transcriber.py)

**Files:**
- Create: `transcriber.py`
- Create: `tests/test_transcriber.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_transcriber.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from transcriber import Transcriber


@pytest.fixture
def transcriber():
    return Transcriber(api_key="test_key")


def test_returns_text_on_success(transcriber):
    mock_response = MagicMock()
    mock_response.text = "hello world"
    with patch.object(transcriber._client.audio.transcriptions, "create", return_value=mock_response):
        result = transcriber.transcribe(b"fake_wav_bytes", filename="audio.wav")
    assert result == "hello world"


def test_returns_none_on_auth_error(transcriber):
    from groq import AuthenticationError
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=AuthenticationError("invalid key", response=MagicMock(), body={})
    ):
        result = transcriber.transcribe(b"fake_wav_bytes")
    assert result is None


def test_returns_none_on_network_error(transcriber):
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=Exception("network error")
    ):
        result = transcriber.transcribe(b"fake_wav_bytes")
    assert result is None


def test_returns_none_on_empty_transcript(transcriber):
    mock_response = MagicMock()
    mock_response.text = "   "  # whitespace only
    with patch.object(transcriber._client.audio.transcriptions, "create", return_value=mock_response):
        result = transcriber.transcribe(b"fake_wav_bytes")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcriber.py -v
```

Expected: `ModuleNotFoundError: No module named 'transcriber'`

- [ ] **Step 3: Implement transcriber.py**

```python
import io
import logging
from groq import Groq, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "whisper-large-v3-turbo"


class TranscriptionError(Exception):
    """Raised when transcription fails. message is user-friendly."""
    pass


class Transcriber:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str | None:
        """
        Send WAV bytes to Groq Whisper. Returns transcribed text or None on error.
        Raises TranscriptionError with a user-friendly message for known errors.
        """
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            response = self._client.audio.transcriptions.create(
                file=audio_file,
                model=MODEL,
            )
            text = response.text.strip()
            return text if text else None
        except AuthenticationError:
            logger.error("Groq API key inválida (401)")
            raise TranscriptionError("API key inválida")
        except RateLimitError:
            logger.error("Groq rate limit (429)")
            raise TranscriptionError("Límite de Groq alcanzado")
        except Exception as e:
            logger.error(f"Groq error: {e}")
            raise TranscriptionError("Sin conexión")
```

- [ ] **Step 4: Update tests to match TranscriptionError**

Update `tests/test_transcriber.py` — the `returns_none` tests now expect `TranscriptionError`:

```python
def test_returns_none_on_auth_error(transcriber):
    from groq import AuthenticationError
    from transcriber import TranscriptionError
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=AuthenticationError("invalid key", response=MagicMock(), body={})
    ):
        with pytest.raises(TranscriptionError, match="inválida"):
            transcriber.transcribe(b"fake_wav_bytes")


def test_returns_none_on_network_error(transcriber):
    from transcriber import TranscriptionError
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=Exception("network error")
    ):
        with pytest.raises(TranscriptionError):
            transcriber.transcribe(b"fake_wav_bytes")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_transcriber.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add transcriber.py tests/test_transcriber.py
git commit -m "feat: Groq Whisper transcriber with typed error handling"
```

---

## Task 5: Clipboard Paster (clipboard_paster.py)

**Files:**
- Create: `clipboard_paster.py`
- Create: `tests/test_clipboard_paster.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_clipboard_paster.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, call


def test_paste_calls_attach_thread_input(mocker):
    mock_clipboard = mocker.patch("clipboard_paster.QApplication")
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mocker.patch("clipboard_paster.win32api")
    mocker.patch("clipboard_paster.win32con")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("hello", hwnd=12345)
    import clipboard_paster as cp
    assert cp.win32gui.AttachThreadInput.call_count == 2  # attach + detach


def test_paste_sets_clipboard_text(mocker):
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mocker.patch("clipboard_paster.win32api")
    mocker.patch("clipboard_paster.win32con")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("my text", hwnd=12345)
    app_mock.clipboard.return_value.setText.assert_called_once_with("my text")


def test_paste_sends_ctrl_v(mocker):
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mocker.patch("clipboard_paster.win32con")
    mock_win32api = mocker.patch("clipboard_paster.win32api")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("hello", hwnd=12345)
    # keybd_event called at least twice (ctrl down, v down, v up, ctrl up)
    assert mock_win32api.keybd_event.call_count >= 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_clipboard_paster.py -v
```

Expected: `ModuleNotFoundError: No module named 'clipboard_paster'`

- [ ] **Step 3: Implement clipboard_paster.py**

```python
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
        fg_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_clipboard_paster.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add clipboard_paster.py tests/test_clipboard_paster.py
git commit -m "feat: clipboard paster with AttachThreadInput focus restore"
```

---

## Task 6: Hotkey Manager (hotkey_manager.py)

**Files:**
- Create: `hotkey_manager.py`

> No unit tests for this module — it requires a live Windows message loop. Tested via integration in Task 10.

- [ ] **Step 1: Implement hotkey_manager.py**

```python
import logging
import win32con
import win32gui
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAbstractNativeEventFilter

logger = logging.getLogger(__name__)

# Hotkey ID (arbitrary int, must be unique per process)
HOTKEY_ID = 1
# Ctrl+Shift+Space
MODIFIERS = win32con.MOD_CONTROL | win32con.MOD_SHIFT
VKEY = win32con.VK_SPACE
WM_HOTKEY = 0x0312


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """
    Registers Ctrl+Shift+Space as a system-wide hotkey via win32 RegisterHotKey.
    Integrates with Qt's event loop via QAbstractNativeEventFilter (no extra thread needed).

    Emits:
        hotkey_pressed  — user pressed the combo
        hotkey_released — user released the combo (key-up WM_HOTKEY, simulated via hold detection)

    Note: RegisterHotKey fires on key-down only. We detect "released" by listening to the
    raw WM_KEYUP of VK_SPACE while Ctrl+Shift are still held, via a secondary filter.
    For simplicity in v1 we treat each WM_HOTKEY as a toggle: odd=press, even=release.
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
        result = win32gui.RegisterHotKey(None, HOTKEY_ID, MODIFIERS, VKEY)
        if result:
            self._registered = True
            logger.info("Hotkey Ctrl+Shift+Space registered")
        else:
            logger.error("Failed to register hotkey (already in use?)")
        return bool(result)

    def unregister(self):
        if self._registered:
            win32gui.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        """Called by Qt event loop for every native Windows message."""
        # message is a sip.voidptr; convert to MSG struct
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
```

- [ ] **Step 2: Commit**

```bash
git add hotkey_manager.py
git commit -m "feat: hotkey manager via pywin32 RegisterHotKey + Qt native event filter"
```

---

## Task 7: Pill UI (pill_ui.py)

**Files:**
- Create: `pill_ui.py`

> UI smoke test done manually in Task 10. No automated unit tests for PyQt6 window rendering.

- [ ] **Step 1: Implement pill_ui.py**

```python
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

        # Background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 24, 24)

        if self._state == PillState.ERROR:
            bg_color = QColor(180, 40, 40, 220)
        elif self._state == PillState.RECORDING:
            bg_color = QColor(30, 30, 30, 230)
        else:
            bg_color = QColor(30, 30, 30, 200)

        painter.fillPath(path, bg_color)

        # Content
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

    # --- Drag support ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._save_position()
```

- [ ] **Step 2: Commit**

```bash
git add pill_ui.py
git commit -m "feat: floating pill UI with 4 states and audio bar visualization"
```

---

## Task 8: System Tray (tray_icon.py)

**Files:**
- Create: `tray_icon.py`
- Create: `assets/icon.png` (16x16 or 32x32 microphone icon)

- [ ] **Step 1: Create a simple icon**

Run this one-time Python snippet to generate a placeholder icon (or drop in your own PNG):

```python
# run once: python -c "exec(open('make_icon.py').read())"
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
pm = QPixmap(32, 32)
pm.fill(Qt.GlobalColor.transparent)
p = QPainter(pm)
p.setBrush(QColor(80, 160, 255))
p.setPen(Qt.PenStyle.NoPen)
p.drawEllipse(4, 4, 24, 24)
p.end()
import os; os.makedirs("assets", exist_ok=True)
pm.save("assets/icon.png")
print("icon saved")
```

Save as `make_icon.py` and run:

```bash
python make_icon.py
```

- [ ] **Step 2: Implement tray_icon.py**

```python
import os
import logging
import webbrowser
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QInputDialog, QLineEdit
from PyQt6.QtGui import QIcon, QAction

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, db, dashboard_port: int, parent=None):
        icon = QIcon("assets/icon.png")
        super().__init__(icon, parent)
        self._db = db
        self._port = dashboard_port
        self._setup_menu()
        self.setToolTip("sflow — Ctrl+Shift+Space para dictar")

    def _setup_menu(self):
        menu = QMenu()

        open_action = QAction("📊 Abrir dashboard", menu)
        open_action.triggered.connect(self._open_dashboard)
        menu.addAction(open_action)

        apikey_action = QAction("🔑 Configurar API key", menu)
        apikey_action.triggered.connect(self._configure_api_key)
        menu.addAction(apikey_action)

        menu.addSeparator()

        quit_action = QAction("❌ Salir", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _open_dashboard(self):
        webbrowser.open(f"http://localhost:{self._port}")

    def _configure_api_key(self):
        text, ok = QInputDialog.getText(
            None,
            "API Key de Groq",
            "Ingresa tu API key de Groq (gsk_...):",
            QLineEdit.EchoMode.Password,
        )
        if ok and text.strip():
            self._write_env_key(text.strip())
            self.showMessage(
                "sflow",
                "API key guardada. Reinicia la app para aplicar.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _write_env_key(self, key: str):
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        new_lines = [l for l in lines if not l.startswith("GROQ_API_KEY")]
        new_lines.append(f"GROQ_API_KEY={key}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)

    def _quit(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def notify(self, message: str):
        self.showMessage("sflow", message, QSystemTrayIcon.MessageIcon.Warning, 4000)
```

- [ ] **Step 3: Commit**

```bash
git add tray_icon.py make_icon.py assets/
git commit -m "feat: system tray icon with dashboard, API key config, and quit"
```

---

## Task 9: Flask Dashboard (dashboard/)

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/server.py`
- Create: `dashboard/templates/index.html`

- [ ] **Step 1: Create dashboard/__init__.py (empty)**

- [ ] **Step 2: Implement dashboard/server.py**

```python
import logging
import threading
from flask import Flask, render_template, request

logger = logging.getLogger(__name__)


def create_dashboard(db, port: int) -> threading.Thread:
    """Create and start the Flask dashboard in a daemon thread. Returns the thread."""
    app = Flask(__name__, template_folder="templates")

    @app.route("/")
    def index():
        page = int(request.args.get("page", 1))
        search = request.args.get("q", "")
        results, total = db.get_transcriptions(page=page, search=search)
        total_pages = max(1, (total + 49) // 50)
        return render_template(
            "index.html",
            transcriptions=results,
            page=page,
            total_pages=total_pages,
            total=total,
            search=search,
        )

    def run():
        try:
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
        except OSError as e:
            logger.warning(f"Dashboard could not start on port {port}: {e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
```

- [ ] **Step 3: Create dashboard/templates/index.html**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>sflow — Historial</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 24px; }
    h1 { font-size: 1.4rem; margin-bottom: 16px; color: #7eb8ff; }
    .search-bar { display: flex; gap: 8px; margin-bottom: 20px; }
    .search-bar input { flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid #333; background: #1a1a1a; color: #e0e0e0; font-size: 0.95rem; }
    .search-bar button { padding: 8px 16px; border-radius: 8px; border: none; background: #3a78c9; color: white; cursor: pointer; }
    .stats { font-size: 0.85rem; color: #888; margin-bottom: 16px; }
    .card { background: #1a1a1a; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; position: relative; }
    .card .text { font-size: 0.95rem; line-height: 1.5; margin-bottom: 8px; }
    .card .meta { font-size: 0.78rem; color: #666; }
    .card .copy-btn { position: absolute; top: 12px; right: 12px; padding: 4px 10px; border-radius: 6px; border: 1px solid #333; background: #222; color: #aaa; cursor: pointer; font-size: 0.78rem; }
    .card .copy-btn:hover { background: #333; color: #fff; }
    .pagination { display: flex; gap: 8px; margin-top: 24px; justify-content: center; }
    .pagination a { padding: 6px 14px; border-radius: 6px; background: #1a1a1a; color: #7eb8ff; text-decoration: none; border: 1px solid #333; }
    .pagination a.active { background: #3a78c9; color: #fff; border-color: #3a78c9; }
    .empty { color: #555; text-align: center; padding: 48px; }
  </style>
</head>
<body>
  <h1>🎙️ sflow — Historial</h1>
  <form class="search-bar" method="get">
    <input type="text" name="q" placeholder="Buscar transcripciones…" value="{{ search }}">
    <button type="submit">Buscar</button>
    {% if search %}<a href="/" style="padding:8px 12px;color:#888;text-decoration:none">✕</a>{% endif %}
  </form>
  <p class="stats">{{ total }} transcripción{% if total != 1 %}es{% endif %}{% if search %} para "{{ search }}"{% endif %}</p>

  {% if transcriptions %}
    {% for t in transcriptions %}
    <div class="card">
      <div class="text">{{ t.text }}</div>
      <div class="meta">{{ t.created_at }} · {{ "%.1f"|format(t.duration) }}s</div>
      <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.card').querySelector('.text').textContent)">Copiar</button>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">No hay transcripciones{% if search %} que coincidan{% endif %}.</div>
  {% endif %}

  {% if total_pages > 1 %}
  <div class="pagination">
    {% for p in range(1, total_pages + 1) %}
      <a href="?page={{ p }}&q={{ search }}" {% if p == page %}class="active"{% endif %}>{{ p }}</a>
    {% endfor %}
  </div>
  {% endif %}

  <script>
    // Auto-reload every 10s if on page 1 with no search
    {% if page == 1 and not search %}
    setTimeout(() => location.reload(), 10000);
    {% endif %}
  </script>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/
git commit -m "feat: Flask dashboard with search and pagination"
```

---

## Task 10: App Entry Point (app.py)

**Files:**
- Create: `app.py`

- [ ] **Step 1: Implement app.py**

```python
import sys
import logging
import os
from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    from db import Database
    from audio_recorder import AudioRecorder
    from transcriber import Transcriber, TranscriptionError
    from clipboard_paster import ClipboardPaster
    from hotkey_manager import HotkeyManager
    from pill_ui import PillUI, PillState
    from tray_icon import TrayIcon
    from dashboard.server import create_dashboard

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        logger.error("GROQ_API_KEY not set. Please configure it via the tray icon.")

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

    # Start dashboard
    create_dashboard(db, port)

    # Register hotkey
    if not hotkey_mgr.register():
        tray.notify("No se pudo registrar el hotkey (¿ya está en uso?)")

    app.installNativeEventFilter(hotkey_mgr)

    # --- Wiring ---
    _target_hwnd: list[int] = [0]

    def on_hotkey_pressed():
        import win32gui
        _target_hwnd[0] = win32gui.GetForegroundWindow()
        recorder.start()
        pill.set_state(PillState.RECORDING)
        logger.info("Recording started")

    def on_hotkey_released():
        recorder.stop()
        wav = recorder.get_wav_if_long_enough()
        if wav is None:
            pill.set_state(PillState.IDLE)
            return
        pill.set_state(PillState.PROCESSING)
        worker.audio_bytes = wav
        worker.start()

    def on_rms(value: float):
        pill.set_rms(value)

    from PyQt6.QtCore import QThread, pyqtSignal as Signal

    class TranscribeWorker(QThread):
        done = Signal(str)      # text
        failed = Signal(str)    # error message

        def __init__(self):
            super().__init__()
            self.audio_bytes: bytes = b""

        def run(self):
            try:
                text = transcriber.transcribe(self.audio_bytes)
                if text:
                    self.done.emit(text)
                else:
                    self.failed.emit("Sin texto detectado")
            except TranscriptionError as e:
                self.failed.emit(str(e))

    worker = TranscribeWorker()

    def on_transcription_done(text: str):
        import sounddevice as sd
        paster.paste(text, hwnd=_target_hwnd[0])
        duration = len(text) / 15  # rough estimate fallback
        db.save_transcription(text, duration)
        pill.set_state(PillState.IDLE)
        logger.info(f"Transcribed: {text[:60]}")

    def on_transcription_failed(message: str):
        pill.set_state(PillState.ERROR)
        tray.notify(message)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: pill.set_state(PillState.IDLE))
        logger.warning(f"Transcription failed: {message}")

    hotkey_mgr.hotkey_pressed.connect(on_hotkey_pressed)
    hotkey_mgr.hotkey_released.connect(on_hotkey_released)
    recorder.rms_signal.connect(on_rms)
    worker.done.connect(on_transcription_done)
    worker.failed.connect(on_transcription_failed)

    pill.show()
    tray.show()

    logger.info("sflow started — Ctrl+Shift+Space to dictate")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: app entry point wiring all modules together"
```

---

## Task 11: Integration Smoke Test

- [ ] **Step 1: Run the app manually**

```bash
python app.py
```

Expected:
- Pill appears in corner of screen
- Tray icon appears in Windows taskbar
- No errors in console

- [ ] **Step 2: Test recording flow manually**

1. Hold `Ctrl+Shift+Space` — pill shows RECORDING state with animated bars
2. Say a sentence out loud
3. Release keys — pill shows PROCESSING
4. Text appears in the active window — pill returns to IDLE

- [ ] **Step 3: Test error handling**

1. Open `.env`, set `GROQ_API_KEY=invalid_key`
2. Restart app and record a phrase
3. Expected: pill shows ERROR state, tray notification "API key inválida"

- [ ] **Step 4: Test dashboard**

1. Open `http://localhost:5678` in browser
2. Confirm transcriptions appear
3. Test search box
4. Test copy button

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: sflow-windows v1 complete — push-to-talk voice transcription for Windows 11"
```

---

## Quick Start (for new developers)

```bash
# 1. Clone and enter project
cd C:\Projects\sflow-windows

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
copy .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_your_key

# 5. Generate icon
python make_icon.py

# 6. Run (as Administrator — required for global hotkey)
python app.py
```

> **Important:** Run `python app.py` from an **Administrator** command prompt or terminal. Right-click → "Run as administrator". Without this, the hotkey won't work when an elevated window (e.g. Task Manager) is in focus.
