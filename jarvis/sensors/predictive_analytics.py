"""
JARVIS AI — Predictive Telemetry & Proactive Warning Engine
===========================================================
Monitors rolling time-series sensor windows to detect abnormal trends
(e.g., rapid O2 depletion rate, steady HR escalation, pressure leaks)
and generates proactive vocal alerts BEFORE critical thresholds are breached.
"""

from collections import deque
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, List, Optional, Tuple


class PredictiveAnalytics:
    """
    Rolling-window predictive telemetry engine.
    Calculates sensor consumption rates (dValue/dt) and issues proactive alerts.
    """

    def __init__(self, window_minutes: float = 5.0, alert_cooldown_seconds: float = 60.0):
        self.window_minutes = window_minutes
        self.alert_cooldown_seconds = alert_cooldown_seconds

        # Time-series history buffers: deque of (datetime, float_value)
        self.history: Dict[str, deque] = {
            "o2_percent": deque(maxlen=300),
            "co2_ppm": deque(maxlen=300),
            "heart_rate": deque(maxlen=300),
            "suit_pressure_hpa": deque(maxlen=300),
            "battery_percent": deque(maxlen=300),
        }

        # Cooldown timestamps to prevent repeating the same proactive alert continuously
        self.last_alerts: Dict[str, datetime] = {}

    def push_reading(self, metric: str, value: float) -> None:
        """Push a new sensor reading into the rolling history window."""
        if metric in self.history:
            now = datetime.now()
            self.history[metric].append((now, float(value)))
            self._prune_old(metric, now)

    def _prune_old(self, metric: str, now: datetime) -> None:
        """Remove samples older than window_minutes."""
        cutoff = now - timedelta(minutes=self.window_minutes)
        buffer = self.history[metric]
        while buffer and buffer[0][0] < cutoff:
            buffer.popleft()

    def analyze(self) -> Optional[str]:
        """
        Analyze current rolling windows for abnormal trends.
        Returns a proactive vocal alert string if a trend is detected, else None.
        """
        now = datetime.now()

        # 1. Check Oxygen Depletion Rate (dO2/dt)
        o2_alert = self._check_o2_rate(now)
        if o2_alert:
            return o2_alert

        # 2. Check Heart Rate Escalation (dHR/dt)
        hr_alert = self._check_hr_rate(now)
        if hr_alert:
            return hr_alert

        # 3. Check Suit Pressure Leak (dPres/dt)
        pres_alert = self._check_pressure_rate(now)
        if pres_alert:
            return pres_alert

        return None

    def _check_o2_rate(self, now: datetime) -> Optional[str]:
        """Detect rapid Oxygen depletion rate (>0.6% drop over 5 minutes)."""
        metric = "o2_percent"
        if self._in_cooldown(metric, now):
            return None

        buf = self.history[metric]
        if len(buf) < 10:
            return None

        t_start, v_start = buf[0]
        t_end, v_end = buf[-1]
        dt_min = (t_end - t_start).total_seconds() / 60.0

        if dt_min >= 1.0:
            delta_o2 = v_start - v_end  # Positive if dropping
            drop_rate_per_5min = (delta_o2 / dt_min) * 5.0

            if drop_rate_per_5min >= 0.6:
                self.last_alerts[metric] = now
                logger.warning(f"[PREDICTIVE ANALYTICS] High O2 drop rate: {drop_rate_per_5min:.2f}% per 5min")
                return (
                    f"AOUDA Warning: Oxygen consumption rate elevated at {drop_rate_per_5min:.1f} percent "
                    f"per five minutes. Recommend pacing your exertion."
                )
        return None

    def _check_hr_rate(self, now: datetime) -> Optional[str]:
        """Detect sustained Heart Rate escalation (>20 bpm rise over 5 minutes)."""
        metric = "heart_rate"
        if self._in_cooldown(metric, now):
            return None

        buf = self.history[metric]
        if len(buf) < 10:
            return None

        t_start, v_start = buf[0]
        t_end, v_end = buf[-1]
        dt_min = (t_end - t_start).total_seconds() / 60.0

        if dt_min >= 1.0:
            delta_hr = v_end - v_start  # Positive if increasing
            hr_rate_per_5min = (delta_hr / dt_min) * 5.0

            if hr_rate_per_5min >= 20.0 and v_end > 110:
                self.last_alerts[metric] = now
                logger.warning(f"[PREDICTIVE ANALYTICS] HR spike rate: +{hr_rate_per_5min:.1f} bpm per 5min")
                return (
                    f"AOUDA Notice: Cardiac activity increased by {hr_rate_per_5min:.0f} beats per minute. "
                    f"Current pulse: {v_end:.0f} BPM. Consider taking a short pause."
                )
        return None

    def _check_pressure_rate(self, now: datetime) -> Optional[str]:
        """Detect suit pressure drop rate (>15 hPa drop over 3 minutes)."""
        metric = "suit_pressure_hpa"
        if self._in_cooldown(metric, now):
            return None

        buf = self.history[metric]
        if len(buf) < 10:
            return None

        t_start, v_start = buf[0]
        t_end, v_end = buf[-1]
        dt_min = (t_end - t_start).total_seconds() / 60.0

        if dt_min >= 0.5:
            delta_p = v_start - v_end
            if delta_p >= 15.0:
                self.last_alerts[metric] = now
                logger.warning(f"[PREDICTIVE ANALYTICS] Suit pressure drop detected: -{delta_p:.1f} hPa")
                return (
                    f"CRITICAL AOUDA ALERT: Suit pressure drop detected. "
                    f"Pressure decreased by {delta_p:.0f} hPa. Inspect suit seal integrity immediately."
                )
        return None

    def _in_cooldown(self, metric: str, now: datetime) -> bool:
        """Check if an alert for this metric was issued recently."""
        if metric in self.last_alerts:
            elapsed = (now - self.last_alerts[metric]).total_seconds()
            return elapsed < self.alert_cooldown_seconds
        return False
