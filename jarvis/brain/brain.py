"""
JARVIS AI — Dual Brain Decision Engine (Little Brain + Big Brain)
=================================================================
100% Deterministic Dual-Brain Architecture:
  1. Little Brain (Reflex & Telemetry Engine):
     Handles instant (<1ms) safety checks, emergency protocols, and live suit telemetry.
  2. Big Brain (Mission Memory Engine):
     Retrieves verified facts from structured knowledge files (EVA procedures, suit manuals,
     geology codes, crew manifest) with ZERO hallucination.
"""

import re
from pathlib import Path
from loguru import logger
from typing import Optional, TYPE_CHECKING

from jarvis.brain.little_brain import LittleBrain
from jarvis.brain.big_brain import BigBrain
from jarvis.brain.local_rag import LocalRAG

if TYPE_CHECKING:
    from jarvis.sensors.suit_data_manager import SuitDataManager


class Brain:
    """
    JARVIS Decision Engine — Dual-Brain Architecture.
    Combines Little Brain (reflex & telemetry), Big Brain (mission memory),
    and Local RAG (zero-hallucination document fallback).
    """

    def __init__(self, config: dict, sensor_manager=None):
        self.config = config
        brain_cfg = config.get("brain", {})
        
        self.fallback: str = brain_cfg.get(
            "fallback_response",
            "Command not recognized. Please repeat after JARVIS."
        )
        self.astronaut_name: str = config.get("mission", {}).get("astronaut_name", "Astronaut-01")
        self.emergency_keywords: list = config.get("mission", {}).get("emergency_keywords", ["emergency", "help", "sos"])
        self.mode: str = brain_cfg.get("mode", "dual_brain")

        # Initialize Little Brain (Reflex & Telemetry)
        self.little_brain = LittleBrain(sensor_manager=sensor_manager)

        # Initialize Big Brain (Mission Memory & Procedures)
        kb_dir = brain_cfg.get("knowledge_base_path", "data/knowledge_base/")
        self.big_brain = BigBrain(knowledge_dir=kb_dir)

        # Initialize Local RAG Engine (Zero-Hallucination Fallback)
        self.local_rag = LocalRAG(knowledge_dir=kb_dir)

        logger.success(f"[BRAIN] Dual-Brain + Local RAG Engine initialized — Mode: {self.mode.upper()} — 100% Deterministic & Fact-Driven")

    def set_sensor_manager(self, sensor_manager) -> None:
        """Update sensor manager reference for Little Brain."""
        self.little_brain.set_sensor_manager(sensor_manager)

    @property
    def is_session_active(self) -> bool:
        """Returns True if an interactive procedure or guided conversation is active."""
        return self.big_brain.has_active_session

    def get_active_session_info(self) -> dict:
        """Returns dict of active procedure title, step number, and text."""
        return self.big_brain.get_active_session_info()

    def _normalize_query_text(self, text: str) -> str:
        """
        Normalize STT transcription text (SAFE text-only cleaning):
        - Converts written number words to digits ("step four" -> "step 4", "étape 3" -> "step 3")
        - Strips leading conversational filler words ("euh", "humm", "listen", "please")
        - Keeps audio pipeline & wake word detector 100% untouched and safe!
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Remove leading filler words
        fillers = [r"^(euh|humm|hum|listen|please|could\s+you|can\s+you|dis\s+moi|s'il\s+te\s+plaît)\s+"]
        for pat in fillers:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

        # Normalize number words to digits
        num_map = {
            r"\bstep\s+one\b": "step 1",
            r"\bstep\s+two\b": "step 2",
            r"\bstep\s+three\b": "step 3",
            r"\bstep\s+four\b": "step 4",
            r"\bstep\s+five\b": "step 5",
            r"\bstep\s+six\b": "step 6",
            r"\bstep\s+seven\b": "step 7",
            r"\bstep\s+eight\b": "step 8",
            r"\bstep\s+nine\b": "step 9",
            r"\bétape\s+un\b": "step 1",
            r"\bétape\s+deux\b": "step 2",
            r"\bétape\s+trois\b": "step 3",
            r"\bétape\s+quatre\b": "step 4",
            r"\bétape\s+cinq\b": "step 5",
        }
        for pat, repl in num_map.items():
            cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)

        return cleaned

    def process(self, text: str) -> str:
        """
        Process user query through Dual Brain:
          1. Little Brain (Reflex, Emergency, Live Telemetry)
          2. Big Brain (Mission Memory, Manuals, Procedures)
          3. Deterministic Fallback if not found in memory/sensors
        """
        if not text or not text.strip():
            return self.fallback

        raw_text = text.strip()
        query_text = self._normalize_query_text(raw_text)
        logger.debug(f"[BRAIN] Processing query: '{query_text}' (raw: '{raw_text}')")

        # --- Phase 1: Little Brain (Reflex & Telemetry) ---
        little_reply = self.little_brain.process(query_text)
        if little_reply:
            logger.info(f"[LITTLE BRAIN] Matched: '{little_reply[:80]}...'")
            if any(k in query_text.lower() for k in self.emergency_keywords):
                self.big_brain.reset_session()
            return little_reply

        # --- Phase 2: Big Brain (Mission Memory & Procedures) ---
        big_reply = self.big_brain.query(query_text)
        if big_reply:
            logger.info(f"[BIG BRAIN] Matched: '{big_reply[:80]}...'")
            return big_reply

        # --- Phase 3: Local RAG (Grounded Document Fallback) ---
        rag_reply = self.local_rag.query(query_text)
        if rag_reply:
            logger.info(f"[LOCAL RAG] Matched: '{rag_reply[:80]}...'")
            return rag_reply

        # --- Phase 4: Smart Clarification Fallback ---
        logger.info(f"[BRAIN] No match in Little/Big Brain/RAG for: '{query_text}'")

        proc_names = [
            doc.replace("_procedure", "").replace("_", " ").title()
            for doc in self.big_brain.procedure_navigators
        ]
        if proc_names:
            options = ", ".join(proc_names)
            return (
                f"Command not recognized. Which equipment or procedure are you working with? "
                f"Available: {options}. Or ask about suit telemetry, EVA checklist, or system status."
            )
        return self.fallback
