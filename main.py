"""
JARVIS AI - Point d'Entree Principal
======================================
Orchestre le pipeline complet :
  Wake Word -> STT -> Brain -> TTS

Mission : AMADEE-27 (OeWF)
Mode : Prototype Windows (simulation) -> Raspberry Pi (production)
"""

import sys
import os
import signal
import time
import yaml
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ------------------------------------------------------------------
# Fix Windows : force UTF-8 pour eviter UnicodeEncodeError cp1252
# ------------------------------------------------------------------
os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32":
    import io
    # Reconfigure stdout/stderr en UTF-8 avec remplacement des caract. inconnus
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Modules Jarvis
from jarvis.audio.audio_engine import AudioEngine
from jarvis.audio.wake_word import WakeWordDetector
from jarvis.stt.speech_to_text import SpeechToText
from jarvis.brain.brain import Brain
from jarvis.tts.text_to_speech import TextToSpeech
from jarvis.sensors.suit_data_manager import SuitDataManager
from web_dashboard import STATE, run_dashboard_server


# ── Configuration du logging ───────────────────────────────────────
def setup_logging(config: dict) -> None:
    logger.remove()
    log_cfg = config.get("logging", {
        "level": "INFO",
        "log_file": "logs/jarvis.log",
        "rotation": "10 MB",
        "retention": "7 days"
    })

    # Console - format sans emojis pour compatibilite Windows legacy
    logger.add(
        sys.stderr,
        level=log_cfg.get("level", "INFO"),
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    # Fichier rotatif (UTF-8 explicite)
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        log_cfg.get("log_file", "logs/jarvis.log"),
        rotation=log_cfg.get("rotation", "10 MB"),
        retention=log_cfg.get("retention", "7 days"),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        encoding="utf-8",
    )


# ── Chargement configuration ──────────────────────────────────────
def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Banniere ASCII (100% compatible tous terminaux Windows) ───────
def print_banner(config: dict, console: Console) -> None:
    jarvis_cfg = config.get("jarvis", {})
    mission_cfg = config.get("mission", {})
    version   = jarvis_cfg.get("version", "0.3.0")
    mission   = jarvis_cfg.get("mission", "AMADEE-27")
    astronaut = mission_cfg.get("astronaut_name", "Astronaut")

    lines = [
        "  +========================================+",
        "  |                                        |",
        "  |    J . A . R . V . I . S    A I        |",
        f"  |    Version  : {version:<25}|",
        f"  |    Mission  : {mission:<25}|",
        f"  |    Pilote   : {astronaut:<25}|",
        "  |    Mode     : Edge AI - 100% Offline   |",
        "  |                                        |",
        "  +========================================+",
    ]

    banner = Text()
    for line in lines:
        banner.append(line + "\n", style="bold cyan")

    console.print(Panel(
        banner,
        title="[bold red]>>> AMADEE (OeWF) Mission <<<[/bold red]",
        border_style="cyan"
    ))


