# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small Ubuntu/GNOME (X11 + Wayland) desktop tray app written in Python + PySide6. It scans a folder for `*.prompt` files and shows them as clickable cards in a centered modal over a full-screen animated scrim (a starfield with shooting stars); clicking a card (or pressing `Alt+1..9`) copies that prompt's text to the clipboard, then hides back to the tray.

## Commands

Setup and run go through Bash scripts that wrap a project-local `.venv`. The package also exposes a `prompt-library` console entry point (`[project.scripts]` → `prompt_library.__main__:main`), so `pipx install .` / `pip install .` work too; the repo-root `prompt-library` Bash launcher is the same name but a different file (it runs the module from source via the venv).

```bash
./install.sh                    # venv + app + icon + .desktop menu + autostart + Super+Shift+P hotkey
./install.sh '<Control><Alt>p'  # same, with a different global hotkey

./prompt-library            # run the window (uses .venv python by absolute path)
./prompt-library --show     # open/wake an existing instance (what the global hotkey runs)
./prompt-library --tray     # start hidden in the tray (what autostart runs)

./setup-hotkey.sh '<Super><Shift>p'   # register/replace just the GNOME global hotkey
./setup-hotkey.sh --remove            # remove it
```

### Tests and lint

```bash
.venv/bin/python -m pip install -e ".[dev]"   # one-time: app + pytest, pytest-qt, ruff

.venv/bin/python -m pytest                 # run all tests
.venv/bin/python -m pytest tests/test_app.py::test_search_filters_visible   # single test
.venv/bin/ruff check .                     # lint
.venv/bin/ruff check --fix .               # lint + autofix
```

All tooling and dependencies live in `pyproject.toml` (runtime deps, the `dev` extra, ruff rules, pytest `testpaths`, the `prompt-library` console entry point, and the hatchling build) — there are no `requirements*.txt` files. CI (`.github/workflows/ci.yml`) runs ruff + pytest on Python 3.10–3.12; it installs `libegl1 libxkbcommon0 libdbus-1-3` so PySide6 imports headless. GUI tests run headless via the Qt **offscreen** platform, forced in `tests/conftest.py` — no display server needed. `tests/test_app.py` builds a real `MainWindow` against a throwaway prompt folder by monkeypatching `app.load_config`; the `qapp` fixture (pytest-qt) owns the singleton `QApplication`. There is no separate build step; the `.venv` is created by `install.sh` and the `prompt-library` launcher refuses to run until it exists.

## Architecture

Three modules under `prompt_library/` (run as `python -m prompt_library`):

- **`__main__.py`** — entry point and **single-instance** coordinator. Uses `QLocalServer`/`QLocalSocket` on a per-user socket name (`prompt-library-<user>`). On launch it first tries to connect to an existing instance and send `show`; if that succeeds it exits immediately, otherwise it becomes the primary, listens on the socket, and routes incoming `show` messages to `MainWindow.summon()`. This is what makes the GNOME hotkey (`--show`) wake the already-running tray instance instead of spawning a second one.
- **`app.py`** — all UI and behavior in `MainWindow`, plus helper widgets (`FlowLayout`, `PromptCard`) and `make_icon()` (the clipboard icon is drawn in code with `QPainter`, no asset files).
- **`config.py`** — JSON config at `~/.config/prompt-library/config.json` (`directory`, `hide_delay_ms`, `selected_suffix`). Reads/writes are best-effort; all I/O errors are swallowed so a bad config never crashes the app.

### Key design points

