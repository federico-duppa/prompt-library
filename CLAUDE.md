# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small Ubuntu/GNOME (X11 + Wayland) desktop tray app written in Python + PySide6. It scans a folder for `*.prompt` files and shows them as clickable cards in a centered, scrim-dimmed modal overlay; clicking a card (or pressing `Alt+1..9`) copies that prompt's text to the clipboard, then hides back to the tray.

## Commands

Setup and run go through Bash scripts that wrap a project-local `.venv` — there is no global Python entry point.

```bash
./install.sh                    # venv + PySide6 + icon + .desktop menu + autostart + Super+Shift+P hotkey
./install.sh '<Control><Alt>p'  # same, with a different global hotkey

./prompt-library            # run the window (uses .venv python by absolute path)
./prompt-library --show     # open/wake an existing instance (what the global hotkey runs)
./prompt-library --tray     # start hidden in the tray (what autostart runs)

./setup-hotkey.sh '<Super><Shift>p'   # register/replace just the GNOME global hotkey
./setup-hotkey.sh --remove            # remove it
```

### Tests and lint

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # one-time: pytest, pytest-qt, ruff

.venv/bin/python -m pytest                 # run all tests
.venv/bin/python -m pytest tests/test_app.py::test_search_filters_visible   # single test
.venv/bin/ruff check .                     # lint
.venv/bin/ruff check --fix .               # lint + autofix
```

Tooling config lives in `pyproject.toml` (ruff rules + pytest `testpaths`). GUI tests run headless via the Qt **offscreen** platform, forced in `tests/conftest.py` — no display server needed. `tests/test_app.py` builds a real `MainWindow` against a throwaway prompt folder by monkeypatching `app.load_config`; the `qapp` fixture (pytest-qt) owns the singleton `QApplication`. There is no separate build step; the `.venv` is created by `install.sh` and the `prompt-library` launcher refuses to run until it exists.

## Architecture

Three modules under `prompt_library/` (run as `python -m prompt_library`):

- **`__main__.py`** — entry point and **single-instance** coordinator. Uses `QLocalServer`/`QLocalSocket` on a per-user socket name (`prompt-library-<user>`). On launch it first tries to connect to an existing instance and send `show`; if that succeeds it exits immediately, otherwise it becomes the primary, listens on the socket, and routes incoming `show` messages to `MainWindow.summon()`. This is what makes the GNOME hotkey (`--show`) wake the already-running tray instance instead of spawning a second one.
- **`app.py`** — all UI and behavior in `MainWindow`, plus helper widgets (`FlowLayout`, `PromptCard`) and `make_icon()` (the clipboard icon is drawn in code with `QPainter`, no asset files).
- **`config.py`** — JSON config at `~/.config/prompt-library/config.json` (`directory`, `hide_delay_ms`). Reads/writes are best-effort; all I/O errors are swallowed so a bad config never crashes the app.

### Key design points

- **Overlay model, not a normal window.** `MainWindow` is a frameless, translucent, full-screen `Qt.Dialog` that paints a dark scrim (`paintEvent`) and centers the dialog frame using layout stretches. Clicking the dark area (`mousePressEvent`) or `Esc` hides to tray. `closeEvent` is overridden to hide instead of quit.
- **Autohide-on-focus-loss is gated.** After `summon()`, autohide is *armed* only after a ~450ms delay (`_arm_autohide`) and suppressed during native dialogs (`_suppress_autohide`, used around `choose_directory`'s `QFileDialog`). This prevents the window from vanishing the instant it gains/loses focus or while a file picker is open. Be careful editing the show/hide flow — these flags interact.
- **Cards and hotkeys are rebuilt from filtered state.** `reload_prompts()` reads the folder (flat, non-recursive `glob("*.prompt")`, sorted by stem); `rebuild_list()` filters by the search box into `self.visible` and re-creates all `PromptCard`s. `Alt+1..9` map to the first nine entries of `self.visible`, so the numbering follows the current search filter. `_fit_dialog_height()` computes column/row count to size the dialog to its content up to `DIALOG_MAX_HEIGHT`.
- **Prompt display name** is the filename stem: `summarize text.prompt` → "summarize text".
- **Tunable layout constants** live at the top of `app.py`: `SCRIM_ALPHA`, `DIALOG_WIDTH`, `DIALOG_MAX_HEIGHT`, `CARD_WIDTH`, `CARD_HEIGHT`, `CARD_SPACING`, `MAX_HOTKEYS`. The whole visual theme is one `STYLESHEET` string (Qt CSS via object names like `#card`, `#overlay`, `#badge`).

### Global hotkey (Wayland constraint)

On Wayland an app cannot grab a global hotkey itself. `setup-hotkey.sh` instead registers a **GNOME custom keybinding** via `gsettings` that runs `./prompt-library --show`; GNOME captures the key and the single-instance logic does the rest. This is why the hotkey path goes through `gsettings`/`.desktop` files rather than Qt. `install.sh` also writes a menu `.desktop` (`--show`) and an autostart `.desktop` (`--tray`).
