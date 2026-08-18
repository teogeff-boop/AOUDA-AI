"""
JARVIS AI — Module Audio Engine
================================
Capture le flux microphone et détecte le wake word.
Compatible Windows (dev) et Raspberry Pi (prod).
"""

import queue
import threading
import numpy as np
import sounddevice as sd
from loguru import logger
from typing import Optional, Callable


class AudioEngine:
    """
    Moteur d'acquisition audio.
    Capture le flux microphone en continu dans un buffer thread-safe.
    """

    def __init__(self, config: dict):
        audio_cfg = config.get("audio", {})
        self.sample_rate: int = audio_cfg.get("sample_rate", 16000)
        self.channels: int = audio_cfg.get("channels", 1)
        self.chunk_size: int = audio_cfg.get("chunk_size", 4000)
        self.input_device: Optional[int] = audio_cfg.get("input_device_index", None)

        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._running: bool = False

    def _audio_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """Callback appelé par sounddevice à chaque chunk audio capturé."""
        if status:
            logger.warning(f"Audio status: {status}")
        # Copie le chunk dans la queue (évite les références partagées)
        self._audio_queue.put(indata.copy())

    def start(self) -> None:
        """Démarre la capture microphone en arrière-plan."""
        if self._running:
            logger.warning("AudioEngine déjà en cours d'exécution.")
            return

        logger.info(
            f"Démarrage AudioEngine — "
            f"sample_rate={self.sample_rate}Hz, "
            f"channels={self.channels}, "
            f"device={self.input_device or 'défaut'}"
        )

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.chunk_size,
            device=self.input_device,
            dtype="int16",
            callback=self._audio_callback,
        )
        self._stream.start()
        self._running = True
        logger.success("🎙️  Microphone actif.")

    def stop(self) -> None:
        """Arrête proprement la capture microphone."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False
        logger.info("AudioEngine arrêté.")

    def read_chunk(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Lit le prochain chunk audio disponible.

        Args:
            timeout: Secondes d'attente max.

        Returns:
            np.ndarray de shape (chunk_size, channels) ou None si timeout.
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Vide le buffer audio (ex: après wake word détecté)."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def list_devices(self) -> None:
        """Affiche tous les périphériques audio disponibles (debug)."""
        logger.info("Périphériques audio disponibles :")
        print(sd.query_devices())

    @property
    def is_running(self) -> bool:
        return self._running
