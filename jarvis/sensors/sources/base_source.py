"""
JARVIS AI — Abstract Sensor Data Source
=========================================
Base class defining the interface all sensor sources must implement.
Swap between Simulated / CSV / Network by changing config.yaml.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


# ── Sensor Reading Type ────────────────────────────────────────────────────────
# Each reading is a dict: {"value": <any>, "unit": str, "age_s": float, "ok": bool}
SensorReading = Dict[str, Any]
SensorData    = Dict[str, SensorReading]


class SuitDataSource(ABC):
    """
    Abstract interface for Aouda suit sensor data sources.

    Implementations:
      - SimulatedSource   : realistic random data (dev/testing)
      - AoudaCSVSource    : reads live or replayed CSV logs from Aouda
      - AoudaNetworkSource: connects to Aouda telemetry server (Wi-Fi)
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the data source.
        Returns True if successful, False otherwise.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up and close the data source connection."""
        ...

    @abstractmethod
    def read(self) -> SensorData:
        """
        Read the latest available sensor values.

        Returns:
            Dict mapping sensor name to SensorReading.
            Example:
            {
                "heart_rate":   {"value": 78.0, "unit": "bpm", "age_s": 0.2, "ok": True},
                "o2_percent":   {"value": 20.9, "unit": "%",   "age_s": 0.2, "ok": True},
                "co2_ppm":      {"value": 420,  "unit": "ppm", "age_s": 0.2, "ok": True},
                "suit_pressure_hpa": {"value": 1013, "unit": "hPa", "age_s": 0.2, "ok": True},
                "body_temperature":  {"value": 37.1, "unit": "°C",  "age_s": 0.2, "ok": True},
                "battery_percent":   {"value": 85.0, "unit": "%",   "age_s": 0.2, "ok": True},
                "humidity_percent":  {"value": 55.0, "unit": "%",   "age_s": 0.2, "ok": True},
                "gps": {
                    "value": {"lat": 47.5012, "lon": 14.1234, "alt": 1200.0},
                    "unit": "deg/m", "age_s": 1.0, "ok": True
                },
            }
        """
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if the source is currently connected and providing data."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source (for logging)."""
        ...

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def make_reading(
        value: Any,
        unit: str,
        age_s: float = 0.0,
        ok: bool = True,
    ) -> SensorReading:
        """Factory method to create a standardized SensorReading dict."""
        return {"value": value, "unit": unit, "age_s": age_s, "ok": ok}
