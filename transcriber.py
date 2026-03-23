import io
import logging
from groq import Groq, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "whisper-large-v3-turbo"


class TranscriptionError(Exception):
    """Raised when transcription fails. Message is user-friendly."""
    pass


class Transcriber:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str | None:
        """
        Send WAV bytes to Groq Whisper API.
        Returns transcribed text (str) or None if audio had no speech.
        Raises TranscriptionError with user-friendly message on API errors.
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
