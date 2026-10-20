from __future__ import annotations

import hmac
import html
import re
import socket
import subprocess
import sys
from pathlib import Path

import psutil
import segno
import streamlit as st
import streamlit.components.v1 as components
import yaml
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.yaml"
EXAMPLE = ROOT / "config.example.yaml"
ENV = ROOT / ".env"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "monitor.log"
PROCESS_LOG = LOG_DIR / "process.log"
PID_FILE = LOG_DIR / "monitor.pid"
ICON = ROOT / "static" / "icon-192.png"

SECTORS = {
    "Popular (Activo/Adherente)": "popular|s sur|2° sur|3° sur|s norte|2° norte|3° norte",
    "1ra bandeja (Platea baja)": "1ra bandeja|1° bandeja|primera bandeja|platea baja",
    "2da bandeja (Platea media)": "2da bandeja|2° bandeja|segunda bandeja|platea media",
    "3ra bandeja sin K (Platea alta)": "3ra bandeja|3° bandeja|tercera bandeja|platea alta",
    "K": "k|!sin k",
    "Torres (Terrazas)": "torre|torres|terraza|terrazas|ts|tn",
    "Plateas preferenciales": "platea preferencial|plateas preferenciales|preferencial|preferenciales",
    "Palcos": "palco|palcos",
}
ENV_KEYS = ["SOYSOCIO_DNI", "SOYSOCIO_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "PANEL_PASSWORD"]
LOG_LINE = re.compile(r"^(\d\d:\d\d:\d\d) \[(\w+)\] [\w.]+: (.*)$")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap');
:root { --azul: #0B2D6B; --azul-osc: #061A40; --azul-claro: #123C86; --oro: #F6B40E; --oro-claro: #FFD45C;
        --texto-suave: #C9D6F2; --verde: #3DDC97; --rojo: #FF6B6B; --naranja: #FFA94D; }
.stApp { background:
    radial-gradient(1200px 500px at 50% -10%, rgba(246,180,14,.10), transparent 60%),
    linear-gradient(180deg, var(--azul-osc) 0%, #0A2558 100%); }
.block-container { padding-top: 3rem; max-width: 1000px; }

.hero { position: relative; border-radius: 22px; overflow: hidden; margin-bottom: 1.2rem;
        background: linear-gradient(135deg, var(--azul-claro), var(--azul) 55%, var(--azul-osc));
        border: 1px solid rgba(246,180,14,.35); box-shadow: 0 18px 40px rgba(0,0,0,.35); }
.hero .arriba { padding: 1.6rem 1.8rem 1.1rem; }
.hero .kicker { color: var(--texto-suave); font-weight: 700; letter-spacing: .25em; font-size: .72rem; }
.hero .nombre { font-family: 'Bebas Neue', 'Arial Narrow', sans-serif; color: #fff; font-size: 3.4rem;
                line-height: .95; margin: .25rem 0 0; letter-spacing: .02em; }
.hero .nombre span { color: var(--oro); }
.hero .franja { background: linear-gradient(90deg, var(--oro), var(--oro-claro), var(--oro)); color: var(--azul-osc);
                padding: .6rem 1.8rem; font-weight: 800; letter-spacing: .2em; font-size: .78rem; }
.hero .abajo { padding: .85rem 1.8rem 1.2rem; color: var(--texto-suave); font-size: 1rem; }
.hero .estrella { position: absolute; right: -30px; top: -40px; width: 230px; opacity: .10; }

.tarjeta { background: rgba(14,50,112,.55); border: 1px solid rgba(255,255,255,.10); border-radius: 18px;
           padding: 1.1rem 1.3rem; margin-bottom: .8rem; }
.estado { display: inline-flex; align-items: center; gap: .55rem; padding: .45rem 1.1rem; border-radius: 999px;
          font-weight: 800; font-size: 1rem; }
.estado .punto { width: .7rem; height: .7rem; border-radius: 50%; background: currentColor; }
.estado.on { background: rgba(61,220,151,.14); color: var(--verde); border: 1px solid rgba(61,220,151,.6); }
.estado.on .punto { animation: pulso 1.4s ease-out infinite; }
.estado.off { background: rgba(255,255,255,.06); color: var(--texto-suave); border: 1px solid rgba(255,255,255,.2); }
.estado.alerta { background: var(--oro); color: var(--azul-osc); animation: latido 1s ease-in-out infinite; }
@keyframes pulso { 0% { box-shadow: 0 0 0 0 rgba(61,220,151,.7); } 100% { box-shadow: 0 0 0 10px rgba(61,220,151,0); } }
@keyframes latido { 50% { transform: scale(1.05); } }
.metricas { display: grid; grid-template-columns: repeat(3, 1fr); gap: .6rem; margin-top: .9rem; }
.metrica { background: rgba(6,26,64,.55); border-radius: 12px; padding: .6rem .8rem; }
.metrica .valor { font-family: 'Bebas Neue', 'Arial Narrow', sans-serif; font-size: 1.7rem; color: #fff; line-height: 1; }
.metrica .etiqueta { color: var(--texto-suave); font-size: .75rem; margin-top: .2rem; }

.camino .titulo { font-family: 'Bebas Neue', 'Arial Narrow', sans-serif; font-size: 1.7rem; color: #fff;
                  letter-spacing: .03em; line-height: 1; }
.camino .barra { height: 10px; border-radius: 999px; background: rgba(255,255,255,.10); overflow: hidden; margin: .5rem 0 .9rem; }
.camino .barra div { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--oro), var(--oro-claro)); }
.paso { display: flex; gap: .75rem; align-items: flex-start; padding: .55rem 0; border-top: 1px solid rgba(255,255,255,.06); }
.paso .icono { flex: 0 0 1.6rem; height: 1.6rem; border-radius: 50%; display: flex; align-items: center;
               justify-content: center; font-weight: 900; font-size: .85rem; }
.paso.ok .icono { background: var(--oro); color: var(--azul-osc); }
.paso.pend .icono { border: 2px solid rgba(255,255,255,.3); color: var(--texto-suave); }
.paso .que { font-weight: 700; color: #fff; }
.paso .como { color: var(--texto-suave); font-size: .88rem; }
.paso.ok .como { color: #9FB3DD; }

.actividad { list-style: none; padding: 0; margin: 0; }
.actividad li { display: flex; gap: .7rem; padding: .45rem .2rem; border-bottom: 1px solid rgba(255,255,255,.06);
                font-size: .92rem; color: #E6ECFA; }
.actividad .hora { color: #8FA6D6; font-variant-numeric: tabular-nums; flex: 0 0 4.2rem; }
.actividad .dot { flex: 0 0 .55rem; height: .55rem; border-radius: 50%; margin-top: .45rem; background: #5B8DEF; }
.actividad .warn .dot { background: var(--naranja); }
.actividad .err .dot { background: var(--rojo); }
.actividad li.lugar { background: rgba(246,180,14,.16); border-radius: 10px; font-weight: 800; color: var(--oro-claro); }
.actividad li.lugar .dot { background: var(--oro); }

.guia { color: var(--texto-suave); font-size: .92rem; margin-bottom: .6rem; }
.stButton > button, .stFormSubmitButton > button { font-weight: 800; border-radius: 12px; min-height: 3rem; }
.stTabs [data-baseweb="tab-list"] { gap: .2rem; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { font-weight: 700; }
.stTabs [aria-selected="true"] { color: var(--oro) !important; }
div[data-testid="stExpander"] details { border-radius: 14px; border-color: rgba(255,255,255,.12); }
pre { border-left: 3px solid var(--oro); }

@media (max-width: 640px) {
  .block-container { padding: 2.4rem .8rem 2rem; }
  .hero { border-radius: 18px; }
  .hero .arriba { padding: 1.2rem 1.2rem .9rem; }
  .hero .nombre { font-size: 2.6rem; }
  .hero .franja { padding: .5rem 1.2rem; letter-spacing: .12em; font-size: .68rem; }
  .hero .abajo { padding: .7rem 1.2rem 1rem; font-size: .92rem; }
  .metrica .valor { font-size: 1.35rem; }
}
</style>
"""

STAR = (
    '<svg class="estrella" viewBox="0 0 100 100"><polygon fill="#F6B40E" '
    'points="50,4 61,38 97,38 68,59 79,94 50,73 21,94 32,59 3,38 39,38"/></svg>'
)
HERO = f"""
<div class="hero">{STAR}
  <div class="arriba">
    <div class="kicker">SOY SOCIO · BOCA JUNIORS</div>
    <div class="nombre">MONITOR <span>XENEIZE</span></div>
  </div>
  <div class="franja">ALERTA DE UBICACIONES</div>
  <div class="abajo">Vigila la venta por vos y te avisa al toque cuando hay lugar en tu sector.
  Vos elegís la ubicación y confirmás la compra.</div>
</div>
"""

HEAD_TAGS = """<script>
const d = window.parent.document, h = d.head, root = d.documentElement;
root.lang = 'es'; root.setAttribute('translate', 'no'); root.classList.add('notranslate');
const tags = [
  ['link', {rel: 'apple-touch-icon', href: './app/static/apple-touch-icon.png'}],
  ['meta', {name: 'apple-mobile-web-app-title', content: 'Xeneize'}],
  ['meta', {name: 'apple-mobile-web-app-capable', content: 'yes'}],
  ['meta', {name: 'mobile-web-app-capable', content: 'yes'}],
  ['meta', {name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent'}],
  ['meta', {name: 'theme-color', content: '#061A40'}],
];
for (const [tag, attrs] of tags) {
  const [k, v] = Object.entries(attrs)[0];
  if (h.querySelector(`${tag}[${k}="${v}"]`)) continue;
  const el = d.createElement(tag);
  for (const [a, b] of Object.entries(attrs)) el.setAttribute(a, b);
  h.appendChild(el);
}
</script>"""

TELEGRAM_HELP = """
**1. Crear tu bot (una sola vez)**
- En Telegram buscá **@BotFather** y escribile `/newbot`.
- Te pregunta el nombre (*"How are we going to call it?"*): escribí cualquiera, por ejemplo `Alerta Boca`.
- Te pide un usuario que termine en `bot` (*"choose a username"*): por ejemplo `alertaboca_tunombre_bot`.
  Si dice *"already taken"*, probá con otro.
- Te responde *"Done! Congratulations"*. Debajo de *"Use this token"* hay un código largo: ese es el **token**.

**2. Activar el bot**
- Tocá el link `t.me/...` que viene en ese mensaje, apretá **Iniciar** y mandale "hola".

**3. Tu número de chat**
- Buscá **@userinfobot** y apretá **Iniciar**: el número después de **Id** es tu **chat_id**.
"""


def load_config() -> dict:
    source = CONFIG if CONFIG.exists() else EXAMPLE
    return yaml.safe_load(source.read_text(encoding="utf-8")) or {}


def dump_config(cfg: dict) -> str:
    return yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)


def save_env(values: dict[str, str]) -> None:
    ENV.touch(exist_ok=True)
    for key, value in values.items():
        set_key(str(ENV), key, value, quote_mode="always")


def monitor_process() -> psutil.Process | None:
    try:
        pid = int(PID_FILE.read_text().strip())
        proc = psutil.Process(pid)
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE and "monitor" in " ".join(proc.cmdline()):
            return proc
    except (OSError, ValueError, psutil.Error):
        pass
    return None


def spawn(*extra: str) -> subprocess.Popen:
    LOG_DIR.mkdir(exist_ok=True)
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    out = open(PROCESS_LOG, "a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "monitor", "--config", str(CONFIG), *extra],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=out, **kwargs,
    )


def start_monitor() -> None:
    proc = spawn()
    PID_FILE.write_text(str(proc.pid))


def stop_monitor(proc: psutil.Process) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except psutil.TimeoutExpired:
        proc.kill()
    PID_FILE.unlink(missing_ok=True)


def read_log_tail(lines: int = 200) -> list[str]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(encoding="utf-8", errors="replace") as fh:
        return fh.readlines()[-lines:]


def current_run_lines(tail: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(tail) if "Navegador iniciado" in line]
    return tail[starts[-1]:] if starts else tail


def split_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def placeholder_free(value) -> str:
    value = str(value or "")
    return "" if value.upper().startswith("CAMBIAR") else value


def missing_fields(cfg: dict) -> list[str]:
    login, check = cfg.get("login", {}), cfg.get("check", {})
    missing = []
    if not placeholder_free(check.get("match_url")):
        missing.append("la página del partido (pestaña Sectores)")
    if not placeholder_free(login.get("url")) or not placeholder_free(login.get("logged_in_selector")):
        missing.append("los datos de inicio de sesión (pestaña Avanzado)")
    if check.get("mode") == "api":
        if not (check.get("api_url") and check.get("items_path") and check.get("count_field")):
            missing.append("los datos del modo API (pestaña Avanzado)")
    elif not placeholder_free(check.get("available_selector")):
        missing.append("cómo reconocer un lugar disponible (pestaña Avanzado)")
    return missing


def lan_url() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    return f"http://{ip}:{st.get_option('server.port')}"


def require_access(env: dict[str, str]) -> bool:
    """La PC entra directo; cualquier otro dispositivo necesita la contraseña del panel."""
    if st.context.ip_address is None or st.session_state.get("autorizado"):
        return True
    panel_password = env.get("PANEL_PASSWORD", "")
    if not panel_password:
        st.error(
            "Para entrar desde el celular primero creá una contraseña del panel "
            "en la computadora (pestaña Celular)."
        )
        return False
    with st.form("acceso"):
        attempt = st.text_input("Contraseña del panel", type="password")
        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            if hmac.compare_digest(attempt.encode(), panel_password.encode()):
                st.session_state["autorizado"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    return False


def journey_html(steps: list[tuple[bool, str, str]]) -> str:
    done = sum(ok for ok, _, _ in steps)
    rows = "".join(
        f'<div class="paso {"ok" if ok else "pend"}"><div class="icono">{"✓" if ok else i}</div>'
        f'<div><div class="que">{html.escape(what)}</div><div class="como">{html.escape(how)}</div></div></div>'
        for i, (ok, what, how) in enumerate(steps, 1)
    )
    return (
        f'<div class="tarjeta camino"><div class="titulo">Tu camino a la Bombonera</div>'
        f'<div class="guia" style="margin:0">{done} de {len(steps)} listos</div>'
        f'<div class="barra"><div style="width:{done / len(steps) * 100:.0f}%"></div></div>{rows}</div>'
    )


def activity_html(lines: list[str]) -> str:
    items = []
    for line in reversed(lines):
        match = LOG_LINE.match(line.strip())
        if not match:
            continue
        hour, level, message = match.groups()
        message = re.sub(r"\s*\(perfil: .*\)", "", message)
        css = "lugar" if "LUGAR DISPONIBLE" in message else {"WARNING": "warn", "ERROR": "err"}.get(level, "")
        items.append(
            f'<li class="{css}"><span class="dot"></span><span class="hora">{hour}</span>'
            f"<span>{html.escape(message)}</span></li>"
        )
    if not items:
        return '<div class="guia">Todavía no hay actividad. Cuando empieces a vigilar, acá vas a ver cada consulta.</div>'
    return f'<ul class="actividad">{"".join(items[:40])}</ul>'


st.set_page_config(page_title="Monitor Xeneize", page_icon=str(ICON) if ICON.exists() else "⭐", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)
if hasattr(st, "iframe"):
    st.iframe(HEAD_TAGS, height=1)
else:
    components.html(HEAD_TAGS, height=0)
st.markdown(HERO, unsafe_allow_html=True)

env = {k: v or "" for k, v in dotenv_values(ENV).items()} if ENV.exists() else {}
if not require_access(env):
    st.stop()
on_pc = st.context.ip_address is None
if toast := st.session_state.pop("toast", None):
    st.toast(toast)

config_existed = CONFIG.exists()
cfg = load_config()
saved_cfg_text = dump_config(cfg)
browser, login, check = cfg.setdefault("browser", {}), cfg.setdefault("login", {}), cfg.setdefault("check", {})
poll, alert = cfg.setdefault("poll", {}), cfg.setdefault("alert", {})
proc = monitor_process()
missing = missing_fields(cfg)
session_saved = (ROOT / (browser.get("profile_dir") or "browser_profile") / "session_state.json").exists()


@st.fragment(run_every=2)
def status_card() -> None:
    running = monitor_process()
    run_lines = current_run_lines(read_log_tail(500))
    checks = [line for line in run_lines if "Consulta #" in line]
    found = running and any("LUGAR DISPONIBLE" in line for line in run_lines)
    if found:
        badge = '<span class="estado alerta">¡HAY LUGAR! Andá a la computadora a confirmar</span>'
    elif running:
        badge = '<span class="estado on"><span class="punto"></span>Vigilando la venta</span>'
    else:
        badge = '<span class="estado off"><span class="punto"></span>Detenido</span>'
    since = next((line[:5] for line in run_lines if "Navegador iniciado" in line), "—") if running else "—"
    last = checks[-1][:8] if running and checks else "—"
    st.markdown(
        f'<div class="tarjeta">{badge}<div class="metricas">'
        f'<div class="metrica"><div class="valor">{len(checks) if running else 0}</div><div class="etiqueta">consultas</div></div>'
        f'<div class="metrica"><div class="valor">{last}</div><div class="etiqueta">última consulta</div></div>'
        f'<div class="metrica"><div class="valor">{since}</div><div class="etiqueta">vigilando desde</div></div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


status_card()

col1, col2, col3 = st.columns(3)
with col1:
    if proc:
        if st.button("Detener", use_container_width=True):
            stop_monitor(proc)
            st.rerun()
    elif st.button("Empezar a vigilar", type="primary", use_container_width=True, disabled=bool(missing)):
        start_monitor()
        st.rerun()
with col2:
    login_clicked = st.button(
        "Iniciar sesión en Soy Socio", use_container_width=True, disabled=bool(proc) or bool(missing),
        help="Abre el navegador en la computadora. Se hace una vez y la sesión queda guardada.",
    )
with col3:
    test_clicked = st.button("Probar alerta", use_container_width=True, help="Suena en la computadora y te manda un Telegram de prueba.")

# Contenedor fijo: si los avisos agregaran o quitaran elementos, las pestañas se recrearían y volverían a la primera.
with st.container():
    if missing and not proc:
        st.info("Para empezar a vigilar falta configurar " + " y ".join(missing) + ".")
    if login_clicked:
        spawn("--login-only")
        st.success("Se abrió el navegador en la computadora. Si no entra solo, iniciá sesión en esa ventana.")
    if test_clicked:
        result = subprocess.run(
            [sys.executable, "-m", "monitor", "--config", str(CONFIG), "--test-notify"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            st.success("¡Listo! Sonó la alarma y te llegó el mensaje a Telegram.")
        else:
            errors = [line.split(": ", 1)[-1] for line in result.stdout.splitlines() if "[ERROR]" in line]
            st.error("\n\n".join(errors) or (result.stdout + result.stderr)[-800:])

journey_box = st.empty()

tab_cuenta, tab_alertas, tab_sectores, tab_celular, tab_actividad, tab_avanzado = st.tabs(
    ["1 · Tu cuenta", "2 · Alertas", "3 · Sectores", "Celular", "Actividad", "Avanzado"]
)

with tab_cuenta:
    st.markdown(
        '<div class="guia">Con estos datos la app vuelve a entrar sola si la sesión se vence. '
        "Quedan guardados solo en esta computadora. Si preferís no cargarlos, iniciás sesión a mano.</div>",
        unsafe_allow_html=True,
    )
    dni = st.text_input("DNI", env.get("SOYSOCIO_DNI", ""), placeholder="Sin puntos")
    password = st.text_input("Contraseña de Soy Socio", env.get("SOYSOCIO_PASSWORD", ""), type="password")

with tab_alertas:
    st.markdown(
        '<div class="guia">Te llega un mensaje al celular apenas hay lugar, estés donde estés.</div>',
        unsafe_allow_html=True,
    )
    tg_token = st.text_input("Token del bot de Telegram", env.get("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat = st.text_input("Tu chat_id de Telegram", env.get("TELEGRAM_CHAT_ID", ""), placeholder="Un número, por ejemplo 123456789")
    with st.expander("¿Cómo consigo estos datos? (5 minutos)"):
        st.markdown(TELEGRAM_HELP)

with tab_sectores:
    saved_locations = check.get("include_text") or []
    keyword_to_sector = {v: k for k, v in SECTORS.items()}
    chosen = st.multiselect(
        "¿Dónde querés ir? Elegí en orden de preferencia",
        list(SECTORS),
        default=[keyword_to_sector[e] for e in saved_locations if e in keyword_to_sector],
        placeholder="Tocá para elegir (vacío = cualquier sector)",
    )
    extra = split_list(st.text_input(
        "Otros sectores del mapa (opcional)",
        ", ".join(e for e in saved_locations if e not in keyword_to_sector),
        placeholder="Por ejemplo: 2° Sur, LPD",
    ))
    check["include_text"] = [SECTORS[c] for c in chosen] + extra
    if chosen or extra:
        st.markdown(
            '<div class="guia">Si hay lugar en varios, te avisamos primero por: <b>'
            + " → ".join(f"{i}° {html.escape(n)}" for i, n in enumerate(chosen + extra, 1))
            + "</b></div>",
            unsafe_allow_html=True,
        )
    check["match_url"] = st.text_input(
        "Página donde se compran las entradas", placeholder_free(check.get("match_url")),
        help="Normalmente es la sección Partidos de Soy Socio. Si un partido tiene su propia página, pegá esa dirección.",
    )

with tab_celular:
    panel_password = env.get("PANEL_PASSWORD", "")
    if not on_pc:
        st.markdown("Ya estás usando el panel desde otro dispositivo. La contraseña se cambia desde la computadora.")
    else:
        st.markdown(
            '<div class="guia">Manejá todo desde el celular. La computadora tiene que quedar <b>prendida con '
            "<code>iniciar</code> abierto</b> y el celular <b>en el mismo Wi-Fi</b>.</div>",
            unsafe_allow_html=True,
        )
        new_password = st.text_input(
            "Creá una contraseña para entrar desde el celular", panel_password, type="password",
            help="Mínimo 6 caracteres. No uses la misma de Soy Socio.",
        )
        if new_password and len(new_password) < 6:
            st.warning("Usá al menos 6 caracteres; esta contraseña todavía no se guardó.")
        else:
            panel_password = new_password
        url = lan_url()
        if not panel_password:
            st.info("Cuando crees la contraseña aparece acá un código QR para abrir el panel en el celular.")
        elif url:
            qr_col, text_col = st.columns([1, 2])
            qr_col.markdown(
                f'<img alt="Código QR del panel" width="170" style="border-radius:14px" '
                f'src="{segno.make(url, error="m").svg_data_uri(scale=6, border=2)}">',
                unsafe_allow_html=True,
            )
            text_col.markdown(
                f"1. Apuntá con la **cámara** del celular al código (o escribí **{url}**).\n"
                "2. Entrá con la contraseña que creaste.\n"
                "3. Para tenerlo como app: en iPhone **Compartir → Agregar a inicio**; "
                "en Android **⋮ → Agregar a pantalla principal**.\n\n"
                "Si Windows pregunta por Python, elegí **Redes privadas → Permitir acceso**."
            )
        else:
            st.warning("No se encontró la dirección de esta computadora en la red. ¿Está conectada al Wi-Fi?")

with tab_actividad:
    @st.fragment(run_every=3)
    def live_activity() -> None:
        st.markdown(activity_html(read_log_tail(120)), unsafe_allow_html=True)

    live_activity()

with tab_avanzado:
    st.markdown(
        '<div class="guia">Solo hace falta tocar esto una vez, para que la app sepa leer la página de Soy Socio. '
        "La guía está en la sección 4.2 del README.</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Inicio de sesión"):
        login["url"] = st.text_input("Dirección de inicio de sesión", login.get("url") or "")
        login["logged_in_selector"] = st.text_input(
            "Algo que solo se ve con la sesión iniciada", placeholder_free(login.get("logged_in_selector")),
            help="Selector CSS o de texto, por ejemplo text=Cerrar sesión",
        )
        login["username_selector"] = st.text_input("Campo DNI del formulario", login.get("username_selector") or "")
        login["password_selector"] = st.text_input("Campo contraseña del formulario", login.get("password_selector") or "")
        login["submit_selector"] = st.text_input("Botón ingresar del formulario", login.get("submit_selector") or "")
        login["manual_timeout_s"] = st.number_input(
            "Tiempo para iniciar sesión a mano (s)", min_value=30.0, value=float(login.get("manual_timeout_s", 300))
        )
    with st.expander("Detección de lugares", expanded=st.session_state.setdefault("abrir_deteccion", bool(missing))):
        mode_label = st.radio(
            "Cómo detectar", ["Leyendo la página", "Leyendo la API (JSON)"],
            index=1 if check.get("mode") == "api" else 0, horizontal=True,
        )
        check["mode"] = "api" if mode_label.startswith("Leyendo la API") else "page"
        if check["mode"] == "page":
            check["available_selector"] = st.text_input(
                "Selector de un sector disponible", placeholder_free(check.get("available_selector"))
            )
            check["ready_selector"] = st.text_input("Selector de página cargada (opcional)", check.get("ready_selector") or "")
            check["session_check_selector"] = st.text_input(
                "Selector visible solo logueado en el partido (opcional)", check.get("session_check_selector") or ""
            )
        else:
            check["api_url"] = st.text_input("URL del JSON", check.get("api_url") or "")
            check["items_path"] = st.text_input("Ruta a la lista de sectores", check.get("items_path") or "sectores[*]")
            check["count_field"] = st.text_input("Campo de lugares libres", check.get("count_field") or "disponibles")
            check["label_field"] = st.text_input("Campo con el nombre del sector", check.get("label_field") or "nombre")
            check["min_value"] = st.number_input("Mínimo de lugares", min_value=1, value=int(check.get("min_value", 1)))
        check["block_text"] = split_list(st.text_input(
            "Textos que indican captcha o bloqueo", ", ".join(check.get("block_text") or [])
        ))
    with st.expander("Tiempos y sonido"):
        poll["min_delay_s"] = st.number_input("Espera mínima entre consultas (s)", min_value=5.0, value=max(5.0, float(poll.get("min_delay_s", 5))), step=0.5)
        poll["max_delay_s"] = st.number_input("Espera máxima entre consultas (s)", min_value=5.0, value=max(5.0, float(poll.get("max_delay_s", 7))), step=0.5)
        poll["page_timeout_s"] = st.number_input("Tiempo máximo de carga (s)", min_value=5.0, value=float(poll.get("page_timeout_s", 20)))
        poll["max_backoff_s"] = st.number_input("Espera máxima ante errores (s)", min_value=30.0, value=float(poll.get("max_backoff_s", 300)))
        poll["blocked_pause_s"] = st.number_input("Pausa ante captcha (s)", min_value=30.0, value=float(poll.get("blocked_pause_s", 120)))
        alert["sound_repeats"] = int(st.number_input("Repeticiones de la alarma", min_value=1, max_value=20, value=int(alert.get("sound_repeats", 5))))
    with st.expander("Registro técnico"):
        tail = read_log_tail(200)
        st.code("".join(tail) if tail else "Todavía no hay registros.", language="log")
    browser.setdefault("profile_dir", "browser_profile")
    browser["headless"] = False

poll["max_delay_s"] = max(poll["max_delay_s"], poll["min_delay_s"])
new_env = {
    "SOYSOCIO_DNI": dni.strip(), "SOYSOCIO_PASSWORD": password,
    "TELEGRAM_BOT_TOKEN": tg_token.strip(), "TELEGRAM_CHAT_ID": tg_chat.strip(),
    "PANEL_PASSWORD": panel_password,
}
cfg_text = dump_config(cfg)
if cfg_text != saved_cfg_text or not config_existed or any(env.get(k, "") != new_env[k] for k in ENV_KEYS):
    CONFIG.write_text(cfg_text, encoding="utf-8")
    save_env(new_env)
    if config_existed:
        st.session_state["toast"] = "Cambios guardados" + (". Detené y volvé a empezar para aplicarlos." if proc else "")
    st.rerun()

steps = [
    (bool(new_env["TELEGRAM_BOT_TOKEN"] and new_env["TELEGRAM_CHAT_ID"]), "Alertas en tu celular",
     "Listo: te avisamos por Telegram." if new_env["TELEGRAM_CHAT_ID"] else "Completá la pestaña 2 · Alertas y tocá «Probar alerta»."),
    (bool(new_env["SOYSOCIO_DNI"] and new_env["SOYSOCIO_PASSWORD"]) or session_saved, "Tu cuenta de socio",
     "Listo." if new_env["SOYSOCIO_DNI"] or session_saved else "Completá la pestaña 1 · Tu cuenta."),
    (bool(check["include_text"]), "Tus sectores",
     ("Listo: " + ", ".join(chosen + extra)) if check["include_text"] else "Elegilos en la pestaña 3 · Sectores."),
    (session_saved, "Sesión iniciada en Soy Socio",
     "Listo: la sesión queda guardada." if session_saved else "Tocá «Iniciar sesión en Soy Socio», arriba."),
    (not missing, "Lectura de la página de compra",
     "Listo." if not missing else "Se configura una sola vez en Avanzado, cuando la venta esté visible en tu cuenta."),
]
journey_box.markdown(journey_html(steps), unsafe_allow_html=True)
