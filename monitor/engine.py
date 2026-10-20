from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from .auth import BrowserSession
from .config import CheckConfig

log = logging.getLogger(__name__)

Status = Literal["available", "unavailable", "logged_out", "blocked"]

_TOKEN_RE = re.compile(r"([^\[\]]*)((?:\[(?:\*|\d+)\])*)")
_INDEX_RE = re.compile(r"\[(\*|\d+)\]")


class TransientError(Exception):
    """Error temporal del servidor o la red; se reintenta con backoff."""


@dataclass
class CheckResult:
    status: Status
    details: list[str] = field(default_factory=list)


def resolve_path(data: Any, path: str) -> list[Any]:
    """Resuelve rutas tipo 'data.sectores[*]' o 'items[0].stock' y devuelve todos los valores encontrados."""
    nodes = [data]
    for token in filter(None, path.split(".")):
        match = _TOKEN_RE.fullmatch(token)
        if not match:
            raise ValueError(f"Segmento de ruta inválido: {token!r}")
        key, indexes = match.group(1), _INDEX_RE.findall(match.group(2))
        next_nodes: list[Any] = []
        for node in nodes:
            if key:
                if not isinstance(node, dict) or key not in node:
                    continue
                node = node[key]
            current = [node]
            for index in indexes:
                expanded: list[Any] = []
                for item in current:
                    if not isinstance(item, list):
                        continue
                    if index == "*":
                        expanded.extend(item)
                    elif int(index) < len(item):
                        expanded.append(item[int(index)])
                current = expanded
            next_nodes.extend(current)
        nodes = next_nodes
    return nodes


def location_priority(label: str, include_text: list[str]) -> int | None:
    """Posición (0 = máxima prioridad) de la primera ubicación que coincide; None si ninguna.

    Cada entrada admite sinónimos separados por '|' (comparados por palabra completa) y
    exclusiones con '!': 'k|!sin k' coincide con "Sector K" pero no con "3ra bandeja (SIN K)".
    """
    if not include_text:
        return 0
    for index, entry in enumerate(include_text):
        terms = [t.strip() for t in entry.split("|") if t.strip()]
        excluded = [t[1:].strip() for t in terms if t.startswith("!")]
        wanted = [t for t in terms if not t.startswith("!")]
        if any(_has_words(label, t) for t in excluded):
            continue
        if any(_has_words(label, t) for t in wanted):
            return index
    return None


def _has_words(text: str, words: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(words)}(?!\w)", text, re.IGNORECASE) is not None


def _to_number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class AvailabilityChecker:
    def __init__(self, session: BrowserSession, cfg: CheckConfig, timeout_s: float):
        self._session = session
        self._cfg = cfg
        self._timeout_ms = timeout_s * 1000

    async def check(self) -> CheckResult:
        try:
            if self._cfg.mode == "api":
                return await self._check_api()
            return await self._check_page()
        except PlaywrightTimeoutError as exc:
            raise TransientError(f"Timeout: {exc}") from exc
        except PlaywrightError as exc:
            raise TransientError(f"Error de navegador/red: {exc}") from exc

    def _rank(self, labels: list[str]) -> list[str]:
        ranked = [(location_priority(label, self._cfg.include_text), label) for label in labels]
        return [label for priority, label in sorted((r for r in ranked if r[0] is not None), key=lambda r: r[0])]

    def _looks_blocked(self, text: str) -> bool:
        text = text.lower()
        return any(marker.lower() in text for marker in self._cfg.block_text)

    async def _check_page(self) -> CheckResult:
        page = self._session.page
        response = await page.goto(self._cfg.match_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
        if response is not None:
            if response.status == 429 or response.status >= 500:
                raise TransientError(f"HTTP {response.status}")
            if response.status in (401, 403):
                return CheckResult("blocked" if response.status == 403 else "logged_out")

        if self._cfg.ready_selector:
            await page.locator(self._cfg.ready_selector).first.wait_for(state="attached", timeout=self._timeout_ms)
        else:
            try:
                await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
            except PlaywrightTimeoutError:
                log.debug("La página no llegó a networkidle; se evalúa igual")

        if self._looks_blocked(await page.inner_text("body")):
            return CheckResult("blocked")

        if self._cfg.session_check_selector and await page.locator(self._cfg.session_check_selector).count() == 0:
            return CheckResult("logged_out")

        texts = await page.locator(self._cfg.available_selector).all_inner_texts()
        found = self._rank([" ".join(t.split()) for t in texts])
        return CheckResult("available" if found else "unavailable", found)

    async def _check_api(self) -> CheckResult:
        response = await self._session.context.request.get(
            self._cfg.api_url,
            headers={"Accept": "application/json"},
            timeout=self._timeout_ms,
        )
        if response.status == 401:
            return CheckResult("logged_out")
        if response.status == 403:
            return CheckResult("blocked")
        if response.status == 429 or response.status >= 500:
            raise TransientError(f"HTTP {response.status}")
        if not response.ok:
            raise TransientError(f"HTTP {response.status} inesperado")

        try:
            data = await response.json()
        except (ValueError, PlaywrightError):
            body = await response.text()
            if self._looks_blocked(body):
                return CheckResult("blocked")
            raise TransientError("La respuesta no es JSON (¿sesión vencida o cambió la API?)")

        candidates: list[str] = []
        for item in resolve_path(data, self._cfg.items_path):
            values = resolve_path(item, self._cfg.count_field)
            count = _to_number(values[0]) if values else 0.0
            labels = resolve_path(item, self._cfg.label_field) if self._cfg.label_field else []
            label = str(labels[0]) if labels else "Sector"
            if count >= self._cfg.min_value:
                candidates.append(f"{label}: {count:g} disponibles")
        found = self._rank(candidates)
        return CheckResult("available" if found else "unavailable", found)
