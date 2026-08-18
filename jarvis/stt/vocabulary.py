"""
JARVIS AI — Mission Vocabulary Builder
=======================================
Automatically builds a Vosk grammar from all mission knowledge sources:
  - Knowledge base documents (procedures, manuals, YAML)
  - Config (phonetic corrections, hotwords, mission keywords)
  - Hard-coded command vocabulary

When Vosk is constrained to this grammar, it ONLY looks for these exact words,
which makes it far more accurate for domain-specific terms like 'Caillou' or 'AOUDA',
even with a non-native accent.
"""

import re
import json
import yaml
from pathlib import Path
from typing import List, Set
from loguru import logger


# ── Base English command vocabulary ──────────────────────────────────────────

QUESTION_WORDS = [
    "what", "how", "where", "when", "which", "who", "why",
    "is", "are", "was", "the", "my", "your", "our",
    "do", "did", "can", "could", "should", "would",
    "give", "tell", "show", "get", "read",
    "and", "or", "to", "for", "of", "in", "at", "on",
    "with", "please", "now",
]

STEP_NUMBER_WORDS = [
    "step", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
    "step one", "step two", "step three", "step four",
    "step five", "step six", "step seven", "step eight",
    "step nine", "step ten", "step eleven", "step twelve",
]

NAVIGATION_WORDS = [
    "next", "previous", "repeat", "again", "back", "go back",
    "before", "after", "following", "redo", "return",
    "start", "begin", "restart", "stop", "done", "complete", "ready",
    "first", "last", "current",
]

EMERGENCY_WORDS = [
    "emergency", "mayday", "help", "sos", "rescue", "medical",
    "alert", "danger", "abort", "critical",
]

SENSOR_WORDS = [
    "oxygen", "heart", "rate", "battery", "carbon", "dioxide",
    "gps", "location", "temperature", "pressure", "power",
    "vitals", "status", "level", "percent", "reading",
    "sensor", "telemetry", "monitor",
]

GENERAL_COMMANDS = [
    "yes", "no", "okay", "roger", "copy", "affirmative",
    "negative", "confirm", "check", "verify", "activate",
    "deactivate", "enable", "disable", "open", "close",
    "start", "stop", "pause", "resume",
]

# All base vocabulary combined
BASE_VOCABULARY: List[str] = (
    QUESTION_WORDS + STEP_NUMBER_WORDS + NAVIGATION_WORDS
    + EMERGENCY_WORDS + SENSOR_WORDS + GENERAL_COMMANDS
)


# ── Vocabulary builder ────────────────────────────────────────────────────────

def build_mission_grammar(knowledge_dir: str, config: dict) -> str:
    """
    Build a Vosk grammar JSON string from all mission vocabulary sources.

    Returns a JSON array of words/phrases that Vosk will restrict recognition to.
    Including '[unk]' allows Vosk to handle silence/noise without crashing.
    """
    vocabulary: Set[str] = set(w.lower() for w in BASE_VOCABULARY)

    # ── 1. Config: phonetic correction targets (e.g. "caillou") ──────────────
    stt_cfg = config.get("stt", {})
    for corrected in stt_cfg.get("phonetic_corrections", {}).values():
        vocabulary.add(corrected.lower().strip())

    # ── 2. Config: whisper hotwords ───────────────────────────────────────────
    for word in stt_cfg.get("whisper_hotwords", []):
        vocabulary.add(word.lower().strip())

    # ── 3. Mission metadata from config ──────────────────────────────────────
    jarvis_cfg = config.get("jarvis", {})
    for field in ("name", "mission"):
        val = jarvis_cfg.get(field, "")
        if val:
            for w in val.lower().split():
                vocabulary.add(w)

    # Wake word + variants
    ww = config.get("wakeword", {}).get("keyword", "aouda")
    vocabulary.update([ww, ww[:4], ww + "a"])

    # Emergency keywords
    for word in config.get("mission", {}).get("emergency_keywords", []):
        vocabulary.add(word.lower())

    # ── 4. Knowledge base: all meaningful words from .md / .yaml / .txt ──────
    kb_path = Path(knowledge_dir)
    files_scanned = 0
    if kb_path.exists():
        for fp in (
            list(kb_path.glob("*.md"))
            + list(kb_path.glob("*.txt"))
            + list(kb_path.glob("*.yaml"))
            + list(kb_path.glob("*.yml"))
        ):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    raw = f.read()
                # Extract all alphabetic words ≥ 3 chars (avoid YAML keys/numbers)
                words = re.findall(r"\b[a-zA-Z]{3,}\b", raw)
                for w in words:
                    vocabulary.add(w.lower())
                files_scanned += 1
            except Exception as e:
                logger.warning(f"[VOCAB] Could not read {fp.name}: {e}")

    # ── 5. Clean up: remove single chars and pure symbols ────────────────────
    vocabulary = {w for w in vocabulary if len(w) >= 2 and w.isascii()}

    # '[unk]' tells Vosk to output something for unrecognized sounds
    vocab_list = sorted(vocabulary) + ["[unk]"]

    logger.success(
        f"[VOCAB] Mission grammar built: {len(vocab_list)} words "
        f"(from {files_scanned} KB files + config)"
    )
    return json.dumps(vocab_list)


def build_wakeword_grammar(config: dict) -> str:
    """
    Minimal grammar for wake word detection only.
    Tightly constrained to prevent false positives.
    """
    keyword = config.get("wakeword", {}).get("keyword", "aouda").lower()

    # Include the exact keyword + phonetically close variants
    variants = {
        keyword,
        keyword[:4],      # "aouda" → "aoud"
        keyword + "a",    # "aoudaa"
    }

    # Add custom variants from config if provided
    for v in config.get("wakeword", {}).get("phonetic_variants", []):
        variants.add(v.lower())

    wake_list = sorted(variants) + ["[unk]"]
    logger.debug(f"[VOCAB] Wake word grammar: {wake_list}")
    return json.dumps(wake_list)
