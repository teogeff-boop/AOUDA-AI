"""
JARVIS AI — Aouda Network Sensor Source
=========================================
Connects to the Aouda suit telemetry server over Wi-Fi.

The Aouda suit transmits telemetry via 5GHz Wi-Fi to the Mission Support Center.
This module connects to that stream and reads sensor values in real time.

CURRENT STATUS: Placeholder — protocol details needed from OeWF technical team.
Configure network_host, network_port, and network_protocol in config.yaml.

Expected interface (to be confirmed with OeWF):
  - TCP socket or UDP broadcast
  - Data format: JSON lines or CSV per message
  - Message example: {"sensor": "heart_rate", "value": 78.2, "ts": 1234567890}

Once the exact protocol is confirmed, implement _parse_message() accordingly.
"""

import socket
import json
import time
import threading
from loguru import logger
from typing import Optional
from jarvis.sensors.sources.base_source import SuitDataSource, SensorData


class AoudaNetworkSource(SuitDataSource):
    """
    Network-based Aouda suit telemetry source.
    Connects to the Aouda Wi-Fi telemetry stream.

    PLACEHOLDER: Awaiting OeWF protocol documentation.
    """

    def __init__(self, config: dict):
        sensor_cfg = config.get("sensors", {})
        self._host: str    = sensor_cfg.get("network_host", "192.168.1.100")
        self._port: int    = sensor_cfg.get("network_port", 5005)
        self._protocol: str = sensor_cfg.get("network_protocol", "tcp")

        self._socket: Optional[socket.socket] = None
        self._connected: bool = False
        self._latest_data: SensorData = {}
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Attempt to connect to the Aouda telemetry server."""
        try:
            if self._protocol == "tcp":
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(5.0)
                self._socket.connect((self._host, self._port))
            elif self._protocol == "udp":
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.settimeout(5.0)
                self._socket.bind(("", self._port))
            else:
                logger.error(f"Unknown protocol: {self._protocol}")
                return False

            self._connected = True
            logger.success(
                f"[SENSORS] AoudaNetworkSource connected — "
                f"{self._protocol.upper()}://{self._host}:{self._port}"
            )
            return True

        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.warning(
                f"[SENSORS] Cannot connect to Aouda telemetry server "
                f"({self._host}:{self._port}): {e}\n"
                "Check that the Aouda suit Wi-Fi is active and the IP is correct."
            )
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close the socket connection."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False
        logger.info("[SENSORS] AoudaNetworkSource disconnected.")

    def read(self) -> SensorData:
        """
        Read the latest telemetry from the network socket.

        TODO: Implement _parse_message() once OeWF protocol is confirmed.
        Current implementation returns empty dict (not yet integrated).
        """
        if not self._connected or not self._socket:
            return {}

        try:
            if self._protocol == "tcp":
                raw = self._socket.recv(4096)
            else:
                raw, _ = self._socket.recvfrom(4096)

            if raw:
                return self._parse_message(raw.decode("utf-8", errors="replace"))

        except socket.timeout:
            pass  # No new data — return last known values
        except OSError as e:
            logger.error(f"Network read error: {e}")
            self._connected = False

        return self._latest_data

    def _parse_message(self, raw: str) -> SensorData:
        """
        Parse a raw telemetry message from the Aouda suit.

        TODO: Implement based on actual Aouda protocol.
        Options to implement once protocol is known:
          - JSON lines: {"sensor": "heart_rate", "value": 78.2, "ts": 1234}
          - CSV frame: "hr,78.2;o2,20.9;co2,420;..."
          - Binary protocol: struct.unpack(...)

        Args:
            raw: Raw string received from socket.

        Returns:
            Parsed SensorData dict.
        """
        # PLACEHOLDER IMPLEMENTATION — replace with actual Aouda protocol
        logger.debug(f"[SENSORS] Raw message received ({len(raw)} bytes) — parser not yet implemented.")

        # Attempt JSON parsing (common format)
        try:
            msg = json.loads(raw)
            sensor_name = msg.get("sensor")
            value = msg.get("value")
            if sensor_name and value is not None:
                self._latest_data[sensor_name] = self.make_reading(
                    value=value,
                    unit=msg.get("unit", "?"),
                    age_s=0.0,
                    ok=True,
                )
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message: {raw[:100]}")

        return self._latest_data

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def source_name(self) -> str:
        return f"AoudaNetworkSource({self._host}:{self._port})"
