import pytest
from unittest.mock import MagicMock, patch
from transcriber import Transcriber, TranscriptionError


@pytest.fixture
def transcriber():
    return Transcriber(api_key="test_key")


def test_returns_text_on_success(transcriber):
    mock_response = MagicMock()
    mock_response.text = "hello world"
    with patch.object(transcriber._client.audio.transcriptions, "create", return_value=mock_response):
        result = transcriber.transcribe(b"fake_wav_bytes", filename="audio.wav")
    assert result == "hello world"


def test_returns_none_on_empty_transcript(transcriber):
    mock_response = MagicMock()
    mock_response.text = "   "  # whitespace only
    with patch.object(transcriber._client.audio.transcriptions, "create", return_value=mock_response):
        result = transcriber.transcribe(b"fake_wav_bytes")
    assert result is None


def test_raises_transcription_error_on_auth_error(transcriber):
    from groq import AuthenticationError
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=AuthenticationError("invalid key", response=MagicMock(), body={})
    ):
        with pytest.raises(TranscriptionError, match="inválida"):
            transcriber.transcribe(b"fake_wav_bytes")


def test_raises_transcription_error_on_rate_limit(transcriber):
    from groq import RateLimitError
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=RateLimitError("rate limited", response=MagicMock(), body={})
    ):
        with pytest.raises(TranscriptionError, match="Límite"):
            transcriber.transcribe(b"fake_wav_bytes")


def test_raises_transcription_error_on_network_error(transcriber):
    with patch.object(
        transcriber._client.audio.transcriptions, "create",
        side_effect=Exception("network error")
    ):
        with pytest.raises(TranscriptionError):
            transcriber.transcribe(b"fake_wav_bytes")
