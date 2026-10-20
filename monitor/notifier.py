from __future__ import annotations

import asyncio
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
            log.info("Telegram no configurado: solo habrá alerta sonora y logs")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    async def play_sound(self) -> None:
        await asyncio.to_thread(_beep_blocking, self._sound_repeats)

    async def send_text(self, text: str, button_url: str | None = None) -> bool:
        if not self.telegram_enabled:
            return False
        payload: dict = {"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True}
        if button_url:
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Abrir partido", "url": button_url}]]}
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            for attempt in range(1, 4):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        return True
                    log.warning("Telegram respondió %s: %s", response.status_code, response.text[:200])
                    if response.status_code < 500 and response.status_code != 429:
                        return False
                except httpx.HTTPError as exc:
                    log.warning("Error enviando a Telegram (intento %d): %s", attempt, exc)
                await asyncio.sleep(2**attempt)
        return False

    async def send_availability_alert(self, match_url: str, details: list[str]) -> None:
        lines = ["¡HAY LUGAR DISPONIBLE!", ""]
        lines += [f"- {d}" for d in details[:15]] or ["- (sin detalle)"]
        lines += ["", "La ventana del navegador ya está abierta con tu sesión en la página del partido.", match_url]
        await asyncio.gather(self.play_sound(), self.send_text("\n".join(lines), button_url=match_url))
