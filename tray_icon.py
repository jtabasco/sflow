import os
import logging
import webbrowser
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QInputDialog, QLineEdit
from PyQt6.QtGui import QIcon, QAction

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, db, dashboard_port: int, parent=None):
        icon = QIcon("assets/icon.png")
        super().__init__(icon, parent)
        self._db = db
        self._port = dashboard_port
        self._setup_menu()
        self.setToolTip("sflow — Ctrl+Shift+Space para dictar")

    def _setup_menu(self):
        menu = QMenu()

        open_action = QAction("📊 Abrir dashboard", menu)
        open_action.triggered.connect(self._open_dashboard)
        menu.addAction(open_action)

        apikey_action = QAction("🔑 Configurar API key", menu)
        apikey_action.triggered.connect(self._configure_api_key)
        menu.addAction(apikey_action)

        menu.addSeparator()

        quit_action = QAction("❌ Salir", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _open_dashboard(self):
        webbrowser.open(f"http://localhost:{self._port}")

    def _configure_api_key(self):
        text, ok = QInputDialog.getText(
            None,
            "API Key de Groq",
            "Ingresa tu API key de Groq (gsk_...):",
            QLineEdit.EchoMode.Password,
        )
        if ok and text.strip():
            self._write_env_key(text.strip())
            self.showMessage(
                "sflow",
                "API key guardada. Reinicia la app para aplicar.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _write_env_key(self, key: str):
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        new_lines = [l for l in lines if not l.startswith("GROQ_API_KEY")]
        new_lines.append(f"GROQ_API_KEY={key}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)

    def _quit(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def notify(self, message: str):
        self.showMessage("sflow", message, QSystemTrayIcon.MessageIcon.Warning, 4000)
