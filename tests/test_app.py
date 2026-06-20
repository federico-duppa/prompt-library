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


def test_flowlayout_basic_accounting(qapp):
    layout = FlowLayout()
    before = layout.count()
    from PySide6.QtWidgets import QLabel

    layout.addWidget(QLabel("x"))
    assert layout.count() == before + 1
    assert layout.takeAt(0) is not None
    assert layout.count() == before
