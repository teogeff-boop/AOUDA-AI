"""
JARVIS AI — Unit Tests for Advanced Intelligence Modules
========================================================
Tests for Local RAG, Predictive Analytics, VAD, and Mission State.
"""

import pytest
from pathlib import Path
from jarvis.brain.local_rag import LocalRAG
from jarvis.sensors.predictive_analytics import PredictiveAnalytics
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.brain.mission_state import MissionStateManager
import numpy as np


def test_local_rag_search():
    rag = LocalRAG(knowledge_dir="data/knowledge_base/")
    res = rag.search_relevant_chunks("Caillou laser targeting", top_k=1)
    assert len(res) > 0
    score, doc = res[0]
    assert score > 0.0
    assert "caillou" in doc["text"].lower() or "laser" in doc["text"].lower()


def test_predictive_analytics_o2_drop():
    from datetime import datetime, timedelta
    pred = PredictiveAnalytics(window_minutes=5.0, alert_cooldown_seconds=0.0)
    now = datetime.now()

    # Push 10 readings spanning over 5 minutes (from 5 mins ago to now)
    for i in range(10):
        t = now - timedelta(minutes=5 - (i * 0.5))
        val = 20.9 - (i * 0.1)  # Drops 0.9% over 5 mins
        pred.history["o2_percent"].append((t, val))

    alert = pred.analyze()
    assert alert is not None
    assert "Oxygen" in alert or "AOUDA" in alert


def test_vad_speech_detection():
    vad = VoiceActivityDetector(energy_threshold=500.0)
    # Silent audio chunk (zeros)
    silent_chunk = np.zeros(1600, dtype=np.int16)
    assert not vad.is_speech(silent_chunk)

    # Active audio chunk (high energy)
    speech_chunk = (np.sin(np.linspace(0, 100, 1600)) * 10000).astype(np.int16)
    assert vad.is_speech(speech_chunk)


def test_mission_state_and_report_generation(tmp_path):
    state_file = tmp_path / "mission_state.json"
    report_dir = tmp_path / "mission_reports"
    manager = MissionStateManager(state_file=str(state_file), report_dir=str(report_dir))

    manager.set_active_payload("Caillou")
    manager.record_step_completed("Caillou Spectrometer", 4, "Laser Alignment")
    
    assert manager.state["active_payload"] == "Caillou"
    assert len(manager.state["completed_steps"]) == 1

    report_file = manager.generate_mission_report()
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "AMADEE-27" in content
    assert "Caillou Spectrometer" in content
