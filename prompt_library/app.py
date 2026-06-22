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
  * The window covers the whole screen with a solid black backdrop
    (scrim) and centers the dialog on top, to highlight it
    (Alt+F2 aesthetic). Click on the dark area or Esc = close.
  * Single instance: a second invocation (--show) wakes the window.
"""
from __future__ import annotations

import getpass
import math
import random
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QLinearGradient,
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
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import load_config, save_config

APP_NAME = "Prompt Library"
SERVER_NAME = f"prompt-library-{getpass.getuser()}"
MAX_HOTKEYS = 9

CARD_WIDTH = 164
CARD_HEIGHT = 96
CARD_SPACING = 10
DIALOG_MARGIN = 16        # side padding inside the dialog frame
MIN_DIALOG_WIDTH = 380    # keep the search row usable even for a 1-column grid
EMPTY_DIALOG_WIDTH = 440  # width used for the "no prompts / no match" message
MAX_COLS = 5              # the grid is at most MAX_COLS x MAX_COLS
MAX_GRID = MAX_COLS * MAX_COLS  # 25 cards fit without scroll; search to see more

# Prompts whose filename stem starts with this go into the "suffix" section:
# selecting one appends its text to whatever main prompt is copied next.
SUFFIX_PREFIX = "Suffix"
SUFFIX_SEPARATOR = "\n\n"  # placed between the main prompt and the suffix on copy

# --- animated scrim (twinkling starfield + shooting stars) ---
SCRIM_FPS = 32               # animation refresh rate while the overlay is visible
STAR_COUNT = 110             # static background stars
METEOR_MAX = 3               # max shooting stars on screen at once
METEOR_SPAWN_CHANCE = 0.035  # probability of spawning one per frame (under the cap)
STAR_COLOR = (208, 218, 255)     # cool white
METEOR_COLOR = (120, 150, 255)   # faint blue trail, matching the accent


def grid_dims(n: int) -> tuple[int, int]:
    """Return (cols, rows) for a compact, vertical-leaning grid.

    The grid is the smallest rectangle that holds ``n`` cards (clamped to
    1..MAX_GRID), capped at MAX_COLS x MAX_COLS. Perfect squares (4, 9, 16,
    25) become squares; every other count becomes a vertical rectangle
    (``rows >= cols``), e.g. 5 -> 2x3, 7 -> 2x4, 13 -> 3x5.
    """
    n = max(1, min(n, MAX_GRID))
    cols = max(math.ceil(n / MAX_COLS), math.isqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


class _Star:
    """A static background star with a per-star twinkle phase."""

    __slots__ = ("x", "y", "r", "alpha", "phase")

    def __init__(self, x: float, y: float, r: float, alpha: int, phase: float):
        self.x = x
        self.y = y
        self.r = r
        self.alpha = alpha
        self.phase = phase


class Meteor:
    """A shooting star: a head moving at constant velocity with a fading trail.

    Pure geometry/lifetime logic (no Qt), so it is unit-testable on its own;
    the painting lives in ``MainWindow._draw_meteor``.
    """

    def __init__(self, x, y, vx, vy, length, life):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.length = length
        self.life = life      # frames to live
        self.age = 0

    def advance(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.age += 1

    @property
    def done(self) -> bool:
        return self.age >= self.life

    def alpha(self) -> float:
        """Overall opacity 0..1 — quick fade-in, gentle fade-out near the end."""
        fade_in = min(1.0, self.age / 6.0)
        fade_out = min(1.0, (self.life - self.age) / 12.0)
        return max(0.0, fade_in * fade_out)


def spawn_meteor(w: float, h: float) -> Meteor:
    """Make a shooting star that enters near the top and streaks down-right."""
    angle = math.radians(random.uniform(20, 38))
    speed = random.uniform(16, 30)
    vx = speed * math.cos(angle)
    vy = speed * math.sin(angle)
    x = random.uniform(-0.15 * w, 0.85 * w)
    y = random.uniform(-0.30 * h, -0.02 * h)
    length = random.uniform(160, 340)
    life = int((h - y + length) / max(1.0, vy)) + 6
    return Meteor(x, y, vx, vy, length, life)


def _rgba(rgb: tuple[int, int, int], alpha_f: float) -> QColor:
    """Build a QColor from an (r, g, b) tuple and a 0..1 alpha."""
    color = QColor(*rgb)
    color.setAlphaF(max(0.0, min(1.0, alpha_f)))
    return color


def make_starfield(w: float, h: float, n: int = STAR_COUNT) -> list[_Star]:
    """Scatter ``n`` static stars across a ``w`` x ``h`` area."""
    return [
        _Star(
            x=random.uniform(0, w),
            y=random.uniform(0, h),
            r=random.uniform(0.5, 1.7),
            alpha=random.randint(25, 150),
            phase=random.uniform(0, 2 * math.pi),
        )
        for _ in range(n)
    ]


STYLESHEET = """
QWidget#root { background: #000; }
QFrame#overlay {
    background: #23242c;
    border: 2px solid #5b6173;
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
QFrame#card[selected="true"] {
    background: #2b3c63; border: 2px solid #4c8bf5;
}
QFrame#card[selected="true"]:hover { background: #324672; border: 2px solid #6fa0ff; }
QLabel#section {
    color: #9aa0b4; font-size: 11px; font-weight: bold;
    text-transform: uppercase; letter-spacing: 1px;
}
QFrame#sep { background: #3a3d4a; max-height: 1px; min-height: 1px; }
QLabel#name { color: #e8e8ee; font-size: 13px; }
QLabel#badge {
    color: #cdd2ff; background: #404663; border-radius: 6px;
    padding: 1px 6px; font-size: 10px; font-weight: bold;
}
QWidget#listhost { background: transparent; border: none; }
"""


_icon: QIcon | None = None


def make_icon() -> QIcon:
    """Return the clipboard icon (drawn once in code, then cached)."""
    global _icon
    if _icon is not None:
        return _icon
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
    _icon = QIcon(pm)
    return _icon


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
        # Use width (not QRect.right(), which is x + width - 1) so a container
        # sized to fit exactly N columns does not wrap off the last one.
        right = rect.x() + rect.width() - m.right()
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
    shift_clicked = Signal()

    def __init__(self, name: str, hotkey: str):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setToolTip(name)
        self.setProperty("selected", False)

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
            if event.modifiers() & Qt.ShiftModifier:
                self.shift_clicked.emit()
            else:
                self.clicked.emit()
            # Accept so the press does not propagate to MainWindow.mousePressEvent,
            # which would hide the overlay (a click "outside" the dialog).
            event.accept()
            return
        super().mousePressEvent(event)

    def set_selected(self, on: bool) -> None:
        """Toggle the highlighted state (used by suffix cards)."""
        self.setProperty("selected", bool(on))
        # A dynamic property change needs a style re-polish to take effect.
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QWidget):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.setStyleSheet(STYLESHEET)  # scoped to this window, not the whole app
        self.config = load_config()
        self.hide_delay_ms = int(self.config.get("hide_delay_ms", 250))
        self.directory = ""
        self.prompts: list[dict] = []   # [{name, path}] — main prompts
        self.visible: list[dict] = []
        self.suffixes: list[dict] = []  # [{name, path}] — Suffix* prompts
        self._suffix_cards: dict[str, PromptCard] = {}  # stem -> card
        # Sticky selection: the stem of the suffix appended on copy ("" = none).
        self.selected_suffix: str = self.config.get("selected_suffix", "")
        self._tray_hint_shown = False
        self._autohide_armed = False
        self._suppress_autohide = False

        # Animated scrim: a twinkling starfield with occasional shooting stars,
        # ticked only while the overlay is visible (see summon/hide_to_tray).
        self._frame = 0
        self._stars: list[_Star] = []
        self._meteors: list[Meteor] = []
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(int(1000 / SCRIM_FPS))
        self._anim_timer.timeout.connect(self._tick_scrim)

        # Full-screen, frameless window painted solid black as a scrim, with
        # the dialog centered on top. (A see-through scrim isn't possible on
        # GNOME Wayland: a fullscreen surface has no desktop composited behind
        # it, so the backdrop is opaque regardless of alpha.)
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )

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
        # Width/height are sized to the grid in _fit_dialog().
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

        # The card grid is sized to exactly N columns and centered, so the
        # dialog can stay wider (for the search row) than a narrow grid.
        grid_row = QHBoxLayout()
        grid_row.setContentsMargins(0, 0, 0, 0)
        grid_row.addStretch(1)
        self.list_host = QWidget()
        self.list_host.setObjectName("listhost")
        self.flow = FlowLayout(self.list_host, margin=0, spacing=CARD_SPACING)
        grid_row.addWidget(self.list_host)
        grid_row.addStretch(1)
        root.addLayout(grid_row)

        # Suffix section: cards for Suffix* prompts. Selecting one only
        # highlights it; its text is appended to whatever main prompt is copied.
        self.suffix_section = QWidget()
        suffix_box = QVBoxLayout(self.suffix_section)
        suffix_box.setContentsMargins(0, 4, 0, 0)
        suffix_box.setSpacing(8)
        sep = QFrame()
        sep.setObjectName("sep")
        suffix_box.addWidget(sep)
        header = QLabel("Suffix prompts")
        header.setObjectName("section")
        suffix_box.addWidget(header)
        suffix_row = QHBoxLayout()
        suffix_row.setContentsMargins(0, 0, 0, 0)
        suffix_row.addStretch(1)
        self.suffix_host = QWidget()
        self.suffix_host.setObjectName("listhost")
        self.suffix_flow = FlowLayout(self.suffix_host, margin=0, spacing=CARD_SPACING)
        suffix_row.addWidget(self.suffix_host)
        suffix_row.addStretch(1)
        suffix_box.addLayout(suffix_row)
        self.suffix_section.setVisible(False)
        root.addWidget(self.suffix_section)

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
        self.directory = directory if directory and Path(directory).is_dir() else ""
        self.prompts = []
        self.suffixes = []
        if self.directory:
            files = sorted(
                Path(self.directory).glob("*.prompt"),
                key=lambda p: p.stem.lower(),
            )
            for p in files:
                entry = {"name": p.stem, "path": str(p)}
                if p.stem.startswith(SUFFIX_PREFIX):
                    self.suffixes.append(entry)
                else:
                    self.prompts.append(entry)
        # Drop a sticky selection that no longer exists in this folder.
        if self.selected_suffix and self.selected_suffix not in {
            s["name"] for s in self.suffixes
        }:
            self.selected_suffix = ""
            self.config["selected_suffix"] = ""
            save_config(self.config)
        self.rebuild_suffixes()
        self.rebuild_list()

    def rebuild_list(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)  # remove from view now; deleteLater is deferred
                w.deleteLater()

        query = self.search.text().strip().lower()
        if query:
            self.visible = [p for p in self.prompts if query in p["name"].lower()]
        else:
            self.visible = list(self.prompts)

        self._update_path_label()

        if not self.prompts:
            self._add_empty("No prompts. Choose a folder with .prompt files 📁")
        elif not self.visible:
            self._add_empty("No prompt matches the search.")
        else:
            # Show at most MAX_GRID cards; the rest are reachable via search.
            for i, p in enumerate(self.visible[:MAX_GRID]):
                hotkey = f"Alt+{i + 1}" if i < MAX_HOTKEYS else ""
                card = PromptCard(p["name"], hotkey)
                card.clicked.connect(lambda pp=p: self.copy_prompt(pp))
                card.shift_clicked.connect(lambda pp=p: self.copy_prompt(pp))
                self.flow.addWidget(card)

        self._fit_dialog()

    @staticmethod
    def _suffix_label(name: str) -> str:
        """Drop the 'Suffix' prefix for a cleaner label (the header names the section)."""
        rest = name[len(SUFFIX_PREFIX):].lstrip(" -_:·").strip()
        return rest or name

    def rebuild_suffixes(self) -> None:
        """(Re)build the suffix cards; selection comes from self.selected_suffix."""
        while self.suffix_flow.count():
            item = self.suffix_flow.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._suffix_cards = {}

        self.suffix_section.setVisible(bool(self.suffixes))
        for s in self.suffixes[:MAX_GRID]:
            card = PromptCard(self._suffix_label(s["name"]), "")
            card.setToolTip("Click to select · Shift+click to copy only this suffix")
            card.set_selected(s["name"] == self.selected_suffix)
            card.clicked.connect(lambda ss=s: self._toggle_suffix(ss))
            card.shift_clicked.connect(lambda ss=s: self._copy_suffix_only(ss))
            self.suffix_flow.addWidget(card)
            self._suffix_cards[s["name"]] = card

    def _toggle_suffix(self, suffix: dict) -> None:
        """Select a suffix, or deselect it if already selected (persisted in config)."""
        name = suffix["name"]
        self.selected_suffix = "" if self.selected_suffix == name else name
        self.config["selected_suffix"] = self.selected_suffix
        save_config(self.config)
        # Update highlight in place; no resize needed.
        for stem, card in self._suffix_cards.items():
            card.set_selected(stem == self.selected_suffix)

    def _update_path_label(self) -> None:
        if not self.directory:
            self.path_lbl.setText("No folder selected")
            return
        text = f"📂 {self.directory}  ·  {len(self.prompts)} prompts"
        if len(self.visible) > MAX_GRID:
            text += f"  ·  showing first {MAX_GRID}, refine your search"
        self.path_lbl.setText(text)

    @staticmethod
    def _grid_size(total: int, shown: int) -> tuple[int, int]:
        """Pixel (width, height) of a compact grid: columns fixed by ``total``,
        rows by what is currently ``shown`` (both capped at MAX_GRID)."""
        cols, _ = grid_dims(min(total, MAX_GRID))
        rows = math.ceil(min(shown, MAX_GRID) / cols)
        width = cols * CARD_WIDTH + (cols - 1) * CARD_SPACING
        height = rows * CARD_HEIGHT + (rows - 1) * CARD_SPACING
        return width, height

    def _fit_dialog(self) -> None:
        """Size the grid and dialog to a compact grid (no scrolling).

        Columns are fixed by the folder's prompt count (stable width), so the
        dialog does not jump around as a live search narrows the matches; only
        the row count (height) adapts to what is currently shown.
        """
        has_main = bool(self.prompts and self.visible)
        if has_main:
            inner_w, inner_h = self._grid_size(len(self.prompts), len(self.visible))
        else:
            inner_w = EMPTY_DIALOG_WIDTH - 2 * DIALOG_MARGIN
            inner_h = CARD_HEIGHT

        # Fixing the grid size makes the FlowLayout wrap at exactly `cols`.
        self.list_host.setFixedSize(inner_w, inner_h)

        # The suffix grid sizes itself the same way; the dialog widens to fit
        # whichever section is broader so neither grid wraps off-screen.
        content_w = inner_w
        if self.suffixes:
            suffix_w, suffix_h = self._grid_size(len(self.suffixes), len(self.suffixes))
            self.suffix_host.setFixedSize(suffix_w, suffix_h)
            content_w = max(content_w, suffix_w)

        floor = MIN_DIALOG_WIDTH if has_main else EMPTY_DIALOG_WIDTH
        dialog_w = max(floor, content_w + 2 * DIALOG_MARGIN)
        self.dialog_frame.setFixedWidth(dialog_w)
        # Recompute the frame layout now: after cards are added/removed the
        # layout's sizeHint is stale until the next event loop, so reading it
        # directly would keep the old height and clip newly added rows. An
        # explicit activate() forces a synchronous recalculation.
        frame_layout = self.dialog_frame.layout()
        frame_layout.activate()
        self.dialog_frame.setFixedHeight(frame_layout.sizeHint().height())

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

    def _read_text(self, path: str) -> str | None:
        """Read a prompt file, or surface a tray error and return None."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.tray.showMessage(APP_NAME, f"Read error: {exc}",
                                  QSystemTrayIcon.Critical, 3000)
            return None

    def _copy_and_hide(self, text: str, status: str) -> None:
        QApplication.clipboard().setText(text)
        self._flash_status(status)
        QTimer.singleShot(self.hide_delay_ms, self.hide_to_tray)

    def copy_prompt(self, prompt: dict) -> None:
        text = self._read_text(prompt["path"])
        if text is None:
            return
        status = f"✓ Copied: {prompt['name']}"
        suffix_text = self._selected_suffix_text()
        if suffix_text is not None:
            text = text + SUFFIX_SEPARATOR + suffix_text
            status += f"  +  {self._suffix_label(self.selected_suffix)}"
        self._copy_and_hide(text, status)

    def _copy_suffix_only(self, suffix: dict) -> None:
        """Shift+click on a suffix: copy just that suffix's text (no main prompt)."""
        text = self._read_text(suffix["path"])
        if text is None:
            return
        label = self._suffix_label(suffix["name"])
        self._copy_and_hide(text, f"✓ Copied suffix: {label}")

    def _selected_suffix_text(self) -> str | None:
        """Text of the sticky suffix prompt, or None if none is selected/readable."""
        if not self.selected_suffix:
            return None
        entry = next(
            (s for s in self.suffixes if s["name"] == self.selected_suffix), None
        )
        if entry is None:
            return None
        try:
            return Path(entry["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

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
        # Re-scan the folder on every open (e.g. via the hotkey), so prompts
        # added or removed since last time show up without a manual reload.
        self.reload_prompts()
        # Open on the screen under the cursor (multi-monitor), not just primary.
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setScreen(screen)
            geo = screen.geometry()
            self.setGeometry(geo)
            self._stars = make_starfield(geo.width(), geo.height())
        self._meteors = []
        self._frame = 0
        self._anim_timer.start()
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
        self._anim_timer.stop()  # no animation work while hidden
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
    def _tick_scrim(self) -> None:
        self._frame += 1
        w, h = self.width(), self.height()
        for mt in self._meteors:
            mt.advance()
        self._meteors = [
            mt for mt in self._meteors
            if not mt.done and mt.x - mt.length < w and mt.y - mt.length < h
        ]
        if len(self._meteors) < METEOR_MAX and random.random() < METEOR_SPAWN_CHANCE:
            self._meteors.append(spawn_meteor(w, h))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))  # solid black backdrop
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Twinkling starfield.
        painter.setPen(Qt.NoPen)
        for s in self._stars:
            twinkle = 0.55 + 0.45 * math.sin(self._frame * 0.05 + s.phase)
            color = QColor(*STAR_COLOR)
            color.setAlpha(max(0, min(255, int(s.alpha * twinkle))))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(s.x, s.y), s.r, s.r)

        # Shooting stars on top.
        for mt in self._meteors:
            self._draw_meteor(painter, mt)

    def _draw_meteor(self, painter: QPainter, mt: Meteor) -> None:
        a = mt.alpha()
        if a <= 0.0:
            return
        speed = math.hypot(mt.vx, mt.vy) or 1.0
        ux, uy = mt.vx / speed, mt.vy / speed
        head = QPointF(mt.x, mt.y)
        tail = QPointF(mt.x - ux * mt.length, mt.y - uy * mt.length)

        grad = QLinearGradient(head, tail)
        grad.setColorAt(0.0, _rgba(STAR_COLOR, 0.9 * a))
        grad.setColorAt(0.4, _rgba(METEOR_COLOR, 0.35 * a))
        grad.setColorAt(1.0, _rgba(METEOR_COLOR, 0.0))
        pen = QPen(QBrush(grad), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(head, tail)

        # Bright head.
        painter.setPen(Qt.NoPen)
        painter.setBrush(_rgba((235, 240, 255), a))
        painter.drawEllipse(head, 1.9, 1.9)

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
