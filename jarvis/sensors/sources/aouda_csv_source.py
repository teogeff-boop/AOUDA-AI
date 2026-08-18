"""
JARVIS AI — Aouda CSV Sensor Source
======================================
Reads Aouda suit telemetry from CSV files.

Supports two modes:
  1. LIVE MODE   : Reads the latest line from actively-written CSV files
                   (Aouda writes one CSV per sensor, updated in real-time)
  2. REPLAY MODE : Replays a recorded mission CSV at configurable speed
                   (useful for post-mission analysis or demos)

Expected CSV format (one file per sensor):
  timestamp,value
  2024-01-15T09:00:00.123Z,78.2
  2024-01-15T09:00:01.124Z,79.1
  ...

Directory structure expected:
  data/sensor_logs/
  ├── heart_rate.csv
  ├── o2_percent.csv
  ├── co2_ppm.csv
  ├── suit_pressure_hpa.csv
  ├── body_temperature.csv
  ├── battery_percent.csv
  ├── humidity_percent.csv
  └── gps.csv   (format: timestamp,lat,lon,alt)
"""

import csv
import time
from pathlib import Path
from loguru import logger
from typing import Optional
from jarvis.sensors.sources.base_source import SuitDataSource, SensorData


# Mapping: sensor name -> (filename, unit, min_ok, max_ok)
SENSOR_FILES = {
    "heart_rate":        ("heart_rate.csv",        "bpm",  50,   150),
    "o2_percent":        ("o2_percent.csv",         "%",    19.5, 25),
    "co2_ppm":           ("co2_ppm.csv",            "ppm",  0,    5000),
    "suit_pressure_hpa": ("suit_pressure_hpa.csv",  "hPa",  950,  1050),
    "body_temperature":  ("body_temperature.csv",   "C",    35,   38.5),
    "battery_percent":   ("battery_percent.csv",    "%",    20,   100),
    "humidity_percent":  ("humidity_percent.csv",   "%",    0,    100),
}


class AoudaCSVSource(SuitDataSource):
    """
    Reads Aouda suit telemetry from CSV log files.
    Can read live data (tail of CSV) or replay recorded missions.
    """

    def __init__(self, config: dict):
        sensor_cfg = config.get("sensors", {})
        self._csv_dir = Path(sensor_cfg.get("csv_directory", "data/sensor_logs/"))
        self._connected: bool = False
        self._file_positions: dict = {}  # Track file read positions for live mode
        self._cache: SensorData = {}
        self._last_read: float = 0.0

    def connect(self) -> bool:
        """Check CSV directory exists and files are accessible."""
        if not self._csv_dir.exists():
            logger.warning(
                f"CSV directory not found: {self._csv_dir}\n"
                "Create the directory and add Aouda CSV log files."
            )
            self._connected = False
            return False

        available = list(self._csv_dir.glob("*.csv"))
        if not available:
            logger.warning(f"No CSV files found in {self._csv_dir}")
            self._connected = False
            return False

        logger.success(
            f"[SENSORS] AoudaCSVSource connected — "
            f"{len(available)} CSV files found in {self._csv_dir}"
        )
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._file_positions.clear()
        logger.info("[SENSORS] AoudaCSVSource disconnected.")

    def read(self) -> SensorData:
        """Read the latest values from all available CSV files."""
        if not self._connected:
            return {}

        data: SensorData = {}

        for sensor_name, (filename, unit, min_val, max_val) in SENSOR_FILES.items():
            csv_path = self._csv_dir / filename
            if not csv_path.exists():
                continue

            value = self._read_latest_value(csv_path)
            if value is not None:
                ok = min_val <= value <= max_val
                age = time.time() - self._last_read
                data[sensor_name] = self.make_reading(value, unit, age, ok)

        # GPS is special (3 values per row)
        gps_path = self._csv_dir / "gps.csv"
        if gps_path.exists():
            gps = self._read_gps(gps_path)
            if gps:
                data["gps"] = self.make_reading(gps, "deg/m", 0.0, True)

        self._last_read = time.time()
        self._cache = data
        return data

    def _read_latest_value(self, csv_path: Path) -> Optional[float]:
        """Read the last numeric value from a CSV file (timestamp,value format)."""
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))

            # Skip header, get last data row
            data_rows = [r for r in rows if r and not r[0].startswith("#")
                         and r[0].lower() != "timestamp"]
            if not data_rows:
                return None

            last_row = data_rows[-1]
            if len(last_row) >= 2:
                return float(last_row[1])

        except (IOError, ValueError, IndexError) as e:
            logger.debug(f"Could not read {csv_path.name}: {e}")

        return None

    def _read_gps(self, csv_path: Path) -> Optional[dict]:
        """Read GPS data: timestamp,lat,lon,alt format."""
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))

            data_rows = [r for r in rows if r and not r[0].startswith("#")
                         and r[0].lower() != "timestamp"]
            if not data_rows:
                return None

            last_row = data_rows[-1]
            if len(last_row) >= 4:
                return {
                    "lat": float(last_row[1]),
                    "lon": float(last_row[2]),
                    "alt": float(last_row[3]),
                }

        except (IOError, ValueError, IndexError) as e:
            logger.debug(f"Could not read GPS CSV: {e}")

        return None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def source_name(self) -> str:
        return f"AoudaCSVSource({self._csv_dir})"


def generate_sample_csv(output_dir: str = "data/sensor_logs/") -> None:
    """
    Generate sample CSV files with realistic Aouda mission data.
    Useful for testing the CSV source without real hardware.
    Run directly: python -m jarvis.sensors.sources.aouda_csv_source
    """
    import math
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = 60  # 1 minute of data at 1Hz

    # Heart rate
    with open(out / "heart_rate.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            hr = 75 + 8 * math.sin(i / 10.0) + (i % 3) * 0.5
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(hr, 1)])

    # O2
    with open(out / "o2_percent.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(20.9 + (i % 5) * 0.01, 2)])

    # CO2
    with open(out / "co2_ppm.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(420 + i * 2, 0)])

    # Pressure
    with open(out / "suit_pressure_hpa.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(1013 + math.sin(i) * 0.5, 1)])

    # Temperature
    with open(out / "body_temperature.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(37.0 + i * 0.01, 2)])

    # Battery
    with open(out / "battery_percent.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(85.0 - i * 0.1, 1)])

    # Humidity
    with open(out / "humidity_percent.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        for i in range(rows):
            w.writerow([f"2024-01-15T09:00:{i:02d}.000Z", round(55 + math.sin(i * 0.3) * 3, 1)])

    # GPS
    with open(out / "gps.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "lat", "lon", "alt"])
        for i in range(rows):
            w.writerow([
                f"2024-01-15T09:00:{i:02d}.000Z",
                round(47.5012 + i * 0.000005, 6),
                round(14.1234 + i * 0.000003, 6),
                round(1200.0 + math.sin(i * 0.2) * 2, 1),
            ])

    print(f"Sample CSV files generated in: {out.resolve()}")


if __name__ == "__main__":
    generate_sample_csv()
