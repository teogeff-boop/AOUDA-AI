"""
AOUDA AI — Wake Word Accent Debugger
======================================
Prints EXACTLY what Vosk transcribes when you pronounce "AOUDA" in your microphone.

Run this script and say "AOUDA" (or "AH-OU-DA" / "OW-DA") multiple times.
We will see the exact English words Vosk outputs for your voice and accent!

Usage:
    .\\venv\\Scripts\\python.exe scripts\\debug_aouda_wakeword.py
"""

import os
import json
import queue
import time
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

os.environ["VOSK_LOG_LEVEL"] = "-1"

print("=" * 65)
print("  AOUDA AI — Wake Word Accent Diagnostic")
print("=" * 65)
print("\nLoading Vosk STT model...")

model_path = "models/vosk/vosk-model-small-en-us-0.15"
model = Model(model_path)
rec = KaldiRecognizer(model, 16000)

q = queue.Queue()

def callback(indata, frames, time_info, status):
    arr = np.frombuffer(indata, dtype=np.int16).astype(np.float32)
    peak = np.abs(arr).max()
    if peak > 100.0:  # Noise gate
        target_peak = 16000.0
        gain = min(target_peak / (peak + 1e-5), 10.0)
        arr = np.clip(arr * gain, -32768, 32767).astype(np.int16)
        q.put(arr.tobytes())

print("\n>>> SPEAK NOW: Say 'AOUDA' or 'AH-OU-DA' or 'OW-DA' into your mic! <<<")
print("Press Ctrl+C when done.\n")

try:
    with sd.RawInputStream(samplerate=16000, blocksize=4000, channels=1, dtype="int16", callback=callback):
        while True:
            try:
                data = q.get(timeout=0.5)
            except queue.Empty:
                continue

            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "").strip()
                if text:
                    print(f"  [HEARD PHRASE] -> \"{text}\"")
            else:
                part = json.loads(rec.PartialResult())
                partial = part.get("partial", "").strip()
                if partial:
                    print(f"  [partial]        -> \"{partial}\"")

except KeyboardInterrupt:
    print("\nDiagnostic complete!")
