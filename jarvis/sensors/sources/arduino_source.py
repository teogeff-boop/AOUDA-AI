"""
JARVIS AI — Arduino Mega 2560 + DHT11 Real Hardware Sensor Source
===================================================================
Connects via USB Serial (COM4) to read live temperature and humidity
from an Arduino Mega 2560 R3 board equipped with a DHT11 sensor.

Parses incoming Serial data in multiple formats:
  - JSON: {"temperature": 24.5, "humidity": 55.0}
  - Text: "Temp: 24.5 C, Humidity: 55 %"
  - CSV: "24.5, 55"
  - Single float: "24.5"
"""

import re
import json
import time
import math
import random
import threading
from typing import Dict, Any, Optional
from loguru import logger

from jarvis.sensors.sources.base_source import SuitDataSource, SensorData


class ArduinoSource(SuitDataSource):
    """
    Real Hardware Sensor Source reading live DHT11 telemetry from an Arduino Mega 2560 via Serial.
    Fills physiological suit telemetry (Heart rate, O2, Battery) with realistic baselines
    while overriding body_temperature and humidity with LIVE hardware sensor readings.
    """

    def __init__(self, config: dict):
        self._config = config
        arduino_cfg = config.get("sensors", {}).get("arduino", {})
        self._port: str = arduino_cfg.get("port", "COM4")
        self._baudrate: int = arduino_cfg.get("baudrate", 9600)

        self._connected: bool = False
        self._serial_obj = None
        self._start_time: float = time.time()
        self._lock = threading.Lock()

        # Latest readings from DHT11 hardware
        self._live_temp: Optional[float] = None
        self._live_humidity: Optional[float] = None
        self._last_hardware_time: float = 0.0

        # Background thread to continuously read Serial without blocking main loop
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False

    def connect(self) -> bool:
        """Connect to the Arduino Mega 2560 via PySerial."""
        import serial
        import serial.tools.list_ports

        # Auto-detect COM port if COM4 is not available or if list of ports matches Arduino
        available_ports = list(serial.tools.list_ports.comports())
        target_port = self._port

        found = False
        for p in available_ports:
            if hasattr(p, 'device') and p.device == target_port:
                found = True
                break

        if not found:
            for p in available_ports:
                if any(kw in p.description.lower() for kw in ["arduino", "mega", "ch340", "usb"]):
                    target_port = p.device
                    logger.info(f"[ARDUINO] Auto-detected Arduino port: {target_port} ({p.description})")
                    break

        logger.info(f"[ARDUINO] Attempting connection to Arduino Mega on {target_port} at {self._baudrate} baud...")

        try:
            self._serial_obj = serial.Serial(target_port, self._baudrate, timeout=1)
            self._port = target_port
            self._connected = True
            self._running = True

            # Launch serial reader thread
            self._thread = threading.Thread(target=self._serial_reader_loop, daemon=True, name="ArduinoSerialReader")
            self._thread.start()

            logger.success(f"[ARDUINO] Connected to Real Hardware Arduino Mega on {target_port}!")
            return True
        except Exception as e:
            logger.warning(f"[ARDUINO] Serial connection failed on {target_port}: {e}. Fallback to simulated hardware values.")
            self._connected = True  # Keep operational with fallback
            return True

    def disconnect(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._serial_obj and self._serial_obj.is_open:
            try:
                self._serial_obj.close()
            except Exception:
                pass
        self._connected = False
        logger.info("[ARDUINO] Disconnected from Arduino Mega.")

    def _serial_reader_loop(self) -> None:
        """Background thread continuously reading lines from Arduino Serial."""
        while self._running and self._serial_obj and self._serial_obj.is_open:
            try:
                if self._serial_obj.in_waiting > 0:
                    raw_bytes = self._serial_obj.readline()
                    line = raw_bytes.decode("utf-8", errors="ignore").strip()
                    if line:
                        self._parse_arduino_line(line)
            except Exception as e:
                logger.debug(f"[ARDUINO] Serial read error: {e}")
            time.sleep(0.05)

    def _parse_arduino_line(self, line: str) -> None:
        """
        Flexibly parse Arduino serial output string.
        Supports JSON, Key-Value text, CSV, space-separated, and raw float values.
        """
        temp, humidity = None, None

        # 1. Try JSON parsing
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                temp = data.get("temp") or data.get("temperature") or data.get("t")
                humidity = data.get("humidity") or data.get("hum") or data.get("h")
                if temp is not None: temp = float(temp)
                if humidity is not None: humidity = float(humidity)
            except Exception:
                pass

        # 2. Explicit Keyword-based extraction (FR & EN)
        if temp is None:
            t_match = re.search(r"(?:temp(?:erature|érature)?|t)\s*[:=]?\s*([0-9]+\.?[0-9]*)", line, re.IGNORECASE)
            if t_match:
                try:
                    temp = float(t_match.group(1))
                except ValueError:
                    pass

        if humidity is None:
            h_match = re.search(r"(?:hum(?:idity|idité)?|h)\s*[:=]?\s*([0-9]+\.?[0-9]*)", line, re.IGNORECASE)
            if h_match:
                try:
                    humidity = float(h_match.group(1))
                except ValueError:
                    pass

        # 3. CSV or Space-separated pair parsing (e.g. "24.5, 55.0" or "24.5 55.0")
        if temp is None:
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
            if len(nums) >= 2:
                try:
                    val1 = float(nums[0])
                    val2 = float(nums[1])
                    if 0 <= val1 <= 80: temp = val1
                    if 0 <= val2 <= 100: humidity = val2
                except ValueError:
                    pass
            elif len(nums) == 1:
                try:
                    val = float(nums[0])
                    if 0 <= val <= 80: temp = val
                except ValueError:
                    pass

        with self._lock:
            if temp is not None:
                self._live_temp = temp
                self._last_hardware_time = time.time()
                logger.success(f"[ARDUINO HARDWARE] Live DHT11 Temperature: {temp:.1f}°C")
            if humidity is not None:
                self._live_humidity = humidity
                logger.success(f"[ARDUINO HARDWARE] Live DHT11 Humidity: {humidity:.1f}%")

    def read(self) -> SensorData:
        """
        Return snapshot of suit sensors, merging live DHT11 readings with
        simulated baseline vitals for full suit telemetry compatibility.
        """
        if not self._connected:
            return {}

        t = time.time() - self._start_time

        with self._lock:
            has_temp = self._live_temp is not None
            has_hum = self._live_humidity is not None
            temp_val = self._live_temp if has_temp else None
            hum_val = self._live_humidity if has_hum else None

        # Simulated baseline suit physiological vitals
        hr = 75.0 + 5.0 * math.sin(t / 60.0) + random.gauss(0, 1)
        o2 = 20.9 + random.gauss(0, 0.05)
        co2 = 420.0 + random.gauss(0, 5)
        pressure = 1013.0 + random.gauss(0, 1)
        battery = max(20.0, 85.0 - (t / 3600.0) * 5.0)

        return {
            "heart_rate": self.make_reading(round(hr, 1), "bpm"),
            "o2_percent": self.make_reading(round(o2, 1), "%"),
            "co2_ppm": self.make_reading(round(co2, 1), "ppm"),
            "suit_pressure_hpa": self.make_reading(round(pressure, 1), "hPa"),
            "body_temperature": self.make_reading(round(temp_val, 1) if has_temp else "OFFLINE", "°C", ok=has_temp),
            "humidity_percent": self.make_reading(round(hum_val, 1) if has_hum else "OFFLINE", "%", ok=has_hum),
            "battery_percent": self.make_reading(round(battery, 1), "%"),
            "gps": self.make_reading({"lat": 47.5012, "lon": 14.1234, "alt": 1200.0}, "deg/m"),
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def source_name(self) -> str:
        return f"Arduino Mega 2560 ({self._port})"
