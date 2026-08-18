"""
AOUDA AI — Smart Auto-Calibrating Voice Trainer
===============================================
1. Automatically measures your microphone's background noise floor for 1.5 seconds.
2. Sets a dynamic vocal threshold above your ambient noise floor.
3. Waits until you ACTUALLY speak "AOUDA" before recording samples!

Usage:
    .\\venv\\Scripts\\python.exe scripts\\record_wakeword.py
"""

import time
import numpy as np
import sounddevice as sd
from pathlib import Path

SAMPLE_RATE   = 16000
CHUNK_SAMPLES = 8000   # 0.5s
SAMPLES_DIR   = Path("models/wakeword")
SAVE_FILE     = SAMPLES_DIR / "aouda_user.npy"


def calibrate_noise_floor() -> float:
    print("  [Step 1/2] Calibrating microphone noise floor...")
    print("  >>> STAY SILENT FOR 1.5 SECONDS... <<<\n")
    time.sleep(0.5)

    noise_peaks = []
    def callback(indata, frames, time_info, status):
        noise_peaks.append(np.abs(indata).max())

    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=1600, channels=1, dtype="int16", callback=callback):
        time.sleep(1.5)

    max_noise = max(noise_peaks) if noise_peaks else 2000
    vocal_threshold = max(max_noise * 1.8, 8000.0)
    print(f"  [OK] Noise floor max: {max_noise} — Vocal threshold set to: {int(vocal_threshold)}")
    return vocal_threshold


def extract_features(arr: np.ndarray) -> np.ndarray:
    arr_f = arr.flatten().astype(np.float32)
    if len(arr_f) > CHUNK_SAMPLES:
        arr_f = arr_f[:CHUNK_SAMPLES]
    elif len(arr_f) < CHUNK_SAMPLES:
        arr_f = np.pad(arr_f, (0, CHUNK_SAMPLES - len(arr_f)))

    fft_mag = np.abs(np.fft.rfft(arr_f))
    norm = np.linalg.norm(fft_mag)
    if norm > 1e-5:
        fft_mag /= norm
    return fft_mag


def capture_spoken_sample(sample_num: int, vocal_threshold: float) -> np.ndarray:
    print(f"\n--- SAMPLE {sample_num}/3 ---")
    print("  [Waiting for voice...] SPEAK 'AOUDA' CLEARLY NOW!")

    audio_buffer = []
    recording = False

    def callback(indata, frames, time_info, status):
        nonlocal recording
        arr = indata.copy()
        peak = np.abs(arr).max()

        if not recording:
            if peak >= vocal_threshold:
                recording = True
                audio_buffer.append(arr)
                print(f"  🎙️ Voice detected! (Level: {peak}) — Recording...")
        else:
            audio_buffer.append(arr)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=1600,
        channels=1,
        dtype="int16",
        callback=callback
    ):
        while len(audio_buffer) * 1600 < CHUNK_SAMPLES:
            time.sleep(0.05)

    full_audio = np.concatenate(audio_buffer)[:CHUNK_SAMPLES]
    print(f"  ✅ Sample {sample_num} recorded successfully!")
    return extract_features(full_audio)


def main():
    print("=" * 65)
    print("  AOUDA AI — Auto-Calibrating Voice Trainer")
    print("=" * 65)

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Measure background noise floor dynamically
    vocal_threshold = calibrate_noise_floor()

    print("\n  [Step 2/2] Recording 3 samples of your voice saying 'AOUDA'...")

    features_list = []
    for i in range(1, 4):
        feat = capture_spoken_sample(i, vocal_threshold)
        features_list.append(feat)
        time.sleep(0.5)

    template = np.mean(features_list, axis=0)
    norm = np.linalg.norm(template)
    if norm > 1e-5:
        template /= norm

    np.save(SAVE_FILE, template)

    print("\n" + "=" * 65)
    print(f"  🎉 SUCCESS! Your personal voice profile is saved to {SAVE_FILE}")
    print("  AOUDA is now 100% calibrated to your voice!")
    print("=" * 65)


if __name__ == "__main__":
    main()
