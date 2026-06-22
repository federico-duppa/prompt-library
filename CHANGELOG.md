# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-22

### Added
- **Shift+click a suffix to copy only that suffix** (and close), for when you just
  need the modifier text on its own — without changing the sticky selection.

### Fixed
- Selecting or deselecting a suffix no longer closes the overlay: the card now
  accepts the mouse press instead of letting it propagate to the scrim's
  click-to-close handler. As a side effect, copying a main prompt now hides after
  the configured `hide_delay_ms` (showing the "✓ Copied" status) instead of
  closing instantly.

## [0.2.0] - 2026-06-22

### Added
- **Suffix prompts for clipboard composition.** Prompts named `Suffix*.prompt`
  appear in a separate section below the main grid. Selecting one only highlights
  it (click again to deselect) and is sticky across opens (persisted as
  `selected_suffix` in the config). Copying a main prompt then appends the selected
  suffix's text after a blank line, so a reusable modifier can be pinned onto any
  prompt.
- **Self-contained Debian package.** `packaging/build-deb.sh` builds a vendored
  `.deb` that bundles PySide6/Qt under `/opt/prompt-library`, installs a launcher,
  menu entry, system-wide autostart and icon, and registers the global hotkey on
  first launch. Verified on Ubuntu 22.04/24.04 and Debian 12.

### Changed
- The selector now re-scans the folder on every open (including via the hotkey),
  so added/removed prompts show up without a manual reload.
- The version is single-sourced in `prompt_library/__init__.py`; `pyproject.toml`
  reads it dynamically and the `.deb` build derives it from there.

### Fixed
- The modal now resizes correctly after a reload: forcing a synchronous layout
  recalculation stops newly added prompts from being clipped.

## [0.1.0] - 2026-06-19

### Added
- Initial release: GNOME tray app that scans a folder for `*.prompt` files and
  shows them as clickable cards in a full-screen overlay with an animated starfield
  scrim. Click or `Alt+1..9` copies a prompt to the clipboard. Global hotkey
  (`Super+Shift+P`), single-instance wake, search box, and a compact 5×5 grid.

[0.3.0]: https://github.com/federico-duppa/prompt-library/releases/tag/v0.3.0
[0.2.0]: https://github.com/federico-duppa/prompt-library/releases/tag/v0.2.0
[0.1.0]: https://github.com/federico-duppa/prompt-library/releases/tag/v0.1.0
