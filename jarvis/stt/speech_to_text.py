"""
JARVIS AI — STT Module (Speech-to-Text)
========================================
Two engines supported:
  1. faster-whisper (DEFAULT) — Best for accents, technical terms, multilingual words.
     Runs 100% offline. Models: tiny, base, small, medium.
  2. vosk (FALLBACK) — Lightweight, lower accuracy, English-only small model.

faster-whisper handles:
  - French accents speaking English
  - Technical/proper nouns (e.g. "Caillou", "Aouda", "AMADEE")
  - Any word spoken imprecisely
"""

import os
import re
import json
import queue
import time
import numpy as np
import sounddevice as sd
from loguru import logger
from pathlib import Path
from typing import Optional
from jarvis.stt.vocabulary import build_mission_grammar


os.environ.setdefault("VOSK_LOG_LEVEL", "-1")

SAMPLE_RATE = 16000
CHUNK_SIZE  = 4000   # 0.25s chunks


class SpeechToText:
    """
    STT engine with automatic engine selection.
    Tries faster-whisper first (best accent & word accuracy), falls back to Vosk, then keyboard.
    """

    def __init__(self, config: dict):
        self.model_path:      str   = config["stt"]["model_path"]
        self.sample_rate:     int   = config["stt"]["sample_rate"]
        self.silence_timeout: float = config["stt"]["silence_timeout_s"]
        self._input_device: Optional[int] = config["audio"]["input_device_index"]

        stt_cfg = config.get("stt", {})
        self._engine_name: str = stt_cfg.get("engine", "vosk")
        self._whisper_model_size: str = stt_cfg.get("whisper_model_size", "tiny")
        self._whisper_language: str = stt_cfg.get("whisper_language", "en")

        # Phonetic corrections: {"cargo": "caillou", ...} — applied to any engine output
        raw_corrections: dict = stt_cfg.get("phonetic_corrections", {})
        self._corrections: dict = {k.lower().strip(): v.strip()
                                   for k, v in raw_corrections.items()}

        # Build initial_prompt from mission hotwords (whisper only)
        hotwords: list = stt_cfg.get("whisper_hotwords", [])
        self._whisper_prompt: str = ("Mission vocabulary: " + ", ".join(hotwords) + "."
                                     if hotwords else "")

        # Build Vosk constrained grammar for domain terms (Caillou, Aouda, etc.)
        kb_dir: str = config.get("brain", {}).get("knowledge_base_path", "data/knowledge_base/")
        self._grammar_json: str = build_mission_grammar(kb_dir, config)

        self._whisper_model = None
        self._vosk_model    = None
        self._simulation_mode: bool = False
        self._active_engine: str = "none"

        self._load_engine()

    def _load_engine(self) -> None:
        """Load preferred STT engine with fallback chain: whisper → vosk → keyboard."""

        # --- Try faster-whisper ---
        if self._engine_name in ("whisper", "faster_whisper", "auto"):
            try:
                from faster_whisper import WhisperModel
                logger.info(f"[STT] Loading faster-whisper model '{self._whisper_model_size}' (downloading if needed)...")
                self._whisper_model = WhisperModel(
                    self._whisper_model_size,
                    device="cpu",
                    compute_type="int8",
                )
                self._active_engine = "whisper"
                logger.success(f"[STT] OpenAI-Whisper '{self._whisper_model_size}' ready (Sub-second response).")
                return
            except Exception as e:
                logger.warning(f"[STT] faster-whisper not available: {e} — trying Vosk fallback.")

        # --- Try Vosk ---
        try:
            from vosk import Model
            if not Path(self.model_path).exists():
                raise FileNotFoundError(f"Vosk model not found: {self.model_path}")
            logger.info(f"[STT] Loading Vosk model: {self.model_path}")
            self._vosk_model = Model(self.model_path)
            self._active_engine = "vosk"
            logger.success("[STT] Vosk model loaded (limited accent support).")
            return
        except Exception as e:
            logger.warning(f"[STT] Vosk not available: {e} — using keyboard simulation.")

        # --- Keyboard simulation ---
        self._simulation_mode = True
        self._active_engine = "keyboard"

    def transcribe_stream(self, audio_engine=None, timeout: float = 10.0, command_check_callback=None) -> Optional[str]:
        """Listen from microphone, transcribe, and apply phonetic corrections."""
        if self._simulation_mode:
            return self._apply_corrections(self._simulate_input() or "")

        if self._active_engine == "whisper":
            raw = self._listen_and_transcribe_whisper(timeout, command_check_callback)
        elif self._active_engine == "vosk":
            raw = self._listen_and_transcribe_vosk(timeout)
        else:
            raw = self._simulate_input()

        return self._apply_corrections(raw) if raw else None

    def _apply_corrections(self, text: str) -> str:
        """
        Apply phonetic corrections (word & multi-word phrases, ignoring punctuation & case).
        E.g. 'cargo?', 'call you', 'can you' → 'caillou'.
        """
        if not text:
            return text

        result = text

        # 1. Multi-word phrase replacements (Whisper mishearings for Caillou)
        phrases = {
            "call you": "caillou",
            "can you": "caillou",
            "guy you": "caillou",
            "cow you": "caillou",
        }
        for phrase, target in phrases.items():
            pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
            result = pattern.sub(target, result)

        # 2. Single word dictionary replacements (stripping punctuation)
        if self._corrections:
            def replace_word(m):
                w = m.group(0)
                return self._corrections.get(w.lower(), w)

            result = re.sub(r"\b[a-zA-Z]+\b", replace_word, result)

        # 3. Filter out Whisper YouTube / video hallucinations on quiet ambient noise
        clean_check = result.lower().strip().rstrip(".!?")
        hallucinations = {
            "see you in the next video", "thanks for watching", "subscribe to my channel",
            "subtitles by", "thank you for watching", "see you next time", "bye", "you"
        }
        if clean_check in hallucinations:
            logger.info(f"[STT] Filtered Whisper ambient hallucination: '{result}'")
            return ""

        if result != text:
            logger.info(f"[STT] Phonetic fix: '{text}' → '{result}'")
        return result



    # ── faster-whisper recording loop ─────────────────────────────────────────

    def _listen_and_transcribe_whisper(self, timeout: float, command_check_callback=None) -> Optional[str]:
        """
        Record audio with a proper 3-state machine:
          WAITING  → look for speech above SPEECH_THRESHOLD
          SPEAKING → speech detected, keep recording
          SILENCE  → below SILENCE_THRESHOLD, count silent frames → stop

        Two separate thresholds prevent background noise (fans, ambient) from
        keeping the system in WAITING or resetting the silence counter.
        """
        SPEECH_THRESHOLD = 1500   # Balanced threshold for speech capture
        SILENCE_THRESHOLD = 500   # Below this = silence
        SILENCE_FRAMES_NEEDED = int(self.silence_timeout * 10)  # at 0.1s per check

        logger.info("[STT/Whisper] Listening... (speak now)")

        audio_chunks: list = []
        state = "WAITING"   # WAITING → SPEAKING → SILENCE → done
        silence_count = 0
        start_time = time.time()

        def callback(indata, frames, time_info, status):
            chunk = np.frombuffer(indata, dtype=np.int16).copy()
            audio_chunks.append(chunk)

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=CHUNK_SIZE,
                channels=1,
                dtype="int16",
                device=self._input_device,
                callback=callback,
            ):
                while True:
                    time.sleep(0.1)

                    if command_check_callback and command_check_callback():
                        logger.info("[STT/Whisper] Interrupted by Ground Control command.")
                        return None

                    if time.time() - start_time > timeout:
                        if state == "WAITING":
                            logger.info("[STT/Whisper] No speech detected within timeout.")
                            return None
                        # If we heard something, process what we have
                        logger.debug("[STT/Whisper] Timeout reached — processing captured audio.")
                        break

                    if not audio_chunks:
                        continue

                    peak = int(np.abs(audio_chunks[-1]).max())

                    if state == "WAITING":
                        if peak >= SPEECH_THRESHOLD:
                            state = "SPEAKING"
                            silence_count = 0
                            logger.debug(f"[STT/Whisper] Speech detected (peak={peak})")

                    elif state == "SPEAKING":
                        if peak < SILENCE_THRESHOLD:
                            state = "SILENCE"
                            silence_count = 1
                        # else: still speaking, keep recording

                    elif state == "SILENCE":
                        if peak >= SPEECH_THRESHOLD:
                            # Speech resumed
                            state = "SPEAKING"
                            silence_count = 0
                        else:
                            silence_count += 1
                            if silence_count >= SILENCE_FRAMES_NEEDED:
                                logger.debug(f"[STT/Whisper] Silence confirmed ({self.silence_timeout}s) — done.")
                                break

        except Exception as e:
            logger.error(f"[STT/Whisper] Recording error: {e}")
            return None

        if not audio_chunks or state == "WAITING":
            return None

        audio_np = np.concatenate(audio_chunks).astype(np.float32) / 32768.0

        try:
            segments, info = self._whisper_model.transcribe(
                audio_np,
                language=self._whisper_language,
                beam_size=5,
                initial_prompt=self._whisper_prompt or None,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            text = " ".join(seg.text.strip() for seg in segments).strip()

            if text:
                logger.success(f"[STT/Whisper] Transcribed: '{text}'")
                return text
            else:
                logger.info("[STT/Whisper] Empty transcription.")
                return None

        except Exception as e:
            logger.error(f"[STT/Whisper] Transcription error: {e}")
            return None

    # ── Vosk recording loop (fallback) ────────────────────────────────────────

    def _listen_and_transcribe_vosk(self, timeout: float) -> Optional[str]:
        """Core Vosk recording loop (grammar-constrained for max accuracy & speed)."""
        from vosk import KaldiRecognizer

        if self._grammar_json:
            recognizer = KaldiRecognizer(self._vosk_model, self.sample_rate, self._grammar_json)
        else:
            recognizer = KaldiRecognizer(self._vosk_model, self.sample_rate)

        recognizer.SetWords(False)
        audio_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            arr = np.frombuffer(indata, dtype=np.int16)
            if np.abs(arr).max() > 150:
                audio_queue.put(bytes(indata))

        logger.info("[STT/Vosk] Listening...")

        full_text = ""
        last_speech_time = time.time()
        start_time = time.time()
        heard_something = False

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=CHUNK_SIZE,
            channels=1,
            dtype="int16",
            device=self._input_device,
            callback=callback,
        ):
            while True:
                if time.time() - start_time > timeout:
                    break
                if heard_something and time.time() - last_speech_time >= self.silence_timeout:
                    break
                try:
                    audio_data = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(audio_data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        full_text += (" " if full_text else "") + text
                        last_speech_time = time.time()
                        heard_something = True
                else:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                    if partial:
                        last_speech_time = time.time()
                        heard_something = True

        try:
            remaining = json.loads(recognizer.FinalResult()).get("text", "").strip()
            if remaining:
                full_text += (" " if full_text else "") + remaining
        except Exception:
            pass

        full_text = full_text.strip()
        if full_text:
            logger.success(f"[STT/Vosk] Transcribed: '{full_text}'")
        return full_text if full_text else None

    def _simulate_input(self) -> Optional[str]:
        """Keyboard fallback mode."""
        logger.info("[SIM MODE] Type your command and press ENTER:")
        try:
            text = input(">>> ").strip()
            if text:
                return text
        except EOFError:
            pass
        return None

    @property
    def is_simulation(self) -> bool:
        return self._simulation_mode

    @property
    def active_engine(self) -> str:
        return self._active_engine
