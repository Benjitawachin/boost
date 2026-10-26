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


def test_no_sale_text_alone_is_enough_and_placeholders_are_ignored(tmp_path):
    check = {
        "mode": "page", "match_url": "https://example.test/partidos",
        "available_selector": "CAMBIAR: selector", "unavailable_text": "Aún no hay partidos | Sin venta",
    }
    settings = load_settings(write(tmp_path, {**BASE, "check": check}))
    assert settings.check.available_selector == ""
    assert settings.check.unavailable_text == ["Aún no hay partidos", "Sin venta"]


def test_page_mode_needs_some_detection(tmp_path):
    check = {"mode": "page", "match_url": "https://example.test/partidos"}
    with pytest.raises(ConfigError, match="unavailable_text"):
        load_settings(write(tmp_path, {**BASE, "check": check}))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "config.yaml")