# ── Pipeline Principal ────────────────────────────────────────────
class JarvisApp:
    """Orchestrateur du pipeline vocal complet."""

    def __init__(self, config: dict):
        self.config = config
        self._running = False

        logger.info("Initializing JARVIS modules...")

        self.audio     = AudioEngine(config)
        self.wake_word = WakeWordDetector(config)
        self.stt       = SpeechToText(config)
        self.tts       = TextToSpeech(config)
        self.sensors   = SuitDataManager(config, alert_tts_callback=self.tts.speak)
        self.brain     = Brain(config)

        self._log_mode_summary()

    def _log_mode_summary(self) -> None:
        """Print a summary of active vs simulation modes."""
        logger.info("-" * 50)
        logger.info("MODULE STATUS:")
        ww      = "[SIM]" if self.wake_word.is_simulation else "[REAL]"
        stt     = "[SIM]" if self.stt.is_simulation       else "[REAL]"
        tts_s   = "[SIM]" if self.tts.is_simulation        else "[REAL]"
        sensors = f"[{self.sensors.source_mode}]"
        logger.info(f"  Wake Word : {ww}")
        logger.info(f"  STT       : {stt}")
        logger.info(f"  TTS       : {tts_s}")
        logger.info(f"  Sensors   : {sensors}")
        logger.info("-" * 50)

    def _check_ground_control_commands(self) -> bool:
        """Check and execute pending ground control override triggers. Returns True if a command was executed."""
        cmd = STATE.pop_command()
        if not cmd:
            return False

        logger.info(f"[GROUND CONTROL] Executing override command: [{cmd}]")
        if cmd == "telemetry":
            query = "status"
        elif cmd == "next_step":
            query = "next"
        elif cmd == "emergency":
            query = "emergency"
        elif cmd.startswith("query:"):
            query = cmd[6:].strip()
        else:
            query = cmd.strip()

        STATE.add_chat("Ground Control", f"Triggered command: {query}")
        response = self.brain.process(query)
        STATE.add_chat("AOUDA", response)

        proc_info = self.brain.get_active_session_info()
        if proc_info:
            STATE.set_procedure(proc_info.get("title", "AOUDA Standby"), proc_info.get("step", 0), proc_info.get("instruction", ""))

        self.tts.speak(response)
        return True

    def run(self) -> None:
        """Launch the main JARVIS pipeline loop."""
        self._running = True

        # Launch Web Dashboard Server automatically in background
        run_dashboard_server(port=8501)
        STATE.add_event("Web Dashboard HUD linked & streaming live.")

        # Start sensor data polling (background thread)
        sensor_ok = self.sensors.start()
        if sensor_ok:
            self.brain.set_sensor_manager(self.sensors)
            logger.success(f"[SENSORS] Live data active: {self.sensors.source_mode}")
        else:
            logger.warning("[SENSORS] No sensor data available — static responses only.")

        # Start microphone
        self.audio.start()

        mission_name = self.config.get("jarvis", {}).get("mission", "AMADEE-27")
        welcome_text = (
            f"AOUDA online. Mission {mission_name}. "
            "All systems nominal. Say AOUDA to activate."
        )
        STATE.add_chat("AOUDA", welcome_text)
        self.tts.speak(welcome_text)

        logger.success("AOUDA listening. Press Ctrl+C to stop.\n")

        try:
            while self._running:
                if self.sensors.is_running:
                    STATE.update_telemetry(self.sensors.get_all())
                self._run_cycle()
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Shutdown requested by operator.")
        finally:
            self.shutdown()

    def _run_cycle(self) -> None:
        """One full cycle: Wake word (if enabled) → Continuous Follow-up Session → Standby."""

        # ── STEP 1: Wait for wake word (if enabled) ───────────────────────
        if self.wake_word.enabled:
            triggered = self.wake_word.wait_for_wakeword(command_check_callback=self._check_ground_control_commands)
            if not triggered or not self._running:
                return

            logger.success("Wake word 'AOUDA' detected! Session active.")
            STATE.add_event("Wake word 'AOUDA' detected — Voice Session Active.")
            STATE.add_chat("AOUDA", "Yes?")
            self.tts.speak("Yes?")
        else:
            self._check_ground_control_commands()

        in_followup = False
        consecutive_silences = 0

        # ── STEP 3: Continuous Follow-Up Session Loop ─────────────────────
        while self._running:
            if self._check_ground_control_commands():
                break

            if self.sensors.is_running:
                STATE.update_telemetry(self.sensors.get_all())

            listen_timeout = 10.0 if in_followup else self.config.get("wakeword", {}).get("listen_timeout_s", 10)
            command_text = self.stt.transcribe_stream(timeout=listen_timeout, command_check_callback=self._check_ground_control_commands)

            if not command_text:
                if in_followup:
                    consecutive_silences += 1
                    if consecutive_silences >= 1:
                        logger.info("Procedure follow-up window timed out — returning to standby.")
                        STATE.add_chat("AOUDA", "AOUDA returning to standby.")
                        self.tts.speak("AOUDA returning to standby.")
                        break
                    continue
                else:
                    consecutive_silences += 1
                    if consecutive_silences <= 1:
                        # Give the astronaut a second chance without requiring wake word again!
                        in_followup = True
                        STATE.add_chat("AOUDA", "I did not catch that. Please repeat your command.")
                        self.tts.speak("I did not catch that. Please repeat your command.")
                        continue
                    else:
                        break

            consecutive_silences = 0
            logger.info(f"Command received: '{command_text}'")
            STATE.add_chat("Astronaut", command_text)

            # ── STEP 4: Brain — process command ────────────────────────────
            response = self.brain.process(command_text)
            STATE.add_chat("AOUDA", response)

            # Update dashboard active procedure card
            proc_info = self.brain.get_active_session_info()
            if proc_info:
                STATE.set_procedure(proc_info.get("title", "AOUDA Standby"), proc_info.get("step", 0), proc_info.get("instruction", ""))

            # ── STEP 5: TTS — speak response ───────────────────────────────
            self.tts.speak(response)

            # ── Mission log ────────────────────────────────────────────────
            if self.config.get("mission", {}).get("log_all_interactions", True):
                from datetime import datetime
                vitals = self.sensors.get_summary_text() if self.sensors.is_running else "no sensor data"
                logger.info(
                    f"[MISSION LOG] {datetime.now().isoformat()} | "
                    f"Vitals: {vitals} | "
                    f"Astronaut: '{command_text}' | "
                    f"AOUDA: '{response[:80]}...'"
                )

            # Check if procedure or guided session is active
            if self.brain.is_session_active:
                in_followup = True
                logger.info("[SESSION] Active procedure ongoing — listening directly for next/done/previous...")
            else:
                logger.info("[SESSION] No active procedure — returning to wake word standby.")
                break

    def shutdown(self) -> None:
        """Clean shutdown of all modules."""
        self._running = False
        self.sensors.stop()
        self.audio.stop()
        self.tts.speak("AOUDA going offline. Good mission, astronaut.")
        logger.info("AOUDA shut down cleanly.")


# ── Point d'Entree ────────────────────────────────────────────────
if __name__ == "__main__":
    # Console Rich en mode securise pour Windows
    console = Console(safe_box=True)

    config = load_config("config.yaml")
    setup_logging(config)

    print_banner(config, console)

    app = JarvisApp(config)
    signal.signal(signal.SIGINT, lambda s, f: setattr(app, "_running", False))

    app.run()
