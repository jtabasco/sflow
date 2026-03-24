# sflow — Voice-to-Text for Windows

Dictate anywhere on Windows 11. Hold a hotkey, speak, release — your words appear wherever the cursor is.

Powered by [Groq Whisper](https://console.groq.com) (free tier, ~300 minutes/day).

---

## Features

- **Push-to-talk** — hold `Ctrl+Shift+Space`, speak, release
- **Floating pill UI** — always-on-top, draggable, shows live audio bars while recording
- **Pastes at cursor** — works in any app: browsers, editors, chat apps, etc.
- **History dashboard** — browse and search all transcriptions at `http://localhost:5678`
- **System tray** — configure API key, open dashboard, quit

## Requirements

- Windows 11
- Python 3.12+
- A free [Groq API key](https://console.groq.com)

## Setup

```bash
# 1. Clone
git clone https://github.com/jtabasco/sflow.git
cd sflow

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API key
copy .env.example .env
# Edit .env and paste your GROQ_API_KEY

# 4. Run
python app.py
```

Or double-click `launch.bat` to run without a terminal window.

## Controls

| Action | Hotkey |
|--------|--------|
| Push-to-talk | Hold `Ctrl+Shift+Space` |
| Open dashboard | Tray icon → Abrir Dashboard |
| Configure API key | Tray icon → Configurar API key |
| Quit | Tray icon → Salir |

## Build standalone .exe

```bash
build_exe.bat
# Output: dist\sflow.exe
```

## Project structure

```
app.py                  # Entry point
audio_recorder.py       # Microphone capture (sounddevice)
transcriber.py          # Groq Whisper API
clipboard_paster.py     # Paste at cursor (Win32)
hotkey_manager.py       # GetAsyncKeyState polling
pill_ui.py              # Floating pill widget (PyQt6)
tray_icon.py            # System tray
db.py                   # SQLite history
dashboard/              # Flask history dashboard
assets/                 # Icons
tests/                  # pytest unit tests
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key (required) |
| `DASHBOARD_PORT` | Dashboard port (default: `5678`) |

Copy `.env.example` to `.env` and fill in your values. Never commit `.env`.

## Credits

Inspired by [sflow](https://github.com/daniel-carreon/sflow) for macOS by Daniel Carreón.
