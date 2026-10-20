from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from .config import BrowserConfig, LoginConfig, Secrets

log = logging.getLogger(__name__)


class LoginError(Exception):
    pass


class BrowserSession:
    """Navegador con perfil persistente: las cookies quedan guardadas en disco entre ejecuciones."""

    def __init__(self, browser_cfg: BrowserConfig, login_cfg: LoginConfig, secrets: Secrets):
        self._browser_cfg = browser_cfg
        self._login = login_cfg
        self._secrets = secrets
        self._pw: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> None:
        self._browser_cfg.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._browser_cfg.profile_dir),
            headless=self._browser_cfg.headless,
            viewport=None,
            locale="es-AR",
        )
        await self._restore_cookies()
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        log.info("Navegador iniciado (perfil: %s)", self._browser_cfg.profile_dir)

    @property
    def _state_file(self) -> Path:
        return self._browser_cfg.profile_dir / "session_state.json"

    # Chromium descarta al cerrar las cookies sin vencimiento (las de sesión), así que se guardan aparte.
    async def save_cookies(self) -> None:
        try:
            state = await self.context.storage_state()
            self._state_file.write_text(json.dumps(state), encoding="utf-8")
        except (PlaywrightError, OSError) as exc:
            log.warning("No se pudieron guardar las cookies: %s", exc)

    async def _restore_cookies(self) -> None:
        if not self._state_file.exists():
            return
        try:
            cookies = json.loads(self._state_file.read_text(encoding="utf-8")).get("cookies", [])
            if cookies:
                await self.context.add_cookies(cookies)
                log.info("Cookies de sesión restauradas (%d)", len(cookies))
        except (PlaywrightError, OSError, ValueError) as exc:
            log.warning("No se pudieron restaurar las cookies guardadas: %s", exc)

    async def close(self) -> None:
        try:
            if self.context:
                await self.save_cookies()
                await self.context.close()
        except PlaywrightError as exc:
            log.debug("Error cerrando el navegador: %s", exc)
        finally:
            if self._pw:
                await self._pw.stop()
            self.context = None
            self.page = None
            self._pw = None

    async def is_logged_in(self, timeout_s: float = 5) -> bool:
        try:
            await self.page.locator(self._login.logged_in_selector).first.wait_for(
                state="visible", timeout=timeout_s * 1000
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def ensure_logged_in(self) -> None:
        await self.page.goto(self._login.url, wait_until="domcontentloaded")
        if await self.is_logged_in():
            log.info("Sesión de Soy Socio activa")
            return

        if self._can_autofill():
            log.info("Iniciando sesión en Soy Socio...")
            try:
                await self._autofill()
                if await self.is_logged_in(timeout_s=30):
                    log.info("Sesión iniciada correctamente")
                    await self.save_cookies()
                    return
                log.warning("El login automático no se confirmó (¿captcha o datos incorrectos?)")
            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                log.warning("No se pudo completar el formulario de login: %s", exc)

        if self._browser_cfg.headless:
            raise LoginError("No hay sesión y el navegador es headless: no se puede iniciar sesión a mano")

        log.warning(
            "Iniciá sesión a mano en la ventana del navegador (tenés %.0f s)", self._login.manual_timeout_s
        )
        await self.page.bring_to_front()
        if not await self.is_logged_in(timeout_s=self._login.manual_timeout_s):
            raise LoginError("No se detectó la sesión iniciada dentro del tiempo límite")
        await self.save_cookies()
        log.info("Login manual detectado; cookies guardadas en el perfil")

    async def open_for_user(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.bring_to_front()

    def _can_autofill(self) -> bool:
        lg = self._login
        return bool(
            self._secrets.dni
            and self._secrets.password
            and lg.username_selector
            and lg.password_selector
            and lg.submit_selector
        )

    async def _autofill(self) -> None:
        lg = self._login
        user_field = self.page.locator(lg.username_selector).first
        await user_field.wait_for(state="visible", timeout=15000)
        await user_field.fill(self._secrets.dni)
        await self.page.locator(lg.password_selector).first.fill(self._secrets.password)
        await self.page.locator(lg.submit_selector).first.click()
        await self.page.wait_for_load_state("domcontentloaded")