- **Overlay model, not a normal window.** `MainWindow` is a frameless, full-screen `Qt.Dialog` that paints a solid black scrim (`paintEvent`) and centers the dialog frame using layout stretches. Clicking the dark area (`mousePressEvent`) or `Esc` hides to tray. `closeEvent` is overridden to hide instead of quit. `summon()` targets the screen under the cursor (`QGuiApplication.screenAt`) before `showFullScreen()` for multi-monitor setups. The scrim is opaque on purpose: GNOME Wayland doesn't composite the desktop behind a fullscreen surface, so a see-through scrim renders black regardless of alpha — translucency was removed rather than left as dead config.
- **The scrim is animated (twinkling starfield + shooting stars).** `paintEvent` fills black, then draws the `_stars` (with a `sin`-based twinkle keyed to `self._frame`) and the live `_meteors`. A `QTimer` at `SCRIM_FPS` runs `_tick_scrim` (advance meteors, cull off-screen/expired, probabilistically spawn under `METEOR_MAX`, `self.update()`), and is **started in `summon()` / stopped in `hide_to_tray()`** so there's zero animation cost while hidden. `Meteor`, `spawn_meteor`, and `make_starfield` are pure (no Qt) and unit-tested in `tests/test_scrim.py`; only `MainWindow._draw_meteor` touches the painter (a gradient trail + bright head).
- **Autohide-on-focus-loss is gated.** After `summon()`, autohide is *armed* only after a ~450ms delay (`_arm_autohide`) and suppressed during native dialogs (`_suppress_autohide`, used around `choose_directory`'s `QFileDialog`). This prevents the window from vanishing the instant it gains/loses focus or while a file picker is open. Be careful editing the show/hide flow — these flags interact.
- **Cards and hotkeys are rebuilt from filtered state.** `reload_prompts()` reads the folder (flat, non-recursive `glob("*.prompt")`, sorted by stem); `rebuild_list()` filters by the search box into `self.visible` and renders the first `MAX_GRID` (25) as `PromptCard`s (the rest stay reachable via search — `self.visible` keeps the full filtered list). `Alt+1..9` map to the first nine entries of `self.visible`, so the numbering follows the current search filter.
- **The grid is sized to a compact rectangle, never scrolls.** `grid_dims(n)` (module-level, unit-tested in `tests/test_grid.py`) returns `(cols, rows)` for the smallest vertical rectangle holding `n` cards — capped at 5×5, perfect squares (4/9/16/25) become squares. `_fit_dialog()` sets `list_host` to exactly that pixel size (so `FlowLayout` wraps at `cols`) and centers it; the dialog frame sizes its width to fit the grid (floored at `MIN_DIALOG_WIDTH` so the search row stays usable) and its height to the layout's `sizeHint`. There is no `QScrollArea`. **Columns are fixed by the folder's prompt count, not the live match count** — so the dialog width stays put while a search narrows results (only the row count / height adapts); don't reintroduce per-keystroke width jumps. Note: `FlowLayout._do_layout` must use `rect.x() + rect.width()` for the right edge, not `QRect.right()` (off by one) — otherwise a container sized to exactly `cols` wraps off its last column.
- **Suffix prompts enable composition.** `reload_prompts()` splits the folder by stem prefix: `SUFFIX_PREFIX` (`"Suffix"`, case-sensitive) goes into `self.suffixes` (shown in a separate section below the main grid, unaffected by the search box), the rest into `self.prompts`. A suffix card click `_toggle_suffix()`s its highlight (it does **not** copy/close); the chosen suffix's stem is the sticky `selected_suffix` (persisted via `save_config`, validated/dropped on reload if its file is gone, re-applied on the next open). `copy_prompt()` appends the selected suffix's text after `SUFFIX_SEPARATOR` (`"\n\n"`). Selection is keyed by **stem**, not path, everywhere (config value, `_suffix_cards` map, toggle compare). `_fit_dialog()` sizes the suffix host with the same `_grid_size()` helper and widens the dialog to whichever section is broader.
- **`_fit_dialog()` must `activate()` the frame layout before reading `sizeHint()`.** After cards are added/removed the layout's `sizeHint` is stale until the next event loop, so reading it directly keeps the old height and clips new rows; the explicit `frame_layout.activate()` forces a synchronous recalc. `summon()` also calls `reload_prompts()` on every open so folder changes show up without a manual reload.
- **Prompt display name** is the filename stem: `summarize text.prompt` → "summarize text" (suffix cards additionally strip the leading `Suffix` prefix via `_suffix_label`).
- **Tunable constants** live at the top of `app.py`: layout (`CARD_WIDTH`, `CARD_HEIGHT`, `CARD_SPACING`, `MAX_COLS`/`MAX_GRID`, `MIN_DIALOG_WIDTH`, `EMPTY_DIALOG_WIDTH`, `DIALOG_MARGIN`, `MAX_HOTKEYS`) and the scrim animation (`SCRIM_FPS`, `STAR_COUNT`, `METEOR_MAX`, `METEOR_SPAWN_CHANCE`, `STAR_COLOR`, `METEOR_COLOR`). The whole visual theme is one `STYLESHEET` string applied via `app.setStyleSheet` in `MainWindow.__init__` (Qt CSS through object names like `#card`, `#overlay`, `#badge`).

### Global hotkey (Wayland constraint)

On Wayland an app cannot grab a global hotkey itself. `setup-hotkey.sh` instead registers a **GNOME custom keybinding** via `gsettings` that runs `./prompt-library --show`; GNOME captures the key and the single-instance logic does the rest. This is why the hotkey path goes through `gsettings`/`.desktop` files rather than Qt. `install.sh` also writes a menu `.desktop` (`--show`) and an autostart `.desktop` (`--tray`).
