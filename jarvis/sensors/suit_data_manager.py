"""
JARVIS AI — Suit Data Manager
================================
Central aggregator for all Aouda suit sensor data.

Runs a background thread that polls the configured data source at
a fixed interval and maintains the latest reading for each sensor.
The Brain queries this manager to build dynamic responses.

Usage:
    manager = SuitDataManager(config)
    manager.start()

    # In Brain:
    data = manager.get_all()
    hr   = manager.get("heart_rate")
    alerts = manager.get_active_alerts()
"""

import time
import threading
from loguru import logger
from typing import Optional, Dict, List

from jarvis.sensors.sources.base_source import SuitDataSource, SensorData, SensorReading
from jarvis.sensors.predictive_analytics import PredictiveAnalytics


class SuitDataManager:
    """
    Central sensor data hub for the Aouda suit.
    Polls the configured source in a background thread.
    Thread-safe reads via lock.
    """

    def __init__(self, config: dict, alert_tts_callback=None):
        self._config = config
        self._alert_tts_callback = alert_tts_callback
        sensor_cfg = config.get("sensors", {})
        self._update_interval: float = sensor_cfg.get("update_interval_s", 0.1)
        self._alert_thresholds: dict = sensor_cfg.get("alerts", {})

        self.predictive = PredictiveAnalytics()
        self._source: Optional[SuitDataSource] = None
        self._latest_data: SensorData = {}
        self._last_voice_warning_time: Dict[str, float] = {}
        self._lock = threading.RLock()

        self._thread: Optional[threading.Thread] = None
        self._running: bool = False

        # Load the configured source
        self._source = self._load_source(sensor_cfg.get("mode", "simulated"))

    def _load_source(self, mode: str) -> Optional[SuitDataSource]:
        """Instantiate the correct data source based on config mode."""
        mode = mode.lower()

        if mode == "simulated":
            from jarvis.sensors.sources.simulated_source import SimulatedSource
            logger.info("[SENSORS] Mode: SIMULATED — using synthetic sensor data.")
            return SimulatedSource(self._config)

        elif mode in ("arduino", "serial"):
            from jarvis.sensors.sources.arduino_source import ArduinoSource
            logger.info("[SENSORS] Mode: ARDUINO — connecting to Arduino Mega 2560 on COM4.")
            return ArduinoSource(self._config)

        elif mode == "csv":
            from jarvis.sensors.sources.aouda_csv_source import AoudaCSVSource
            logger.info("[SENSORS] Mode: CSV — reading Aouda log files.")
            return AoudaCSVSource(self._config)

        elif mode == "network":
            from jarvis.sensors.sources.aouda_network_source import AoudaNetworkSource
            logger.info("[SENSORS] Mode: NETWORK — connecting to Aouda telemetry server.")
            return AoudaNetworkSource(self._config)

        else:
            logger.error(f"Unknown sensor mode: '{mode}'. Using SIMULATED as fallback.")
            from jarvis.sensors.sources.simulated_source import SimulatedSource
            return SimulatedSource(self._config)

    def start(self) -> bool:
        """
        Connect to the data source and start the background polling thread.
        Returns True if successfully started.
        """
        if self._source is None:
            logger.error("No sensor source configured.")
            return False

        connected = self._source.connect()
        if not connected:
            logger.warning(
                f"[SENSORS] {self._source.source_name} failed to connect. "
                "Sensor data will be unavailable."
            )
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="SensorPollThread",
            daemon=True,  # Dies with main program
        )
        self._thread.start()

        logger.success(
            f"[SENSORS] SuitDataManager started — "
            f"polling every {self._update_interval}s from {self._source.source_name}"
        )
        return True

    def stop(self) -> None:
        """Stop the polling thread and disconnect."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._source:
            self._source.disconnect()
        logger.info("[SENSORS] SuitDataManager stopped.")

    def _poll_loop(self) -> None:
        """Background thread: continuously polls sensor source."""
        from web_dashboard import STATE

        while self._running:
            try:
                new_data = self._source.read()
                if new_data:
                    with self._lock:
                        self._latest_data = new_data
                        for sensor_name, reading in new_data.items():
                            if isinstance(reading.get("value"), (int, float)):
                                self.predictive.push_reading(sensor_name, float(reading["value"]))
                    
                    # Update web dashboard UI state continuously in background thread
                    STATE.update_telemetry(new_data)
                    self._check_alerts(new_data)
            except Exception as e:
                logger.error(f"[SENSORS] Poll error: {e}")

            time.sleep(self._update_interval)

    def _check_alerts(self, data: SensorData) -> None:
        """Log warnings, push HUD alert events, and speak voice warnings if out of safe range."""
        from web_dashboard import STATE
        thresh = self._alert_thresholds
        now = time.time()

        checks = [
            ("heart_rate",        "heart_rate_min", "heart_rate_max"),
            ("o2_percent",        "o2_min_percent",  None),
            ("co2_ppm",           None,              "co2_max_ppm"),
            ("battery_percent",   "battery_min_percent", None),
            ("body_temperature",  None,              "temperature_max_c"),
            ("humidity_percent",  None,              "humidity_max_percent"),
            ("suit_pressure_hpa", "pressure_min_hpa", None),
        ]

        for sensor, min_key, max_key in checks:
            reading = data.get(sensor)
            if not reading:
                continue

            val = reading["value"]
            if not isinstance(val, (int, float)):
                continue

            is_alert = False
            alert_msg = ""
            voice_msg = ""

            if min_key and min_key in thresh and val < thresh[min_key]:
                is_alert = True
                alert_msg = f"CRITICAL: {sensor} ({val}) below min threshold ({thresh[min_key]})"
                if sensor == "o2_percent":
                    voice_msg = f"Warning: Low oxygen level detected! Oxygen is at {val:.1f} percent."
                elif sensor == "battery_percent":
                    voice_msg = f"Warning: Suit battery low! Charge is at {val:.0f} percent."
                else:
                    voice_msg = f"Warning: {sensor.replace('_', ' ')} is below threshold at {val:.1f}."

            if max_key and max_key in thresh and val > thresh[max_key]:
                is_alert = True
                alert_msg = f"CRITICAL: {sensor} ({val}) above max threshold ({thresh[max_key]})"
                if sensor == "body_temperature":
                    voice_msg = f"Warning: High suit temperature detected! Temperature is {val:.1f} degrees Celsius."
                elif sensor == "humidity_percent":
                    voice_msg = f"Warning: High humidity level detected! Relative humidity is {val:.1f} percent."
                elif sensor == "co2_ppm":
                    voice_msg = f"Warning: Elevated carbon dioxide concentration! CO2 is {val:.0f} PPM."
                else:
                    voice_msg = f"Warning: {sensor.replace('_', ' ')} is above limit at {val:.1f}."

            if is_alert:
                reading["ok"] = False
                logger.warning(f"[ALERT] {alert_msg}")
                STATE.add_event(f"⚠️ [ALERT] {alert_msg}")

                # Trigger voice warning once every 10 seconds per alert sensor
                last_time = self._last_voice_warning_time.get(sensor, 0.0)
                if voice_msg and (now - last_time > 10.0):
                    self._last_voice_warning_time[sensor] = now
                    STATE.add_chat("AOUDA", voice_msg)
                    logger.warning(f"[VOICE ALERT] Speaking warning: '{voice_msg}'")
                    if self._alert_tts_callback:
                        try:
                            self._alert_tts_callback(voice_msg)
                        except Exception as e:
                            logger.error(f"[VOICE ALERT] TTS error: {e}")
            else:
                reading["ok"] = True

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_all(self) -> SensorData:
        """Return the latest snapshot of all sensor readings (thread-safe)."""
        with self._lock:
            return dict(self._latest_data)

    def get(self, sensor_name: str) -> Optional[SensorReading]:
        """Return the latest reading for a specific sensor."""
        with self._lock:
            return self._latest_data.get(sensor_name)

    def get_active_alerts(self) -> List[str]:
        """
        Return a list of sensors currently in alert state.
        An alert is when SensorReading["ok"] is False.
        """
        with self._lock:
            return [
                name for name, reading in self._latest_data.items()
                if not reading.get("ok", True)
            ]

    def get_summary_text(self) -> str:
        """Return a human-readable one-line summary of key vitals."""
        data = self.get_all()
        if not data:
            return "No sensor data available."

        parts = []
        if "heart_rate" in data:
            parts.append(f"HR {data['heart_rate']['value']:.0f} bpm")
        if "o2_percent" in data:
            parts.append(f"O2 {data['o2_percent']['value']:.1f}%")
        if "co2_ppm" in data:
            parts.append(f"CO2 {data['co2_ppm']['value']:.0f} ppm")
        if "battery_percent" in data:
            parts.append(f"BAT {data['battery_percent']['value']:.0f}%")

        alerts = self.get_active_alerts()
        alert_str = f" | ALERTS: {', '.join(alerts)}" if alerts else ""
        return " | ".join(parts) + alert_str

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def source_mode(self) -> str:
        return self._source.source_name if self._source else "none"
