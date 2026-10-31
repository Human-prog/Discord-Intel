"""Speech-to-text (STT) and text-to-speech (TTS) for voice interaction.

Uses local Whisper (openai-whisper / whisper) for transcription and
pyttsx3 / gTTS for voice playback. Degrades safely if packages missing.
All audio processing stays local (no cloud STT unless explicitly configured).
"""

# mypy: ignore-errors
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Speech-to-Text (SttEngine)
# ------------------------------------------------------------------


class SttEngine:
    """Transcribe audio to text using Whisper (local)."""

    def __init__(self, model_name: str = "base") -> None:
        self.model_name = model_name
        self._model = None
        self._available = False

    def _load(self) -> bool:
        if self._model is not None:
            return self._available
        try:
            import whisper  # type: ignore[import-untyped]

            self._model = whisper.load_model(self.model_name)
            self._available = True
            logger.info("Whisper %s loaded for STT", self.model_name)
        except Exception as exc:
            logger.warning("Whisper STT unavailable: %s", exc)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._load()

    def transcribe(self, audio_path: str) -> str | None:
        """Transcribe an audio file to text."""
        if not self._load():
            return None
        try:
            result = self._model.transcribe(audio_path)  # type: ignore[union-attr]
            return result.get("text", "").strip()
        except Exception as exc:
            logger.warning("Whisper transcription failed: %s", exc)
            return None


# ------------------------------------------------------------------
# Text-to-Speech (TtsEngine)
# ------------------------------------------------------------------


class TtsEngine:
    """Convert text to spoken audio for voice playback."""

    def __init__(self, voice: str = "default") -> None:
        self.voice = voice
        self._engine = None
        self._available = False

    def _load(self) -> bool:
        if self._engine is not None:
            return self._available
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            voices = self._engine.getProperty("voices")
            # Pick first available voice
            if voices:
                self._engine.setProperty("voice", voices[0].id)
            self._available = True
            logger.info("TTS engine (pyttsx3) loaded")
        except Exception as exc:
            logger.warning("TTS unavailable (pyttsx3 missing): %s", exc)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._load()

    def speak_to_file(self, text: str, output_path: str) -> bool:
        """Generate a WAV file from text."""
        if not self._load():
            return False
        try:
            self._engine.save_to_file(text, output_path)
            self._engine.runAndWait()
            return Path(output_path).exists() and Path(output_path).stat().st_size > 0
        except Exception as exc:
            logger.warning("TTS generation failed: %s", exc)
            return False


# ------------------------------------------------------------------
# Voice interaction pipeline
# ------------------------------------------------------------------


class VoiceInteraction:
    """End-to-end voice interaction: listen → STT → understand → respond."""

    def __init__(self, settings: object | None = None) -> None:
        from project_intelligence.config import load_settings

        self.settings = settings or load_settings()
        self.stt = SttEngine(model_name="base")
        self.tts = TtsEngine()
        self._recording = False

    def can_transcribe(self) -> bool:
        return self.stt.is_available()

    def can_speak(self) -> bool:
        return self.tts.is_available()

    def transcribe_file(self, audio_path: str) -> str | None:
        return self.stt.transcribe(audio_path)

    def speak_file(self, text: str, output_path: str = "/tmp/voice_response.wav") -> str | None:  # noqa: S108
        if not self.tts.speak_to_file(text, output_path):
            return None
        return output_path
