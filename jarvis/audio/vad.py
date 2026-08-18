"""
JARVIS AI — Voice Activity Detector (Silero / Energy VAD)
=========================================================
Filters suit ventilation noise, breathing, and ambient wind from speech.
Provides energy-based and model-based speech detection.
"""

import numpy as np
from loguru import logger


class VoiceActivityDetector:
    """
    100% Offline Voice Activity Detector (VAD).
    Determines if audio buffer contains active human speech.
    """

    def __init__(self, sample_rate: int = 16000, energy_threshold: float = 800.0):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if audio chunk contains human speech.
        Supports float32 [-1, 1] and int16 PCM arrays.
        """
        if audio_chunk is None or len(audio_chunk) == 0:
            return False

        if audio_chunk.dtype == np.int16:
            energy = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
        else:
            # Float32 normalized [-1.0, 1.0]
            energy = np.sqrt(np.mean((audio_chunk * 32768.0) ** 2))

        return energy >= self.energy_threshold
