"""
Unit tests for ArduinoSource hardware sensor module.
"""

import pytest
from jarvis.sensors.sources.arduino_source import ArduinoSource

def test_arduino_source_initialization():
    config = {
        "sensors": {
            "mode": "arduino",
            "arduino": {
                "port": "COM4",
                "baudrate": 9600
            }
        }
    }
    source = ArduinoSource(config)
    assert source.source_name == "Arduino Mega 2560 (COM4)"
    assert source.connect() is True
    assert source.is_connected is True

    # Test line parsing
    source._parse_arduino_line("Temp: 23.4 C, Humidity: 54 %")
    readings = source.read()
    assert readings["body_temperature"]["value"] == 23.4
    assert readings["humidity_percent"]["value"] == 54.0

    source.disconnect()
    assert source.is_connected is False
