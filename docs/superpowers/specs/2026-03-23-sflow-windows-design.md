# sflow-windows — Design Spec
**Fecha:** 2026-03-23
**Proyecto:** Aplicación de escritorio Windows para voz-a-texto
**Referencia:** https://github.com/daniel-carreon/sflow (versión macOS)

---

## Objetivo

Construir una aplicación de escritorio para Windows 11 que permita dictado de voz en cualquier aplicación mediante push-to-talk (`Ctrl+Shift+Space`), transcribiendo con la API gratuita de Groq (Whisper), mostrando una pill flotante animada, y guardando el historial en un dashboard web local.

---

## Stack tecnológico

- **Lenguaje:** Python 3.11+
- **UI:** PyQt6 (pill flotante + system tray)
- **Hotkeys globales:** `pywin32` (`RegisterHotKey` via `win32con`) — hotkey de 3 teclas `Ctrl+Shift+Space`. La app debe correr con **privilegios de administrador** (manifest `requireAdministrator`) para garantizar que el hotkey se capture incluso cuando la ventana activa es un proceso elevado (ej. Task Manager). Sin admin, el hotkey falla silenciosamente en esos casos.
- **Captura de audio:** `sounddevice` + `numpy`
- **Transcripción:** Groq SDK — modelo `whisper-large-v3-turbo` (tier gratuito)
- **Portapapeles y pegado:** `QClipboard` (PyQt6) + `win32api.keybd_event` (VK_CONTROL + VK_V)
- **Historial:** SQLite (módulo `sqlite3` de stdlib)
- **Dashboard web:** Flask en `localhost:5678` (puerto configurable)
- **Config:** `python-dotenv` + archivo `.env`
- **Focus/window management:** `pywin32` (`win32gui`) para capturar HWND activo

---

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    app.py (Entry Point)              │
└──────┬──────────────────────────────────────┬────────┘
       │                                      │
┌──────▼──────┐                    ┌──────────▼────────┐
│  HotkeyMgr  │                    │   SystemTray      │
│ (pywin32    │                    │   (PyQt6)         │
│RegisterHotKey)│                  │                   │
└──────┬──────┘                    └──────────┬────────┘
       │ Ctrl+Shift+Space                     │ abrir dashboard / salir
       │ held/released
┌──────▼──────┐
│AudioRecorder│──── nivel RMS (via Qt Signal) ──► PillUI (PyQt6 flotante)
│(sounddevice)│
└──────┬──────┘
       │ WAV BytesIO (PCM→WAV via stdlib wave)
┌──────▼──────┐
│ Transcriber │──── Groq Whisper API ────► texto / error
│ (groq SDK)  │
└──────┬──────┘
       │ texto transcrito
┌──────┴──────────────────┐
│                         │
▼                         ▼
ClipboardPaster        HistoryDB (SQLite, thread-safe)
(QClipboard+keyboard)       │
                           ▼
                    Flask Dashboard
                    localhost:5678
