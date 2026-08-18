"""
AOUDA AI — Wake Word Detector (faster-whisper)
===============================================
Strategy:
  1. Collect audio in a rolling 1.5s buffer.
  2. Gate on energy: only process audio when peak > ENERGY_THRESHOLD.
  3. Run faster-whisper transcription on the buffer with initial_prompt="AOUDA.".
  4. Match: "aouda" (or phonetic variants) in transcript.
"""

import queue
import time
import numpy as np
import sounddevice as sd
from loguru import logger
from pathlib import Path
from typing import Optional

SAMPLE_RATE      = 16000
BUFFER_SECONDS   = 1.5
BUFFER_SAMPLES   = int(SAMPLE_RATE * BUFFER_SECONDS)
ENERGY_THRESHOLD = 5000
WAKE_WORDS       = {"aouda", "awada", "auda", "houda", "howda"}


class WakeWordDetector:
    """
    Detects the wake word "AOUDA" using faster-whisper for robust, accent-tolerant recognition.
    """

    def __init__(self, config: dict):
        self.enabled        = config["wakeword"]["enabled"]
        self.keyword        = config["wakeword"]["keyword"].lower()
        self._input_device  = config["audio"]["input_device_index"]
        self._simulation_mode = False
        self._model         = None

        ww_cfg  = config.get("wakeword", {})
        stt_cfg = config.get("stt", {})
        model_size = ww_cfg.get("whisper_model_size",
                     stt_cfg.get("whisper_model_size", "base"))
        self._language = stt_cfg.get("whisper_language", "en")

        if self.enabled:
            self._load_model(model_size)

    def _load_model(self, model_size: str) -> None:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"[WAKE] Loading faster-whisper '{model_size}' for wake word detection...")
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.success(f"[WAKE] Wake word detector ready — whisper '{model_size}'.")
        except Exception as e:
            logger.warning(f"[WAKE] faster-whisper not available: {e} — falling back to keyboard simulation.")
            self._simulation_mode = True

    def wait_for_wakeword(self, command_check_callback=None) -> bool:
        """Block until 'AOUDA' is confidently detected OR a ground control command is received."""
        if self._simulation_mode or self._model is None:
            return self._wait_keyboard()

        logger.info("[WAKE] Listening for wake word — say 'AOUDA'...")

        audio_queue: queue.Queue = queue.Queue()
        rolling: list[np.ndarray] = []

        def callback(indata, frames, time_info, status):
            audio_queue.put(indata.copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=int(SAMPLE_RATE * 0.25),
            channels=1,
            dtype="int16",
            device=self._input_device,
            callback=callback,
        ):
            while True:
                # Check ground control buttons while waiting for wake word!
                if command_check_callback and command_check_callback():
                    return False

                try:
                    chunk = audio_queue.get(timeout=0.2)
                    rolling.append(chunk.flatten())
                except queue.Empty:
                    continue

                total = sum(len(c) for c in rolling)
                while total > BUFFER_SAMPLES and rolling:
                    removed = rolling.pop(0)
                    total -= len(removed)

                if total < BUFFER_SAMPLES:
                    continue

                buf = np.concatenate(rolling)
                peak = int(np.abs(buf).max())
                if peak < ENERGY_THRESHOLD:
                    continue

                word = self._transcribe(buf)
                if word:
                    logger.debug(f"[WAKE] Heard: '{word}'")
                    if self._is_wake_word(word):
                        logger.success(f"[WAKE] AOUDA detected! ('{word}', peak={peak})")
                        return True

    def _transcribe(self, audio_int16: np.ndarray) -> Optional[str]:
        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        try:
            segments, _ = self._model.transcribe(
                audio_f32,
                language=self._language,
                beam_size=3,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
                initial_prompt="AOUDA.",
            )
            text = " ".join(s.text.strip() for s in segments).strip().lower()
            return text if text else None
        except Exception as e:
            logger.debug(f"[WAKE] Transcription error: {e}")
            return None

    def _is_wake_word(self, text: str) -> bool:
        import re
        words = set(re.findall(r"\b[a-z]+\b", text.lower()))
        if words & WAKE_WORDS:
            return True
        return False

    def _wait_keyboard(self) -> bool:
        print("\n" + "=" * 60)
        print("  [SIM MODE] Press ENTER to activate AOUDA")
        print("=" * 60)
        input()
        logger.success("[SIM] Wake word simulated via Enter key.")
        return True

    @property
    def is_simulation(self) -> bool:
        return self._simulation_mode
