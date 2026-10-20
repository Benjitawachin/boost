import pytest
import yaml

from monitor.config import ConfigError, load_settings

BASE = {
    "login": {"url": "https://example.test/", "logged_in_selector": "#cuenta"},
    "check": {"mode": "page", "match_url": "https://example.test/partido", "available_selector": ".libre"},
    "poll": {"min_delay_s": 5, "max_delay_s": 7},
}


def write(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path):
    settings = load_settings(write(tmp_path, BASE))
    assert settings.check.mode == "page"
    assert settings.browser.profile_dir == tmp_path / "browser_profile"


def test_delay_below_five_seconds_is_clamped(tmp_path):
    data = {**BASE, "poll": {"min_delay_s": 1, "max_delay_s": 2}}
    settings = load_settings(write(tmp_path, data))
    assert settings.poll.min_delay_s == 5
    assert settings.poll.max_delay_s >= 5


def test_placeholder_values_are_rejected(tmp_path):
    data = {**BASE, "check": {**BASE["check"], "match_url": "CAMBIAR: URL"}}
    with pytest.raises(ConfigError, match="match_url"):
        load_settings(write(tmp_path, data))


def test_api_mode_requires_api_fields(tmp_path):
    data = {**BASE, "check": {"mode": "api", "match_url": "https://example.test/partido"}}
    with pytest.raises(ConfigError, match="api_url"):
        load_settings(write(tmp_path, data))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "config.yaml")