```

---

## Estructura de archivos

```
sflow-windows/
├── app.py                  # Entry point: inicializa todos los módulos
├── hotkey_manager.py       # Detecta Ctrl+Shift+Space via win32con.RegisterHotKey
├── audio_recorder.py       # Captura audio, calcula RMS, emite Qt Signals
├── transcriber.py          # Llama a Groq Whisper API, retorna texto o error
├── clipboard_paster.py     # Copia texto con QClipboard y simula Ctrl+V
├── pill_ui.py              # Ventana PyQt6 flotante sin bordes, siempre encima
├── tray_icon.py            # Ícono en bandeja del sistema con menú contextual
├── db.py                   # Operaciones SQLite thread-safe (transcriptions + settings)
├── dashboard/
│   ├── server.py           # Flask app en localhost:5678
│   └── templates/
│       └── index.html      # Lista de transcripciones + buscador + paginación
├── requirements.txt        # Con versiones pinadas
├── .env.example
└── README.md
```

---

## Interfaz de usuario

### Pill flotante (PyQt6)

- Ventana sin bordes, fondo semitransparente oscuro, esquinas redondeadas
- Siempre encima de todas las ventanas (`WindowStaysOnTopHint`)
- Draggable: el usuario puede moverla con click+arrastrar
- Posición guardada en tabla `settings` de SQLite entre sesiones
- **4 estados visuales:**
  - **IDLE:** `🎙️ sflow` — pequeña, discreta
  - **GRABANDO:** `🔴 ▁▃▅▇▅▃▁ grabando…` — barra animada con nivel RMS real
  - **PROCESANDO:** `⏳ Transcribiendo…` — mientras espera respuesta de Groq
  - **ERROR:** `⚠️ Error — ver tray` — fondo rojo suave, 3 segundos, luego IDLE

### System Tray

- Ícono en bandeja del sistema de Windows
- Menú contextual (clic derecho):
  - Abrir dashboard (`localhost:5678` en navegador por defecto)
  - Configurar API key (diálogo `QInputDialog` simple, guarda en `.env`)
  - Salir

### Dashboard web (Flask)

- Lista de transcripciones con fecha/hora, paginada (50 por página)
- Buscador por texto (filtro SQL `LIKE`)
- Botón para copiar cada transcripción al portapapeles
- HTML/CSS sin frameworks externos
- Acceso solo desde `localhost` (`host='127.0.0.1'`, `debug=False`)

---

## Flujo de datos

```
1. Usuario presiona Ctrl+Shift+Space
   → HotkeyManager detecta press del combo de 3 teclas
   → win32gui.GetForegroundWindow() captura HWND activo (guardado en memoria)
   → AudioRecorder.start() — buffer en memoria (BytesIO)
   → PillUI → estado GRABANDO + animación RMS

2. Mientras mantiene presionado
   → sounddevice captura chunks @ 16kHz mono
   → Callback de audio (C-level thread): calcula RMS con numpy
   → Emite Qt Signal con valor float → PillUI actualiza barra (thread-safe)

3. Usuario suelta Ctrl+Shift+Space
   → AudioRecorder.stop() → PCM raw buffer
   → Validación: duración >= 0.5s (si no, descarta y vuelve a IDLE)
   → Encode PCM → WAV usando stdlib `wave` module (16kHz, mono, 16-bit) → BytesIO
   → PillUI → estado PROCESANDO

4. Transcriber.transcribe(audio_bytes) — corre en QThread
   → POST a Groq API con modelo whisper-large-v3-turbo
   → Si éxito: retorna texto (puede ser vacío si no hubo voz detectada)
   → Si error (timeout, 401, 429, etc.): retorna None + log del error

5a. Si texto recibido y no vacío:
   → Restaurar foco con AttachThreadInput trick (necesario en Windows):
       fg_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
       cur_thread = win32api.GetCurrentThreadId()
       win32gui.AttachThreadInput(fg_thread, cur_thread, True)
       win32gui.SetForegroundWindow(hwnd_guardado)
       win32gui.AttachThreadInput(fg_thread, cur_thread, False)
   → QClipboard.setText(texto)
   → win32api.keybd_event(VK_V + CTRL) — paste via win32 (no keyboard lib)
   → PillUI → estado IDLE
   → HistoryDB.save(texto, duración_seg, timestamp)

5b. Si texto vacío o None:
   → PillUI → estado ERROR por 3 segundos → IDLE
   → No se pega nada, no se guarda en historial

6. Dashboard Flask (thread daemon separado)
   → GET /  → HistoryDB.query(page, search) → HTML
   → SQLite accedido con check_same_thread=False + Lock de threading
