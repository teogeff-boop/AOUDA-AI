"""
AOUDA AI — Microphone & Speech Diagnostics Tool
================================================
Run this tool to record 3 seconds from your microphone and test exact Whisper & Vosk transcriptions.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\debug_microphone.py
"""

import sys
import time
import numpy as np
import sounddevice as sd
from loguru import logger

SAMPLE_RATE = 16000

print("=" * 70)
print("  🎙️ AOUDA AI — MICROPHONE & SPEECH DIAGNOSTICS")
print("=" * 70)

# 1. List audio devices
devices = sd.query_devices()
default_in = sd.default.device[0]
print(f"Default Input Device Index: {default_in} — {devices[default_in]['name']}")

# 2. Record 3 seconds
print("\n  >>> SAY 'AOUDA' OR ANY COMMAND NOW (RECORDING FOR 3 SECONDS)... <<<\n")
time.sleep(0.5)

audio_data = []

def callback(indata, frames, time_info, status):
    audio_data.append(indata.copy())

with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
    for i in range(30):
        time.sleep(0.1)
        sys.stdout.write(".")
        sys.stdout.flush()

print("\n\n  ✅ Recording complete!")

full_audio = np.concatenate(audio_data).flatten()
peak = int(np.abs(full_audio).max())
rms = int(np.sqrt(np.mean(full_audio.astype(np.float64)**2)))

print(f"  📊 Audio Peak Level: {peak} (Max: 32767)")
print(f"  📊 Audio RMS Volume: {rms}")

if peak < 500:
    print("\n  ⚠️ WARNING: Microphone input volume is extremely low! Please check your Windows mic volume setting or mic switch.")

# 3. Transcribe with Whisper
print("\n  🧠 Testing Whisper 'large-v3-turbo' Transcription...")
try:
    from faster_whisper import WhisperModel
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    audio_f32 = full_audio.astype(np.float32) / 32768.0

    segments, info = model.transcribe(
        audio_f32,
        language=None,   # Auto-detect language (French or English)
        beam_size=5,
        initial_prompt="AOUDA, Caillou, AMADEE, status.",
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    print(f"  📝 Whisper Result: '{text}' (Language detected: {info.language}, prob={info.language_probability:.2f})")
except Exception as e:
    print(f"  ❌ Whisper error: {e}")

# 4. Transcribe with Vosk
print("\n  🧠 Testing Vosk Transcription...")
try:
    import json
    from vosk import Model, KaldiRecognizer
    vmodel = Model("models/vosk/vosk-model-small-en-us-0.15")
    rec = KaldiRecognizer(vmodel, SAMPLE_RATE)
    rec.AcceptWaveform(bytes(full_audio))
    vres = json.loads(rec.FinalResult())
    print(f"  📝 Vosk Result: '{vres.get('text', '')}'")
except Exception as e:
    print(f"  ❌ Vosk error: {e}")

print("\n" + "=" * 70)
