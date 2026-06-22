# Copyright 2026 Federico De Malmayne Duppa
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Entry point. Manages the single instance.

Usage:
  python -m prompt_library            -> opens the window
  python -m prompt_library --show     -> opens/wakes the window (global hotkey)
  python -m prompt_library --tray     -> starts hidden in the tray (autostart)
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .app import APP_NAME, SERVER_NAME, MainWindow, make_icon
from .hotkey import ensure_hotkey_registered


def _notify_running_instance() -> bool:
    """If an instance already exists, ask it to show and return True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(200):
        sock.write(b"show\n")
        sock.flush()
        sock.waitForBytesWritten(200)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    argv = sys.argv[1:]

    # We don't need QApplication to check the single instance, but QLocalSocket
    # does require a Qt event loop: we create the app first.
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)

    if _notify_running_instance():
        return 0

    # We are the primary instance: clean up a stale socket and listen.
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        print(f"Warning: could not open socket {SERVER_NAME}", file=sys.stderr)

    win = MainWindow(app)

    def on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def on_ready() -> None:
            data = bytes(conn.readAll()).decode(errors="ignore")
            if "show" in data:
                win.summon()
            conn.disconnectFromServer()

        conn.readyRead.connect(on_ready)

    server.newConnection.connect(on_new_connection)

    # First-launch convenience: register the GNOME global hotkey for this user.
    ensure_hotkey_registered()

    start_hidden = "--tray" in argv
    if start_hidden:
        # give the tray a moment to register before any message
        QTimer.singleShot(0, lambda: None)
    else:
        win.summon()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
