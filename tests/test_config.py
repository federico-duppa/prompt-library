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
"""Tests for the JSON config layer (pure logic, no Qt)."""
from prompt_library import config


def _isolate(monkeypatch, tmp_path):
    """Point the config dir at a throwaway XDG_CONFIG_HOME."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def test_defaults_when_no_file(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = config.load_config()
    assert cfg == config.DEFAULTS
    assert cfg is not config.DEFAULTS  # must be a copy, not the shared dict


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.save_config({"directory": "/tmp/prompts", "hide_delay_ms": 500})
    cfg = config.load_config()
    assert cfg["directory"] == "/tmp/prompts"
    assert cfg["hide_delay_ms"] == 500


def test_partial_file_keeps_defaults(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.config_path().write_text('{"directory": "/x"}', encoding="utf-8")
    cfg = config.load_config()
    assert cfg["directory"] == "/x"
    assert cfg["hide_delay_ms"] == config.DEFAULTS["hide_delay_ms"]


def test_malformed_json_falls_back_to_defaults(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.config_path().write_text("{not valid json", encoding="utf-8")
    assert config.load_config() == config.DEFAULTS


def test_config_dir_is_created(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    d = config.config_dir()
    assert d.is_dir()
    assert d.name == config.APP_DIRNAME
