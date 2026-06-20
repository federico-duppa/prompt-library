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
"""Prompt Library — scrim overlay + system tray.

Flow:
  * Scans a folder for *.prompt files (flat, non-recursive).
  * Shows each prompt as a clickable *card* in a grid; click = copy.
  * Alt+1..Alt+9 copy the first nine visible cards.
  * After copying, the window hides to the tray a few ms later.
  * The window covers the whole screen with a dark, semi-transparent
    background (scrim) and centers the dialog on top, to highlight it
    (Alt+F2 aesthetic). Click on the dark area or Esc = close.
  * Single instance: a second invocation (--show) wakes the window.
"""
from __future__ import annotations

import getpass
import math
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import load_config, save_config

APP_NAME = "Prompt Library"
SERVER_NAME = f"prompt-library-{getpass.getuser()}"
MAX_HOTKEYS = 9

DIALOG_WIDTH = 720
DIALOG_MAX_HEIGHT = 560
DIALOG_MIN_HEIGHT = 200
CARD_WIDTH = 164
CARD_HEIGHT = 96
CARD_SPACING = 10
SCRIM_ALPHA = 150  # 0..255, how dark the background gets

STYLESHEET = """
QWidget#root { background: transparent; }
QFrame#overlay {
    background: #23242c;
    border: 1px solid #41444f;
    border-radius: 16px;
}
QLineEdit {
    background: #2e303b; color: #e8e8ee; border: 1px solid #3a3d4a;
    border-radius: 9px; padding: 9px 12px; font-size: 14px;
}
QLineEdit:focus { border: 1px solid #4c8bf5; }
QLabel#path { color: #8a8d9a; font-size: 11px; }
QLabel#empty { color: #8a8d9a; font-size: 13px; }
QLabel#status { color: #6fe08a; font-size: 12px; }
QPushButton#tool {
    background: #2e303b; color: #e8e8ee; border: 1px solid #3a3d4a;
    border-radius: 9px; padding: 7px 11px; font-size: 14px;
}
QPushButton#tool:hover { background: #3a3d4a; }
QFrame#card {
    background: #2e303b; border: 1px solid #3a3d46; border-radius: 12px;
}
QFrame#card:hover { background: #36405a; border: 1px solid #4c8bf5; }
QLabel#name { color: #e8e8ee; font-size: 13px; }
QLabel#badge {
    color: #cdd2ff; background: #404663; border-radius: 6px;
    padding: 1px 6px; font-size: 10px; font-weight: bold;
}
QScrollArea, QWidget#listhost { background: transparent; border: none; }
"""


