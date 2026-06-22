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
"""Best-effort registration of the GNOME global hotkey on first launch.

On Wayland an app can't grab a global hotkey itself, so the .deb can't do it at
install time either (postinst runs as root; the binding lives in per-user
gsettings). Instead the running app registers it once, the first time the user
opens it, by invoking the same ``setup-hotkey.sh`` script the source install
uses. A marker file under the config dir means we never fight the user: if they
later remove the binding, we don't keep re-adding it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .config import config_dir

DEFAULT_BINDING = "<Super><Shift>p"
_MARKER_NAME = "hotkey-registered"


def _find_script() -> str | None:
    """Locate the hotkey script in both packaged and source layouts."""
    override = os.environ.get("PROMPT_LIBRARY_HOTKEY")
    if override and Path(override).exists():
        return override
    # Installed by the .deb as /usr/bin/prompt-library-hotkey.
    on_path = shutil.which("prompt-library-hotkey")
    if on_path:
        return on_path
    # Source checkout: setup-hotkey.sh at the repo root (two levels up).
    dev = Path(__file__).resolve().parent.parent / "setup-hotkey.sh"
    if dev.exists():
        return str(dev)
    return None


def ensure_hotkey_registered(binding: str = DEFAULT_BINDING) -> None:
    """Register the global hotkey once. Best-effort: never raises, never blocks long."""
    try:
        marker = config_dir() / _MARKER_NAME
        if marker.exists():
            return
        if not shutil.which("gsettings"):
            return  # not a GNOME session; try again next launch
        script = _find_script()
        if not script:
            return
        subprocess.run(
            [script, binding],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        marker.write_text(binding, encoding="utf-8")
    except Exception:
        # A failed hotkey registration must never stop the app from opening.
        pass
