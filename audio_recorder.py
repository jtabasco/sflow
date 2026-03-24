import io
import wave
import threading
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


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
        self._lock = threading.Lock()
        self._latest_rms: float = 0.0

        # Pre-warm stream — always running; start() just enables buffering
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()

        # Poll RMS on main thread every 50ms (avoids cross-thread Qt signal issues)
        self._rms_timer = QTimer(self)
        self._rms_timer.timeout.connect(self._emit_rms)
        self._rms_timer.start(50)

    def start(self):
        if self.is_recording:
            return
        with self._lock:
            self._buffer = np.array([], dtype=np.float32)
        self.is_recording = True

    def stop(self):
        self.is_recording = False

    def get_wav_if_long_enough(self) -> tuple[bytes, float] | None:
        """Returns (wav_bytes, duration_seconds) or None if too short."""
        with self._lock:
            duration = len(self._buffer) / self.sample_rate
            if duration < MIN_DURATION_SECONDS:
                return None
            return self._encode_wav(self._buffer.copy()), duration

    def _audio_callback(self, indata: np.ndarray, frames: int, time, status):
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        self._latest_rms = self._calc_rms(mono)
        if self.is_recording:
            with self._lock:
                self._buffer = np.concatenate([self._buffer, mono])

    def _emit_rms(self):
        if self.is_recording:
            self.rms_signal.emit(self._latest_rms)

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

    def close(self):
        self._rms_timer.stop()
        self._stream.stop()
        self._stream.close()
