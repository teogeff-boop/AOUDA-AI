"""
JARVIS / AOUDA — Real-Time Suit HUD & Ground Control Web Dashboard
===================================================================
100% Offline, Zero-Dependency Futuristic Space HUD Dashboard for AMADEE-27 Analog Missions.
Features Dual-Screen Architecture:
1. /ops (or /) -> OPS Workstation Control Center (Full Desktop UI with Authentic ÖWF Oval Logo, 3D Chat Feed, PDF Viewer, 1000px HD Zoom)
2. /astronaut (or /tft) -> Astronaut V-700 TFT Helmet Display (100% English Typography, Authentic ÖWF Oval Logo, 3D Speech Popups, Real-Time Live Telemetry Curve Popups, Dynamic Procedure Footer)

Listens strictly on 127.0.0.1 (loopback only — no administrator/firewall alerts).
"""

import os
import json
import time
import threading
from collections import deque
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from loguru import logger
from typing import Dict, List, Any, Optional
from socketserver import ThreadingMixIn


class DashboardState:
    """Singleton state manager holding live telemetry, chat history, mission events, and astronaut screen mode."""

    def __init__(self):
        self._lock = threading.Lock()
        self.telemetry: Dict[str, Any] = {
            "o2_percent": {"value": 20.9, "unit": "%", "ok": True},
            "co2_ppm": {"value": 420.0, "unit": "ppm", "ok": True},
            "heart_rate": {"value": 78.0, "unit": "bpm", "ok": True},
            "suit_pressure_hpa": {"value": 1013.0, "unit": "hPa", "ok": True},
            "battery_percent": {"value": 95.0, "unit": "%", "ok": True},
            "body_temperature": {"value": 24.5, "unit": "°C", "ok": True},
            "humidity_percent": {"value": 55.0, "unit": "%", "ok": True},
        }

        self.chat_history: List[Dict[str, str]] = [
            {"speaker": "AOUDA", "text": "AOUDA online. All systems nominal. AMADEE-27 HUD active.", "time": datetime.now().strftime("%H:%M:%S")}
        ]

        self.active_procedure: Dict[str, Any] = {
            "title": "AOUDA Standby",
            "step": 0,
            "max_steps": 0,
            "instruction": "Say 'AOUDA' or pre-select a procedure from Ground OPS Control."
        }

        self.event_log: List[Dict[str, str]] = [
            {"time": datetime.now().strftime("%H:%M:%S"), "event": "AMADEE-27 Mission HUD Linked & Live."}
        ]

        # Astronaut V-700 TFT Screen View Mode ('default', 'vitals', 'alert', 'temp_popup', 'hum_popup', 'hr_popup')
        self.astronaut_view: str = "default"
        self.popup_until: float = 0.0
        self.last_speech_time: float = time.time()

        self.pending_commands: deque = deque()
        self.documents_cache: List[Dict[str, Any]] = []
        self.pdf_cache: List[Dict[str, str]] = []
        self._load_knowledge_base_cache()

    def _load_knowledge_base_cache(self) -> None:
        """Load structured procedures and PDF documents for frontend selection."""
        kb_path = Path("data/knowledge_base")
        if kb_path.exists():
            all_files = list(kb_path.glob("*.md")) + list(kb_path.glob("*.yaml")) + list(kb_path.glob("*.yml")) + list(kb_path.glob("*.txt"))
            for file in all_files:
                try:
                    content = file.read_text(encoding="utf-8")
                    title = file.stem.replace("_", " ").title()
                    steps = []
                    for line in content.split("\n"):
                        line_s = line.strip()
                        if line_s.startswith("- Step") or line_s.startswith("* Step") or "Step " in line_s or line_s.startswith("- Étape") or line_s.startswith("Etape "):
                            steps.append(line_s)
                    
                    self.documents_cache.append({
                        "id": file.stem,
                        "title": title,
                        "filename": file.name,
                        "content": content,
                        "steps": steps
                    })
                except Exception as e:
                    logger.error(f"[DASHBOARD] Error caching {file}: {e}")

        # Scan PDF documents folder
        pdf_path = Path("data/pdf_documents")
        if pdf_path.exists():
            for pdf_file in pdf_path.glob("*.pdf"):
                self.pdf_cache.append({
                    "filename": pdf_file.name,
                    "title": pdf_file.stem.replace("_", " ").title(),
                    "url": f"/pdf/{pdf_file.name}"
                })

    def set_astronaut_view(self, view_mode: str, duration_sec: float = 0.0) -> None:
        """Set Astronaut V-700 TFT display view mode with optional auto-dismiss duration."""
        with self._lock:
            self.astronaut_view = view_mode
            if duration_sec > 0:
                self.popup_until = time.time() + duration_sec
            else:
                self.popup_until = 0.0
            now_str = datetime.now().strftime("%H:%M:%S")
            self.event_log.append({"time": now_str, "event": f"Astronaut V-700 Display view set to [{view_mode.upper()}]"})

    def update_telemetry(self, sensor_data: dict) -> None:
        """Update live telemetry snapshot."""
        with self._lock:
            for key, reading in sensor_data.items():
                if isinstance(reading, dict) and "value" in reading:
                    self.telemetry[key] = reading

    def add_chat(self, speaker: str, text: str) -> None:
        """Add a speech item to live chat feed and auto-trigger smart overlays if query requests sensors/docs."""
        with self._lock:
            now_str = datetime.now().strftime("%H:%M:%S")
            self.chat_history.append({"speaker": speaker, "text": text, "time": now_str})
            self.last_speech_time = time.time()
            if len(self.chat_history) > 30:
                self.chat_history.pop(0)

            # Auto-detect telemetry queries (in English or French) to trigger fullscreen animated popups
            txt_lower = text.lower()
            if any(kw in txt_lower for kw in ["temperature", "température", "temp", "thermal", "heat", "chaleur", "degree", "degré", "dht11"]):
                self.astronaut_view = "temp_popup"
                self.popup_until = time.time() + 10.0
            elif any(kw in txt_lower for kw in ["humidity", "humidité", "hum"]):
                self.astronaut_view = "hum_popup"
                self.popup_until = time.time() + 10.0
            elif any(kw in txt_lower for kw in ["heart", "pulse", "cardiac", "bpm", "pouls", "coeur", "cardiaque"]):
                self.astronaut_view = "hr_popup"
                self.popup_until = time.time() + 10.0
            elif any(kw in txt_lower for kw in ["capteur", "capteurs", "sensor", "sensors", "vitals"]):
                self.astronaut_view = "temp_popup"
                self.popup_until = time.time() + 10.0

    def set_procedure(self, title: str, step: int, instruction: str, max_steps: int = 5) -> None:
        """Update active procedure step."""
        with self._lock:
            self.active_procedure = {
                "title": title,
                "step": step,
                "max_steps": max_steps if max_steps > 0 else 5,
                "instruction": instruction
            }
            if title and title != "AOUDA Standby":
                self.astronaut_view = "procedure"

    def add_event(self, event_text: str) -> None:
        """Log a mission event."""
        with self._lock:
            now_str = datetime.now().strftime("%H:%M:%S")
            self.event_log.append({"time": now_str, "event": event_text})
            if len(self.event_log) > 40:
                self.event_log.pop(0)

    def add_command(self, cmd: str) -> None:
        """Queue a ground control override command."""
        with self._lock:
            self.pending_commands.append(cmd)

    def pop_command(self) -> Optional[str]:
        """Pop next pending ground control command if available."""
        with self._lock:
            if self.pending_commands:
                return self.pending_commands.popleft()
            return None

    def get_full_snapshot(self) -> Dict[str, Any]:
        """Return full JSON snapshot for frontend web UI."""
        with self._lock:
            # Check auto-dismiss for popups
            if self.popup_until > 0 and time.time() > self.popup_until:
                self.astronaut_view = "default"
                self.popup_until = 0.0

            return {
                "telemetry": dict(self.telemetry),
                "chat": list(self.chat_history),
                "procedure": dict(self.active_procedure),
                "events": list(self.event_log),
                "documents": self.documents_cache,
                "pdf_documents": self.pdf_cache,
                "astronaut_view": self.astronaut_view,
                "speech_age_sec": round(time.time() - self.last_speech_time, 1),
                "popup_remaining": max(0.0, round(self.popup_until - time.time(), 1)) if self.popup_until > 0 else 0
            }


# Global state instance
STATE = DashboardState()


# HTML Tag for Official ÖWF Oval Logo Image (serves /assets/owf_logo.png)
HTML_OWF_LOGO_IMG = '<img src="/assets/owf_logo.png" alt="ÖWF Official Logo" style="height: 42px; width: auto; max-width: 150px; object-fit: contain; filter: drop-shadow(0 0 10px rgba(0, 242, 254, 0.5)); transition: transform 0.3s;" onhover="this.style.transform=\'scale(1.05)\'">'


