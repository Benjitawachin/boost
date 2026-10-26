from __future__ import annotations

import asyncio
import html
import logging
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_LINUX_SOUNDS = [
    Path("/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"),
    Path("/usr/share/sounds/freedesktop/stereo/complete.oga"),
]


def _beep_blocking(repeats: int) -> None:
    system = platform.system()
    linux_sound = next((p for p in _LINUX_SOUNDS if p.exists()), None)
    for _ in range(repeats):
        try:
            if system == "Windows":
                import winsound

                winsound.Beep(1200, 400)
            elif system == "Darwin":
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False, timeout=5)
            elif linux_sound and shutil.which("paplay"):
                subprocess.run(["paplay", str(linux_sound)], check=False, timeout=5)
            else:
                sys.stdout.write("\a")
                sys.stdout.flush()
                time.sleep(0.4)
        except (OSError, subprocess.SubprocessError) as exc:
            log.debug("No se pudo reproducir sonido: %s", exc)
            sys.stdout.write("\a")
            sys.stdout.flush()


class Notifier:
    def __init__(self, telegram_token: str, telegram_chat_id: str, sound_repeats: int = 5):
        self._token = telegram_token
        self._chat_id = telegram_chat_id
        self._sound_repeats = sound_repeats
        if not self.telegram_enabled:
            log.info("Telegram sin configurar: solo va a sonar la alarma en la computadora")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    async def play_sound(self) -> None:
        await asyncio.to_thread(_beep_blocking, self._sound_repeats)

    async def send_text(self, text: str, button_url: str | None = None, as_html: bool = False) -> bool:
        if not self.telegram_enabled:
            return False
        payload: dict = {"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True}
        if as_html:
            payload["parse_mode"] = "HTML"
        if button_url and button_url.startswith(("http://", "https://")):
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Abrir Soy Socio", "url": button_url}]]}
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            for attempt in range(1, 4):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        return True
                    log.warning("Telegram respondió %s: %s", response.status_code, response.text[:200])
                    if response.status_code < 500 and response.status_code != 429:
                        log.error("%s", _telegram_hint(response.status_code, response.text))
                        return False
                except httpx.HTTPError as exc:
                    log.warning("Error enviando a Telegram (intento %d): %s", attempt, exc)
                await asyncio.sleep(2**attempt)
        log.error("No se pudo conectar con Telegram. Revisá tu conexión a internet y volvé a probar.")
        return False

    async def send_availability_alert(self, match_url: str, details: list[str]) -> bool:
        lines = ["<b>¡HAY LUGAR DISPONIBLE!</b>", ""]
        if len(details) > 1:
            lines.append("<b>Sectores con lugar</b> (en tu orden de preferencia):")
            lines += [f"<b>{i}°</b> {html.escape(d)}" for i, d in enumerate(details[:15], 1)]
        else:
            lines.append(html.escape(details[0]) if details else "(sin detalle)")
        lines += ["", "La página del partido ya está abierta con tu sesión en la computadora. Elegí la ubicación y confirmá."]
        text = "\n".join(lines)
        _, sent = await asyncio.gather(self.play_sound(), self.send_text(text, button_url=match_url, as_html=True))
        return sent

    async def send_test(self) -> bool:
        text = (
            "<b>PRUEBA</b> · Monitor Xeneize\n\n"
            "Si te llegó este mensaje, las alertas funcionan.\nEsto <b>no</b> es una alerta real."
        )
        _, sent = await asyncio.gather(self.play_sound(), self.send_text(text, as_html=True))
        return sent


def _telegram_hint(status: int, body: str) -> str:
    body = body.lower()
    if status in (401, 404):
        return "Telegram: el token del bot es incorrecto. Copialo de nuevo del mensaje de @BotFather."
    if "chat not found" in body:
        return "Telegram: chat_id incorrecto, o todavía no le mandaste un mensaje a tu bot (abrilo y tocá Iniciar)."
    if "blocked" in body:
        return "Telegram: bloqueaste al bot. Abrilo en Telegram y desbloquealo."
    return f"Telegram rechazó el mensaje (código {status})."
