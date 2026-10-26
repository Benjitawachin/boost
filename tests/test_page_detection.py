import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from monitor.config import CheckConfig
from monitor.engine import AvailabilityChecker

playwright_api = pytest.importorskip("playwright.async_api")

SHELL = (
    "<html><body><a>CERRAR SESIÓN</a><h1>PRÓXIMOS PARTIDOS</h1><div id='c'></div>"
    "<script>setTimeout(() => {{ document.getElementById('c').innerHTML = `{body}`; }}, {delay});</script>"
    "</body></html>"
)
PAGES = {
    "/vacia": SHELL.format(body="<p>Aún no hay partidos habilitados</p>", delay=1000),
    "/abierta": SHELL.format(body="<div>Boca vs River <button>Obtener mi lugar</button></div>", delay=300),
    "/login": "<html><body><form><input name='dni'><button>Ingresar</button></form></body></html>",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = PAGES.get(self.path, "no").encode()
        self.send_response(200 if self.path in PAGES else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def check(base_url: str, path: str) -> str:
    async def run() -> str:
        async with playwright_api.async_playwright() as p:
            try:
                browser = await p.chromium.launch()
            except playwright_api.Error as exc:
                pytest.skip(f"Chromium no disponible: {exc}")
            page = await browser.new_page()
            cfg = CheckConfig(
                mode="page",
                match_url=base_url + path,
                ready_selector="text=Próximos partidos",
                session_check_selector="text=Cerrar sesión",
                unavailable_text=["Aún no hay partidos habilitados", "Necesitás tener tu carnet físico"],
            )
            result = await AvailabilityChecker(SimpleNamespace(page=page), cfg, timeout_s=3).check()
            await browser.close()
            return result.status

    return asyncio.run(run())


def test_late_no_sale_banner_is_not_a_false_alarm(base_url):
    assert check(base_url, "/vacia") == "unavailable"


def test_sale_opening_is_detected(base_url):
    assert check(base_url, "/abierta") == "available"


def test_expired_session_is_detected(base_url):
    assert check(base_url, "/login") == "logged_out"