```

---

## Gestión de threads

| Thread | Tipo | Responsabilidad |
|--------|------|-----------------|
| Main thread | Qt event loop | UI, system tray, eventos de usuario |
| Hotkey listener | `QAbstractNativeEventFilter` | Recibe `WM_HOTKEY` de `RegisterHotKey`, emite Qt Signal |
| sounddevice callback | C-level thread | Captura audio, calcula RMS, emite Signal via `QMetaObject.invokeMethod` |
| Transcription worker | `QThread` | Llama a Groq API sin bloquear UI |
| Flask server | `threading.Thread` daemon | Sirve el dashboard web |

**Regla:** Toda comunicación con PyQt6 se hace exclusivamente via Qt Signals/Slots o `QMetaObject.invokeMethod(Qt.QueuedConnection)`. Ningún thread externo llama métodos de Qt directamente.

**Nota de implementación — hotkey con pywin32:** `RegisterHotKey` requiere un message loop de Windows. Se implementa en `hotkey_manager.py` como `QAbstractNativeEventFilter` registrado en la `QApplication`, que intercepta `WM_HOTKEY` (0x0312) en el event loop de Qt. Esto evita necesitar un thread extra para el message loop.

---

## Base de datos SQLite

### Tabla `transcriptions`
```sql
CREATE TABLE transcriptions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    text      TEXT NOT NULL,
    duration  REAL NOT NULL,   -- segundos
    created_at TEXT NOT NULL   -- ISO 8601: "2026-03-23T14:30:00"
);
```

### Tabla `settings`
```sql
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Ejemplo: key='pill_x', value='1200' | key='pill_y', value='800'
```

**Thread safety:** `db.py` usa una única instancia de `sqlite3.connect` con `check_same_thread=False` protegida por un `threading.Lock`. Toda operación adquiere el lock antes de ejecutar.

---

## Manejo de errores

| Escenario | Comportamiento |
|-----------|---------------|
| Sin micrófono disponible | Error en startup: notificación tray + log, app sigue sin grabar |
| Grabación < 0.5 segundos | Descartada silenciosamente, pill vuelve a IDLE |
| Transcripción vacía (sin voz) | Pill → ERROR 3s → IDLE, no se pega nada |
| Groq API key inválida (401) | Pill → ERROR, notificación tray "API key inválida" |
| Groq rate limit (429) | Pill → ERROR, notificación tray "Límite de Groq alcanzado" |
| Timeout de red | Pill → ERROR, notificación tray "Sin conexión" |
| Puerto 5678 ocupado | Log de warning, dashboard no disponible (app sigue funcionando) |
| Ventana activa cerrada antes del pegado | `SetForegroundWindow` falla silenciosamente, no se pega |

---

## Configuración (.env)

```
GROQ_API_KEY=gsk_xxxxxxxxxxxx
DASHBOARD_PORT=5678
```

**Nota sobre el hotkey:** En v1 el hotkey `Ctrl+Shift+Space` está **hardcodeado** en `hotkey_manager.py` como constantes de `win32con` (`MOD_CONTROL | MOD_SHIFT`, `VK_SPACE`). No se expone como configurable en `.env` para evitar la complejidad de parsear strings a enteros de `RegisterHotKey`. La UI muestra el hotkey como texto literal. La configurabilidad queda fuera de alcance de v1.

---

## Dependencias (requirements.txt — versiones mínimas)

```
pyqt6>=6.6.0
sounddevice>=0.4.6
numpy>=1.26.0
groq>=0.9.0
pywin32>=306
flask>=3.0.0
python-dotenv>=1.0.0
```

**Nota:** `keyboard` ya no es una dependencia — se usa `pywin32` (`RegisterHotKey` + `win32api.keybd_event`) para hotkeys y paste, lo que garantiza funcionamiento correcto con ventanas elevadas. `wave` (stdlib) para codificación WAV, sin dependencia adicional.

---

## Fuera de alcance (v1)

- Múltiples idiomas configurables
- Instalador `.exe` / distribución con PyInstaller
- Inicio automático con Windows
- Soporte para otros servicios de transcripción (OpenAI, local Whisper)
- Autenticación en el dashboard web
- Selección manual de dispositivo de micrófono
