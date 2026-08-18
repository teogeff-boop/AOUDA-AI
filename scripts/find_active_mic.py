"""
JARVIS AI — Find Active Mic & Test Audio Gain
================================================
Lists all input devices and monitors their input levels to find which one is the headset microphone.
"""

import time
import numpy as np
import sounddevice as sd

print("=" * 60)
print("  JARVIS AI — Headset Microphone Detector")
print("=" * 60)

devices = sd.query_devices()
input_devices = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]

print(f"Found {len(input_devices)} input device(s):\n")
for idx in input_devices:
    d = devices[idx]
    print(f"  [{idx}] {d['name']} (HostApi: {d['hostapi']})")

print("\nMonitoring sound level on default input device for 5 seconds...")
print("PLEASE SPEAK INTO YOUR HEADSET MICROPHONE NOW!\n")

def test_device(device_idx, name):
    peak = 0.0
    def callback(indata, frames, time_info, status):
        nonlocal peak
        val = np.abs(indata).max()
        if val > peak:
            peak = val
    try:
        with sd.InputStream(device=device_idx, samplerate=16000, channels=1, dtype='int16', callback=callback):
            time.sleep(3.0)
        print(f"Device [{device_idx}] {name[:35]:<35} -> Peak amplitude: {peak:.1f}")
        return peak
    except Exception as e:
        print(f"Device [{device_idx}] {name[:35]:<35} -> Error: {e}")
        return 0

for idx in [1, 2, 7, 8, 14, 15]:
    if idx < len(devices):
        test_device(idx, devices[idx]['name'])

print("\nDone testing candidates.")
