"""
JARVIS AI — Full Voice Pipeline Test
=======================================
Tests the complete voice chain: Mic → STT → Brain → TTS

Run this to verify everything works before launching main.py:
    .\\venv\\Scripts\\python.exe scripts\\test_voice_pipeline.py
"""

import os, sys, yaml
os.environ["VOSK_LOG_LEVEL"] = "-1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

with open("config.yaml") as f:
    config = yaml.safe_load(f)

print("=" * 60)
print("  JARVIS AI — Voice Pipeline Test")
print("=" * 60)

# ── 1. STT Test ───────────────────────────────────────────────────
from jarvis.stt.speech_to_text import SpeechToText

print("\n[1/3] STT — Speak a sentence (10s max)...")
print("      Say something like: 'what is my heart rate'")
print()

stt = SpeechToText(config)
result = stt.transcribe_stream(timeout=10.0)

if result:
    print(f"\n  >> Transcribed: '{result}'")
else:
    print("\n  [WARN] Nothing transcribed. Check microphone.")
    sys.exit(1)

# ── 2. Brain Test ─────────────────────────────────────────────────
from jarvis.brain.brain import Brain

print("\n[2/3] Brain — Processing command...")
brain = Brain(config)
response = brain.process(result)
print(f"  >> JARVIS response: '{response[:100]}...'")

# ── 3. TTS Test ───────────────────────────────────────────────────
from jarvis.tts.text_to_speech import TextToSpeech

print("\n[3/3] TTS — Speaking response...")
tts = TextToSpeech(config)
tts.speak(response)

print("\n" + "=" * 60)
print("  Pipeline test complete!")
print("  If all 3 steps worked, run: .\\venv\\Scripts\\python.exe main.py")
print("=" * 60)
