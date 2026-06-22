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
"""Tests for the widget layer. Run headless via the offscreen platform.

The `qapp` fixture (pytest-qt) provides the singleton QApplication.
"""
import pytest
from PySide6.QtWidgets import QApplication

from prompt_library import app as app_module
from prompt_library.app import FlowLayout, MainWindow, PromptCard, make_icon


@pytest.fixture
def prompt_dir(tmp_path):
    """A folder with three .prompt files (alphabetical: alpha, beta, gamma)."""
    (tmp_path / "beta.prompt").write_text("BETA BODY", encoding="utf-8")
    (tmp_path / "alpha.prompt").write_text("ALPHA BODY", encoding="utf-8")
    (tmp_path / "gamma.prompt").write_text("GAMMA BODY", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")  # not *.prompt
    return tmp_path


@pytest.fixture
def window(qapp, monkeypatch, prompt_dir):
    """A MainWindow whose config points at the throwaway prompt_dir."""
    cfg = {"directory": str(prompt_dir), "hide_delay_ms": 0}
    monkeypatch.setattr(app_module, "load_config", lambda: dict(cfg))
    win = MainWindow(qapp)
    yield win
    win.deleteLater()


def test_make_icon_is_not_null(qapp):
    assert not make_icon().isNull()


def test_reload_scans_only_prompt_files_sorted(window):
    names = [p["name"] for p in window.prompts]
    assert names == ["alpha", "beta", "gamma"]  # sorted by stem, .txt excluded


def test_cards_built_for_each_prompt(window):
    cards = window.list_host.findChildren(PromptCard)
    assert len(cards) == 3


def test_search_filters_visible(window):
    window.search.setText("amma")  # substring of "gamma"
    visible = [p["name"] for p in window.visible]
    assert visible == ["gamma"]


def test_search_no_match_clears_visible(window):
    window.search.setText("zzz")
    assert window.visible == []


def test_trigger_index_copies_body_to_clipboard(window):
    window.trigger_index(0)  # first visible == "alpha"
    assert QApplication.clipboard().text() == "ALPHA BODY"


def test_trigger_index_follows_search_renumbering(window):
    window.search.setText("gamma")
    window.trigger_index(0)  # only match is now index 0
    assert QApplication.clipboard().text() == "GAMMA BODY"


def test_trigger_index_out_of_range_is_noop(window):
    QApplication.clipboard().setText("untouched")
    window.trigger_index(99)
    assert QApplication.clipboard().text() == "untouched"


def test_empty_directory_shows_no_cards(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(
        app_module, "load_config",
        lambda: {"directory": str(tmp_path), "hide_delay_ms": 0},
    )
    win = MainWindow(qapp)
    assert win.prompts == []
    assert win.list_host.findChildren(PromptCard) == []
    win.deleteLater()


def test_display_capped_at_25_but_visible_keeps_all(qapp, monkeypatch, tmp_path):
    for i in range(30):
        (tmp_path / f"p{i:02d}.prompt").write_text(f"BODY {i}", encoding="utf-8")
    monkeypatch.setattr(
        app_module, "load_config",
        lambda: {"directory": str(tmp_path), "hide_delay_ms": 0},
    )
    win = MainWindow(qapp)
    assert len(win.prompts) == 30
    assert len(win.visible) == 30                       # full list retained
    assert len(win.list_host.findChildren(PromptCard)) == 25  # only 25 rendered
    win.deleteLater()


def test_flowlayout_basic_accounting(qapp):
    layout = FlowLayout()
    before = layout.count()
    from PySide6.QtWidgets import QLabel

    layout.addWidget(QLabel("x"))
    assert layout.count() == before + 1
    assert layout.takeAt(0) is not None
    assert layout.count() == before


def test_grid_renders_full_5x5(qapp, monkeypatch, tmp_path):
    """25 prompts must render as a real 5x5 grid (all 25 visible, no wrap).

    Guards the QRect.right() off-by-one in FlowLayout._do_layout: with the
    host sized to exactly 5 columns, reverting to `rect.right()` wraps the
    5th column away (rendering 4x7, only 20 cards fit the fixed height).
    """
    for i in range(25):
        (tmp_path / f"p{i:02d}.prompt").write_text("X", encoding="utf-8")
    monkeypatch.setattr(
        app_module, "load_config",
        lambda: {"directory": str(tmp_path), "hide_delay_ms": 0},
    )
    win = MainWindow(qapp)
    win.show()
    qapp.processEvents()
    qapp.processEvents()
    cards = win.list_host.findChildren(PromptCard)
    cols = len({c.x() for c in cards})
    rows = len({c.y() for c in cards})
    win.hide()
    win.deleteLater()
    assert (cols, rows) == (5, 5)


# ---------- suffix prompts (composition) ----------
from prompt_library.app import SUFFIX_SEPARATOR  # noqa: E402


@pytest.fixture
def suffix_dir(tmp_path):
    """Two main prompts plus two Suffix* prompts."""
    (tmp_path / "alpha.prompt").write_text("ALPHA BODY", encoding="utf-8")
    (tmp_path / "beta.prompt").write_text("BETA BODY", encoding="utf-8")
    (tmp_path / "Suffix in spanish.prompt").write_text("SUFFIX ES", encoding="utf-8")
    (tmp_path / "Suffix terse.prompt").write_text("SUFFIX TERSE", encoding="utf-8")
    return tmp_path


def _make_window(qapp, monkeypatch, directory, selected_suffix=""):
    """Build a MainWindow with load/save_config redirected (save is captured)."""
    cfg = {
        "directory": str(directory),
        "hide_delay_ms": 0,
        "selected_suffix": selected_suffix,
    }
    monkeypatch.setattr(app_module, "load_config", lambda: dict(cfg))
    saved = {}
    monkeypatch.setattr(app_module, "save_config", lambda c: saved.update(c))
    win = MainWindow(qapp)
    win._saved = saved  # test-only handle on the last persisted config
    return win


@pytest.fixture
def suffix_window(qapp, monkeypatch, suffix_dir):
    win = _make_window(qapp, monkeypatch, suffix_dir)
    yield win
    win.deleteLater()


def test_suffix_split_separates_prefixed_prompts(suffix_window):
    assert [p["name"] for p in suffix_window.prompts] == ["alpha", "beta"]
    assert [s["name"] for s in suffix_window.suffixes] == [
        "Suffix in spanish", "Suffix terse",
    ]


def test_suffix_label_strips_prefix(suffix_window):
    labels = [suffix_window._suffix_label(s["name"]) for s in suffix_window.suffixes]
    assert labels == ["in spanish", "terse"]


def test_select_suffix_highlights_and_persists(suffix_window):
    suffix_window._toggle_suffix(suffix_window.suffixes[0])
    assert suffix_window.selected_suffix == "Suffix in spanish"
    assert suffix_window._saved["selected_suffix"] == "Suffix in spanish"
    assert suffix_window._suffix_cards["Suffix in spanish"].property("selected") is True
    assert suffix_window._suffix_cards["Suffix terse"].property("selected") is False


def test_reselecting_same_suffix_deselects(suffix_window):
    suffix_window._toggle_suffix(suffix_window.suffixes[0])
    suffix_window._toggle_suffix(suffix_window.suffixes[0])
    assert suffix_window.selected_suffix == ""
    assert suffix_window._saved["selected_suffix"] == ""
    assert suffix_window._suffix_cards["Suffix in spanish"].property("selected") is False


def test_clicking_suffix_card_toggles_selection(suffix_window):
    # Exercise the real mouse path: the card's clicked signal -> _toggle_suffix.
    card = suffix_window._suffix_cards["Suffix terse"]
    card.clicked.emit()
    assert suffix_window.selected_suffix == "Suffix terse"
    assert card.property("selected") is True
    card.clicked.emit()  # click again deselects
    assert suffix_window.selected_suffix == ""
    assert card.property("selected") is False


def test_card_press_is_accepted_so_overlay_stays_open(suffix_window):
    # A plain left press on a card must be accepted (not propagated to
    # MainWindow.mousePressEvent, which would hide the overlay on selection).
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    card = suffix_window._suffix_cards["Suffix terse"]
    ev = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    card.mousePressEvent(ev)
    assert ev.isAccepted()
    assert suffix_window.selected_suffix == "Suffix terse"  # plain click selects


def test_shift_click_suffix_copies_only_that_suffix(suffix_window):
    suffix_window._toggle_suffix(suffix_window.suffixes[0])  # selects "Suffix in spanish"
    card = suffix_window._suffix_cards["Suffix terse"]
    card.shift_clicked.emit()  # shift+click a *different* suffix
    assert QApplication.clipboard().text() == "SUFFIX TERSE"  # only the suffix body
    assert suffix_window.selected_suffix == "Suffix in spanish"  # selection unchanged


def test_shift_click_main_card_still_copies(suffix_window):
    # findChildren keeps insertion order, which is the visible order (alpha, beta).
    first_main = suffix_window.list_host.findChildren(PromptCard)[0]
    first_main.shift_clicked.emit()
    assert QApplication.clipboard().text() == "ALPHA BODY"


def test_copy_composes_main_plus_selected_suffix(suffix_window):
    suffix_window._toggle_suffix(suffix_window.suffixes[0])  # "Suffix in spanish"
    suffix_window.trigger_index(1)  # main "beta"
    expected = "BETA BODY" + SUFFIX_SEPARATOR + "SUFFIX ES"
    assert QApplication.clipboard().text() == expected


def test_copy_without_selection_is_plain(suffix_window):
    suffix_window.trigger_index(0)  # main "alpha"
    assert QApplication.clipboard().text() == "ALPHA BODY"


def test_sticky_selection_applied_on_init(qapp, monkeypatch, suffix_dir):
    win = _make_window(qapp, monkeypatch, suffix_dir, selected_suffix="Suffix terse")
    assert win.selected_suffix == "Suffix terse"
    assert win._suffix_cards["Suffix terse"].property("selected") is True
    win.deleteLater()


def test_stale_selection_dropped_on_load(qapp, monkeypatch, suffix_dir):
    win = _make_window(qapp, monkeypatch, suffix_dir, selected_suffix="Suffix gone")
    assert win.selected_suffix == ""
    assert win._saved.get("selected_suffix") == ""  # the clear was persisted
    win.deleteLater()


def test_only_suffix_folder_keeps_section(qapp, monkeypatch, tmp_path):
    (tmp_path / "Suffix only.prompt").write_text("X", encoding="utf-8")
    win = _make_window(qapp, monkeypatch, tmp_path)
    assert win.prompts == []
    assert len(win.suffixes) == 1
    assert not win.suffix_section.isHidden()
    win.deleteLater()
