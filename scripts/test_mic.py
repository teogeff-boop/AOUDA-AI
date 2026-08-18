"""
JARVIS AI — Mic Level Test
============================
Tests that the microphone is capturing audio and shows a live level meter.
Run this BEFORE starting JARVIS to verify your microphone works.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\test_mic.py
"""

import sys
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION_S  = 8   # Seconds to test

print("=" * 60)
print("  JARVIS AI — Microphone Level Test")
print("=" * 60)
print()

# Show all devices
print("Available input devices:")
devices = sd.query_devices()
for i, d in enumerate(devices):
    if d["max_input_channels"] > 0:
        marker = ">>> " if i == sd.default.device[0] else "    "
        print(f"  {marker}[{i}] {d['name']}")

print()
print(f"Default input: [{sd.default.device[0]}] {sd.query_devices(kind='input')['name']}")
print()
print(f"Recording for {DURATION_S} seconds — SPEAK INTO YOUR MICROPHONE NOW...")
print()

# Capture audio in chunks and show level meter
peak_levels = []

def audio_callback(indata, frames, time_info, status):
    volume = np.sqrt(np.mean(indata**2)) * 100
    peak_levels.append(volume)
    bar_len = int(volume * 2)
    bar = "#" * min(bar_len, 50)
    spaces = " " * (50 - len(bar))
    level_str = f"  Level: [{bar}{spaces}] {volume:.1f}"
    if volume > 5:
        level_str += "  << SIGNAL DETECTED"
    print(f"\r{level_str}", end="", flush=True)

with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16",
    callback=audio_callback,
    blocksize=1600,
):
    time.sleep(DURATION_S)

print("\n")
max_level = max(peak_levels) if peak_levels else 0
avg_level = sum(peak_levels) / len(peak_levels) if peak_levels else 0

print("=" * 60)
print(f"  Peak level : {max_level:.1f}")
print(f"  Avg level  : {avg_level:.1f}")

if max_level < 1.0:
    print()
    print("  [WARNING] No signal detected!")
    print("  Check that your microphone is:")
    print("    1. Plugged in and selected in Windows Sound settings")
    print("    2. Not muted in Windows mixer")
    print("    3. Permissions granted (Settings > Privacy > Microphone)")
    print()
    print("  Try a different device index in config.yaml:")
    print("    audio:")
    print("      input_device_index: 1  # or 2, 7, 8, 14, 15...")
elif max_level < 5.0:
    print()
    print("  [OK] Weak signal — try speaking louder or moving mic closer.")
    print("  Vosk should still work at this level.")
else:
    print()
    print("  [OK] Good signal! Microphone is working correctly.")
    print("  Vosk STT should transcribe your speech accurately.")

print("=" * 60)
