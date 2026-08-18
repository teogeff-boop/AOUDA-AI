"""
Unit tests for JARVIS Dual-Brain (Little Brain + Big Brain) and Sensor modules.
100% Deterministic — Zero LLM required — Zero Hallucination.
"""

import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jarvis.brain.brain import Brain
from jarvis.brain.little_brain import LittleBrain
from jarvis.brain.big_brain import BigBrain
from jarvis.sensors.suit_data_manager import SuitDataManager
from jarvis.sensors.sources.simulated_source import SimulatedSource


# ── Configs ───────────────────────────────────────────────────────────────────

BRAIN_CONFIG = {
    "brain": {
        "mode": "dual_brain",
        "knowledge_base_path": "data/knowledge_base/",
        "fallback_response": "Command not recognized. Please repeat after JARVIS.",
        "mission_responses_path": "jarvis/brain/mission_responses.yaml",
    },
    "mission": {
        "astronaut_name": "Astronaut-01",
        "emergency_keywords": ["emergency", "help", "sos", "mayday", "rescue"],
        "log_all_interactions": False,
    },
}

SENSOR_CONFIG = {
    "sensors": {
        "mode": "simulated",
        "update_interval_s": 0.1,
        "alerts": {
            "heart_rate_min": 50,
            "heart_rate_max": 150,
            "co2_max_ppm": 5000,
            "o2_min_percent": 19.5,
            "pressure_min_hpa": 950,
            "battery_min_percent": 20,
            "temperature_max_c": 38.5,
        },
    }
}

FULL_CONFIG = {**BRAIN_CONFIG, **SENSOR_CONFIG}


# ── Brain Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def brain():
    return Brain(BRAIN_CONFIG)


@pytest.fixture
def big_brain():
    return BigBrain(knowledge_dir="data/knowledge_base/")


@pytest.fixture
def little_brain():
    return LittleBrain()


# ── Basic & Unit Tests ────────────────────────────────────────────────────────

class TestBrainBasic:
    def test_brain_initializes(self, brain):
        assert brain is not None

    def test_empty_input_returns_fallback(self, brain):
        assert brain.process("") == BRAIN_CONFIG["brain"]["fallback_response"]

    def test_none_input_returns_fallback(self, brain):
        assert brain.process(None) == BRAIN_CONFIG["brain"]["fallback_response"]


class TestLittleBrainReflex:
    def test_status_query(self, brain):
        r = brain.process("what is your status")
        assert "nominal" in r.lower() or "operational" in r.lower()

    def test_time_query(self, brain):
        r = brain.process("what time is it")
        assert "time" in r.lower() or "date" in r.lower()

    def test_identify_query(self, brain):
        r = brain.process("who are you identify yourself")
        assert "aouda" in r.lower() or "version" in r.lower()


class TestLittleBrainEmergency:
    def test_emergency_keyword(self, brain):
        r = brain.process("emergency I need assistance")
        assert "alert" in r.lower() or "ground" in r.lower()

    def test_mayday_keyword(self, brain):
        r = brain.process("mayday mayday")
        assert "alert" in r.lower() or "emergency" in r.lower()

    def test_sos_keyword(self, brain):
        r = brain.process("SOS send help")
        assert "alert" in r.lower() or "ground" in r.lower()

    def test_help_with_context_is_emergency(self, brain):
        r = brain.process("help I cannot move I am stuck")
        assert "alert" in r.lower() or "ground" in r.lower() or "protocol" in r.lower()

    def test_medical_keyword(self, brain):
        r = brain.process("I feel pain medical issue")
        assert "medical" in r.lower() or "alert" in r.lower() or "ground" in r.lower()


class TestBigBrainKnowledge:
    def test_eva_checklist_query(self, big_brain):
        r = big_brain.query("give me the EVA checklist")
        assert r is not None
        assert "step 1" in r.lower() or "verify suit pressure" in r.lower()

    def test_geology_code_query(self, big_brain):
        r = big_brain.query("what is regolith rock code")
        assert r is not None
        assert "reg-01" in r.lower() or "regolith" in r.lower()

    def test_suit_manual_battery_limit(self, big_brain):
        r = big_brain.query("suit battery capacity limit")
        assert r is not None
        assert "450" in r or "battery" in r.lower()

    def test_crew_manifest_query(self, big_brain):
        r = big_brain.query("who is the commander")
        assert r is not None
        assert "commander" in r.lower() or "astronaut-01" in r.lower()

    def test_caillou_preparation_query(self, big_brain):
        r = big_brain.query("how to charge Caillou battery")
        assert r is not None
        assert "usb-c" in r.lower() or "2 hours" in r.lower() or "battery" in r.lower()

    def test_caillou_laser_targeting_query(self, big_brain):
        r = big_brain.query("how to align laser dot on sample")
        assert r is not None
        assert "laser" in r.lower() or "target" in r.lower()

    def test_caillou_measurement_query(self, big_brain):
        r = big_brain.query("how to perform spectrometer measurement")
        assert r is not None
        assert "skirt" in r.lower() or "ground" in r.lower() or "measurement" in r.lower()


