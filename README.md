# AOUDA AI — Assistant Vocal Astronaute Analogique
# Mission AMADEE (ÖWF) — Combinaison Spatiale Aouda

## 🚀 Vue d'ensemble

**AOUDA AI** (version 0.3.0) est un assistant vocal **100 % hors-ligne (Edge AI)** conçu pour aider les astronautes analogues sous la combinaison spatiale **Aouda** lors des missions simulées de l'Austrian Space Forum (ÖWF / AMADEE).

## 🏗️ Architecture du Pipeline

```
Microphone USB / Casque
         │
         ▼
┌──────────────────┐
│  Wake Word       │  ← "AOUDA" (Empreinte spectrale ou Vosk STT)
│  Detection       │
└────────┬─────────┘
         │ détecté
         ▼
┌──────────────────┐
│  Speech-to-Text  │  ← Vosk EN (100% offline, embarqué)
│  (STT)           │
└────────┬─────────┘
         │ texte
         ▼
┌──────────────────┐  ← Instantané (<0.01s) : Télémétrie Aouda & Urgences
│  Brain           │
│  (Décision)      │  ← Offline Local LLM (Qwen2.5 GGUF) : Open-ended Q&A
└────────┬─────────┘
         │ réponse
         ▼
┌──────────────────┐
│  Text-to-Speech  │  ← Piper TTS (Voix naturelle, offline)
│  (TTS)           │
└────────┬─────────┘
         │ audio
         ▼
Haut-parleur Casque
```

## ⚡ Démarrage Rapide sur PC (Windows / Linux)

### 1. Entraîner AOUDA à votre voix (Calibration Astronaute)
```powershell
.\venv\Scripts\python.exe scripts/record_wakeword.py
```
*(Prononcez "AOUDA" 3 fois quand le terminal vous le demande).*

### 2. Lancer AOUDA
```powershell
.\venv\Scripts\python.exe main.py
```

### 3. Exécuter les tests unitaires
```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

---

## 🍓 Déploiement Direct sur Raspberry Pi 4 / 5 (Debian ARM64)

Tout le code développé dans cet environnement est 100% compatible Raspberry Pi :

```bash
# 1. Transférer le projet sur la Raspberry Pi
scp -r "Jarvis AI/" pi@raspberrypi.local:~/aouda/

# 2. Se connecter en SSH
ssh pi@raspberrypi.local

# 3. Installer l'environnement
cd ~/aouda
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Lancer AOUDA sur la Pi
python main.py
```

---

## 📡 Commandes Telemétrie & Mission Supportées

| Commande Vocal | Description |
|---|---|
| `"AOUDA"` | Déclenchement vocal (répondu par *"Yes?"*) |
| `"What is my heart rate?"` | Télémétrie cardiaque en temps réel |
| `"What is the oxygen level?"` | Télémétrie O2 combinaison |
| `"Give me the EVA checklist"` | Procédure de vérification sortie |
| `"Status"` | État global des systèmes de la combinaison |
| `"What is my GPS position?"` | Coordonnées de localisation |
| *"Questions ouvertes..."* | Prises en charge par l'IA locale 100% hors-ligne |

---
*Développé pour la mission AMADEE — ÖWF (Austrian Space Forum)*
