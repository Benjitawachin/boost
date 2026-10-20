from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)

MIN_ALLOWED_DELAY_S = 5.0


class ConfigError(Exception):
    pass


@dataclass
class BrowserConfig:
    profile_dir: Path
    headless: bool = False


@dataclass
class LoginConfig:
    url: str
    logged_in_selector: str
    username_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""
    manual_timeout_s: float = 300


@dataclass
class CheckConfig:
    mode: str
    match_url: str
    ready_selector: str = ""
    available_selector: str = ""
    session_check_selector: str = ""
    api_url: str = ""
    items_path: str = ""
    count_field: str = ""
    label_field: str = ""
    min_value: float = 1
    include_text: list[str] = field(default_factory=list)
    block_text: list[str] = field(default_factory=list)


@dataclass
class PollConfig:
    min_delay_s: float = 5
    max_delay_s: float = 7
    max_backoff_s: float = 300
    blocked_pause_s: float = 120
    page_timeout_s: float = 20


@dataclass
class Secrets:
    dni: str
    password: str
    telegram_token: str
    telegram_chat_id: str


@dataclass
class Settings:
    browser: BrowserConfig
    login: LoginConfig
    check: CheckConfig
    poll: PollConfig
    secrets: Secrets
    sound_repeats: int = 5


def _require(section: dict, key: str, section_name: str) -> str:
    value = str(section.get(key) or "").strip()
    if not value or value.upper().startswith("CAMBIAR"):
        raise ConfigError(f"Falta configurar '{section_name}.{key}' en config.yaml")
    return value


def load_settings(config_path: Path, env_path: Path | None = None) -> Settings:
    load_dotenv(env_path or config_path.parent / ".env")

    if not config_path.exists():
        raise ConfigError(f"No existe {config_path}. Copiá config.example.yaml a config.yaml.")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml inválido: {exc}") from exc

    b, lg, ck = raw.get("browser", {}), raw.get("login", {}), raw.get("check", {})
    pl, al = raw.get("poll", {}), raw.get("alert", {})

    profile_dir = Path(b.get("profile_dir", "browser_profile"))
    if not profile_dir.is_absolute():
        profile_dir = config_path.parent / profile_dir

    login = LoginConfig(
        url=_require(lg, "url", "login"),
        logged_in_selector=_require(lg, "logged_in_selector", "login"),
        username_selector=str(lg.get("username_selector") or ""),
        password_selector=str(lg.get("password_selector") or ""),
        submit_selector=str(lg.get("submit_selector") or ""),
        manual_timeout_s=float(lg.get("manual_timeout_s", 300)),
    )

    mode = str(ck.get("mode", "page")).strip().lower()
    if mode not in ("page", "api"):
        raise ConfigError("check.mode debe ser 'page' o 'api'")
    check = CheckConfig(
        mode=mode,
        match_url=_require(ck, "match_url", "check"),
        ready_selector=str(ck.get("ready_selector") or ""),
        available_selector=str(ck.get("available_selector") or ""),
        session_check_selector=str(ck.get("session_check_selector") or ""),
        api_url=str(ck.get("api_url") or ""),
        items_path=str(ck.get("items_path") or ""),
        count_field=str(ck.get("count_field") or ""),
        label_field=str(ck.get("label_field") or ""),
        min_value=float(ck.get("min_value", 1)),
        include_text=[str(t) for t in ck.get("include_text") or []],
        block_text=[str(t) for t in ck.get("block_text") or []],
    )
    if mode == "page":
        _require(ck, "available_selector", "check")
    else:
        for key in ("api_url", "items_path", "count_field"):
            _require(ck, key, "check")

    poll = PollConfig(
        min_delay_s=float(pl.get("min_delay_s", 5)),
        max_delay_s=float(pl.get("max_delay_s", 7)),
        max_backoff_s=float(pl.get("max_backoff_s", 300)),
        blocked_pause_s=float(pl.get("blocked_pause_s", 120)),
        page_timeout_s=float(pl.get("page_timeout_s", 20)),
    )
    if poll.min_delay_s < MIN_ALLOWED_DELAY_S:
        log.warning("min_delay_s=%.1f es demasiado bajo; se usa %.1f", poll.min_delay_s, MIN_ALLOWED_DELAY_S)
        poll.min_delay_s = MIN_ALLOWED_DELAY_S
    if poll.max_delay_s < poll.min_delay_s:
        poll.max_delay_s = poll.min_delay_s + 2

    secrets = Secrets(
        dni=os.getenv("SOYSOCIO_DNI", "").strip(),
        password=os.getenv("SOYSOCIO_PASSWORD", ""),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    )

    return Settings(
        browser=BrowserConfig(profile_dir=profile_dir, headless=bool(b.get("headless", False))),
        login=login,
        check=check,
        poll=poll,
        secrets=secrets,
        sound_repeats=int(al.get("sound_repeats", 5)),
    )