class TestBrainFallback:
    def test_unknown_command_returns_strict_fallback(self, brain):
        r = brain.process("xkcd zorg blorb")
        assert "not recognized" in r.lower() or "xkcd" in r


class TestOperationalRules:
    def test_rule1_step_ambiguity(self, big_brain):
        r = big_brain.query("What is step 4?")
        assert "multiple" in r.lower() or "which procedure" in r.lower()

    def test_rule1_explicit_step_no_ambiguity(self, big_brain):
        r = big_brain.query("Caillou step 4")
        assert "pre-eva" in r.lower() or "support box" in r.lower()

    def test_rule2_subsection_jump(self, big_brain):
        r = big_brain.query("I need help with laser targeting")
        assert "step 4" in r.lower() and "laser" in r.lower()

    def test_rule3_concise_formatting(self, big_brain):
        r = big_brain.query("What is step 5?")
        assert "duration" in r.lower()
        assert "say 'next'" not in r.lower()

    def test_rule4_decision_point_yes_no(self, big_brain):
        q = big_brain.query("Caillou step 10")
        assert "decision point" in q.lower() or "additional measurements" in q.lower()
        # Answer YES
        yes_reply = big_brain.query("YES")
        assert "step 4" in yes_reply.lower() and "targeting" in yes_reply.lower()


# ── Sensor Tests ──────────────────────────────────────────────────────────────

@pytest.fixture
def sim_source():
    cfg = SENSOR_CONFIG
    src = SimulatedSource(cfg)
    src.connect()
    yield src
    src.disconnect()


@pytest.fixture
def sensor_manager():
    mgr = SuitDataManager(FULL_CONFIG)
    mgr.start()
    time.sleep(0.3)  # Allow first poll to complete
    yield mgr
    mgr.stop()


class TestSimulatedSource:
    def test_connects(self, sim_source):
        assert sim_source.is_connected

    def test_read_returns_data(self, sim_source):
        data = sim_source.read()
        assert len(data) > 0

    def test_all_sensors_present(self, sim_source):
        data = sim_source.read()
        expected = ["heart_rate", "o2_percent", "co2_ppm", "suit_pressure_hpa",
                    "body_temperature", "battery_percent", "humidity_percent", "gps"]
        for sensor in expected:
            assert sensor in data, f"Missing sensor: {sensor}"

    def test_heart_rate_reasonable(self, sim_source):
        data = sim_source.read()
        hr = data["heart_rate"]["value"]
        assert 40 <= hr <= 200, f"Unrealistic heart rate: {hr}"

    def test_o2_reasonable(self, sim_source):
        data = sim_source.read()
        o2 = data["o2_percent"]["value"]
        assert 15.0 <= o2 <= 25.0, f"Unrealistic O2: {o2}"

    def test_gps_has_lat_lon_alt(self, sim_source):
        data = sim_source.read()
        gps = data["gps"]["value"]
        assert "lat" in gps and "lon" in gps and "alt" in gps


class TestSuitDataManager:
    def test_manager_starts(self, sensor_manager):
        assert sensor_manager.is_running

    def test_get_all_returns_data(self, sensor_manager):
        data = sensor_manager.get_all()
        assert len(data) > 0

    def test_get_specific_sensor(self, sensor_manager):
        hr = sensor_manager.get("heart_rate")
        assert hr is not None
        assert "value" in hr

    def test_get_summary_text(self, sensor_manager):
        summary = sensor_manager.get_summary_text()
        assert "HR" in summary or "O2" in summary


# ── Dual-Brain + Sensor Integration Tests ─────────────────────────────────────

class TestBrainWithSensors:
    def test_dynamic_heart_rate_response(self, sensor_manager):
        b = Brain(BRAIN_CONFIG, sensor_manager=sensor_manager)
        r = b.process("what is my heart rate")
        assert "heart rate" in r.lower() or "bpm" in r.lower()
        assert any(char.isdigit() for char in r)

    def test_natural_phrasing_oxygen_query(self, sensor_manager):
        b = Brain(BRAIN_CONFIG, sensor_manager=sensor_manager)
        r = b.process("how much air do I have left")
        assert "oxygen" in r.lower() or "percent" in r.lower() or any(char.isdigit() for char in r)

    def test_natural_phrasing_battery_query(self, sensor_manager):
        b = Brain(BRAIN_CONFIG, sensor_manager=sensor_manager)
        r = b.process("how much power is remaining in the suit")
        assert "battery" in r.lower() or "percent" in r.lower() or any(char.isdigit() for char in r)

    def test_gps_location_query(self, sensor_manager):
        b = Brain(BRAIN_CONFIG, sensor_manager=sensor_manager)
        r = b.process("where am I GPS coordinates")
        assert "latitude" in r.lower() or "gps" in r.lower()
