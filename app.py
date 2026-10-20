from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psutil
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

ENV_KEYS = ["SOYSOCIO_DNI", "SOYSOCIO_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]

CSS = """
<style>
:root { --azul: #0B2D6B; --azul-osc: #061A40; --oro: #F6B40E; }
.stApp { background: linear-gradient(180deg, var(--azul-osc) 0%, #0A2558 100%); }
.block-container { padding-top: 3.5rem; max-width: 1100px; }
.hero { border-radius: 18px; overflow: hidden; margin-bottom: 1.4rem;
        box-shadow: 0 12px 32px rgba(0,0,0,.35); border: 1px solid rgba(246,180,14,.35); }
.hero .franja-azul { background: var(--azul); padding: 1.3rem 1.6rem .9rem; }
.hero .franja-oro { background: var(--oro); color: var(--azul-osc); padding: .55rem 1.6rem;
        font-weight: 800; letter-spacing: .22em; font-size: .85rem; }
.hero .franja-azul.abajo { padding: .7rem 1.6rem 1.1rem; color: #C9D6F2; font-size: .95rem; }
.hero h1 { color: var(--oro) !important; padding: 0 !important; margin: 0; font-size: 2.1rem; font-weight: 900; letter-spacing: .04em; }
.estado { display: inline-block; padding: .35rem .9rem; border-radius: 999px; font-weight: 700;
          font-size: .9rem; margin-bottom: .6rem; }
.estado.on { background: rgba(246,180,14,.18); color: var(--oro); border: 1px solid var(--oro); }
.estado.off { background: rgba(255,255,255,.08); color: #C9D6F2; border: 1px solid rgba(255,255,255,.25); }
.estado.alerta { background: var(--oro); color: var(--azul-osc); border: 1px solid var(--oro);
                 animation: latido 1s ease-in-out infinite; }
@keyframes latido { 50% { transform: scale(1.06); } }
section[data-testid="stSidebar"] { background: var(--azul); border-right: 4px solid var(--oro); }
.stButton > button { font-weight: 700; border-radius: 10px; }
.stTabs [aria-selected="true"] { color: var(--oro) !important; }
pre { border-left: 3px solid var(--oro); }
</style>
"""

HERO = """
<div class="hero">
  <div class="franja-azul"><h1>MONITOR XENEIZE</h1></div>
  <div class="franja-oro">SOY SOCIO · ALERTA DE UBICACIONES</div>
  <div class="franja-azul abajo">Consulta cada 5–7 s, te avisa con sonido y Telegram, y te deja la página
  del partido abierta con tu sesión. La confirmación y el pago los hacés vos.</div>
</div>
"""


def load_config() -> dict:
    source = CONFIG if CONFIG.exists() else EXAMPLE
    return yaml.safe_load(source.read_text(encoding="utf-8")) or {}


def save_config(cfg: dict) -> None:
    CONFIG.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


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
        missing.append("URL del partido (pestaña Partido y ubicación)")
    if not placeholder_free(login.get("url")):
        missing.append("URL de login (pestaña Cuenta y Telegram)")
    if not placeholder_free(login.get("logged_in_selector")):
        missing.append("Selector visible solo con sesión iniciada (pestaña Cuenta y Telegram)")
    if check.get("mode") == "api":
        if not (check.get("api_url") and check.get("items_path") and check.get("count_field")):
            missing.append("Datos del modo API (pestaña Partido y ubicación)")
    elif not placeholder_free(check.get("available_selector")):
        missing.append("Selector de sector disponible (pestaña Partido y ubicación)")
    return missing


st.set_page_config(page_title="Monitor Xeneize", page_icon="⚽", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
# Streamlit declara la página en inglés y Chrome la "traduce" al español deformando los textos.
components.html(
    "<script>const d = window.parent.document.documentElement;"
    "d.lang = 'es'; d.setAttribute('translate', 'no'); d.classList.add('notranslate');</script>",
    height=0,
)
st.markdown(HERO, unsafe_allow_html=True)
if flash := st.session_state.pop("flash", None):
    st.success(flash)

cfg = load_config()
env = {k: v or "" for k, v in dotenv_values(ENV).items()} if ENV.exists() else {}
browser, login, check = cfg.setdefault("browser", {}), cfg.setdefault("login", {}), cfg.setdefault("check", {})
poll, alert = cfg.setdefault("poll", {}), cfg.setdefault("alert", {})
proc = monitor_process()
missing = missing_fields(cfg) if CONFIG.exists() else ["Guardar la configuración"]

with st.sidebar:
    submitted = st.button("Guardar configuración", type="primary", use_container_width=True)
    st.divider()
    st.markdown("### Control")

    @st.fragment(run_every=2)
    def status_badge() -> None:
        running = monitor_process()
        run_lines = current_run_lines(read_log_tail(400))
        if running and any("LUGAR DISPONIBLE" in line for line in run_lines):
            st.markdown('<span class="estado alerta">¡LUGAR DISPONIBLE!</span>', unsafe_allow_html=True)
        elif running:
            st.markdown('<span class="estado on">● Monitoreando</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="estado off">○ Detenido</span>', unsafe_allow_html=True)
        consultas = sum("Consulta #" in line for line in run_lines) if running else 0
        st.caption(f"Consultas en esta corrida: {consultas}")

    status_badge()

    if proc:
        if st.button("Detener monitor", use_container_width=True):
            stop_monitor(proc)
            st.rerun()
    else:
        if st.button("Iniciar monitor", type="primary", use_container_width=True, disabled=bool(missing)):
            start_monitor()
            st.rerun()
        if missing:
            st.markdown("**Para poder iniciar falta:**\n" + "\n".join(f"- {m}" for m in missing))

    st.divider()
    if st.button("Iniciar sesión y guardar cookies", use_container_width=True, disabled=bool(proc) or bool(missing)):
        spawn("--login-only")
        st.info("Se abrió el navegador. Si no se loguea solo, completá el login en esa ventana.")
    if st.button("Probar alerta (sonido + Telegram)", use_container_width=True):
        result = subprocess.run(
            [sys.executable, "-m", "monitor", "--config", str(CONFIG), "--test-notify"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            st.success("¡Listo! Sonó la alarma y te llegó el mensaje a Telegram.")
        else:
            errors = [line.split(": ", 1)[-1] for line in result.stdout.splitlines() if "[ERROR]" in line]
            st.error("\n\n".join(errors) or (result.stdout + result.stderr)[-800:])

tab_partido, tab_cuenta, tab_avanzado, tab_logs = st.tabs(
    ["Partido y ubicación", "Cuenta y Telegram", "Avanzado", "Logs en vivo"]
)

with tab_partido:
    check["match_url"] = st.text_input(
        "URL de la página del partido", placeholder_free(check.get("match_url")),
        help="Abrí el partido en Soy Socio y copiá la URL de la barra de direcciones.",
    )
    saved_locations = check.get("include_text") or []
    keyword_to_sector = {v: k for k, v in SECTORS.items()}
    chosen = st.multiselect(
        "Sectores que te interesan, en orden de prioridad",
        list(SECTORS),
        default=[keyword_to_sector[e] for e in saved_locations if e in keyword_to_sector],
        placeholder="Elegí uno o más sectores (vacío = cualquiera)",
        help="El primero que marques es el más importante: si hay lugar en varios, la alerta lo muestra primero.",
    )
    extra = split_list(st.text_input(
        "Otros sectores (opcional, separados por coma)",
        ", ".join(e for e in saved_locations if e not in keyword_to_sector),
        help="Por ejemplo un sector puntual del mapa: 2° Sur, LPD, Palcos VIP N.",
    ))
    check["include_text"] = [SECTORS[c] for c in chosen] + extra
    if chosen or extra:
        st.caption("Prioridad: " + " → ".join(f"{i}° {name}" for i, name in enumerate(chosen + extra, 1)))
    mode_label = st.radio(
        "Cómo detectar disponibilidad", ["Leyendo la página", "Leyendo la API (JSON, más liviano)"],
        index=1 if check.get("mode") == "api" else 0, horizontal=True,
    )
    check["mode"] = "api" if mode_label.startswith("Leyendo la API") else "page"
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Modo página**")
        check["available_selector"] = st.text_input(
            "Selector CSS de un sector disponible", placeholder_free(check.get("available_selector"))
        )
        check["ready_selector"] = st.text_input(
            "Selector que indica página cargada (opcional)", check.get("ready_selector") or ""
        )
        check["session_check_selector"] = st.text_input(
            "Selector visible solo logueado en el partido (opcional)", check.get("session_check_selector") or ""
        )
    with col2:
        st.markdown("**Modo API**")
        check["api_url"] = st.text_input("URL del JSON (pestaña Network)", check.get("api_url") or "")
        check["items_path"] = st.text_input("Ruta a la lista de sectores", check.get("items_path") or "sectores[*]")
        check["count_field"] = st.text_input("Campo de lugares libres", check.get("count_field") or "disponibles")
        check["label_field"] = st.text_input("Campo con el nombre del sector", check.get("label_field") or "nombre")
        check["min_value"] = st.number_input("Mínimo de lugares", min_value=1, value=int(check.get("min_value", 1)))

with tab_cuenta:
    st.caption("Se guardan solo en el archivo .env de esta carpeta, en tu computadora.")
    col1, col2 = st.columns(2)
    with col1:
        dni = st.text_input("DNI", env.get("SOYSOCIO_DNI", ""))
        password = st.text_input("Contraseña", env.get("SOYSOCIO_PASSWORD", ""), type="password")
    with col2:
        tg_token = st.text_input("Token del bot de Telegram", env.get("TELEGRAM_BOT_TOKEN", ""), type="password")
        tg_chat = st.text_input("Tu chat_id de Telegram", env.get("TELEGRAM_CHAT_ID", ""))
    login["url"] = st.text_input("URL de login", login.get("url") or "")
    login["logged_in_selector"] = st.text_input(
        "Selector visible solo con sesión iniciada", placeholder_free(login.get("logged_in_selector"))
    )
    col1, col2, col3 = st.columns(3)
    login["username_selector"] = col1.text_input("Selector campo DNI", login.get("username_selector") or "")
    login["password_selector"] = col2.text_input("Selector campo contraseña", login.get("password_selector") or "")
    login["submit_selector"] = col3.text_input("Selector botón ingresar", login.get("submit_selector") or "")

with tab_avanzado:
    col1, col2, col3 = st.columns(3)
    poll["min_delay_s"] = col1.number_input("Espera mínima (s)", min_value=5.0, value=max(5.0, float(poll.get("min_delay_s", 5))), step=0.5)
    poll["max_delay_s"] = col2.number_input("Espera máxima (s)", min_value=5.0, value=max(5.0, float(poll.get("max_delay_s", 7))), step=0.5)
    poll["page_timeout_s"] = col3.number_input("Timeout de carga (s)", min_value=5.0, value=float(poll.get("page_timeout_s", 20)))
    col1, col2, col3 = st.columns(3)
    poll["max_backoff_s"] = col1.number_input("Backoff máximo ante errores (s)", min_value=30.0, value=float(poll.get("max_backoff_s", 300)))
    poll["blocked_pause_s"] = col2.number_input("Pausa ante captcha/bloqueo (s)", min_value=30.0, value=float(poll.get("blocked_pause_s", 120)))
    alert["sound_repeats"] = int(col3.number_input("Repeticiones del sonido", min_value=1, max_value=20, value=int(alert.get("sound_repeats", 5))))
    login["manual_timeout_s"] = st.number_input("Tiempo para login manual (s)", min_value=30.0, value=float(login.get("manual_timeout_s", 300)))
    check["block_text"] = split_list(st.text_input(
        "Textos que indican captcha/bloqueo (separados por coma)", ", ".join(check.get("block_text") or [])
    ))
    browser["profile_dir"] = st.text_input("Carpeta del perfil del navegador", browser.get("profile_dir") or "browser_profile")
    browser["headless"] = False

if submitted:
    poll["max_delay_s"] = max(poll["max_delay_s"], poll["min_delay_s"])
    save_config(cfg)
    save_env({
        "SOYSOCIO_DNI": dni, "SOYSOCIO_PASSWORD": password,
        "TELEGRAM_BOT_TOKEN": tg_token, "TELEGRAM_CHAT_ID": tg_chat,
    })
    st.session_state["flash"] = "Configuración guardada." + (" Reiniciá el monitor para aplicarla." if proc else "")
    st.rerun()

with tab_logs:
    @st.fragment(run_every=2)
    def live_logs() -> None:
        tail = read_log_tail(200)
        st.code("".join(tail) if tail else "Todavía no hay registros.", language="log")

    live_logs()
