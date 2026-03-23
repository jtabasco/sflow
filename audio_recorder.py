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

    def get_wav_if_long_enough(self) -> tuple[bytes, float] | None:
        """Returns (wav_bytes, duration_seconds) or None if too short."""
        with self._lock:
            duration = len(self._buffer) / self.sample_rate
            if duration < MIN_DURATION_SECONDS:
                return None
            return self._encode_wav(self._buffer.copy()), duration

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
