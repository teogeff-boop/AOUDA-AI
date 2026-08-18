"""
JARVIS AI — Simulated Suit Sensor Source
==========================================
Generates realistic, dynamic sensor data for development and testing.

Features:
  - Realistic physiological variations (heart rate fluctuates naturally)
  - Configurable alert injection for emergency protocol testing
  - No hardware required — 100% software simulation
"""

import math
import random
import time
from loguru import logger
from jarvis.sensors.sources.base_source import SuitDataSource, SensorData


class SimulatedSource(SuitDataSource):
    """
    Simulated Aouda suit sensor data source.
    Generates realistic values with natural variation over time.
    Useful for development (Windows) and system testing.
    """

    def __init__(self, config: dict):
        self._connected: bool = False
        self._start_time: float = 0.0

        # Simulation state — base values with natural drift
        self._state = {
            "heart_rate_base":    75.0,   # bpm
            "o2_base":            20.9,   # %
            "co2_base":           420.0,  # ppm
            "pressure_base":      1013.0, # hPa
            "body_temp_base":     37.0,   # °C
            "battery_base":       85.0,   # % (decreases over time)
            "humidity_base":      55.0,   # %
            "gps_lat":            47.5012,
            "gps_lon":            14.1234,
            "gps_alt":            1200.0, # m
        }

        # Alert injection for testing
        self._inject_alert: str = "none"  # "none"|"low_o2"|"high_co2"|"high_hr"|"low_battery"

        logger.success("SimulatedSource initialized — realistic sensor simulation active.")

    def connect(self) -> bool:
        self._connected = True
        self._start_time = time.time()
        logger.info("[SENSORS] Simulated source connected.")
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("[SENSORS] Simulated source disconnected.")

    def read(self) -> SensorData:
        """Generate one snapshot of all sensor readings with natural variation."""
        if not self._connected:
            return {}

        t = time.time() - self._start_time  # seconds since start
        now_age = 0.0  # data is always "fresh" in simulation

        # ── Heart Rate ─────────────────────────────────────────────────────────
        # Natural sinusoidal variation ±8 bpm over ~2 minute cycles
        hr = (
            self._state["heart_rate_base"]
            + 8 * math.sin(t / 120.0 * 2 * math.pi)
            + random.gauss(0, 1.5)
        )
        if self._inject_alert == "high_hr":
            hr = 165.0 + random.gauss(0, 3)

        # ── Oxygen ─────────────────────────────────────────────────────────────
        o2 = self._state["o2_base"] + random.gauss(0, 0.1)
        if self._inject_alert == "low_o2":
            o2 = 18.0 + random.gauss(0, 0.2)

        # ── CO2 ────────────────────────────────────────────────────────────────
        # Slight rise with physical activity simulation
        co2 = (
            self._state["co2_base"]
            + 50 * math.sin(t / 300.0 * 2 * math.pi)
            + random.gauss(0, 10)
        )
        if self._inject_alert == "high_co2":
            co2 = 6500.0 + random.gauss(0, 100)

        # ── Suit Pressure ──────────────────────────────────────────────────────
        pressure = self._state["pressure_base"] + random.gauss(0, 0.5)

        # ── Body Temperature ───────────────────────────────────────────────────
        # Slight rise over time simulating physical exertion
        body_temp = (
            self._state["body_temp_base"]
            + min(t / 3600.0 * 0.8, 1.2)  # Max +1.2°C after 1h of EVA
            + random.gauss(0, 0.05)
        )

        # ── Battery ────────────────────────────────────────────────────────────
        # Drains ~1% every 3 minutes
        battery = max(
            0.0,
            self._state["battery_base"] - (t / 180.0)
            + random.gauss(0, 0.1)
        )
        if self._inject_alert == "low_battery":
            battery = 12.0 + random.gauss(0, 0.5)

        # ── Humidity ───────────────────────────────────────────────────────────
        humidity = self._state["humidity_base"] + random.gauss(0, 1.0)

        # ── GPS ────────────────────────────────────────────────────────────────
        # Simulate slow movement (~1 m/s walk)
        gps_lat = self._state["gps_lat"] + (t * 0.000001)  # ~0.1m per tick
        gps_lon = self._state["gps_lon"] + (t * 0.0000005)
        gps_alt = self._state["gps_alt"] + random.gauss(0, 0.5)

        return {
            "heart_rate":        self.make_reading(round(hr, 1),       "bpm",  now_age, 50 <= hr <= 150),
            "o2_percent":        self.make_reading(round(o2, 2),        "%",    now_age, o2 >= 19.5),
            "co2_ppm":           self.make_reading(round(co2, 0),       "ppm",  now_age, co2 < 5000),
            "suit_pressure_hpa": self.make_reading(round(pressure, 1),  "hPa",  now_age, 950 <= pressure <= 1050),
            "body_temperature":  self.make_reading(round(body_temp, 2), "C",    now_age, body_temp <= 38.5),
            "battery_percent":   self.make_reading(round(battery, 1),   "%",    now_age, battery >= 20),
            "humidity_percent":  self.make_reading(round(humidity, 1),  "%",    now_age, True),
            "gps": self.make_reading(
                {"lat": round(gps_lat, 6), "lon": round(gps_lon, 6), "alt": round(gps_alt, 1)},
                "deg/m", now_age, True
            ),
        }

    def inject_alert(self, alert_type: str) -> None:
        """
        Inject a simulated alert for testing emergency protocols.

        Args:
            alert_type: "none" | "low_o2" | "high_co2" | "high_hr" | "low_battery"
        """
        valid = ["none", "low_o2", "high_co2", "high_hr", "low_battery"]
        if alert_type in valid:
            self._inject_alert = alert_type
            logger.warning(f"[SIMULATION] Alert injected: {alert_type}")
        else:
            logger.error(f"Unknown alert type: {alert_type}. Valid: {valid}")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def source_name(self) -> str:
        return "SimulatedSource"
