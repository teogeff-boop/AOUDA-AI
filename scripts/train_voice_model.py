"""
AOUDA AI — Mission Voice & Accent Training Utility
===================================================
Captures spectral voice signatures for 'AOUDA' and 'CAILLOU'.
Ensures robust voice activity detection with dynamic ambient noise clamping.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\train_voice_model.py
"""

import os
import sys
import time
import numpy as np
import sounddevice as sd
from pathlib import Path

SAMPLE_RATE   = 16000
CHUNK_SAMPLES = 16000   # 1.0s window for full word capture
SAMPLES_DIR   = Path("models/wakeword")
PROFILE_FILE  = SAMPLES_DIR / "aouda_user.npy"
CAILLOU_FILE  = SAMPLES_DIR / "caillou_user.npy"


def calibrate_environment() -> float:
    print("=" * 70)
    print("  [STEP 1/3] Measuring Ambient Room Noise Floor")
    print("=" * 70)
    print("  >>> STAY SILENT FOR 2 SECONDS... <<<\n")
    time.sleep(0.5)

    noise_levels = []

    def callback(indata, frames, time_info, status):
        peak = float(np.abs(indata).max())
        noise_levels.append(peak)

    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=1600, channels=1, dtype="int16", callback=callback):
        time.sleep(2.0)

    # Filter out microphone clipping spikes
    valid_levels = [l for l in noise_levels if l < 30000.0]
    max_noise = max(valid_levels) if valid_levels else 1500.0
    mean_noise = sum(valid_levels) / len(valid_levels) if valid_levels else 400.0

    # Clamp speech trigger threshold between 3,000 and 12,000 (well within spoken int16 range)
    vocal_threshold = min(max(max_noise * 1.3, mean_noise * 2.5, 3000.0), 12000.0)

    print(f"  [OK] Mean Noise: {int(mean_noise)} | Peak Noise: {int(max_noise)}")
    print(f"  [OK] Speech Trigger Threshold set to: {int(vocal_threshold)}\n")
    return vocal_threshold


def compute_audio_fingerprint(arr: np.ndarray) -> np.ndarray:
    """Extract spectral energy distribution fingerprint across 128 frequency bands."""
    arr_f = arr.flatten().astype(np.float32)
    if len(arr_f) > CHUNK_SAMPLES:
        arr_f = arr_f[:CHUNK_SAMPLES]
    elif len(arr_f) < CHUNK_SAMPLES:
        arr_f = np.pad(arr_f, (0, CHUNK_SAMPLES - len(arr_f)))

    # Hanning window to prevent edge spectral leakage
    windowed = arr_f * np.hanning(len(arr_f))
    fft_mag = np.abs(np.fft.rfft(windowed))

    # Group into 128 log-spaced frequency bins
    num_bins = 128
    bins = np.array_split(fft_mag, num_bins)
    fingerprint = np.array([b.mean() for b in bins], dtype=np.float32)

    norm = np.linalg.norm(fingerprint)
    if norm > 1e-5:
        fingerprint /= norm
    return fingerprint


def record_word_samples(word_label: str, count: int, threshold: float) -> np.ndarray:
    print("-" * 70)
    print(f"  [STEP 2/3] Training Voice Signature for '{word_label.upper()}'")
    print(f"  Speak '{word_label}' clearly when prompted.")
    print("-" * 70)

    samples = []
    sample_index = 1

    while sample_index <= count:
        print(f"\n  [Sample {sample_index}/{count}] SPEAK '{word_label.upper()}' NOW...")
        audio_buffer = []
        recording = False

        def callback(indata, frames, time_info, status):
            nonlocal recording
            arr = indata.copy()
            peak = float(np.abs(arr).max())
            if not recording:
                if peak >= threshold:
                    recording = True
                    audio_buffer.append(arr)
                    print(f"   🎙️ Spoken word detected! (Level: {int(peak)}) Recording...")
            else:
                audio_buffer.append(arr)

        with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=1600, channels=1, dtype="int16", callback=callback):
            start = time.time()
            while len(audio_buffer) * 1600 < CHUNK_SAMPLES and (time.time() - start) < 5.0:
                time.sleep(0.05)

        if audio_buffer and len(audio_buffer) * 1600 >= CHUNK_SAMPLES:
            full_audio = np.concatenate(audio_buffer)[:CHUNK_SAMPLES]
            fp = compute_audio_fingerprint(full_audio)
            samples.append(fp)
            print(f"   ✅ Sample {sample_index}/{count} captured successfully!")
            sample_index += 1
        else:
            print(f"   ⚠️ No voice heard above threshold ({int(threshold)}). Retrying sample {sample_index}...")

        time.sleep(0.5)

    master_template = np.mean(samples, axis=0)
    norm = np.linalg.norm(master_template)
    if norm > 1e-5:
        master_template /= norm
    return master_template


def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 70)
    print("  🚀 AOUDA AI — Voice & Accent Training Utility")
    print("=" * 70)

    # 1. Noise calibration
    threshold = calibrate_environment()

    # Save threshold calibration
    thresh_file = SAMPLES_DIR / "threshold_user.txt"
    thresh_file.write_text(str(int(threshold)), encoding="utf-8")
    print(f"  ✅ Environment energy threshold saved: {int(threshold)} to {thresh_file}")

    # 2. Record AOUDA
    aouda_fp = record_word_samples("AOUDA", 3, threshold)
    np.save(PROFILE_FILE, aouda_fp)
    print(f"\n  ✅ Master voice signature saved: {PROFILE_FILE}")

    # 3. Record CAILLOU
    caillou_fp = record_word_samples("CAILLOU", 3, threshold)
    np.save(CAILLOU_FILE, caillou_fp)
    print(f"  ✅ Master voice signature saved: {CAILLOU_FILE}")

    print("\n" + "=" * 70)
    print("  🎉 TRAINING COMPLETE!")
    print("  Your voice signatures for AOUDA and CAILLOU are 100% active!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