def make_icon() -> QIcon:
    """Draws a clipboard icon without depending on external files."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#4c8bf5")))
    p.drawRoundedRect(12, 12, 40, 44, 7, 7)
    p.setBrush(QBrush(QColor("#2f6fe0")))
    p.drawRoundedRect(24, 7, 16, 11, 4, 4)
    pen = QPen(QColor("white"))
    pen.setWidth(3)
    p.setPen(pen)
    for y in (28, 36, 44):
        p.drawLine(20, y, 44, y)
    p.end()
    return QIcon(pm)


class FlowLayout(QLayout):
    """Layout that lays out children in a row and wraps when the width fills up."""

    def __init__(self, parent=None, margin=0, spacing=CARD_SPACING):
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x > right and line_height > 0:
                x = rect.x() + m.left()
                y = y + line_height + self._spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height + m.bottom() - rect.y()


class PromptCard(QFrame):
    """A fixed-size clickable card that represents a prompt."""

    clicked = Signal()

    def __init__(self, name: str, hotkey: str):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setToolTip(name)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 9, 11, 9)
        lay.setSpacing(6)

        if hotkey:
            badge = QLabel(hotkey)
            badge.setObjectName("badge")
            lay.addWidget(badge, 0, Qt.AlignLeft)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("name")
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(name_lbl, 1)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QWidget):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.config = load_config()
        self.hide_delay_ms = int(self.config.get("hide_delay_ms", 250))
        self.prompts: list[dict] = []   # [{name, path}]
        self.visible: list[dict] = []
        self._tray_hint_shown = False
        self._autohide_armed = False
        self._suppress_autohide = False

        # Full-screen, frameless and translucent window: we paint the
        # background as a dark scrim and center the dialog on top.
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)

        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self.reload_prompts()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        # The full-screen scrim centers the dialog with stretches.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        midrow = QHBoxLayout()
        midrow.addStretch(1)

        self.dialog_frame = QFrame()
        self.dialog_frame.setObjectName("overlay")
        self.dialog_frame.setFixedWidth(DIALOG_WIDTH)
        shadow = QGraphicsDropShadowEffect(self.dialog_frame)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.dialog_frame.setGraphicsEffect(shadow)
        midrow.addWidget(self.dialog_frame)

        midrow.addStretch(1)
        outer.addLayout(midrow)
        outer.addStretch(1)

        root = QVBoxLayout(self.dialog_frame)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search prompts…")
        self.search.textChanged.connect(self.rebuild_list)
        top.addWidget(self.search, 1)

        folder_btn = QPushButton("📁")
        folder_btn.setObjectName("tool")
        folder_btn.setToolTip("Choose folder")
        folder_btn.clicked.connect(self.choose_directory)
        top.addWidget(folder_btn)

        reload_btn = QPushButton("⟳")
        reload_btn.setObjectName("tool")
        reload_btn.setToolTip("Reload")
        reload_btn.clicked.connect(self.reload_prompts)
        top.addWidget(reload_btn)
        root.addLayout(top)

        self.path_lbl = QLabel("")
        self.path_lbl.setObjectName("path")
        root.addWidget(self.path_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_host = QWidget()
        self.list_host.setObjectName("listhost")
        self.flow = FlowLayout(self.list_host, margin=0, spacing=CARD_SPACING)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("status")
        root.addWidget(self.status_lbl)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Show", self.summon)
        menu.addAction("Choose folder…", self.choose_directory)
        menu.addAction("Reload", self.reload_prompts)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_shortcuts(self) -> None:
        for i in range(MAX_HOTKEYS):
            sc = QShortcut(QKeySequence(f"Alt+{i + 1}"), self)
            sc.activated.connect(lambda idx=i: self.trigger_index(idx))
        QShortcut(QKeySequence("Escape"), self, activated=self.hide_to_tray)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reload_prompts)

    # ---------- data ----------
    def reload_prompts(self) -> None:
        directory = self.config.get("directory", "")
        self.prompts = []
        if directory and Path(directory).is_dir():
            files = sorted(
                Path(directory).glob("*.prompt"),
                key=lambda p: p.stem.lower(),
            )
            self.prompts = [{"name": p.stem, "path": str(p)} for p in files]
            self.path_lbl.setText(f"📂 {directory}  ·  {len(self.prompts)} prompts")
        else:
            self.path_lbl.setText("No folder selected")
        self.rebuild_list()

    def rebuild_list(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        query = self.search.text().strip().lower()
        if query:
            self.visible = [p for p in self.prompts if query in p["name"].lower()]
        else:
            self.visible = list(self.prompts)

        if not self.prompts:
            self._add_empty("No prompts. Choose a folder with .prompt files 📁")
        elif not self.visible:
            self._add_empty("No prompt matches the search.")
        else:
            for i, p in enumerate(self.visible):
                hotkey = f"Alt+{i + 1}" if i < MAX_HOTKEYS else ""
                card = PromptCard(p["name"], hotkey)
                card.clicked.connect(lambda pp=p: self.copy_prompt(pp))
                self.flow.addWidget(card)

        self.list_host.adjustSize()
        self._fit_dialog_height()

    def _fit_dialog_height(self) -> None:
        """Fits the dialog height to the content, up to a maximum."""
        n = len(self.visible) if self.prompts else 1
        inner_w = DIALOG_WIDTH - 32  # side margins
        cols = max(1, (inner_w + CARD_SPACING) // (CARD_WIDTH + CARD_SPACING))
        rows = max(1, math.ceil(n / cols))
        content = rows * CARD_HEIGHT + (rows - 1) * CARD_SPACING
        chrome = 132  # search box + path + status + margins
        height = min(DIALOG_MAX_HEIGHT, max(DIALOG_MIN_HEIGHT, chrome + content))
        self.dialog_frame.setFixedHeight(int(height))

    def _add_empty(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("empty")
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.flow.addWidget(lbl)

    # ---------- actions ----------
    def trigger_index(self, idx: int) -> None:
        if 0 <= idx < len(self.visible):
            self.copy_prompt(self.visible[idx])

    def copy_prompt(self, prompt: dict) -> None:
        try:
            text = Path(prompt["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.tray.showMessage(APP_NAME, f"Read error: {exc}",
                                  QSystemTrayIcon.Critical, 3000)
            return
        QApplication.clipboard().setText(text)
        self._flash_status(f"✓ Copied: {prompt['name']}")
        QTimer.singleShot(self.hide_delay_ms, self.hide_to_tray)

    def choose_directory(self) -> None:
        start = self.config.get("directory") or str(Path.home())
        self._suppress_autohide = True
        try:
            directory = QFileDialog.getExistingDirectory(
                self, "Choose prompts folder", start
            )
        finally:
            self._suppress_autohide = False
        if directory:
            self.config["directory"] = directory
            save_config(self.config)
            self.reload_prompts()

    # ---------- visibility ----------
    def summon(self) -> None:
        self._autohide_armed = False
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        self.search.selectAll()
        QTimer.singleShot(450, self._arm_autohide)

    def _arm_autohide(self) -> None:
        self._autohide_armed = True

    def hide_to_tray(self) -> None:
        self._autohide_armed = False
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(
                APP_NAME,
                "Still running in the tray. Global hotkey: Super+Shift+P.",
                QSystemTrayIcon.Information, 2500,
            )

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.summon()

    def quit_app(self) -> None:
        self.tray.hide()
        self.app.quit()

    # ---------- scrim / close ----------
    def paintEvent(self, event):  # noqa: N802
        # Dark, semi-transparent background that highlights the dialog.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, SCRIM_ALPHA))

    def mousePressEvent(self, event):  # noqa: N802
        # Click on the dark area (outside the dialog) => close.
        self.hide_to_tray()

    def changeEvent(self, event):  # noqa: N802
        if event.type() == QEvent.ActivationChange:
            if (
                not self.isActiveWindow()
                and self.isVisible()
                and self._autohide_armed
                and not self._suppress_autohide
            ):
                self.hide_to_tray()
        super().changeEvent(event)

    def closeEvent(self, event):  # noqa: N802
        event.ignore()
        self.hide_to_tray()

    # ---------- status/feedback ----------
    def _flash_status(self, text: str) -> None:
        self.status_lbl.setText(text)
        self._status_timer.start(2000)

    def _clear_status(self) -> None:
        self.status_lbl.setText("")
