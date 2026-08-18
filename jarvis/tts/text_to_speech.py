"""
JARVIS AI — TTS Module (Text-to-Speech)
=========================================
100% offline speech synthesis via Piper TTS.
Fallback: console display when model not available.

Fix Windows: uses named temp WAV file instead of BytesIO buffer
(soundfile does not flush headers correctly on Windows with BytesIO).
"""

import os
import io
import time
import tempfile
from pathlib import Path
import sounddevice as sd
import soundfile as sf
from loguru import logger
from typing import Optional


class TextToSpeech:
    """
    Piper-based TTS engine.
    Converts text to audio and plays it on the speaker.
    """

    def __init__(self, config: dict):
        tts_cfg = config.get("tts", {})
        piper_cfg = tts_cfg.get("piper", {})
        self.model_path: str = tts_cfg.get("model_path") or piper_cfg.get("model_path", "models/piper/en_US-lessac-medium.onnx")
        self.model_config: str = tts_cfg.get("model_config") or piper_cfg.get("config_path", "models/piper/en_US-lessac-medium.onnx.json")
        self.output_device: Optional[int] = tts_cfg.get("output_device_index", None)
        self.speed: float = tts_cfg.get("speed") or piper_cfg.get("length_scale", 1.0)
        self._piper_available: bool  = False
        self._simulation_mode: bool  = False
        self._voice = None  # Loaded lazily on first speak()
        self._is_speaking: bool = False
        self._stop_requested: bool = False

        self._check_piper()

    def _check_piper(self) -> None:
        """Check if Piper TTS model is available, falling back to default if custom model missing."""
        try:
            from piper import PiperVoice  # noqa: F401 — just import check

            model = Path(self.model_path)
            if model.exists():
                self._piper_available = True
                logger.success(f"[TTS] Active Voice Model: {self.model_path}")
            else:
                fallback_path = "models/piper/en_US-lessac-medium.onnx"
                fallback_cfg = "models/piper/en_US-lessac-medium.onnx.json"
                if Path(fallback_path).exists():
                    logger.warning(
                        f"[TTS] Custom voice model '{self.model_path}' not found in models/piper/.\n"
                        f"-> Using default Piper model ({fallback_path}) until 'patrick.onnx' is placed in models/piper/."
                    )
                    self.model_path = fallback_path
                    self.model_config = fallback_cfg
                    self._piper_available = True
                else:
                    logger.warning(f"[TTS] Piper model not found: {self.model_path} -> Console mode.")
                    self._simulation_mode = True

        except ImportError:
            logger.warning("[TTS] piper-tts not installed -> Console mode.")
            self._simulation_mode = True

    def _load_voice(self):
        """Lazy-load the Piper voice model (only on first speak)."""
        if self._voice is None:
            from piper import PiperVoice
            logger.info("Loading Piper voice model (first call)...")
            self._voice = PiperVoice.load(
                self.model_path,
                config_path=self.model_config,
            )
            logger.success("Piper voice model loaded.")
        return self._voice

    def speak(self, text: str) -> None:
        """
        Synthesize and play the given text.

        Args:
            text: Text to speak aloud.
        """
        if not text:
            return

        self._stop_requested = False
        self._is_speaking = True

        short = text[:80] + ("..." if len(text) > 80 else "")
        logger.info(f"TTS: \"{short}\"")

        try:
            if self._simulation_mode:
                self._simulate_speech(text)
            elif self._piper_available:
                self._speak_piper(text)
            else:
                self._simulate_speech(text)
        finally:
            self._is_speaking = False

    def _speak_piper(self, text: str) -> None:
        """
        Use Piper to synthesize and play audio.
        PiperVoice.synthesize() returns an Iterable[AudioChunk].
        Each chunk has a .audio attribute (bytes, int16 PCM).
        """
        try:
            voice = self._load_voice()

            # Collect all audio chunks from the iterator
            # AudioChunk attributes: audio_float_array, sample_rate, audio_int16_bytes
            audio_frames = []
            sample_rate = 22050  # Piper default

            for chunk in voice.synthesize(text):
                audio_frames.append(chunk.audio_float_array)
                sample_rate = chunk.sample_rate  # e.g. 22050

            if not audio_frames:
                logger.warning("Piper returned no audio chunks.")
                self._simulate_speech(text)
                return

            # Concatenate all chunks into one float32 array and play
            import numpy as np
            audio = np.concatenate(audio_frames)
            duration = len(audio) / sample_rate
            logger.debug(f"Piper audio: {duration:.2f}s at {sample_rate}Hz")

            sd.play(audio, samplerate=sample_rate, device=self.output_device)
            sd.wait()

        except Exception as e:
            logger.error(f"Piper TTS error: {e}")
            self._simulate_speech(text)

    def _simulate_speech(self, text: str) -> None:
        """
        Simulation mode: print text JARVIS would say.
        Simulates realistic speech delay.
        """
        words = len(text.split())
        speech_duration = words * 0.4  # ~150 wpm

        print(f"\n{'='*60}")
        print(f"  JARVIS : {text}")
        print(f"{'='*60}\n")

        time.sleep(min(speech_duration, 2.0))

    def stop(self) -> None:
        """Immediately interrupt active audio playback (Barge-in)."""
        self._stop_requested = True
        try:
            sd.stop()
            logger.info("[TTS] Playback stopped via barge-in interrupt.")
        except Exception as e:
            logger.error(f"[TTS] Error stopping audio: {e}")
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def is_simulation(self) -> bool:
        return self._simulation_mode