# =====================================================================
# 1. OPS WORKSTATION DASHBOARD HTML (Full Desktop 1920x1080 Layout)
# =====================================================================
DASHBOARD_OPS_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ÖWF AMADEE-27 — OPS Workstation Control Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #050814;
            --card-bg: rgba(13, 22, 44, 0.85);
            --card-border: rgba(0, 242, 254, 0.25);
            --cyan-glow: #00F2FE;
            --blue-glow: #4FACFE;
            --purple-glow: #7928CA;
            --accent-green: #00FF88;
            --accent-red: #FF0055;
            --text-main: #F1F5F9;
            --text-dim: #94A3B8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Rajdhani', sans-serif; }}
        body {{
            background-color: var(--bg);
            background-image: 
                radial-gradient(circle at 10% 10%, rgba(0, 242, 254, 0.1) 0%, transparent 45%),
                radial-gradient(circle at 90% 90%, rgba(121, 40, 202, 0.1) 0%, transparent 45%);
            color: var(--text-main);
            padding: 16px;
            min-height: 100vh;
        }}

        header {{
            display: flex; justify-content: space-between; align-items: center;
            background: rgba(13, 22, 44, 0.8); backdrop-filter: blur(16px);
            border: 1px solid var(--card-border); padding: 14px 22px;
            border-radius: 16px; margin-bottom: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }}
        .logo-box {{ display: flex; align-items: center; gap: 16px; }}
        h1 {{
            font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: 700;
            letter-spacing: 2px; background: linear-gradient(90deg, #fff, var(--cyan-glow));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .mission-sub {{ font-size: 13px; color: var(--text-dim); letter-spacing: 1px; font-weight: 600; }}

        .header-right {{ display: flex; gap: 16px; align-items: center; }}
        .ast-link-btn {{
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.2), rgba(121, 40, 202, 0.2));
            border: 1.5px solid var(--cyan-glow); color: #fff; padding: 10px 20px; border-radius: 24px;
            font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 700;
            text-decoration: none; transition: all 0.3s; box-shadow: 0 0 15px rgba(0,242,254,0.25);
        }}
        .ast-link-btn:hover {{ background: var(--cyan-glow); color: #000; box-shadow: 0 0 25px var(--cyan-glow); transform: translateY(-2px); }}

        .status-badge {{
            display: flex; align-items: center; gap: 8px;
            background: rgba(0, 255, 136, 0.12); border: 1px solid var(--accent-green);
            color: var(--accent-green); padding: 7px 16px; border-radius: 30px;
            font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 700;
        }}
        .pulse-dot {{
            width: 9px; height: 9px; border-radius: 50%; background: var(--accent-green);
            box-shadow: 0 0 12px var(--accent-green); animation: pulse 1.5s infinite;
        }}
        @keyframes pulse {{ 0% {{ opacity: 0.3; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.3; }} }}

        .tab-bar {{
            display: flex; gap: 12px; margin-bottom: 16px;
            border-bottom: 1px solid var(--card-border); padding-bottom: 10px;
        }}
        .tab-btn {{
            background: rgba(13, 22, 44, 0.7); border: 1px solid var(--card-border);
            color: var(--text-dim); padding: 10px 22px; border-radius: 12px;
            font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 700;
            cursor: pointer; transition: all 0.3s; text-transform: uppercase; letter-spacing: 1.5px;
        }}
        .tab-btn:hover {{ color: #fff; border-color: var(--cyan-glow); background: rgba(0, 242, 254, 0.15); }}
        .tab-btn.active-tab {{
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.35), rgba(121, 40, 202, 0.35));
            border-color: var(--cyan-glow); color: #fff; box-shadow: 0 0 20px rgba(0, 242, 254, 0.4);
        }}

        .telemetry-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px; margin-bottom: 16px;
        }}
        .gauge-card {{
            background: var(--card-bg); backdrop-filter: blur(16px);
            border: 1px solid var(--card-border); border-radius: 14px; padding: 12px 14px;
            position: relative; overflow: hidden; transform-style: preserve-3d; transition: all 0.3s;
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
        }}
        .gauge-card:hover {{ transform: translateY(-4px) rotateX(2deg); border-color: var(--cyan-glow); box-shadow: 0 10px 25px rgba(0,242,254,0.2); }}
        .gauge-card::before {{
            content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
            background: linear-gradient(to bottom, var(--cyan-glow), var(--purple-glow));
        }}
        .gauge-title {{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px; font-weight: 700; }}
        .gauge-val {{ font-family: 'Orbitron', sans-serif; font-size: 22px; font-weight: 700; color: #fff; }}
        .gauge-unit {{ font-size: 12px; color: var(--cyan-glow); margin-left: 4px; }}
        .gauge-status {{ font-size: 10px; margin-top: 2px; font-weight: 700; color: var(--accent-green); }}

        .hud-layout {{
            display: grid; grid-template-columns: 1.3fr 1.6fr 1.3fr; gap: 16px; margin-bottom: 16px;
        }}
        .hud-panel {{
            background: var(--card-bg); backdrop-filter: blur(16px);
            border: 1px solid var(--card-border); border-radius: 16px; padding: 16px;
            display: flex; flex-direction: column; gap: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }}
        .panel-header {{
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px;
        }}
        .panel-title {{
            font-family: 'Orbitron', sans-serif; font-size: 12px; font-weight: 700;
            color: var(--cyan-glow); letter-spacing: 1.5px; text-transform: uppercase;
        }}

        .proc-header {{
            background: linear-gradient(90deg, rgba(0, 242, 254, 0.15), rgba(121, 40, 202, 0.15));
            border-left: 4px solid var(--cyan-glow); padding: 12px 16px; border-radius: 10px;
        }}
        .proc-active-title {{ font-family: 'Orbitron', sans-serif; font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 2px; }}
        .proc-active-step {{ font-size: 13px; color: var(--cyan-glow); font-weight: 600; }}

        .proc-selector {{
            width: 100%; background: #080d1a; border: 1px solid var(--card-border);
            color: #fff; padding: 9px 12px; border-radius: 10px; font-size: 12px; outline: none; cursor: pointer;
        }}
        .doc-steps-list {{
            max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; padding-right: 4px;
        }}
        .step-item {{
            background: rgba(8, 13, 26, 0.9); border: 1px solid rgba(255,255,255,0.08);
            padding: 8px 12px; border-radius: 8px; font-size: 12px; cursor: pointer; transition: all 0.2s;
            display: flex; align-items: center; justify-content: space-between;
        }}
        .step-item:hover {{ border-color: var(--cyan-glow); background: rgba(0, 242, 254, 0.15); transform: translateX(3px); }}
        .step-btn-push {{
            background: var(--cyan-glow); color: #000; border: none; padding: 4px 10px;
            border-radius: 6px; font-weight: 700; font-size: 10px; text-transform: uppercase; cursor: pointer;
        }}

        /* 3D Chat Container Style */
        .chat-container-3d {{
            perspective: 1000px; transform-style: preserve-3d;
        }}
        .chat-scroll {{
            max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding-right: 4px;
            transform: rotateX(2deg); transition: transform 0.3s;
        }}
        .chat-bubble {{
            background: rgba(8, 13, 26, 0.92); border: 1.5px solid rgba(0, 242, 254, 0.25);
            padding: 10px 14px; border-radius: 12px; font-size: 13px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.35); transition: all 0.25s;
        }}
        .chat-bubble:hover {{ transform: translateZ(12px); border-color: var(--cyan-glow); }}
        .chat-speaker-aouda {{ color: var(--accent-green); font-weight: 700; font-family: 'Orbitron', sans-serif; font-size: 11px; }}
        .chat-speaker-astro {{ color: var(--cyan-glow); font-weight: 700; font-family: 'Orbitron', sans-serif; font-size: 11px; }}
        .chat-time {{ float: right; font-size: 10px; color: var(--text-dim); }}

        .btn-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .hud-btn {{
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.2), rgba(59, 130, 246, 0.2));
            border: 1px solid var(--cyan-glow); color: #fff; padding: 10px 12px; border-radius: 10px;
            font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 12px;
            cursor: pointer; transition: all 0.25s; text-align: center; text-transform: uppercase;
        }}
        .hud-btn:hover {{ background: linear-gradient(135deg, var(--cyan-glow), var(--blue-glow)); color: #000; box-shadow: 0 0 15px var(--cyan-glow); }}
        .hud-btn-danger {{
            background: linear-gradient(135deg, rgba(255, 0, 85, 0.25), rgba(239, 68, 68, 0.25));
            border: 1px solid var(--accent-red); color: #fff; grid-column: span 2;
        }}
        .hud-btn-danger:hover {{ background: var(--accent-red); color: #fff; box-shadow: 0 0 20px var(--accent-red); }}

        .input-group {{ display: flex; gap: 8px; }}
        .hud-input {{
            flex: 1; background: #080d1a; border: 1px solid var(--card-border);
            color: #fff; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none;
        }}
        .search-box {{
            width: 100%; background: #080d1a; border: 1px solid var(--card-border);
            color: #fff; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none;
        }}

        .tft-mirror-box {{
            background: #030712; border: 2px solid var(--cyan-glow); border-radius: 12px;
            padding: 12px; font-family: 'Orbitron', sans-serif; box-shadow: 0 0 20px rgba(0,242,254,0.25);
        }}
        .tft-mirror-header {{ display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 10px; color: var(--text-dim); }}
        .tft-mirror-mode {{ color: var(--cyan-glow); font-weight: 900; text-transform: uppercase; }}

        .view-btn-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin-top: 6px; }}
        .view-btn {{
            background: #080d1a; border: 1px solid var(--card-border); color: #fff;
            padding: 5px 6px; border-radius: 6px; font-size: 9px; cursor: pointer; text-align: center; font-weight: 700;
        }}
        .view-btn:hover {{ background: var(--cyan-glow); color: #000; }}

        .hud-bottom-graphs {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
        .compact-graph-card {{
            background: rgba(13, 22, 44, 0.7); border: 1px solid var(--card-border);
            border-radius: 12px; padding: 10px; cursor: pointer; transition: all 0.3s;
        }}
        .compact-graph-card:hover {{
            border-color: var(--cyan-glow); background: rgba(0, 242, 254, 0.15);
            transform: translateY(-3px); box-shadow: 0 0 20px rgba(0, 242, 254, 0.35);
        }}
        .compact-canvas-box {{ background: #040814; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; height: 130px; padding: 4px; }}
        canvas {{ display: block; width: 100%; height: 100%; }}

        .pdf-container {{ width: 100%; height: 720px; border-radius: 14px; overflow: hidden; border: 1px solid var(--card-border); }}
        .pdf-iframe {{ width: 100%; height: 100%; border: none; }}
        .zoom-bar {{ display: flex; gap: 10px; margin-bottom: 14px; }}
        .zoom-btn {{
            background: rgba(13, 22, 44, 0.8); border: 1px solid var(--card-border);
            color: var(--text-dim); padding: 8px 16px; border-radius: 10px;
            font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.3s;
        }}
        .zoom-btn.active-zoom {{ background: var(--cyan-glow); color: #000; font-weight: 900; box-shadow: 0 0 15px var(--cyan-glow); }}
        .sensor-stats-bar {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }}
        .stat-box {{ background: rgba(13, 22, 44, 0.8); border: 1px solid var(--card-border); border-radius: 10px; padding: 10px 14px; text-align: center; }}
        .stat-label {{ font-size: 10px; color: var(--text-dim); text-transform: uppercase; font-weight: 700; }}
        .stat-val {{ font-family: 'Orbitron', sans-serif; font-size: 18px; font-weight: 700; color: #fff; }}
        .giant-canvas-box {{ background: #040814; border: 1px solid var(--card-border); border-radius: 14px; padding: 16px; height: 450px; }}
    </style>
</head>
<body>

    <header>
        <div class="logo-box">
            {HTML_OWF_LOGO_IMG}
            <div>
                <h1>ÖWF AMADEE-27 — OPS WORKSTATION CONTROL CENTER</h1>
                <div class="mission-sub">AOUDA AI ASSISTANT | MARS ANALOG SUIT EVA MONITORING</div>
            </div>
        </div>
        <div class="header-right">
            <a href="/tft" target="_blank" class="ast-link-btn">🧑‍🚀 OPEN ASTRONAUT V-700 HUD</a>
            <div class="status-badge">
                <div class="pulse-dot"></div> LIVE OPS LINK
            </div>
        </div>
    </header>

    <div class="tab-bar">
        <button id="tab-btn-hud" class="tab-btn active-tab" onclick="switchTab('hud')">🚀 Mission HUD & Control</button>
        <button id="tab-btn-docs" class="tab-btn" onclick="switchTab('docs')">📖 Official Mission PDFs</button>
        <button id="tab-btn-charts" class="tab-btn" onclick="switchTab('charts')">📈 High-Res Telemetry Charts</button>
    </div>

    <div class="telemetry-grid">
        <div class="gauge-card" id="temp-card">
            <div class="gauge-title">🌡️ Suit Temp (DHT11)</div>
            <div class="gauge-val"><span id="temp-val">24.5</span><span class="gauge-unit">°C</span></div>
            <div class="gauge-status" id="temp-status">DEMO LIMIT: 31.0°C | OK</div>
        </div>
        <div class="gauge-card" id="hum-card">
            <div class="gauge-title">💧 Humidity (DHT11)</div>
            <div class="gauge-val"><span id="hum-val">55.0</span><span class="gauge-unit">%</span></div>
            <div class="gauge-status" id="hum-status">DEMO LIMIT: 70.0% | OK</div>
        </div>
        <div class="gauge-card">
            <div class="gauge-title">Oxygen Level</div>
            <div class="gauge-val"><span id="o2-val">20.9</span><span class="gauge-unit">%</span></div>
        </div>
        <div class="gauge-card">
            <div class="gauge-title">CO2 Level</div>
            <div class="gauge-val"><span id="co2-val">420</span><span class="gauge-unit">ppm</span></div>
        </div>
        <div class="gauge-card">
            <div class="gauge-title">Heart Rate</div>
            <div class="gauge-val"><span id="hr-val">78</span><span class="gauge-unit">bpm</span></div>
        </div>
        <div class="gauge-card">
            <div class="gauge-title">Suit Pressure</div>
            <div class="gauge-val"><span id="pres-val">1013</span><span class="gauge-unit">hPa</span></div>
        </div>
        <div class="gauge-card">
            <div class="gauge-title">Battery</div>
            <div class="gauge-val"><span id="bat-val">95</span><span class="gauge-unit">%</span></div>
        </div>
    </div>

    <div class="tab-panel" id="panel-hud" style="display: block;">
        <div class="hud-layout">
            
            <div class="hud-panel">
                <div class="panel-header">
                    <div class="panel-title">📖 OPS Procedure Pre-Selection</div>
                </div>
                <div>
                    <label style="font-size:10px; color:var(--text-dim); display:block; margin-bottom:4px; font-weight:700;">PRE-SELECT ACTIVE PROCEDURE FOR ASTRONAUT:</label>
                    <select class="proc-selector" id="doc-dropdown" onchange="renderSelectedDoc()">
                        <option value="">-- Select Active Procedure --</option>
                    </select>
                </div>
                <input type="text" class="search-box" id="search-input" placeholder="🔍 Search steps..." onkeyup="filterSteps()">
                <div class="doc-steps-list" id="doc-steps-container">
                    <div style="font-size:12px; color:var(--text-dim); text-align:center; padding:15px;">Select a procedure above.</div>
                </div>
            </div>

            <div class="hud-panel">
                <div class="panel-header">
                    <div class="panel-title">🚀 Active EVA Execution Context</div>
                </div>
                <div class="proc-header">
                    <div class="proc-active-title" id="proc-title">AOUDA Standby</div>
                    <div class="proc-active-step" id="proc-desc">Say 'AOUDA' or trigger next step from OPS.</div>
                </div>

                <div class="tft-mirror-box">
                    <div class="tft-mirror-header">
                        <span>🧑‍🚀 ASTRONAUT V-700 TFT DISPLAY MIRROR</span>
                        <span class="tft-mirror-mode" id="ops-tft-mode">MODE: DEFAULT</span>
                    </div>
                    <div style="font-size:12px; color:#fff;" id="ops-tft-preview">"AOUDA: All systems nominal."</div>
                    <div class="view-btn-row">
                        <button class="view-btn" onclick="sendTrigger('set_view:default')">🖥️ Default</button>
                        <button class="view-btn" onclick="sendTrigger('set_view:procedure')">📖 Proc</button>
                        <button class="view-btn" onclick="sendTrigger('set_view:vitals')">📊 Vitals</button>
                        <button class="view-btn" onclick="sendTrigger('set_view:temp_popup')">🌡️ Temp Pop</button>
                        <button class="view-btn" onclick="sendTrigger('set_view:alert')">🚨 Alert</button>
                    </div>
                </div>

                <div class="panel-header" style="margin-top:2px;">
                    <div class="panel-title">🎙️ Live 3D Dialogue Log</div>
                </div>
                <div class="chat-container-3d">
                    <div class="chat-scroll" id="chat-feed">
                        <div class="chat-bubble">
                            <span class="chat-speaker-aouda">AOUDA:</span> <span>AOUDA online. All systems nominal.</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="hud-panel">
                <div class="panel-header">
                    <div class="panel-title">⚡ OPS Ground Overrides</div>
                </div>
                <div class="btn-grid">
                    <button class="hud-btn" onclick="sendTrigger('query:What is the suit temperature?')">🌡️ Show Temp Curve</button>
                    <button class="hud-btn" onclick="sendTrigger('next_step')">▶️ Next Step</button>
                    <button class="hud-btn" onclick="sendTrigger('query:What is the humidity?')">💧 Show Hum Curve</button>
                    <button class="hud-btn" onclick="sendTrigger('query:How do I prepare the Caillou instrument?')">🪨 Caillou Prep</button>
                    <button class="hud-btn hud-btn-danger" onclick="sendTrigger('emergency')">🚨 EMERGENCY SOS</button>
                </div>
                <div style="margin-top:2px;">
                    <label style="font-size:10px; color:var(--text-dim); display:block; margin-bottom:4px; font-weight:700;">OPS DIRECT QUERY:</label>
                    <div class="input-group">
                        <input type="text" class="hud-input" id="custom-query" placeholder="Type question for AOUDA..." onkeypress="if(event.key==='Enter') sendCustomQuery()">
                        <button class="hud-btn" style="padding:6px 12px;" onclick="sendCustomQuery()">SEND</button>
                    </div>
                </div>
                <div class="panel-header" style="margin-top:2px;">
                    <div class="panel-title">📜 Mission Event Log</div>
                </div>
                <div class="doc-steps-list" id="log-feed" style="max-height:80px;">
                    <div style="font-size:11px; color:var(--text-dim);">System initialized.</div>
                </div>
            </div>

        </div>

        <div class="hud-panel" style="margin-top:12px;">
            <div class="panel-header">
                <div class="panel-title">📊 Live Telemetry Smooth Curves</div>
                <div style="font-size:11px; color:var(--cyan-glow); font-weight:700;">💡 Click any curve to enlarge in HD Zoom Window</div>
            </div>
            <div class="hud-bottom-graphs">
                <div class="compact-graph-card" onclick="openZoomFromHUD('temp')">
                    <div style="font-size:11px; color:var(--cyan-glow); font-weight:700; margin-bottom:6px;">🌡️ Temp (°C)</div>
                    <div class="compact-canvas-box"><canvas id="canvas-temp-compact" width="300" height="130"></canvas></div>
                </div>
                <div class="compact-graph-card" onclick="openZoomFromHUD('hum')">
                    <div style="font-size:11px; color:var(--purple-glow); font-weight:700; margin-bottom:6px;">💧 Humidity (%)</div>
                    <div class="compact-canvas-box"><canvas id="canvas-hum-compact" width="300" height="130"></canvas></div>
                </div>
                <div class="compact-graph-card" onclick="openZoomFromHUD('vitals')">
                    <div style="font-size:11px; color:var(--accent-green); font-weight:700; margin-bottom:6px;">💓 Heart Rate (BPM)</div>
                    <div class="compact-canvas-box"><canvas id="canvas-hr-compact" width="300" height="130"></canvas></div>
                </div>
                <div class="compact-graph-card" onclick="openZoomFromHUD('suit')">
                    <div style="font-size:11px; color:var(--blue-glow); font-weight:700; margin-bottom:6px;">🔋 Battery (%)</div>
                    <div class="compact-canvas-box"><canvas id="canvas-bat-compact" width="300" height="130"></canvas></div>
                </div>
            </div>
        </div>
    </div>

    <div class="tab-panel" id="panel-docs" style="display: none;">
        <div class="hud-panel">
            <div class="panel-header">
                <div class="panel-title">📖 Official Mission PDF Documents Viewer</div>
                <select class="proc-selector" id="pdf-doc-dropdown" style="width:360px;" onchange="renderPdfViewer()">
                    <option value="">-- Loading PDF Documents --</option>
                </select>
            </div>
            <div class="pdf-container">
                <iframe id="pdf-viewer-frame" class="pdf-iframe" src=""></iframe>
            </div>
        </div>
    </div>

    <div class="tab-panel" id="panel-charts" style="display: none;">
        <div class="hud-panel">
            <div class="panel-header">
                <div class="panel-title">📈 High-Resolution Telemetry Chart Zoom Window</div>
                <div style="font-size:12px; color:var(--cyan-glow); font-weight:700;" id="zoom-chart-title">Suit Temperature (°C)</div>
            </div>
            <div class="zoom-bar">
                <button class="zoom-btn active-zoom" id="zbtn-temp" onclick="selectZoomChart('temp')">🌡️ DHT11 Temp (°C)</button>
                <button class="zoom-btn" id="zbtn-hum" onclick="selectZoomChart('hum')">💧 DHT11 Humidity (%)</button>
                <button class="zoom-btn" id="zbtn-vitals" onclick="selectZoomChart('vitals')">💓 Cardio & O2</button>
                <button class="zoom-btn" id="zbtn-suit" onclick="selectZoomChart('suit')">🔋 Battery & Pressure</button>
            </div>
            <div class="sensor-stats-bar">
                <div class="stat-box"><span class="stat-label">CURRENT READING</span><span class="stat-val" id="zoom-stat-curr">--</span></div>
                <div class="stat-box"><span class="stat-label">SESSION MAXIMUM</span><span class="stat-val" id="zoom-stat-max">--</span></div>
                <div class="stat-box"><span class="stat-label">SESSION MINIMUM</span><span class="stat-val" id="zoom-stat-min">--</span></div>
                <div class="stat-box"><span class="stat-label">SENSOR HEALTH</span><span class="stat-val" id="zoom-stat-status" style="color:var(--accent-green);">NOMINAL</span></div>
            </div>
            <div class="giant-canvas-box">
                <canvas id="canvas-giant-zoom" width="1000" height="450"></canvas>
            </div>
        </div>
    </div>

    <script>
        let cachedDocs = [], cachedPdfs = [], lastChatLength = 0;
        const maxPoints = 50;
        let timeLabels = [], tempData = [], humData = [], hrData = [], o2Data = [], batData = [];
        let currentZoomSensor = 'temp', activeTabName = 'hud';

        function switchTab(tab) {{
            activeTabName = tab;
            ['hud', 'docs', 'charts'].forEach(t => {{
                document.getElementById('tab-btn-' + t).classList.remove('active-tab');
                document.getElementById('panel-' + t).style.display = 'none';
            }});
            document.getElementById('tab-btn-' + tab).classList.add('active-tab');
            document.getElementById('panel-' + tab).style.display = 'block';
            if (tab === 'docs') renderPdfViewer();
            if (tab === 'charts') renderGiantZoomChart();
        }}

        function openZoomFromHUD(sensor) {{ switchTab('charts'); selectZoomChart(sensor); }}

        // High-End Smooth Bezier Spline Canvas Renderer
        function drawCanvasChart(canvasId, dataList, colorHex, alertLine) {{
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const w = canvas.width, h = canvas.height, padL = 40, padR = 20, padT = 20, padB = 30;
            ctx.clearRect(0, 0, w, h);
            if (!dataList || dataList.length === 0) return;

            let allVals = [...dataList];
            if (alertLine !== undefined) allVals.push(alertLine);
            let minV = Math.min(...allVals), maxV = Math.max(...allVals);
            if (minV === maxV) {{ minV -= 2; maxV += 2; }}
            const range = (maxV - minV) || 1;

            // Grid Lines
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)'; ctx.lineWidth = 1;
            for (let i = 0; i <= 4; i++) {{
                const y = padT + (h - padT - padB) * (i / 4);
                ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
            }}

            if (alertLine !== undefined) {{
                const alertY = padT + (h - padT - padB) * (1 - (alertLine - minV) / range);
                ctx.strokeStyle = '#FF0055'; ctx.setLineDash([4, 4]); ctx.lineWidth = 1.5;
                ctx.beginPath(); ctx.moveTo(padL, alertY); ctx.lineTo(w - padR, alertY); ctx.stroke();
                ctx.setLineDash([]);
            }}

            const coords = dataList.map((val, i) => ({{
                x: padL + (w - padL - padR) * (i / Math.max(dataList.length - 1, 1)),
                y: padT + (h - padT - padB) * (1 - (val - minV) / range)
            }}));

            if (coords.length > 1) {{
                // Gradient Fill Under Spline
                const grad = ctx.createLinearGradient(0, padT, 0, h - padB);
                grad.addColorStop(0, colorHex + '50');
                grad.addColorStop(1, colorHex + '00');
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.moveTo(coords[0].x, coords[0].y);

                for (let i = 0; i < coords.length - 1; i++) {{
                    const xc = (coords[i].x + coords[i + 1].x) / 2;
                    const yc = (coords[i].y + coords[i + 1].y) / 2;
                    ctx.quadraticCurveTo(coords[i].x, coords[i].y, xc, yc);
                }}
                ctx.lineTo(coords[coords.length - 1].x, coords[coords.length - 1].y);
                ctx.lineTo(coords[coords.length - 1].x, h - padB);
                ctx.lineTo(coords[0].x, h - padB);
                ctx.closePath();
                ctx.fill();

                // Glowing Smooth Curve Line
                ctx.strokeStyle = colorHex; ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.moveTo(coords[0].x, coords[0].y);
                for (let i = 0; i < coords.length - 1; i++) {{
                    const xc = (coords[i].x + coords[i + 1].x) / 2;
                    const yc = (coords[i].y + coords[i + 1].y) / 2;
                    ctx.quadraticCurveTo(coords[i].x, coords[i].y, xc, yc);
                }}
                ctx.lineTo(coords[coords.length - 1].x, coords[coords.length - 1].y);
                ctx.stroke();

                // Target Pulse Point
                const last = coords[coords.length - 1];
                ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(last.x, last.y, 4.5, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = colorHex; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(last.x, last.y, 9, 0, Math.PI * 2); ctx.stroke();
            }}
        }}

        function selectZoomChart(sensor) {{
            currentZoomSensor = sensor;
            ['zbtn-temp', 'zbtn-hum', 'zbtn-vitals', 'zbtn-suit'].forEach(id => {{
                document.getElementById(id).classList.remove('active-zoom');
            }});
            document.getElementById('zbtn-' + sensor).classList.add('active-zoom');
            renderGiantZoomChart();
        }}

        function renderGiantZoomChart() {{
            const titleEl = document.getElementById('zoom-chart-title');
            const elCurr = document.getElementById('zoom-stat-curr');
            const elMax = document.getElementById('zoom-stat-max');
            const elMin = document.getElementById('zoom-stat-min');
            const elStatus = document.getElementById('zoom-stat-status');
            let targetData = [], color = '#00F2FE', alertVal = undefined, unit = '';

            if (currentZoomSensor === 'temp') {{ targetData = tempData; color = '#00F2FE'; alertVal = 31.0; unit = '°C'; titleEl.innerText = "Suit Temperature DHT11 (°C)"; }}
            else if (currentZoomSensor === 'hum') {{ targetData = humData; color = '#7928CA'; alertVal = 70.0; unit = '%'; titleEl.innerText = "Relative Humidity DHT11 (%)"; }}
            else if (currentZoomSensor === 'vitals') {{ targetData = hrData; color = '#00FF88'; unit = 'bpm'; titleEl.innerText = "Heart Rate (BPM)"; }}
            else if (currentZoomSensor === 'suit') {{ targetData = batData; color = '#FFD700'; unit = '%'; titleEl.innerText = "Battery Level (%)"; }}

            drawCanvasChart('canvas-giant-zoom', targetData, color, alertVal);
            if (targetData.length > 0) {{
                const curr = targetData[targetData.length - 1];
                if (elCurr) elCurr.innerText = curr.toFixed(1) + ' ' + unit;
                if (elMax) elMax.innerText = Math.max(...targetData).toFixed(1) + ' ' + unit;
                if (elMin) elMin.innerText = Math.min(...targetData).toFixed(1) + ' ' + unit;
                if (elStatus) elStatus.innerText = (alertVal !== undefined && curr > alertVal) ? '🚨 ALERT' : 'NOMINAL';
            }}
        }}

        async function updateDashboard() {{
            try {{
                const res = await fetch('/api/data?t=' + Date.now(), {{ cache: "no-store" }});
                const data = await res.json();
                const nowStr = new Date().toLocaleTimeString();
                const tel = data.telemetry;
                let curTemp = 24.5, curHum = 55.0, curHr = 78, curO2 = 20.9, curBat = 95;

                if (tel.body_temperature && tel.body_temperature.value !== undefined) {{
                    const val = tel.body_temperature.value;
                    const elVal = document.getElementById('temp-val');
                    if (elVal) elVal.innerText = (typeof val === 'number') ? val.toFixed(1) : val;
                    if (typeof val === 'number') curTemp = val;
                }}
                if (tel.humidity_percent && tel.humidity_percent.value !== undefined) {{
                    const val = tel.humidity_percent.value;
                    const elVal = document.getElementById('hum-val');
                    if (elVal) elVal.innerText = (typeof val === 'number') ? val.toFixed(1) : val;
                    if (typeof val === 'number') curHum = val;
                }}
                if (tel.o2_percent) {{ curO2 = Number(tel.o2_percent.value); document.getElementById('o2-val').innerText = curO2.toFixed(1); }}
                if (tel.co2_ppm) document.getElementById('co2-val').innerText = Number(tel.co2_ppm.value).toFixed(0);
                if (tel.heart_rate) {{ curHr = Number(tel.heart_rate.value); document.getElementById('hr-val').innerText = curHr.toFixed(0); }}
                if (tel.suit_pressure_hpa) document.getElementById('pres-val').innerText = Number(tel.suit_pressure_hpa.value).toFixed(0);
                if (tel.battery_percent) {{ curBat = Number(tel.battery_percent.value); document.getElementById('bat-val').innerText = curBat.toFixed(0); }}

                timeLabels.push(nowStr); tempData.push(curTemp); humData.push(curHum); hrData.push(curHr); o2Data.push(curO2); batData.push(curBat);
                if (timeLabels.length > maxPoints) {{ timeLabels.shift(); tempData.shift(); humData.shift(); hrData.shift(); o2Data.shift(); batData.shift(); }}

                if (activeTabName === 'hud') {{
                    drawCanvasChart('canvas-temp-compact', tempData, '#00F2FE');
                    drawCanvasChart('canvas-hum-compact', humData, '#7928CA');
                    drawCanvasChart('canvas-hr-compact', hrData, '#00FF88');
                    drawCanvasChart('canvas-bat-compact', batData, '#FFD700');
                }} else if (activeTabName === 'charts') {{
                    renderGiantZoomChart();
                }}

                // TFT Display Mirror update
                const modeEl = document.getElementById('ops-tft-mode');
                const prevEl = document.getElementById('ops-tft-preview');
                if (modeEl) modeEl.innerText = "MODE: " + (data.astronaut_view || "DEFAULT").toUpperCase();
                if (prevEl && data.chat && data.chat.length > 0) {{
                    const lastMsg = data.chat[data.chat.length - 1];
                    prevEl.innerText = `"${{lastMsg.speaker}}: ${{lastMsg.text}}"`;
                }}

                // Active Procedure
                const proc = data.procedure;
                if (proc) {{
                    document.getElementById('proc-title').innerText = (proc.title || 'AOUDA Standby') + ((proc.step && proc.step > 0) ? ' — Step ' + proc.step : '');
                    document.getElementById('proc-desc').innerText = proc.instruction || 'Say "AOUDA" or trigger next step.';
                }}

                // Dialogue Feed
                if (data.chat && data.chat.length > 0) {{
                    const chatContainer = document.getElementById('chat-feed');
                    if (chatContainer) {{
                        chatContainer.innerHTML = '';
                        data.chat.forEach(msg => {{
                            const box = document.createElement('div');
                            box.className = 'chat-bubble';
                            const spClass = (msg.speaker === 'Astronaut') ? 'chat-speaker-astro' : 'chat-speaker-aouda';
                            box.innerHTML = `<span class="${{spClass}}">${{msg.speaker}}:</span> <span>"${{msg.text}}"</span><span class="chat-time">${{msg.time}}</span>`;
                            chatContainer.appendChild(box);
                        }});
                        if (data.chat.length !== lastChatLength) {{
                            lastChatLength = data.chat.length;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        }}
                    }}
                }}

                if (data.documents && cachedDocs.length === 0) {{ cachedDocs = data.documents; populateDocDropdown(); }}
                if (data.pdf_documents && cachedPdfs.length === 0) {{ cachedPdfs = data.pdf_documents; populatePdfDropdown(); }}

                if (data.events && data.events.length > 0) {{
                    const logContainer = document.getElementById('log-feed');
                    if (logContainer) {{
                        logContainer.innerHTML = '';
                        data.events.forEach(ev => {{
                            const item = document.createElement('div');
                            item.style.fontSize = '11px'; item.style.color = 'var(--text-dim)';
                            item.innerHTML = `<span style="color:var(--cyan-glow); margin-right:6px;">${{ev.time}}</span>${{ev.event}}`;
                            logContainer.appendChild(item);
                        }});
                    }}
                }}
            }} catch (e) {{}}
        }}

        function populateDocDropdown() {{
            const select1 = document.getElementById('doc-dropdown');
            if (!select1) return;
            select1.innerHTML = '<option value="">-- Choose Procedure --</option>';
            cachedDocs.forEach(doc => {{
                const opt = document.createElement('option'); opt.value = doc.id; opt.innerText = doc.title; select1.appendChild(opt);
            }});
            if (cachedDocs.length > 0) {{ select1.selectedIndex = 1; renderSelectedDoc(); }}
        }}

        function populatePdfDropdown() {{
            const select2 = document.getElementById('pdf-doc-dropdown');
            if (!select2) return;
            select2.innerHTML = '<option value="">-- Select PDF Manual --</option>';
            cachedPdfs.forEach(pdf => {{
                const opt = document.createElement('option'); opt.value = pdf.url; opt.innerText = pdf.title; select2.appendChild(opt);
            }});
            if (cachedPdfs.length > 0) {{ select2.selectedIndex = 1; renderPdfViewer(); }}
        }}

        function renderSelectedDoc() {{
            const select = document.getElementById('doc-dropdown');
            const container = document.getElementById('doc-steps-container');
            if (!select || !container) return;
            container.innerHTML = '';
            const doc = cachedDocs.find(d => d.id === select.value);
            if (!doc || !doc.steps) return;
            doc.steps.forEach(stepText => {{
                const item = document.createElement('div'); item.className = 'step-item';
                item.innerHTML = `<span>${{stepText}}</span> <button class="step-btn-push" onclick="sendTrigger('query:${{stepText}}')">ACTIVATE</button>`;
                container.appendChild(item);
            }});
        }}

        function renderPdfViewer() {{
            const select = document.getElementById('pdf-doc-dropdown');
            const iframe = document.getElementById('pdf-viewer-frame');
            if (!iframe) return;
            const pdfUrl = (select && select.value) ? select.value : (cachedPdfs.length > 0 ? cachedPdfs[0].url : '');
            if (pdfUrl && iframe.src !== window.location.origin + pdfUrl) iframe.src = pdfUrl;
        }}

        function filterSteps() {{
            const input = document.getElementById('search-input');
            if (!input) return;
            const query = input.value.toLowerCase();
            document.querySelectorAll('.step-item').forEach(item => {{
                item.style.display = item.innerText.toLowerCase().includes(query) ? 'flex' : 'none';
            }});
        }}

        function sendCustomQuery() {{
            const input = document.getElementById('custom-query');
            if (!input) return;
            const query = input.value.trim();
            if (!query) return;
            sendTrigger('query:' + query);
            input.value = '';
        }}

        async function sendTrigger(cmd) {{
            try {{
                await fetch('/api/trigger?cmd=' + encodeURIComponent(cmd), {{ cache: "no-store" }});
                updateDashboard();
            }} catch (e) {{}}
        }}

        setInterval(updateDashboard, 800);
        updateDashboard();
    </script>
</body>
</html>
"""


# =====================================================================
# 2. ASTRONAUT V-700 TFT HELMET HUD HTML (Futuristic Sci-Fi HUD Redesign)
# =====================================================================
DASHBOARD_ASTRONAUT_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ÖWF AMADEE-27 — Astronaut Helmet V-700 TFT Display</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800;900&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #030712;
            --card-bg: rgba(13, 22, 44, 0.9);
            --cyan: #00F2FE;
            --green: #00FF88;
            --red: #FF0055;
            --yellow: #FFD700;
            --purple: #7928CA;
            --text-dim: #94A3B8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Orbitron', sans-serif; }}
        body {{
            background-color: var(--bg);
            background-image: 
                radial-gradient(circle at 50% 50%, rgba(0, 242, 254, 0.08) 0%, transparent 60%),
                linear-gradient(rgba(0, 242, 254, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 242, 254, 0.03) 1px, transparent 1px);
            background-size: 100% 100%, 35px 35px, 35px 35px;
            color: #fff;
            padding: 12px;
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
        }}

        /* Sci-Fi HUD Corner Bracket Reticles */
        body::before {{
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0, 242, 254, 0.02) 50%, rgba(0, 242, 254, 0.02));
            background-size: 100% 4px; pointer-events: none; z-index: 100;
        }}

        .top-bar {{
            display: flex; justify-content: space-between; align-items: center;
            background: rgba(13, 22, 44, 0.85); backdrop-filter: blur(20px);
            border: 1.5px solid var(--cyan); padding: 8px 16px; border-radius: 14px;
            box-shadow: 0 0 25px rgba(0, 242, 254, 0.35); z-index: 10;
        }}
        .logo-box-ast {{ display: flex; align-items: center; gap: 14px; }}
        .suit-badge {{ font-size: 14px; font-weight: 900; color: var(--cyan); letter-spacing: 2px; text-shadow: 0 0 10px var(--cyan); }}
        .top-pills {{ display: flex; gap: 12px; align-items: center; font-size: 12px; font-weight: 700; }}
        .pill-btn {{
            display: flex; align-items: center; gap: 6px; background: rgba(0, 242, 254, 0.12);
            border: 1px solid var(--cyan); padding: 5px 10px; border-radius: 8px; cursor: pointer; transition: all 0.25s;
            box-shadow: 0 0 8px rgba(0,242,254,0.2);
        }}
        .pill-btn:hover {{ background: var(--cyan); color: #000; box-shadow: 0 0 18px var(--cyan); transform: scale(1.05); }}

        .hud-main-view {{
            flex: 1; margin: 10px 0; display: flex; flex-direction: column; justify-content: space-between;
            position: relative; z-index: 10; perspective: 1000px;
        }}

        /* 3D Floating Speech Log Card */
        .speech-card-3d {{
            background: rgba(13, 22, 44, 0.95); backdrop-filter: blur(20px);
            border: 2px solid var(--cyan); border-radius: 16px; padding: 16px; margin-bottom: 10px;
            box-shadow: 0 15px 40px rgba(0, 242, 254, 0.3); position: relative; overflow: hidden;
            transform: rotateX(1.5deg); transition: all 0.3s ease;
        }}
        .speech-card-3d::before {{
            content: ''; position: absolute; top: 0; left: 0; width: 5px; height: 100%;
            background: linear-gradient(to bottom, var(--green), var(--cyan));
        }}
        .speech-speaker {{ font-size: 11px; color: var(--green); font-weight: 900; letter-spacing: 1.5px; margin-bottom: 4px; display: flex; justify-content: space-between; }}
        .speech-text {{ font-family: 'Rajdhani', sans-serif; font-size: 24px; font-weight: 700; color: #fff; line-height: 1.35; text-shadow: 0 0 8px rgba(255,255,255,0.2); }}

        /* Large Center 3D Active Speech Modal Overlay */
        .speech-center-overlay {{
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) scale(0.9);
            width: 92%; background: rgba(3, 7, 18, 0.97); backdrop-filter: blur(25px);
            border: 3px solid var(--green); border-radius: 18px; padding: 26px; text-align: center;
            box-shadow: 0 0 50px rgba(0, 255, 136, 0.55); opacity: 0; pointer-events: none;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 50;
        }}
        .speech-center-overlay.active-speech-pop {{
            opacity: 1; pointer-events: auto; transform: translate(-50%, -50%) scale(1);
        }}
        .speech-center-title {{ font-size: 13px; color: var(--green); font-weight: 900; letter-spacing: 2px; margin-bottom: 8px; }}
        .speech-center-body {{ font-family: 'Rajdhani', sans-serif; font-size: 32px; font-weight: 700; color: #fff; line-height: 1.3; text-shadow: 0 0 15px var(--green); }}

        /* Sleek Glowing Active Procedure Banner (Only visible when procedure active) */
        .active-proc-banner {{
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.25), rgba(121, 40, 202, 0.25));
            border: 2px solid var(--cyan); border-radius: 14px; padding: 12px 18px; margin-bottom: 10px;
            display: none; justify-content: space-between; align-items: center; box-shadow: 0 0 25px rgba(0, 242, 254, 0.4);
        }}
        .proc-banner-title {{ font-size: 14px; font-weight: 900; color: #fff; letter-spacing: 1.5px; }}
        .proc-banner-step {{ font-family: 'Rajdhani', sans-serif; font-size: 20px; font-weight: 700; color: var(--green); text-shadow: 0 0 10px var(--green); }}

        .tft-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; }}
        .tft-gauge {{
            background: rgba(13, 22, 44, 0.85); backdrop-filter: blur(16px);
            border: 1.5px solid rgba(0, 242, 254, 0.2); border-radius: 14px; padding: 14px;
            text-align: center; cursor: pointer; transition: all 0.3s; transform-style: preserve-3d;
            box-shadow: 0 6px 20px rgba(0,0,0,0.4);
        }}
        .tft-gauge:hover {{ transform: translateZ(12px) translateY(-2px); border-color: var(--cyan); background: rgba(0, 242, 254, 0.15); box-shadow: 0 0 20px rgba(0, 242, 254, 0.4); }}
        .tft-lbl {{ font-size: 10px; color: var(--text-dim); text-transform: uppercase; margin-bottom: 4px; font-weight: 700; letter-spacing: 0.5px; }}
        .tft-val {{ font-size: 26px; font-weight: 900; color: #fff; text-shadow: 0 0 8px rgba(255,255,255,0.3); }}
        .tft-unit {{ font-size: 12px; color: var(--cyan); margin-left: 2px; }}

        /* ULTRA-PREMIUM SCI-FI HUD HOLOGRAM MODAL OVERLAY FOR LIVE TELEMETRY CURVES */
        .sensor-popup-modal {{
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(3, 7, 18, 0.96); backdrop-filter: blur(25px);
            border: 3px solid var(--cyan); padding: 22px; display: flex; flex-direction: column;
            justify-content: space-between; box-shadow: 0 0 60px rgba(0, 242, 254, 0.65);
            opacity: 0; pointer-events: none; transform: translateY(40px) scale(0.96);
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 99999;
        }}
        .sensor-popup-modal.active-popup {{
            opacity: 1; pointer-events: auto; transform: translateY(0) scale(1);
        }}

        .popup-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .popup-title-group {{ display: flex; align-items: center; gap: 12px; }}
        .popup-title {{ font-size: 18px; font-weight: 900; color: var(--cyan); letter-spacing: 2px; text-shadow: 0 0 12px var(--cyan); }}
        .popup-badge {{ background: rgba(0, 255, 136, 0.15); border: 1px solid var(--green); color: var(--green); padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 900; }}
        .popup-close-btn {{
            background: linear-gradient(135deg, rgba(255, 0, 85, 0.25), rgba(239, 68, 68, 0.25));
            border: 1.5px solid var(--red); color: var(--red);
            padding: 8px 18px; border-radius: 10px; font-weight: 900; font-size: 12px; cursor: pointer; transition: all 0.3s;
            box-shadow: 0 0 12px rgba(255,0,85,0.3);
        }}
        .popup-close-btn:hover {{ background: var(--red); color: #fff; box-shadow: 0 0 25px var(--red); transform: scale(1.05); }}

        .popup-body {{ display: grid; grid-template-columns: 280px 1fr; gap: 20px; align-items: stretch; flex: 1; margin: 12px 0; }}
        .popup-sidebar {{ display: flex; flex-direction: column; gap: 12px; }}
        .popup-metric-box {{
            text-align: center; background: rgba(13, 22, 44, 0.95); border: 2px solid var(--cyan);
            border-radius: 16px; padding: 22px 14px; box-shadow: 0 0 25px rgba(0,242,254,0.3);
        }}
        .popup-metric-val {{ font-size: 58px; font-weight: 900; color: #fff; text-shadow: 0 0 25px var(--cyan); line-height: 1; }}
        .popup-metric-unit {{ font-size: 16px; color: var(--cyan); font-weight: 700; margin-top: 8px; letter-spacing: 1px; }}
        
        .popup-stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .pstat-card {{ background: rgba(13, 22, 44, 0.8); border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 8px; text-align: center; }}
        .pstat-lbl {{ font-size: 9px; color: var(--text-dim); text-transform: uppercase; font-weight: 700; }}
        .pstat-val {{ font-size: 15px; font-weight: 900; color: #fff; margin-top: 2px; }}

        .popup-chart-box {{
            background: radial-gradient(circle at 50% 50%, rgba(0, 242, 254, 0.05) 0%, #040814 80%);
            border: 2px solid rgba(0, 242, 254, 0.4); border-radius: 16px; height: 100%; min-height: 260px;
            position: relative; padding: 12px; box-shadow: inset 0 0 30px rgba(0,242,254,0.15);
        }}
        
        .popup-progress-bar {{ width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: 8px; }}
        .popup-progress-fill {{ height: 100%; background: linear-gradient(90deg, var(--cyan), var(--green)); width: 100%; transition: width 0.1s linear; }}

        /* Context-Sensitive Procedure Actions Footer */
        .proc-actions-footer {{
            background: rgba(13, 22, 44, 0.95); backdrop-filter: blur(20px);
            border: 2px solid var(--cyan); border-radius: 12px; padding: 10px 18px;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 0 20px rgba(0, 242, 254, 0.35); z-index: 10;
        }}
        .proc-actions-title {{ font-size: 12px; color: var(--cyan); font-weight: 900; letter-spacing: 1.5px; }}
        .action-badges {{ display: flex; gap: 14px; align-items: center; }}
        .act-badge {{
            background: rgba(0, 242, 254, 0.15); border: 1.5px solid var(--cyan); color: #fff;
            padding: 5px 14px; border-radius: 8px; font-size: 11px; font-weight: 900; letter-spacing: 1px;
            box-shadow: 0 0 10px rgba(0,242,254,0.3);
        }}
        .act-badge-next {{ background: rgba(0, 255, 136, 0.2); border-color: var(--green); color: var(--green); box-shadow: 0 0 10px rgba(0,255,136,0.3); }}
        .act-badge-stop {{ background: rgba(255, 0, 85, 0.2); border-color: var(--red); color: var(--red); box-shadow: 0 0 10px rgba(255,0,85,0.3); }}
    </style>
</head>
<body>

    <div class="top-bar">
        <div class="logo-box-ast">
            {HTML_OWF_LOGO_IMG}
            <div class="suit-badge">AOUDA-X // HELMET V-700</div>
        </div>
        <div class="top-pills">
            <div class="pill-btn" onclick="openPopupDirect('temp_popup')">TEMP: <span id="tft-top-temp" style="color:var(--cyan);">24.5°C</span></div>
            <div class="pill-btn" onclick="openPopupDirect('hum_popup')">HUM: <span id="tft-top-hum" style="color:var(--purple);">55.0%</span></div>
            <div class="pill-btn" onclick="openPopupDirect('hr_popup')">HR: <span id="tft-top-hr" style="color:var(--green);">78 bpm</span></div>
            <div class="pill-item" style="padding: 5px 10px; background: rgba(255,255,255,0.05); border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">BAT: <span id="tft-top-bat" style="color:var(--yellow);">95%</span></div>
        </div>
    </div>

    <div class="hud-main-view">

        <!-- Center Large 3D Active Speech Modal Overlay -->
        <div class="speech-center-overlay" id="tft-speech-pop-modal">
            <div class="speech-center-title">🎙️ AOUDA VOICE SYNTHESIS</div>
            <div class="speech-center-body" id="tft-speech-pop-text">"AOUDA online. All systems nominal."</div>
        </div>

        <!-- 3D Floating Speech Log Card -->
        <div class="speech-card-3d">
            <div class="speech-speaker">
                <span>🎙️ AOUDA VOICE DIALOGUE STREAM</span>
                <span style="font-size:10px; color:var(--cyan);">ONLINE // AMADEE-27</span>
            </div>
            <div class="speech-text" id="tft-speech-text">"AOUDA online. All systems nominal. AMADEE-27 HUD active."</div>
        </div>

        <!-- Active Procedure Banner (Only visible when Ground OPS selects a procedure) -->
        <div class="active-proc-banner" id="active-proc-banner">
            <div>
                <div style="font-size:10px; color:var(--cyan); letter-spacing:1px; font-weight:900;">📖 ACTIVE MISSION PROCEDURE</div>
                <div class="proc-banner-title" id="proc-banner-title">Caillou Spectrometer</div>
            </div>
            <div class="proc-banner-step" id="proc-banner-step">Step 1: Power on synthetic Raman spectrometer</div>
        </div>

        <!-- 4 Primary Suit Gauges -->
        <div class="tft-grid">
            <div class="tft-gauge" id="tft-g-temp" onclick="openPopupDirect('temp_popup')">
                <div class="tft-lbl">SUIT TEMP (CLICK FOR CURVE)</div>
                <div class="tft-val" id="tft-val-temp">24.5<span class="tft-unit">°C</span></div>
            </div>
            <div class="tft-gauge" id="tft-g-hum" onclick="openPopupDirect('hum_popup')">
                <div class="tft-lbl">HUMIDITY (CLICK FOR CURVE)</div>
                <div class="tft-val" id="tft-val-hum">55.0<span class="tft-unit">%</span></div>
            </div>
            <div class="tft-gauge" onclick="openPopupDirect('hr_popup')">
                <div class="tft-lbl">HEART RATE (CLICK FOR CURVE)</div>
                <div class="tft-val" id="tft-val-hr">78<span class="tft-unit">bpm</span></div>
            </div>
            <div class="tft-gauge">
                <div class="tft-lbl">SUIT BATTERY</div>
                <div class="tft-val" id="tft-val-bat">95<span class="tft-unit">%</span></div>
            </div>
        </div>

    </div>

    <!-- ULTRA-PREMIUM SCI-FI HUD HOLOGRAM MODAL OVERLAY FOR REAL-TIME TELEMETRY CURVE -->
    <div class="sensor-popup-modal" id="sensor-popup-modal">
        <div class="popup-header">
            <div class="popup-title-group">
                <div class="popup-title" id="pop-sensor-title">🌡️ REAL-TIME TELEMETRY TREND (DHT11)</div>
                <div class="popup-badge" id="pop-sensor-badge">SYSTEM NOMINAL</div>
            </div>
            <button class="popup-close-btn" onclick="closePopupDirect()">❌ CLOSE OVERLAY</button>
        </div>
        <div class="popup-body">
            <div class="popup-sidebar">
                <div class="popup-metric-box">
                    <div class="popup-metric-val" id="pop-metric-val">24.5</div>
                    <div class="popup-metric-unit" id="pop-metric-unit">DEGREES CELSIUS</div>
                </div>
                <div class="popup-stats-grid">
                    <div class="pstat-card"><div class="pstat-lbl">PEAK MAX</div><div class="pstat-val" id="pop-stat-max">25.1</div></div>
                    <div class="pstat-card"><div class="pstat-lbl">MIN LOW</div><div class="pstat-val" id="pop-stat-min">23.9</div></div>
                    <div class="pstat-card"><div class="pstat-lbl">AVERAGE</div><div class="pstat-val" id="pop-stat-avg">24.5</div></div>
                    <div class="pstat-card"><div class="pstat-lbl">DRIFT RATE</div><div class="pstat-val" style="color:var(--green);" id="pop-stat-drift">STABLE</div></div>
                </div>
            </div>
            <div class="popup-chart-box" id="popup-chart-container">
                <canvas id="canvas-popup-chart"></canvas>
            </div>
        </div>
        <div class="popup-progress-bar">
            <div class="popup-progress-fill" id="pop-progress-bar"></div>
        </div>
    </div>

    <!-- Context-Sensitive Procedure Actions Footer -->
    <div class="proc-actions-footer" id="tft-proc-footer" style="display:none;">
        <div class="proc-actions-title">🗣️ VOICE SHORTCUTS:</div>
        <div class="action-badges">
            <div class="act-badge act-badge-next">⏩ SAY "NEXT"</div>
            <div class="act-badge">🔄 SAY "REPEAT"</div>
            <div class="act-badge act-badge-stop">🛑 SAY "STOP"</div>
        </div>
        <div style="font-size:11px; color:var(--text-dim); font-weight:700;" id="tft-clock-str">12:00:00</div>
    </div>

    <script>
        let currentPopupMode = 'none';
        const maxPoints = 45;
        let timeLabels = [], tempData = [], humData = [], hrData = [];
        let lastSpeechText = "";

        // Pre-fill telemetry arrays so real-time curves are ALWAYS visible immediately
        for (let i = 0; i < 30; i++) {{
            tempData.push(24.5 + (Math.sin(i / 3) * 0.4));
            humData.push(55.0 + (Math.cos(i / 3) * 0.8));
            hrData.push(78 + Math.floor(Math.sin(i / 2) * 2));
        }}

        function openPopupDirect(mode) {{
            fetch('/api/trigger?cmd=set_view:' + mode);
        }}

        function closePopupDirect() {{
            fetch('/api/trigger?cmd=set_view:default');
        }}

        // State-of-the-Art Smooth Quadratic Bezier Spline Renderer with Glow Effects
        function drawAnimatedPopupChart(dataList, colorHex) {{
            const container = document.getElementById('popup-chart-container');
            const canvas = document.getElementById('canvas-popup-chart');
            if (!canvas || !container) return;
            
            // Dynamically size canvas to container bounds
            canvas.width = container.clientWidth - 24;
            canvas.height = container.clientHeight - 24;

            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const w = canvas.width, h = canvas.height, padL = 45, padR = 25, padT = 25, padB = 35;
            ctx.clearRect(0, 0, w, h);
            if (!dataList || dataList.length === 0) return;

            let minV = Math.min(...dataList), maxV = Math.max(...dataList);
            if (minV === maxV) {{ minV -= 2; maxV += 2; }}
            const range = (maxV - minV) || 1;

            // Background Grid Scanlines
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)'; ctx.lineWidth = 1;
            for (let i = 0; i <= 5; i++) {{
                const y = padT + (h - padT - padB) * (i / 5);
                ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
                
                // Axis Label
                const gridVal = maxV - (range * (i / 5));
                ctx.fillStyle = 'rgba(148, 163, 184, 0.6)'; ctx.font = '10px Rajdhani';
                ctx.fillText(gridVal.toFixed(1), 8, y + 4);
            }}

            const coords = dataList.map((val, i) => ({{
                x: padL + (w - padL - padR) * (i / Math.max(dataList.length - 1, 1)),
                y: padT + (h - padT - padB) * (1 - (val - minV) / range)
            }}));

            if (coords.length > 1) {{
                // Gradient Fill Under Bezier Curve
                const grad = ctx.createLinearGradient(0, padT, 0, h - padB);
                grad.addColorStop(0, colorHex + '55');
                grad.addColorStop(0.6, colorHex + '15');
                grad.addColorStop(1, colorHex + '00');
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.moveTo(coords[0].x, coords[0].y);

                for (let i = 0; i < coords.length - 1; i++) {{
                    const xc = (coords[i].x + coords[i + 1].x) / 2;
                    const yc = (coords[i].y + coords[i + 1].y) / 2;
                    ctx.quadraticCurveTo(coords[i].x, coords[i].y, xc, yc);
                }}
                ctx.lineTo(coords[coords.length - 1].x, coords[coords.length - 1].y);
                ctx.lineTo(coords[coords.length - 1].x, h - padB);
                ctx.lineTo(coords[0].x, h - padB);
                ctx.closePath();
                ctx.fill();

                // Glowing Smooth Curve Line
                ctx.strokeStyle = colorHex; ctx.lineWidth = 3.5;
                ctx.beginPath();
                ctx.moveTo(coords[0].x, coords[0].y);
                for (let i = 0; i < coords.length - 1; i++) {{
                    const xc = (coords[i].x + coords[i + 1].x) / 2;
                    const yc = (coords[i].y + coords[i + 1].y) / 2;
                    ctx.quadraticCurveTo(coords[i].x, coords[i].y, xc, yc);
                }}
                ctx.lineTo(coords[coords.length - 1].x, coords[coords.length - 1].y);
                ctx.stroke();

                // Animated Target Reticle & Glowing Pulse Point
                const last = coords[coords.length - 1];
                ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(last.x, last.y, 5, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = colorHex; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(last.x, last.y, 12, 0, Math.PI * 2); ctx.stroke();
                ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(last.x, last.y, 18, 0, Math.PI * 2); ctx.stroke();
            }}
        }}

        async function updateTftDisplay() {{
            try {{
                const res = await fetch('/api/data?t=' + Date.now(), {{ cache: "no-store" }});
                const data = await res.json();
                const nowStr = new Date().toLocaleTimeString();
                document.getElementById('tft-clock-str').innerText = nowStr;

                const tel = data.telemetry;
                let tVal = 24.5, hVal = 55.0, o2Val = 20.9, hrVal = 78, bVal = 95;

                if (tel.body_temperature && typeof tel.body_temperature.value === 'number') tVal = tel.body_temperature.value;
                if (tel.humidity_percent && typeof tel.humidity_percent.value === 'number') hVal = tel.humidity_percent.value;
                if (tel.o2_percent && typeof tel.o2_percent.value === 'number') o2Val = tel.o2_percent.value;
                if (tel.heart_rate && typeof tel.heart_rate.value === 'number') hrVal = tel.heart_rate.value;
                if (tel.battery_percent && typeof tel.battery_percent.value === 'number') bVal = tel.battery_percent.value;

                tempData.push(tVal); humData.push(hVal); hrData.push(hrVal);
                if (tempData.length > maxPoints) {{ tempData.shift(); humData.shift(); hrData.shift(); }}

                document.getElementById('tft-top-temp').innerText = tVal.toFixed(1) + '°C';
                document.getElementById('tft-top-hum').innerText = hVal.toFixed(1) + '%';
                document.getElementById('tft-top-hr').innerText = hrVal.toFixed(0) + ' bpm';
                document.getElementById('tft-top-bat').innerText = bVal.toFixed(0) + '%';

                document.getElementById('tft-val-temp').innerHTML = tVal.toFixed(1) + '<span class="tft-unit">°C</span>';
                document.getElementById('tft-val-hum').innerHTML = hVal.toFixed(1) + '<span class="tft-unit">%</span>';
                document.getElementById('tft-val-hr').innerHTML = hrVal.toFixed(0) + '<span class="tft-unit">bpm</span>';
                document.getElementById('tft-val-bat').innerHTML = bVal.toFixed(0) + '<span class="tft-unit">%</span>';

                // Active Speech 3D Center Popup Animation
                if (data.chat && data.chat.length > 0) {{
                    const lastMsg = data.chat[data.chat.length - 1];
                    const fullSpeech = `"${{lastMsg.speaker}}: ${{lastMsg.text}}"`;
                    document.getElementById('tft-speech-text').innerText = fullSpeech;

                    const speechAge = data.speech_age_sec || 0;
                    const popModal = document.getElementById('tft-speech-pop-modal');
                    const popText = document.getElementById('tft-speech-pop-text');
                    if (speechAge < 4.5 && lastSpeechText !== fullSpeech) {{
                        popText.innerText = fullSpeech;
                        popModal.classList.add('active-speech-pop');
                    }} else if (speechAge >= 4.5) {{
                        popModal.classList.remove('active-speech-pop');
                    }}
                }}

                // Active Procedure Banner
                const procBanner = document.getElementById('active-proc-banner');
                const procFooter = document.getElementById('tft-proc-footer');
                if (data.procedure && data.procedure.title && data.procedure.title !== 'AOUDA Standby') {{
                    document.getElementById('proc-banner-title').innerText = (data.procedure.title || 'PROCEDURE').toUpperCase();
                    document.getElementById('proc-banner-step').innerText = "▶ " + (data.procedure.instruction || 'Step active');
                    procBanner.style.display = 'flex';
                    if (procFooter) procFooter.style.display = 'flex';
                }} else {{
                    procBanner.style.display = 'none';
                    if (procFooter) procFooter.style.display = 'none';
                }}

                // Ultra-Premium Sci-Fi HUD Hologram Modal Overlay for Real-Time Telemetry Curve
                const viewMode = data.astronaut_view || 'default';
                const popupModal = document.getElementById('sensor-popup-modal');
                if (viewMode.endsWith('_popup')) {{
                    popupModal.classList.add('active-popup');
                    let targetData = tempData, metricVal = tVal.toFixed(1), unitStr = "DEGREES CELSIUS", titleStr = "🌡️ REAL-TIME SUIT TEMPERATURE TREND (DHT11)", colorHex = "#00F2FE";
                    if (viewMode === 'hum_popup') {{ targetData = humData; metricVal = hVal.toFixed(1); unitStr = "RELATIVE HUMIDITY %"; titleStr = "💧 REAL-TIME SUIT HUMIDITY TREND (DHT11)"; colorHex = "#7928CA"; }}
                    else if (viewMode === 'hr_popup') {{ targetData = hrData; metricVal = hrVal.toFixed(0); unitStr = "BEATS PER MINUTE"; titleStr = "💓 CARDIO HEART RATE TREND"; colorHex = "#00FF88"; }}

                    document.getElementById('pop-sensor-title').innerText = titleStr;
                    document.getElementById('pop-metric-val').innerText = metricVal;
                    document.getElementById('pop-metric-unit').innerText = unitStr;

                    // Update Sidebar Stats
                    if (targetData.length > 0) {{
                        const pMax = Math.max(...targetData);
                        const pMin = Math.min(...targetData);
                        const pAvg = (targetData.reduce((a, b) => a + b, 0) / targetData.length);
                        document.getElementById('pop-stat-max').innerText = pMax.toFixed(1);
                        document.getElementById('pop-stat-min').innerText = pMin.toFixed(1);
                        document.getElementById('pop-stat-avg').innerText = pAvg.toFixed(1);
                    }}

                    drawAnimatedPopupChart(targetData, colorHex);

                    const rem = data.popup_remaining || 0;
                    const pct = Math.min(100, Math.max(0, (rem / 10.0) * 100));
                    document.getElementById('pop-progress-bar').style.width = pct + '%';
                }} else {{
                    popupModal.classList.remove('active-popup');
                }}

            }} catch(e) {{}}
        }}

        setInterval(updateTftDisplay, 800);
        updateTftDisplay();
    </script>
</body>
</html>
"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server ensuring OPS and Astronaut requests never block each other."""
    daemon_threads = True
    allow_reuse_address = True


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler supporting OPS Workstation and Astronaut V-700 TFT Display."""

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/ops" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(DASHBOARD_OPS_HTML.encode("utf-8"))

            elif self.path == "/astronaut" or self.path == "/tft":
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
                self.end_headers()
                self.wfile.write(DASHBOARD_ASTRONAUT_HTML.encode("utf-8"))

            elif self.path == "/assets/owf_logo.png" or self.path == "/owf_logo.png":
                logo_path = Path("data/assets/owf_logo.png")
                if logo_path.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(logo_path.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()

            elif self.path.startswith("/api/data"):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(json.dumps(STATE.get_full_snapshot()).encode("utf-8"))

            elif self.path.startswith("/api/trigger"):
                cmd = "unknown"
                if "cmd=" in self.path:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    cmd = parsed.get("cmd", ["unknown"])[0]

                # Immediate detection of sensor queries or view switches
                cmd_lower = cmd.lower()
                if cmd.startswith("set_view:"):
                    view_mode = cmd.split("set_view:")[1]
                    duration = 10.0 if view_mode.endswith("_popup") else 0.0
                    STATE.set_astronaut_view(view_mode, duration_sec=duration)
                elif any(kw in cmd_lower for kw in ["temp", "temperature", "température", "thermal", "heat", "chaleur"]):
                    STATE.set_astronaut_view("temp_popup", duration_sec=10.0)
                    STATE.add_command(cmd)
                    STATE.add_event(f"Ground Control trigger: [{cmd}]")
                elif any(kw in cmd_lower for kw in ["humidity", "humidité", "hum"]):
                    STATE.set_astronaut_view("hum_popup", duration_sec=10.0)
                    STATE.add_command(cmd)
                    STATE.add_event(f"Ground Control trigger: [{cmd}]")
                elif any(kw in cmd_lower for kw in ["heart", "pulse", "cardiac", "bpm", "pouls", "coeur"]):
                    STATE.set_astronaut_view("hr_popup", duration_sec=10.0)
                    STATE.add_command(cmd)
                    STATE.add_event(f"Ground Control trigger: [{cmd}]")
                elif any(kw in cmd_lower for kw in ["capteur", "capteurs", "sensor", "sensors", "vitals"]):
                    STATE.set_astronaut_view("temp_popup", duration_sec=10.0)
                    STATE.add_command(cmd)
                    STATE.add_event(f"Ground Control trigger: [{cmd}]")
                else:
                    STATE.add_command(cmd)
                    STATE.add_event(f"Ground Control trigger: [{cmd}]")

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "command": cmd}).encode("utf-8"))

            elif self.path.startswith("/pdf/"):
                import urllib.parse
                filename = urllib.parse.unquote(os.path.basename(self.path))
                pdf_file = Path("data/pdf_documents") / filename
                if pdf_file.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "application/pdf")
                    self.send_header("Content-Disposition", f"inline; filename=\"{filename}\"")
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.end_headers()
                    self.wfile.write(pdf_file.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()

            else:
                self.send_response(404)
                self.end_headers()
        except Exception:
            pass

    def log_message(self, format, *args):
        """Suppress default HTTP log spam."""
        pass


def run_dashboard_server(port: int = 8501) -> threading.Thread:
    """Run the web dashboard HTTP server in a background daemon thread."""
    server_address = ("127.0.0.1", port)
    httpd = ThreadedHTTPServer(server_address, DashboardRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="DashboardServerThread")
    thread.start()
    logger.success(f"[DASHBOARD] OPS Control Center: http://127.0.0.1:{port}/ops")
    logger.success(f"[DASHBOARD] Astronaut V-700 TFT Helmet HUD: http://127.0.0.1:{port}/astronaut")
    return thread


if __name__ == "__main__":
    server_address = ("127.0.0.1", 8501)
    httpd = ThreadedHTTPServer(server_address, DashboardRequestHandler)
    logger.success("[DASHBOARD] OPS Control Center: http://127.0.0.1:8501/ops")
    logger.success("[DASHBOARD] Astronaut V-700 TFT Helmet HUD: http://127.0.0.1:8501/astronaut")
    print("\n[OK] OPS Control Center: http://127.0.0.1:8501/ops")
    print("[OK] Astronaut V-700 TFT Helmet HUD: http://127.0.0.1:8501/astronaut\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Stopping dashboard...")
