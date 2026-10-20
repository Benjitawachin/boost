from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from .auth import BrowserSession, LoginError
from .config import ConfigError, Settings, load_settings
from .engine import AvailabilityChecker, TransientError
from .notifier import Notifier

log = logging.getLogger("monitor")


def setup_logging(log_dir: Path, verbose: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    file_handler = RotatingFileHandler(log_dir / "monitor.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def wait_until_closed() -> None:
    log.info("Búsqueda finalizada. La ventana queda abierta para que confirmes; Ctrl+C o Detener para cerrarla.")
    await asyncio.Event().wait()


async def monitor_loop(settings: Settings, session: BrowserSession, notifier: Notifier) -> None:
    poll = settings.poll
    checker = AvailabilityChecker(session, settings.check, poll.page_timeout_s)
    failures = 0
    blocked_notified = False
    checks = 0

    while True:
        try:
            result = await checker.check()
            failures = 0
        except TransientError as exc:
            failures += 1
            backoff = min(poll.max_backoff_s, poll.min_delay_s * 2**failures) + random.uniform(0, poll.min_delay_s)
            log.warning("%s — reintento %d en %.0f s", exc, failures, backoff)
            if failures == 5:
                await notifier.send_text(f"Monitor: {failures} errores seguidos del servidor ({exc}). Sigo reintentando.")
            await asyncio.sleep(backoff)
            continue

        checks += 1
        if result.status == "available":
            log.info("LUGAR DISPONIBLE: %s", "; ".join(result.details) or "(sin detalle)")
            await session.open_for_user(settings.check.match_url)
            await notifier.send_availability_alert(settings.check.match_url, result.details)
            await wait_until_closed()
            return

        if result.status == "logged_out":
            log.warning("La sesión se cerró; reconectando")
            await session.ensure_logged_in()
            continue

        if result.status == "blocked":
            log.warning("Posible captcha o bloqueo. Pausa de %.0f s (resolvelo en la ventana si aparece)", poll.blocked_pause_s)
            if not blocked_notified:
                await notifier.send_text("Monitor pausado: el sitio muestra un captcha o bloqueo. Revisá la ventana del navegador.")
                blocked_notified = True
            await asyncio.sleep(poll.blocked_pause_s)
            continue

        blocked_notified = False
        delay = random.uniform(poll.min_delay_s, poll.max_delay_s)
        log.info("Consulta #%d: sin lugares. Próxima en %.1f s", checks, delay)
        await asyncio.sleep(delay)


async def run(settings: Settings, login_only: bool) -> int:
    notifier = Notifier(settings.secrets.telegram_token, settings.secrets.telegram_chat_id, settings.sound_repeats)
    session = BrowserSession(settings.browser, settings.login, settings.secrets)
    try:
        await session.start()
        await session.ensure_logged_in()
        if login_only:
            log.info("Sesión guardada en el perfil. Ya podés ejecutar el monitor.")
            return 0
        await notifier.send_text("Monitor de Soy Socio iniciado.")
        await monitor_loop(settings, session, notifier)
        return 0
    except LoginError as exc:
        log.error("Login: %s", exc)
        await notifier.send_text(f"Monitor detenido: {exc}")
        return 2
    finally:
        await session.close()


async def test_notify(env_path: Path) -> int:
    load_dotenv(env_path)
    notifier = Notifier(os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip(), 3)
    sent = await notifier.send_availability_alert("", ["Prueba de notificación: si te llegó este mensaje, Telegram funciona."])
    if not notifier.telegram_enabled:
        log.error("Sonó la alarma, pero Telegram no está configurado: cargá el token y el chat_id y guardá.")
        return 1
    if not sent:
        log.error("Sonó la alarma, pero no se pudo enviar el mensaje de Telegram (ver el motivo arriba).")
        return 1
    log.info("Prueba enviada: sonó la alarma y salió el mensaje de Telegram.")
    return 0


async def with_sigterm(coro) -> int:
    task = asyncio.current_task()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    except (NotImplementedError, AttributeError):
        pass  # Windows: terminate() mata el proceso directamente
    return await coro


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor de disponibilidad de Soy Socio")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--login-only", action="store_true", help="solo iniciar sesión y guardar cookies")
    parser.add_argument("--test-notify", action="store_true", help="probar sonido y Telegram")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    setup_logging(config_path.parent / "logs", args.verbose)
    if args.test_notify:
        sys.exit(asyncio.run(test_notify(config_path.parent / ".env")))
    try:
        settings = load_settings(config_path)
    except ConfigError as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        sys.exit(asyncio.run(with_sigterm(run(settings, args.login_only))))
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Monitor detenido")
        sys.exit(130)


if __name__ == "__main__":
    main()
