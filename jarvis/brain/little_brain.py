"""
JARVIS AI — Little Brain (Reflex, Telemetry & Safety Engine)
===========================================================
Ultra-fast (<1ms) deterministic reflex engine.
Handles live suit telemetry readings, safety thresholds, emergencies,
and immediate mission commands (Bilingual FR/EN).
"""

from datetime import datetime
from loguru import logger
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.sensors.suit_data_manager import SuitDataManager


EMERGENCY_REPLY = (
    "ALERT. EMERGENCY PROTOCOL ACTIVATED. "
    "Contacting ground support team immediately. "
    "Stay calm. Remain at your current position."
)

STATUS_REPLY = (
    "All systems nominal. All functions operational. "
    "Ready to assist, astronaut."
)

IDENTITY_REPLY = (
    "I am AOUDA, version 0.3.0. "
    "Your offline Edge AI assistant for analog suit AMADEE-27."
)


class LittleBrain:
    """
    Reflex & Sensor Engine (Little Brain).
    Prioritizes astronaut safety, instant sensor telemetry, and reflex system status.
    Supports queries in both French and English.
    """

    def __init__(self, sensor_manager: Optional["SuitDataManager"] = None):
        self.sensors = sensor_manager

    def set_sensor_manager(self, sensor_manager: "SuitDataManager") -> None:
        self.sensors = sensor_manager

    def process(self, text: str) -> Optional[str]:
        """
        Process query through Little Brain.
        Returns response string if matched by reflex rules or telemetry, else None.
        """
        if not text or not text.strip():
            return None

        t = text.lower().strip()

        # 1. Emergency Check (Highest priority)
        if self._is_emergency(t):
            logger.warning(f"[LITTLE BRAIN] EMERGENCY DETECTED: '{t}'")
            return EMERGENCY_REPLY

        # 2. Live Suit Telemetry
        sensor_reply = self._check_sensors(t)
        if sensor_reply:
            return sensor_reply

        # 3. Reflex System Commands
        if any(kw in t for kw in ["status", "systems", "how are you", "all good", "nominal", "statut", "systèmes", "etat", "état"]):
            return STATUS_REPLY

        if any(kw in t for kw in ["identity", "who are you", "what are you", "version", "qui es tu", "qui es-tu", "identifie"]):
            return IDENTITY_REPLY

        if any(kw in t for kw in ["time", "clock", "date", "what time", "heure", "quelle heure"]):
            now = datetime.now()
            return f"Current time is {now.strftime('%H:%M')}. Date: {now.strftime('%B %d, %Y')}."

        return None

    def _check_sensors(self, text: str) -> Optional[str]:
        """Check live sensor telemetry with flexible natural language queries (FR & EN)."""
        if not self.sensors:
            return None

        data = self.sensors.get_all()
        if not data:
            return None

        # Heart Rate / Pulse / BPM
        if any(kw in text for kw in ["heart rate", "pulse", "cardiac", "bpm", "heartbeat", "heart", "pouls", "cardiaque", "coeur", "rythme cardiaque"]):
            hr = data.get("heart_rate")
            if hr:
                val = hr["value"]
                status = "NOMINAL" if 60 <= val <= 100 else "WARNING — out of safe range"
                return f"Heart rate: {val:.0f} beats per minute — {status}."

        # Oxygen / Air supply / O2
        if any(kw in text for kw in ["oxygen", "o2", "air supply", "air level", "breathing", "air left", "air", "oxygene", "oxygène", "air respirable"]):
            o2 = data.get("o2_percent")
            if o2:
                val = o2["value"]
                status = "NOMINAL" if val >= 19.5 else "CRITICAL — LOW OXYGEN"
                return f"Oxygen level: {val:.1f} percent — {status}."

        # CO2 / Carbon Dioxide
        if any(kw in text for kw in ["co2", "carbon", "carbon dioxide", "dioxyde de carbone"]):
            co2 = data.get("co2_ppm")
            if co2:
                val = co2["value"]
                status = "NOMINAL" if val < 5000 else "WARNING — elevated"
                return f"CO2 concentration: {val:.0f} parts per million — {status}."

        # Temperature / Thermal / DHT11
        if any(kw in text for kw in ["temperature", "thermal", "temp", "heat", "température", "chaleur", "temperature corporelle", "dht11"]):
            temp = data.get("body_temperature")
            hum = data.get("humidity_percent")
            if temp:
                val = temp["value"]
                status = "NORMAL" if val <= 38.0 else "ELEVATED"
                hum_str = f", Relative Humidity: {hum['value']:.1f}%" if hum else ""
                return f"Suit sensor temperature: {val:.1f}°C — {status}{hum_str}."

        # Humidity
        if any(kw in text for kw in ["humidity", "humidité", "hum"]):
            hum = data.get("humidity_percent")
            if hum:
                return f"Suit relative humidity: {hum['value']:.1f}%."

        # Suit Pressure
        if any(kw in text for kw in ["suit pressure", "pressure", "hpa", "pression", "pression combinaison"]):
            pres = data.get("suit_pressure_hpa")
            if pres:
                val = pres["value"]
                status = "NOMINAL" if 950 <= val <= 1050 else "WARNING — abnormal pressure"
                return f"Suit pressure: {val:.0f} hPa — {status}."

        # Battery / Power
        if any(kw in text for kw in ["battery", "power", "energy", "charge", "batterie", "energie", "énergie"]):
            bat = data.get("battery_percent")
            if bat:
                val = bat["value"]
                status = "OK" if val >= 20 else "LOW BATTERY"
                return f"Battery level: {val:.0f} percent — {status}."

        # GPS / Location / Coordinates
        if any(kw in text for kw in ["position", "gps", "location", "coordinates", "where am i", "ou suis-je", "où suis-je", "coordonnées", "localisation"]):
            gps = data.get("gps")
            if gps and isinstance(gps.get("value"), dict):
                lat = gps["value"].get("lat", 0.0)
                lon = gps["value"].get("lon", 0.0)
                return f"GPS position: latitude {lat:.4f}, longitude {lon:.4f}. Ground team has your position."

        return None

    def _is_emergency(self, text: str) -> bool:
        """Emergency detection with context awareness (FR & EN)."""
        hard_triggers = ["emergency", "mayday", "sos", "rescue", "distress", "medical", "urgence", "secours", "danger"]
        if any(kw in text for kw in hard_triggers):
            return True

        if "help" in text or "aide" in text or "aider" in text:
            context_words = ["need", "now", "immediately", "stuck", "trapped", "cannot", "can't", "problem", "hurt", "pain", "fall", "besoin", "bloqué", "mal", "chute"]
            return any(ctx in text for ctx in context_words)

        return False
