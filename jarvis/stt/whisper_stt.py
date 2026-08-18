"""
AOUDA AI — Whisper STT Engine (faster-whisper)
==============================================
100% offline, state-of-the-art Speech-to-Text for accent-heavy voice commands.
Features:
  - Hotwords boosting via initial_prompt ('AOUDA', 'Caillou', 'AMADEE', 'EVA')
  - Automatic phonetic corrections dictionary
  - Superior noise immunity (no false hallucinations on mic static)
"""

import os
import time
import numpy as np
from loguru import logger
from pathlib import Path
from typing import Optional, Dict


class WhisperSpeechToText:
    """
    faster-whisper STT engine for AOUDA suit assistant.
    """

    def __init__(self, config: dict):
        stt_cfg = config.get("stt", {})
        self.model_size: str = stt_cfg.get("whisper_model_size", "tiny")
        self.language: str   = stt_cfg.get("whisper_language", "en")
        self.silence_timeout: float = stt_cfg.get("silence_timeout_s", 1.2)
        self.phonetic_corrections: Dict[str, str] = stt_cfg.get("phonetic_corrections", {})
        self.hotwords: list  = stt_cfg.get("whisper_hotwords", ["AOUDA", "Caillou", "AMADEE", "EVA"])

        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load faster-whisper model (tiny/base)."""
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading faster-whisper model ({self.model_size})...")
            # Run on CPU with int8 quantization for ultra-fast offline execution
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )
            logger.success(f"faster-whisper STT ready — Model: {self.model_size}")

        except Exception as e:
            logger.error(f"Failed to load faster-whisper: {e}")
            self._model = None

    def transcribe_audio_array(self, audio_int16: np.ndarray) -> Optional[str]:
        """
        Transcribe a 1D int16 numpy array audio buffer.
        """
        if self._model is None or audio_int16 is None or len(audio_int16) == 0:
            return None

        # Convert int16 -> float32 normalized [-1.0, 1.0] for Whisper
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Build initial prompt with mission hotwords to guide Whisper
        prompt = "Mission AMADEE-27. Vocabulary: " + ", ".join(self.hotwords) + "."

        try:
            segments, _ = self._model.transcribe(
                audio_float32,
                language=self.language,
                beam_size=3,
                initial_prompt=prompt,
                vad_filter=True,  # Voice Activity Filter — ignores noise floor!
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            raw_text = " ".join([seg.text.strip() for seg in segments if seg.text.strip()]).strip()
            if not raw_text:
                return None

            # Apply phonetic corrections
            corrected_text = self._apply_phonetic_corrections(raw_text)
            logger.success(f"Whisper transcribed: '{corrected_text}' (raw: '{raw_text}')")
            return corrected_text

        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None

    def _apply_phonetic_corrections(self, text: str) -> str:
        """Replace phonetically misheard words with their intended mission terms."""
        words = text.split()
        corrected = []
        for w in words:
            clean_w = w.lower().strip(".,!?")
            if clean_w in self.phonetic_corrections:
                corrected.append(self.phonetic_corrections[clean_w])
            else:
                corrected.append(w)
        return " ".join(corrected)
