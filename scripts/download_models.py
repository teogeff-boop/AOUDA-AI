"""
JARVIS AI — Model Downloader
==============================
Downloads all required offline AI models for JARVIS.

Models downloaded:
  - Vosk STT : vosk-model-small-en-us-0.15   (~40 MB, fast, Pi-compatible)
  - Piper TTS: en_US-lessac-medium.onnx       (~63 MB, natural English voice)

Usage:
    python scripts/download_models.py

No admin rights required.
All models are placed in the models/ directory.
"""

import os
import sys
import zipfile
import urllib.request
from pathlib import Path

# ── Model URLs ─────────────────────────────────────────────────────────────────
MODELS = {
    "vosk_en": {
        "name":   "Vosk English STT (small)",
        "url":    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "dest":   "models/vosk/",
        "folder": "vosk-model-small-en-us-0.15",
        "size":   "~40 MB",
    },
    "piper_en_onnx": {
        "name":   "Piper English TTS — lessac voice (model)",
        "url":    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "dest":   "models/piper/",
        "file":   "en_US-lessac-medium.onnx",
        "size":   "~63 MB",
    },
    "piper_en_json": {
        "name":   "Piper English TTS — lessac voice (config)",
        "url":    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "dest":   "models/piper/",
        "file":   "en_US-lessac-medium.onnx.json",
        "size":   "~2 KB",
    },
}


def progress_bar(downloaded: int, total: int, width: int = 40) -> str:
    """Simple ASCII progress bar."""
    if total <= 0:
        return f"  {downloaded // 1024} KB downloaded"
    pct = downloaded / total
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    return f"  [{bar}] {pct*100:.1f}% ({downloaded//1024}KB / {total//1024}KB)"


def download_file(url: str, dest_path: Path, label: str) -> bool:
    """Download a file with a progress display."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.exists():
        print(f"  [OK] Already exists: {dest_path}")
        return True

    print(f"\n  Downloading {label}...")
    print(f"  URL: {url}")
    print(f"  Destination: {dest_path}")

    try:
        downloaded = 0
        last_print = 0

        def reporthook(block_num, block_size, total_size):
            nonlocal downloaded, last_print
            downloaded = block_num * block_size
            if downloaded - last_print > 1_000_000 or downloaded >= total_size:
                print(f"\r{progress_bar(downloaded, total_size)}", end="", flush=True)
                last_print = downloaded

        urllib.request.urlretrieve(url, dest_path, reporthook)
        print()  # newline after progress bar
        print(f"  [OK] Downloaded: {dest_path}")
        return True

    except Exception as e:
        print(f"\n  [ERROR] Failed to download {label}: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def extract_zip(zip_path: Path, dest_dir: Path, expected_folder: str) -> bool:
    """Extract a ZIP file if target folder doesn't exist."""
    target = dest_dir / expected_folder
    if target.exists():
        print(f"  [OK] Already extracted: {target}")
        return True

    print(f"  Extracting {zip_path.name}...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        print(f"  [OK] Extracted to: {target}")
        return True
    except Exception as e:
        print(f"  [ERROR] Extraction failed: {e}")
        return False


def check_existing_models() -> None:
    """Check which models are already present."""
    print("\n=== Current Model Status ===")
    checks = [
        ("Vosk EN STT",    Path("models/vosk/vosk-model-small-en-us-0.15")),
        ("Piper EN .onnx", Path("models/piper/en_US-lessac-medium.onnx")),
        ("Piper EN .json", Path("models/piper/en_US-lessac-medium.onnx.json")),
    ]
    for name, path in checks:
        status = "[OK]" if path.exists() else "[MISSING]"
        print(f"  {status} {name}: {path}")
    print()


def main():
    print("=" * 60)
    print("  JARVIS AI — Model Downloader")
    print("  Mission AMADEE-26 (OeWF)")
    print("=" * 60)

    # Change to project root (script may be run from anywhere)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    print(f"\n  Working directory: {project_root}")

    check_existing_models()

    total_size_mb = sum([40, 63, 0])
    print(f"  Total download: ~{total_size_mb} MB")
    print("  Note: Models are saved locally and only downloaded once.\n")

    success_count = 0

    # ── 1. Vosk STT Model ────────────────────────────────────────────────────
    print("\n[1/3] Vosk English STT Model")
    m = MODELS["vosk_en"]
    zip_path = Path(m["dest"]) / (m["folder"] + ".zip")
    target   = Path(m["dest"]) / m["folder"]

    if target.exists():
        print(f"  [OK] Already present: {target}")
        success_count += 1
    else:
        if download_file(m["url"], zip_path, m["name"]):
            if extract_zip(zip_path, Path(m["dest"]), m["folder"]):
                zip_path.unlink()  # Remove ZIP after extraction
                success_count += 1

    # ── 2. Piper TTS .onnx ───────────────────────────────────────────────────
    print("\n[2/3] Piper English TTS Voice (.onnx model)")
    m = MODELS["piper_en_onnx"]
    dest = Path(m["dest"]) / m["file"]
    if download_file(m["url"], dest, m["name"]):
        success_count += 1

    # ── 3. Piper TTS .json ───────────────────────────────────────────────────
    print("\n[3/3] Piper English TTS Voice (.json config)")
    m = MODELS["piper_en_json"]
    dest = Path(m["dest"]) / m["file"]
    if download_file(m["url"], dest, m["name"]):
        success_count += 1

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if success_count == 3:
        print("  SUCCESS: All models ready!")
        print("  You can now run: .\\venv\\Scripts\\python.exe main.py")
    else:
        print(f"  WARNING: {3 - success_count} model(s) failed to download.")
        print("  Check your internet connection and try again.")
    print("=" * 60)

    # Install Vosk and Piper
    print("\n  Installing Python packages (vosk, piper-tts)...")
    os.system(f'"{sys.executable}" -m pip install vosk piper-tts --quiet')
    print("  [OK] Packages installed.")


if __name__ == "__main__":
    main()
