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
"""Loading and saving of configuration in the XDG directory."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIRNAME = "prompt-library"

DEFAULTS = {
    "directory": "",        # folder to scan; empty => the user will be prompted for one
    "hide_delay_ms": 250,   # ms after copying before hiding to the tray
    "selected_suffix": "",  # stem of the sticky suffix prompt appended on copy
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / APP_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass
