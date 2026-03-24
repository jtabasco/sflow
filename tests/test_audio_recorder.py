import io
import wave
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from audio_recorder import AudioRecorder


@pytest.fixture
def recorder():
    with patch("audio_recorder.sd.InputStream") as mock_stream_cls:
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        r = AudioRecorder(sample_rate=16000)
        yield r
        if r.is_recording:
            r.stop()
        r._rms_timer.stop()


def test_initial_state(recorder):
    assert not recorder.is_recording
    assert recorder.sample_rate == 16000


def test_pcm_to_wav_produces_valid_wav(recorder):
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
    samples = np.zeros(1600, dtype=np.float32)  # 0.1s at 16kHz
    recorder._buffer = samples
    recorder._recording_duration = 0.1
    result = recorder.get_wav_if_long_enough()
    assert result is None


def test_duration_ok_returns_bytes_and_duration(recorder):
    samples = np.zeros(16000, dtype=np.float32)  # 1.0s at 16kHz
    recorder._buffer = samples
    recorder._recording_duration = 1.0
    result = recorder.get_wav_if_long_enough()
    assert result is not None
    wav_bytes, duration = result
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44  # at least WAV header size
    assert duration == pytest.approx(1.0)
