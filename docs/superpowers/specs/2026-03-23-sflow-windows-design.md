# sflow-windows — Design Spec
**Fecha:** 2026-03-23
**Proyecto:** Aplicación de escritorio Windows para voz-a-texto
**Referencia:** https://github.com/daniel-carreon/sflow (versión macOS)

---

## Objetivo

Construir una aplicación de escritorio para Windows 11 que permita dictado de voz en cualquier aplicación mediante push-to-talk (`Ctrl+Shift`), transcribiendo con la API gratuita de Groq (Whisper), mostrando una pill flotante animada, y guardando el historial en un dashboard web local.

---

## Stack tecnológico

- **Lenguaje:** Python 3.11+
- **UI:** PyQt6 (pill flotante + system tray)
- **Hotkeys globales:** `keyboard` (no requiere permisos de administrador en Windows 11)
- **Captura de audio:** `sounddevice` + `numpy`
- **Transcripción:** Groq SDK — modelo `whisper-large-v3-turbo` (tier gratuito)
- **Portapapeles y pegado:** `pyperclip` + `keyboard.send('ctrl+v')`
- **Historial:** SQLite (módulo `sqlite3` de stdlib)
- **Dashboard web:** Flask en `localhost:5678`
- **Config:** `python-dotenv` + archivo `.env`

---

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    app.py (Entry Point)              │
└──────┬──────────────────────────────────────┬────────┘
       │                                      │
┌──────▼──────┐                    ┌──────────▼────────┐
│  HotkeyMgr  │                    │   SystemTray      │
│ (keyboard)  │                    │   (PyQt6)         │
└──────┬──────┘                    └──────────┬────────┘
       │ Ctrl+Shift held/released             │ abrir dashboard / salir
┌──────▼──────┐
│AudioRecorder│──── nivel RMS ──────► PillUI (PyQt6 flotante)
│(sounddevice)│
└──────┬──────┘
       │ audio WAV buffer (BytesIO)
┌──────▼──────┐
│ Transcriber │──── Groq Whisper API ────► texto
│ (groq SDK)  │
└──────┬──────┘
       │ texto transcrito
┌──────┴──────────────────┐
│                         │
▼                         ▼
ClipboardPaster        HistoryDB (SQLite)
(pyperclip+keyboard)        │
                           ▼
                    Flask Dashboard
                    localhost:5678
```

---

## Estructura de archivos

```
sflow-windows/
├── app.py                  # Entry point: inicializa todos los módulos
├── hotkey_manager.py       # Detecta Ctrl+Shift (press/release) globalmente
├── audio_recorder.py       # Captura audio, calcula RMS para visualización
├── transcriber.py          # Llama a Groq Whisper API, retorna texto
├── clipboard_paster.py     # Copia texto y simula Ctrl+V en el cursor activo
├── pill_ui.py              # Ventana PyQt6 flotante sin bordes, siempre encima
├── tray_icon.py            # Ícono en bandeja del sistema con menú contextual
├── db.py                   # Operaciones SQLite (create, insert, query)
├── dashboard/
│   ├── server.py           # Flask app en localhost:5678
│   └── templates/
│       └── index.html      # Lista de transcripciones + buscador
├── requirements.txt
├── .env.example
└── README.md
```

---

## Interfaz de usuario

### Pill flotante (PyQt6)

- Ventana sin bordes, fondo semitransparente oscuro, esquinas redondeadas
- Siempre encima de todas las ventanas (`WindowStaysOnTopHint`)
- Draggable: el usuario puede moverla con click+arrastrar
- Posición guardada en SQLite entre sesiones
- **3 estados visuales:**
  - **IDLE:** `🎙️ sflow` — pequeña, discreta
  - **GRABANDO:** `🔴 ▁▃▅▇▅▃▁ grabando…` — barra animada con nivel de audio real
  - **PROCESANDO:** `⏳ Transcribiendo…` — spinner mientras espera Groq

### System Tray

- Ícono en bandeja del sistema de Windows
- Menú contextual (clic derecho):
  - Abrir dashboard (`localhost:5678`)
  - Configurar API key
  - Salir

### Dashboard web (Flask)

- Lista de transcripciones con fecha/hora
- Buscador por texto (filtro en tiempo real)
- Botón para copiar cada transcripción al portapapeles
- HTML/CSS sin frameworks externos

---

## Flujo de datos

```
1. Usuario presiona Ctrl+Shift
   → HotkeyManager detecta press
   → AudioRecorder.start() — buffer en memoria
   → PillUI → estado GRABANDO + animación RMS

2. Mientras mantiene presionado
   → sounddevice captura chunks de 1024 samples @ 16kHz
   → RMS calculado con numpy → PillUI actualiza barra

3. Usuario suelta Ctrl+Shift
   → AudioRecorder.stop() → WAV en BytesIO
   → PillUI → estado PROCESANDO

4. Transcriber.transcribe(audio_bytes)
   → POST a Groq API con modelo whisper-large-v3-turbo
   → Retorna texto transcrito

5. ClipboardPaster.paste(texto)
   → pyperclip.copy(texto)
   → keyboard.send('ctrl+v')
   → PillUI → estado IDLE

6. HistoryDB.save(texto, duración_seg, timestamp)
   → INSERT INTO transcriptions ...
```

---

## Configuración

Archivo `.env` (no commiteado):
```
GROQ_API_KEY=gsk_xxxxxxxxxxxx
HOTKEY=ctrl+shift
DASHBOARD_PORT=5678
```

Archivo `.env.example` (commiteado como referencia).

---

## Dependencias (requirements.txt)

```
pyqt6
keyboard
sounddevice
numpy
groq
pyperclip
flask
python-dotenv
```

---

## Notas de implementación para Windows 11

- `keyboard` en Windows no requiere permisos de administrador para hotkeys globales
- `sounddevice` usa WASAPI en Windows, compatible con todos los micrófonos
- PyQt6 maneja correctamente el DPI scaling de Windows 11
- El thread de Flask corre como daemon para no bloquear el cierre de la app
- El thread de `keyboard` y el de PyQt6 se comunican via `QMetaObject.invokeMethod` para ser thread-safe

---

## Fuera de alcance (v1)

- Múltiples idiomas configurables (se puede añadir después)
- Instalador `.exe` / distribución (se puede añadir con PyInstaller)
- Inicio automático con Windows
- Soporte para otros servicios de transcripción
