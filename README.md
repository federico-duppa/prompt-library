# Prompt Library

A small desktop app for Ubuntu (GNOME/Wayland) that lives in the **system tray**
and lets you copy prompts to the clipboard with a click or with `Alt+<number>`. It
appears as a **centered modal overlay** (Alt+F2 aesthetic) that dims the rest of the screen.

## What it does

- Scans a folder (flat, non-recursive) looking for `*.prompt` files.
- Shows each prompt by its name (`summarize text.prompt` → **summarize text**)
  as **cards in a grid** (fixed width, designed not to get in the way of autotiling).
- **Click** a card → copies its content to the clipboard.
- **Alt+1 … Alt+9** → copy the first nine visible cards (the badge shows it on each one).
- After copying, the window hides to the tray a few ms later.
- Remembers the last folder used; on first launch it offers to pick one.
- **Global hotkey `Super+Shift+P`** to show the window from anywhere.
- Search box with renumbering of the `Alt+N` shortcuts over the filtered results.

## Interface

- **Overlay with scrim:** the window covers the whole screen with a solid black backdrop,
  highlighting the centered dialog (which has a border and a shadow). A see-through scrim
  isn't possible on GNOME Wayland — a fullscreen surface has no desktop composited behind it.
- **Closing:** `Esc` or **click on the dark area** (outside the dialog). It also hides when it
  loses focus. Clicks inside the dialog do not close it.
- **Compact adaptive grid:** the dialog sizes itself to a compact rectangle — up to **25 prompts (5×5)** without scrolling. Fewer prompts use the smallest vertical rectangle (a square for 4, 9, 16, 25). With more than 25 matches, the first 25 are shown and you narrow them with the search box.
- **Adjustable appearance** from the constants at the top of `prompt_library/app.py`:
  `CARD_WIDTH`, `CARD_HEIGHT`, `MAX_COLS`, `MIN_DIALOG_WIDTH`.

## Why `Super+Shift+P` and not `Super+P`

`Super+P` is reserved by GNOME (display mode) and, on top of that, on **Wayland** no app
can capture global hotkeys on its own. The robust solution is to register a custom GNOME
hotkey (via `gsettings`) that launches the app; the app uses **single instance**, so the
second invocation simply wakes the already-open window. It works on X11 and Wayland.

You can choose another combination at install time.

## Installation

```bash
./install.sh                 # venv + PySide6 + icon + menu + autostart + Super+Shift+P hotkey
# or with another combination:
./install.sh '<Control><Alt>p'
```

`install.sh` sets up:
- the app in the applications menu,
- autostart at login (starts hidden in the tray, `--tray`),
- the global hotkey registered.

### Hotkey only (if you already have the venv)

```bash
./setup-hotkey.sh                 # <Super><Shift>p
./setup-hotkey.sh '<Control><Alt>p'
./setup-hotkey.sh --remove        # remove it
```

## Manual usage

```bash
./prompt-library            # opens the window
./prompt-library --show     # opens/wakes (what the global hotkey invokes)
./prompt-library --tray     # starts hidden in the tray (what autostart uses)
```

- **Left click on the tray icon**: toggles show/hide.
- **Icon menu**: Show · Choose folder · Reload · Quit.
- Inside the dialog: `Ctrl+F` search, `Ctrl+R` reload, `Alt+1..9` copy.
- To close: `Esc` or click on the dark background area.

## Structure

```
prompt_library/        Python package (app.py, __main__.py, config.py)
prompt-library         launcher (uses the venv's python by absolute path)
install.sh             full installation
setup-hotkey.sh        registers/removes the GNOME global hotkey
examples/              example prompts
```

Config in `~/.config/prompt-library/config.json` (`directory`, `hide_delay_ms`).

## Requirements

- Python 3.10+
- GNOME (the tray icon needs the AppIndicator/StatusNotifier extension,
  which Ubuntu ships enabled by default).

## Development

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # pytest, pytest-qt, ruff
.venv/bin/python -m pytest        # tests (headless, Qt offscreen)
.venv/bin/ruff check .            # lint
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
