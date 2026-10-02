#!/usr/bin/env python3
"""
Site Chrome Manager — Instalador v2.1 (puerto a Python de install-site-chrome.sh; solo stdlib).
Administra Header + Footer del sitio Plone/Volto.

  - BACKEND como add-on instalable: collective.sitechrome (pip/uv + perfil GS)
  - Endpoint REST /@site-chrome (GET público / PATCH Manager)
  - 6 registry keys: collective.sitechrome.site_chrome.{header,footer}_{config,base_css,css}
  - Navigation.jsx (header, fat menu) + Footer.jsx (footer por config)
  - Control Panel: Header | Footer, cada uno con sus tabs
  - CSS sin rebuild (Registry + viewlet en <head>), SSR sin flash

Uso:
    python3 install_site_chrome.py [ruta/al/proyecto] [--theme volto-xxx] [--yes] [--no-build] [--dry-run]
    curl -sL https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/install_site_chrome.py | python3 - /opt/plone/proyecto

La ruta también puede venir en PLONE_BASE (por defecto /opt/plone/web-plone).
  --theme NOMBRE  paquete Volto donde instalar (si no existe se crea; debe empezar con 'volto-'); sin él se pregunta.
  --yes           no preguntar nada: usa el primer tema existente (o --theme), confirma y compila/reinicia.
  --no-build      no compila ni reinicia (imprime los comandos pendientes).
  --dry-run       solo detecta y muestra el resumen.
Los archivos del frontend salen de la carpeta src/ junto al script (repo) o de GitHub si no está.

Historial: v1.0 rename a Site Chrome (endpoint @site-chrome, footer por config); v2.0 backend como add-on
collective.sitechrome (perfiles GS), sanitizado al leer/renderizar, log de auditoría del PATCH;
v2.1 puerto a Python (misma lógica; --theme/--yes/--no-build/--dry-run y fallos de build/pip que ya no pasan en silencio).
"""

import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_URL = "https://github.com/RenteriaMX/MF-Site-Chrome.git"
SRC_BASE_URL = "https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/src"
SCRIPT_URL = "https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/install_site_chrome.py"

GREEN, YELLOW, RED, CYAN, NC = "\033[0;32m", "\033[1;33m", "\033[0;31m", "\033[0;36m", "\033[0m"
ARGS = None


class InstallError(Exception):
    pass


def log(m):   print(f"{GREEN}✓{NC} {m}", flush=True)
def info(m):  print(f"{CYAN}→{NC} {m}", flush=True)
def warn(m):  print(f"{YELLOW}⚠{NC} {m}", flush=True)
def hr():     print(f"{CYAN}────────────────────────────────────────{NC}", flush=True)
def fail(m):  raise InstallError(m)


# ── utilidades ─────────────────────────────────────────────────────────────────────────────────────────────

def run(cmd, *, cwd=None, env=None, check=True, tail=0):
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, text=True, capture_output=True)
    except FileNotFoundError:
        if check:
            fail(f"No se encontro el comando '{cmd[0]}'. Instalalo y reintenta.")
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: no encontrado")
    salida = (r.stdout or "") + (r.stderr or "")
    if tail and salida.strip():
        print("\n".join(salida.strip().splitlines()[-tail:]), flush=True)
    if check and r.returncode != 0:
        fail(f"Falló `{' '.join(str(c) for c in cmd)}` (código {r.returncode}):\n" + "\n".join(salida.strip().splitlines()[-30:]))
    return r


def ask(prompt, default=""):
    """Pregunta por stdin si es una terminal, o por /dev/tty (script por pipe). Con --yes o sin terminal usa el valor por defecto."""
    if ARGS and ARGS.yes:
        return default
    try:
        src = sys.stdin if sys.stdin.isatty() else open("/dev/tty")
        sys.stdout.write(prompt)
        sys.stdout.flush()
        ans = src.readline()
        return (ans.strip() or default) if ans else default
    except OSError:
        return default


# ── 1. detección ───────────────────────────────────────────────────────────────────────────────────────────

def detect_backend_name(base):
    src = base / "backend/src"
    nombres = sorted(p.name for p in src.iterdir() if p.is_dir() and p.name != "__pycache__" and not p.name.endswith(".egg-info")) \
        if src.is_dir() else []
    if not nombres:
        fail("No se encontro paquete backend en backend/src/")
    return nombres[0]


def detect_site_id(unit_dirs):
    """Id del sitio Plone leído de RAZZLE_INTERNAL_API_PATH en las unidades plone-*.service; 'Plone' si no se encuentra."""
    for d in unit_dirs:
        for f in sorted(Path(d).glob("plone-*.service")) if Path(d).is_dir() else []:
            try:
                m = re.search(r'RAZZLE_INTERNAL_API_PATH[^\n]*?http://[^/"\s]*/([^/"\s]+)', f.read_text(errors="ignore"))
            except OSError:
                continue
            if m:
                return m.group(1)
    return "Plone"


def detect_unit_files(pattern, directory, base):
    """Nombres de unidades (sin .service) en `directory` cuyo archivo menciona el proyecto y coincide con `pattern`."""
    d = Path(directory)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.service")):
        try:
            t = f.read_text(errors="ignore")
        except OSError:
            continue
        if str(base) in t and re.search(pattern, t):
            out.append(f.stem)
    return out


def detect_services(base, user_dir=None, sys_dir="/etc/systemd/system"):
    """({backend: [...], volto: [...]}, modos): primero servicios de usuario y, por tipo, el fallback a servicios de sistema."""
    user_dir = user_dir or str(Path.home() / ".config/systemd/user")
    be = detect_unit_files(r"runwsgi", user_dir, base)
    vo = detect_unit_files(r"server\.js|start:prod", user_dir, base)
    be_mode = vo_mode = "--user"
    if not be:
        be, be_mode = detect_unit_files(r"runwsgi", sys_dir, base), "system"
    if not vo:
        vo, vo_mode = detect_unit_files(r"server\.js", sys_dir, base), "system"
    return {"backend": be, "volto": vo}, {"backend": be_mode, "volto": vo_mode}


def list_themes(base):
    d = base / "frontend/packages"
    return sorted(p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("volto-")) if d.is_dir() else []


def theme_description(base, pkg):
    try:
        return json.loads((base / "frontend/packages" / pkg / "package.json").read_text()).get("description", "")[:40]
    except (OSError, ValueError):
        return ""


# ── fuentes del frontend ───────────────────────────────────────────────────────────────────────────────────

def script_dir():
    try:
        return Path(__file__).resolve().parent
    except NameError:                                   # ejecutado por stdin
        return None


def get_src(rel):
    """Contenido de src/<rel>: junto al script (repo) o de GitHub (raw)."""
    sd = script_dir()
    if sd and (sd / "src" / rel).is_file():
        return (sd / "src" / rel).read_text()
    try:
        with urllib.request.urlopen(f"{SRC_BASE_URL}/{rel}", timeout=60) as r:
            return r.read().decode()
    except Exception as e:   # noqa: BLE001
        fail(f"No se pudo obtener src/{rel}: {e}")


def write_src(rel, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(get_src(rel))


# ── parches (funciones puras) ──────────────────────────────────────────────────────────────────────────────

def patch_volto_config_new_theme(text, theme):
    """Agrega el tema nuevo a `const addons = [...]` (igual que la versión en shell)."""
    def add(m):
        inner = m.group(1).strip().rstrip(",")
        return "const addons = [{}'{}']".format(inner + ", " if inner else "", theme)
    return re.sub(r"const addons\s*=\s*\[([^\]]*)\]", add, text)


def register_in_package_json(text, theme):
    data = json.loads(text)
    data.setdefault("dependencies", {})[theme] = "workspace:*"
    return json.dumps(data, indent=2)


def ensure_dnd_kit(text):
    """(texto, [agregados]) — dependencias @dnd-kit que usa el Control Panel."""
    data = json.loads(text)
    deps = data.setdefault("dependencies", {})
    added = []
    for pkg, ver in (("@dnd-kit/core", "^6.1.0"), ("@dnd-kit/sortable", "^8.0.0"), ("@dnd-kit/utilities", "^3.2.2")):
        if pkg not in deps:
            deps[pkg] = ver
            added.append(pkg)
    return json.dumps(data, indent=2), added


def theme_package_json(theme):
    return json.dumps({
        "name": theme, "version": "1.0.0", "description": "Tema Plone", "main": "src/index.ts", "license": "MIT",
        "keywords": ["volto-addon", "volto", "plone"], "addons": [],
        "dependencies": {"@dnd-kit/core": "^6.1.0", "@dnd-kit/sortable": "^8.0.0", "@dnd-kit/utilities": "^3.2.2"},
        "peerDependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},
        "devDependencies": {"@plone/registry": "workspace:*", "@plone/scripts": "workspace:*", "@plone/types": "workspace:*",
                            "@types/react": "^18.3.1", "@types/react-dom": "^18.3.1", "typescript": "^5.7.3"},
    }, indent=2) + "\n"


TSCONFIG = '''{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": false,
    "jsx": "react-jsx",
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "baseUrl": "src"
  },
  "include": ["src"]
}
'''


def clean_other_index(text):
    """Quita de un index.ts AJENO las referencias viejas/nuevas de este instalador. None si no había nada que quitar."""
    if "NavigationMenuControlPanel" not in text and "SiteChromeControlPanel" not in text:
        return None
    text = re.sub(r"import NavigationMenuControlPanel[^\n]*\n", "", text)
    text = re.sub(r"import SiteChromeControlPanel[^\n]*\n", "", text)
    text = re.sub(r"import \{ (?:navMenuReducer|siteChromeReducer)[^\n]*\n", "", text)
    text = re.sub(r"\s*\{[^}]*(?:navigation-menu|site-chrome)[^}]*\},?\n?", "\n", text)
    return text


def find_matching_brace(text, open_pos):
    """Cierra la llave abierta en open_pos contando llaves e ignorando strings y comentarios. -1 si no cierra."""
    depth, i, in_str, skip, n = 1, open_pos + 1, None, False, len(text)
    while i < n and depth > 0:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if skip:
            skip = False
        elif in_str:
            if c == "\\":
                skip = True
            elif c == in_str:
                in_str = None
        elif c == "/" and nxt == "/":
            j = text.find("\n", i)
            if j < 0:
                break
            i = j
            continue
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                break
            i = j + 2
            continue
        elif c in ('"', "'", "`"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1


FUNC_PATTERNS = [
    r"(?:export\s+default\s+)?function\s+applyConfig\s*\([^)]*\)\s*(?::\s*\w+\s*)?\{",
    r"const\s+applyConfig\s*=\s*\([^)]*\)\s*(?::\s*\w+\s*)?=>\s*\{",
    r"const\s+applyConfig\s*=\s*\([^)]*\)\s*=>\s*\{",
]


def patch_index_ts(current):
    """Deja en el index.ts del tema el control panel, la ruta y el reducer/extender SSR de Site Chrome, respetando todo lo ajeno.
    Devuelve (texto, estado): 'ya' (sin cambios) | 'ok'. Lanza InstallError si las llaves están desbalanceadas."""
    already = ("SiteChromeControlPanel" in current and "siteChromeReducer" in current
               and "navigation-menu" not in current and "NavigationMenuControlPanel" not in current)
    if already:
        return current, "ya"

    current = re.sub(r"^import NavigationMenuControlPanel[^\n]*\n", "", current, flags=re.M)
    current = re.sub(r"^import \{ navMenuReducer[^\n]*\n", "", current, flags=re.M)

    our_imports = []
    if "import type { ConfigType }" not in current:
        our_imports.append("import type { ConfigType } from '@plone/registry';")
    if "SiteChromeControlPanel" not in current:
        our_imports.append("import SiteChromeControlPanel from './controlpanels/SiteChromeControlPanel';")
    if "siteChromeReducer" not in current:
        our_imports.append("import { siteChromeReducer, siteChromeAsyncExtender } from './siteChromeSSR';")
    if our_imports:
        last_import = None
        for m in re.finditer(r"^import\s.+;$", current, re.MULTILINE):
            last_import = m
        if last_import:
            pos = last_import.end()
            current = current[:pos] + "\n" + "\n".join(our_imports) + current[pos:]
        else:
            current = "\n".join(our_imports) + "\n\n" + current

    func_match = None
    for pat in FUNC_PATTERNS:
        func_match = re.search(pat, current)
        if func_match:
            break
    if not func_match:                                   # no hay applyConfig: crear desde cero
        current = current.rstrip()
        if current:
            current += "\n\n"
        current += "function applyConfig(config: ConfigType) {\n  return config;\n}\n\nexport default applyConfig;\n"
        func_match = re.search(FUNC_PATTERNS[0], current)

    open_pos = func_match.end() - 1
    close_pos = find_matching_brace(current, open_pos)
    if close_pos < 0:
        fail("llaves desbalanceadas en index.ts")
    body = current[open_pos + 1:close_pos]

    # Limpiar entradas previas del instalador (nav-menu y site-chrome), sin tocar reducers/extenders ajenos.
    body = re.sub(r"\s*config\.settings\.navDepth\s*=.*?;", "", body)
    body = re.sub(r"\s*installSettings\(config\);", "", body)
    body = re.sub(r"[ \t]*//[^\n]*SSR:[^\n]*\n", "", body)
    body = re.sub(r"\s*navMenu:\s*navMenuReducer,?", "", body)
    body = re.sub(r"\s*siteChrome:\s*siteChromeReducer,?", "", body)
    body = re.sub(r"\s*\{\s*path:\s*'/',\s*extend:\s*navMenuAsyncExtender\s*\},?", "", body)
    body = re.sub(r"\s*\{\s*path:\s*'/',\s*extend:\s*siteChromeAsyncExtender\s*\},?", "", body)
    body = re.sub(r"\s*config\.settings\.controlpanels\s*=\s*\[.*?\];", "", body, flags=re.DOTALL)
    body = re.sub(r"\s*config\.addonRoutes\s*=\s*\[.*?\];", "", body, flags=re.DOTALL)

    if re.search(r"config\.addonReducers\s*=\s*\{", body):
        body = re.sub(r"(config\.addonReducers\s*=\s*\{)", r"\1\n    siteChrome: siteChromeReducer,", body, count=1)
        add_reducer = False
    else:
        add_reducer = True
    if re.search(r"config\.settings\.asyncPropsExtenders\s*=\s*\[", body):
        body = re.sub(r"(config\.settings\.asyncPropsExtenders\s*=\s*\[)",
                      r"\1\n    { path: '/', extend: siteChromeAsyncExtender },", body, count=1)
        add_extender = False
    else:
        add_extender = True

    entries = ["  config.settings.navDepth = 2;",
               """  config.settings.controlpanels = [
    ...(config.settings.controlpanels || []),
    {
      '@id': '/controlpanel/site-chrome',
      group: 'Add-on Configuration',
      title: 'Site Chrome',
      description: 'Administra header (menu) y footer - sin rebuild.',
      icon: 'list layout',
    },
  ];""",
               """  config.addonRoutes = [
    ...(config.addonRoutes || []),
    {
      path: '/controlpanel/site-chrome',
      component: SiteChromeControlPanel,
    },
  ];"""]
    if add_reducer:
        entries.append("  // SSR: header + footer en el servidor para el HTML inicial (sin flash)\n"
                       "  config.addonReducers = { ...(config.addonReducers || {}), siteChrome: siteChromeReducer };")
    if add_extender:
        entries.append("""  config.settings.asyncPropsExtenders = [
    ...(config.settings.asyncPropsExtenders || []),
    { path: '/', extend: siteChromeAsyncExtender },
  ];""")
    new_entries = "\n\n" + "\n\n".join(entries) + "\n"

    ret_match = re.search(r"\n(\s*return config;)", body)
    if ret_match:
        body = body[:ret_match.start()] + new_entries + body[ret_match.start():]
    else:
        body = body.rstrip() + new_entries + "\n  return config;\n"
    return current[:open_pos + 1] + body + current[close_pos:], "ok"


# ── backend ────────────────────────────────────────────────────────────────────────────────────────────────

def find_uv():
    owner_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    for u in ("uv", owner_home / ".local/bin/uv", Path.home() / ".local/bin/uv", owner_home / ".cargo/bin/uv",
              Path.home() / ".cargo/bin/uv", "/usr/local/bin/uv", "/usr/bin/uv"):
        w = shutil.which(str(u))
        if w:
            return w
    return ""


def get_backend_source(tmp):
    sd = script_dir()
    if sd and (sd / "backend/collective.sitechrome").is_dir():
        return sd / "backend/collective.sitechrome"
    info("Clonando MF-Site-Chrome para obtener el paquete backend...")
    r = run(["git", "clone", "--depth", "1", REPO_URL, tmp / "mf-site-chrome"], check=False)
    if r.returncode != 0:
        fail("No se pudo clonar el repo para obtener collective.sitechrome")
    pkg = tmp / "mf-site-chrome/backend/collective.sitechrome"
    if not pkg.is_dir():
        fail("No se encontro el paquete backend collective.sitechrome")
    return pkg


def install_backend(base, tmp):
    hr()
    info("Instalando add-on backend collective.sitechrome...")
    pkg_src = get_backend_source(tmp)
    bk = base / "backend"
    venv_py = bk / ".venv/bin/python"
    if not os.access(venv_py, os.X_OK):
        venv_py = bk / "bin/python"
    if not os.access(venv_py, os.X_OK):
        fail(f"No se encontro el venv del backend ({bk}/.venv)")
    uv = find_uv()

    (bk / "packages").mkdir(exist_ok=True)
    dst = bk / "packages/collective.sitechrome"
    if dst.exists():
        warn("collective.sitechrome ya existe. Actualizando...")
        shutil.rmtree(dst)
    shutil.copytree(pkg_src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"))

    info("Instalando paquete editable collective.sitechrome ...")
    pip = bk / ".venv/bin/pip"
    if os.access(pip, os.X_OK):
        run([pip, "install", "--no-config", "-e", dst], tail=3)
    elif uv:
        info(f"venv uv-managed -> usando uv ({uv})")
        run([uv, "pip", "install", "--python", venv_py, "-e", dst], tail=3)
    elif run([venv_py, "-m", "pip", "--version"], check=False).returncode == 0:
        run([venv_py, "-m", "pip", "install", "--no-config", "-e", dst], tail=3)
    else:
        fail("No hay forma de instalar el paquete: ni pip en el venv ni uv. "
             "Instala uv (curl -LsSf https://astral.sh/uv/install.sh | sh) y reintenta.")
    log("Paquete backend instalado (collective.sitechrome)")
    activate_addon(base, tmp)
    log("Endpoint /@site-chrome listo (GET publico / PATCH Manager)")


ZCONSOLE_SCRIPT = '''import transaction
from Testing.makerequest import makerequest
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.users import SimpleUser
from zope.site.hooks import setSite

app = makerequest(app)
SITE_ID = None
for oid in app.objectIds():
    o = app[oid]
    if getattr(o, "portal_type", None) == "Plone Site":
        SITE_ID = oid; break
if not SITE_ID:
    print("[site-chrome] ERROR: no Plone site"); import sys; sys.exit(1)
portal = app[SITE_ID]; setSite(portal)
newSecurityManager(None, SimpleUser("admin", "", ["Manager"], []).__of__(app.acl_users))
from Products.CMFPlone.utils import get_installer
installer = get_installer(portal)
if not installer.is_product_installed("collective.sitechrome"):
    installer.install_product("collective.sitechrome")
    print("[site-chrome] add-on instalado.")
else:
    print("[site-chrome] add-on ya instalado.")
transaction.commit()
print("[site-chrome] done.")
'''


def _user_systemctl(*args):
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    try:
        return subprocess.run(["systemctl", "--user", *args], env=env, text=True, capture_output=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", "")


def activate_addon(base, tmp):
    """Activa el add-on en Plone (perfil GS). Best-effort: sin zconsole/zope.conf el add-on igual funciona (autoinclude) y
    se puede instalar luego desde Site Setup → Add-ons."""
    zconsole = next((z for z in (base / "backend/.venv/bin/zconsole", base / "backend/bin/zconsole") if os.access(z, os.X_OK)), None)
    zconf = next((c for c in (base / "backend/instance/etc/zope.conf", base / "backend/etc/zope.conf",
                              base / "backend/parts/instance/etc/zope.conf") if c.is_file()), None)
    if not zconsole or not zconf:
        warn("zconsole/zope.conf no encontrados: instala el add-on desde Site Setup -> Add-ons (collective.sitechrome).")
        return
    r = _user_systemctl("list-units", "--all", "--no-legend", "plone-*-backend*")
    svcs = [ln.replace("●", " ").split()[0] for ln in (r.stdout or "").splitlines() if ln.replace("●", " ").split()]
    for s in svcs:
        _user_systemctl("stop", s)
    if svcs:
        time.sleep(2)
    script = tmp / "sc_install.py"
    script.write_text(ZCONSOLE_SCRIPT)
    info("Activando add-on en Plone (zconsole)...")
    try:
        z = run([zconsole, "run", zconf, script], check=False, cwd=base / "backend")
        print("\n".join(((z.stdout or "") + (z.stderr or "")).strip().splitlines()[-5:]), flush=True)
        if z.returncode != 0:
            warn("Activacion best-effort fallo; instala desde Site Setup -> Add-ons.")
    finally:
        for s in svcs:                              # el reinicio final (si hay build) los reinicia de nuevo
            _user_systemctl("start", s)


# ── frontend ───────────────────────────────────────────────────────────────────────────────────────────────

def install_frontend(base, backend_name, theme, create_new):
    hr()
    info("Configurando frontend...")
    theme_dir = base / "frontend/packages" / theme
    backend_dir = base / "backend/src" / backend_name

    if create_new:
        info(f"Creando estructura del tema {theme}...")
        (theme_dir / "src/components").mkdir(parents=True, exist_ok=True)
        (theme_dir / "package.json").write_text(theme_package_json(theme))
        (theme_dir / "tsconfig.json").write_text(TSCONFIG)
        fp = base / "frontend/package.json"
        fp.write_text(register_in_package_json(fp.read_text(), theme))
        print(f"Registrado en frontend/package.json: {theme}")
        vc = base / "frontend/volto.config.js"
        vc.write_text(patch_volto_config_new_theme(vc.read_text(), theme))
        print(f"Registrado en volto.config.js: {theme}")
        write_src("frontend/index.ts.template", theme_dir / "src/index.ts")
        log(f"Tema {theme} creado y registrado")
    else:
        pj = theme_dir / "package.json"
        nuevo, added = ensure_dnd_kit(pj.read_text())
        pj.write_text(nuevo)
        print(f"@dnd-kit agregado: {', '.join(added)}" if added else "@dnd-kit ya instalado")

    # Limpiar instalación previa de MF-Nav-Menu en este tema (archivos renombrados en el rename a Site Chrome).
    for rel in ("src/controlpanels/NavigationMenuControlPanel.jsx", "src/controlpanels/NavigationMenuControlPanel.css", "src/navMenuSSR.js"):
        (theme_dir / rel).unlink(missing_ok=True)
    for rel in ("viewlets/nav_css_viewlet.py", "viewlets/nav_css_viewlet.pt"):
        (backend_dir / rel).unlink(missing_ok=True)

    nav = theme_dir / "src/customizations/volto/components/theme/Navigation"
    write_src("frontend/Navigation.jsx", nav / "Navigation.jsx")
    write_src("frontend/Navigation.css", nav / "Navigation.css")
    log("Navigation.jsx + css creados (header)")
    foot = theme_dir / "src/customizations/volto/components/theme/Footer"
    write_src("frontend/Footer.jsx", foot / "Footer.jsx")
    write_src("frontend/Footer.css", foot / "Footer.css")
    log("Footer.jsx + css creados (footer)")

    # Limpiar copias conflictivas en OTROS paquetes
    for other in sorted((base / "frontend/packages").iterdir()):
        if not other.is_dir() or other == theme_dir:
            continue
        for rel in ("src/controlpanels/SiteChromeControlPanel.jsx", "src/controlpanels/SiteChromeControlPanel.css",
                    "src/controlpanels/NavigationMenuControlPanel.jsx", "src/controlpanels/NavigationMenuControlPanel.css",
                    "src/customizations/volto/components/theme/Navigation/Navigation.jsx",
                    "src/customizations/volto/components/theme/Navigation/Navigation.css",
                    "src/customizations/volto/components/theme/Footer/Footer.jsx",
                    "src/customizations/volto/components/theme/Footer/Footer.css",
                    "src/navMenuSSR.js", "src/siteChromeSSR.js"):
            (other / rel).unlink(missing_ok=True)
        idx = other / "src/index.ts"
        if idx.is_file():
            limpio = clean_other_index(idx.read_text())
            if limpio is not None:
                idx.write_text(limpio)
                print(f"  Limpiado index.ts en {idx}")

    cp = theme_dir / "src/controlpanels"
    write_src("frontend/SiteChromeControlPanel.jsx", cp / "SiteChromeControlPanel.jsx")
    write_src("frontend/SiteChromeControlPanel.css", cp / "SiteChromeControlPanel.css")
    log("Control Panel creado (Header | Footer)")
    write_src("frontend/siteChromeSSR.js", theme_dir / "src/siteChromeSSR.js")
    log("siteChromeSSR.js creado (Redux SSR)")

    idx = theme_dir / "src/index.ts"
    actual = idx.read_text() if idx.is_file() else ""
    nuevo, estado = patch_index_ts(actual)
    if estado == "ya":
        print("index.ts ya actualizado")
    else:
        idx.write_text(nuevo)
        print("index.ts actualizado (site-chrome: control panel + reducer SSR)")
    log("index.ts actualizado")


# ── build y reinicio ───────────────────────────────────────────────────────────────────────────────────────

def expand_templates(mode, svcs):
    """Una plantilla (nombre que termina en '@') no se puede reiniciar sin instancia: se expande a sus instancias reales."""
    out = []
    for s in svcs:
        if s.endswith("@"):
            r = (_user_systemctl("list-units", "--all", "--no-legend", f"{s}*.service") if mode == "--user"
                 else subprocess.run(["systemctl", "list-units", "--all", "--no-legend", f"{s}*.service"], text=True, capture_output=True))
            inst = [ln.replace("●", " ").split()[0] for ln in (r.stdout or "").splitlines() if ln.replace("●", " ").split()]
            out.extend(inst or [s])
        else:
            out.append(s)
    return out


def restart_services(mode, svcs):
    svcs = expand_templates(mode, svcs)
    if mode == "--user":
        return _user_systemctl("restart", *svcs).returncode == 0
    return subprocess.run(["sudo", "-n", "systemctl", "restart", *svcs]).returncode == 0


def print_restart_cmds(svcs, modes, prefix=""):
    for k in ("backend", "volto"):
        if svcs[k]:
            cmd = "systemctl --user restart" if modes[k] == "--user" else "sudo systemctl restart"
            print(f"{prefix}{cmd} {' '.join(svcs[k])}")


def build_and_restart(base, svcs, modes):
    hr()
    print()
    if not ((ARGS.yes and not ARGS.no_build) or (not ARGS.no_build and re.match(r"^[sS]", ask("Compilar y reiniciar ahora? (s/n) [s]: ", "s")))):
        warn("Compilacion pendiente:")
        print("  cd frontend && pnpm install && pnpm build && cd ..")
        if not (svcs["backend"] or svcs["volto"]):
            print("  (y reinicia backend y Volto con el mecanismo de tu instalación)")
        else:
            print_restart_cmds(svcs, modes, "  ")
        return
    fe = base / "frontend"
    info("Instalando dependencias...")
    run(["pnpm", "install"], cwd=fe, tail=5)
    info("Compilando (esto tarda unos minutos)...")
    logf = Path(f"/tmp/_sitechrome_build_{os.getpid()}.log")
    with open(logf, "w") as lf:
        p = subprocess.Popen(["pnpm", "build"], cwd=fe, stdout=lf, stderr=subprocess.STDOUT)
        t0, tty = time.time(), sys.stdout.isatty()
        while p.poll() is None:
            if tty:
                s = int(time.time() - t0)
                sys.stdout.write(f"\r  compilando  {s // 60:02d}:{s % 60:02d}")
                sys.stdout.flush()
            time.sleep(1)
        if tty:
            sys.stdout.write("\r" + " " * 40 + "\r")
    if p.returncode != 0:
        fail(f"Build fallido. Ver log: {logf}")
    log("Build completado")

    if not (svcs["backend"] or svcs["volto"]):
        warn("No se detectaron servicios systemd de Plone/Volto — no se reinicia nada automáticamente.")
        print("  Reinicia el backend (Zope) y Volto con el mecanismo de tu instalación")
        print("  (p. ej. en HEOC: bash heoc/ctl.sh <proyecto> restart core).")
        return
    info(f"Reiniciando servicios (backend={modes['backend']} volto={modes['volto']})...")
    ok = True
    for k in ("backend", "volto"):
        if svcs[k]:
            ok = restart_services(modes[k], svcs[k]) and ok
    if ok:
        log(f"Reiniciados: {' '.join(svcs['backend'] + svcs['volto'])}")
    else:
        warn("Reinicio manual requerido:\n")
        print_restart_cmds(svcs, modes, f"  {CYAN}")
        print(NC)
        ask("Presiona Enter cuando hayas reiniciado...", "")


# ── main ───────────────────────────────────────────────────────────────────────────────────────────────────

def reexec_as_owner(base, argv):
    """Si el dueño del proyecto no es el usuario actual, vuelve a correr el script como ese usuario (sudo -u)."""
    try:
        owner = pwd.getpwuid(base.stat().st_uid).pw_name
    except (OSError, KeyError):
        return
    if owner == pwd.getpwuid(os.getuid()).pw_name:
        return
    tmp = Path(f"/tmp/_install_site_chrome_asuser_{os.getpid()}.py")
    if script_dir() is None:                      # llegó por stdin (curl | python3 -): se baja a un archivo para relanzarlo
        try:
            with urllib.request.urlopen(SCRIPT_URL, timeout=60) as r:
                tmp.write_bytes(r.read())
        except Exception as e:   # noqa: BLE001
            fail(f"El proyecto es de '{owner}' y no se pudo bajar el instalador para relanzarlo: {e}. "
                 f"Ejecútalo como ese usuario: sudo -u {owner} python3 install_site_chrome.py ...")
    else:
        shutil.copyfile(Path(__file__).resolve(), tmp)
    tmp.chmod(0o644)
    os.execvp("sudo", ["sudo", "-u", owner, "env", f"PLONE_BASE={base}", sys.executable, str(tmp),
                       *[a for a in argv if a != str(base) and not a.startswith("PLONE_BASE=")]])


def main(argv=None):
    global ARGS
    ap = argparse.ArgumentParser(description="Instalador de MF-Site-Chrome")
    ap.add_argument("project", nargs="?", help="ruta del proyecto (o PLONE_BASE; por defecto /opt/plone/web-plone)")
    ap.add_argument("--theme", help="paquete Volto donde instalar (se crea si no existe; debe empezar con 'volto-')")
    ap.add_argument("--yes", "-y", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ARGS = ap.parse_args(argv)

    raw = os.environ.get("PLONE_BASE") or ARGS.project or "/opt/plone/web-plone"
    base = Path(raw)
    base = base.resolve() if base.exists() else base
    if not base.is_dir():
        fail(f"No se encontro {base}")
    reexec_as_owner(base, sys.argv[1:])

    print(f"\n{CYAN}╔══════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║   Site Chrome Manager — Installer        ║{NC}")
    print(f"{CYAN}║                    v2.1                  ║{NC}")
    print(f"{CYAN}╚══════════════════════════════════════════╝{NC}\n")

    hr()
    info("Detectando configuracion...")
    backend_name = detect_backend_name(base)
    log(f"Backend: {backend_name}")
    site_id = detect_site_id(["/etc/systemd/system", str(Path.home() / ".config/systemd/user")])
    log(f"Site ID: {site_id}")
    svcs, modes = detect_services(base)
    log(f"Servicios backend : {' '.join(svcs['backend']) or '(ninguno detectado)'}")
    log(f"Servicios volto   : {' '.join(svcs['volto']) or '(ninguno detectado)'}")
    log(f"Modo backend      : {modes['backend']}")
    log(f"Modo volto        : {modes['volto']}")

    hr()
    info("Seleccion de tema Volto...")
    print()
    existing = list_themes(base)
    create_new, theme = False, None
    if ARGS.theme:
        if not ARGS.theme.startswith("volto-"):
            fail("El nombre del tema debe empezar con 'volto-'")
        theme, create_new = ARGS.theme, ARGS.theme not in existing
        log(f"{'Se creara nuevo tema' if create_new else 'Usando tema existente'}: {theme}")
    else:
        if not existing:
            warn("No se encontraron temas existentes.")
            sel = "n"
        else:
            print("Paquetes disponibles (elige el tema del sitio):")
            for i, p in enumerate(existing):
                print(f"  [{i + 1}] {p:<22}  {theme_description(base, p)}")
            print("  [n] Crear nuevo tema\n")
            sel = ask("Seleccion [1]: ", "1")
        if sel.isdigit() and 1 <= int(sel) <= len(existing):
            theme = existing[int(sel) - 1]
            log(f"Usando tema existente: {theme}")
        else:
            if ARGS.yes:
                fail("No hay tema existente que usar: indica uno con --theme volto-<nombre>")
            while True:
                theme = ask("Nombre del nuevo tema (debe empezar con 'volto-'): ", "")
                if theme.startswith("volto-"):
                    break
                warn("El nombre debe empezar con 'volto-'")
            create_new = True
            log(f"Se creara nuevo tema: {theme}")

    print(f"\n  Backend:  {CYAN}{backend_name}{NC}\n  Tema:     {CYAN}{theme}{NC}  (nuevo: {str(create_new).lower()})\n  Site ID:  {CYAN}{site_id}{NC}\n")
    if ARGS.dry_run:
        log("--dry-run: no se modifica nada.")
        return 0
    if re.match(r"^[nN]", ask("Continuar? (s/n) [s]: ", "s")):
        info("Cancelado.")
        return 0

    for cmd in ("pnpm",) if not ARGS.no_build else ():
        if not shutil.which(cmd):
            fail(f"Se requiere '{cmd}' pero no esta instalado.")
    os.chdir(base)
    with tempfile.TemporaryDirectory(prefix="sitechrome-") as t:
        install_backend(base, Path(t))
    install_frontend(base, backend_name, theme, create_new)
    build_and_restart(base, svcs, modes)

    hr()
    print(f"\n{GREEN}Instalacion completada — Site Chrome v2.1{NC}\n")
    print(f"  Backend add-on: {CYAN}collective.sitechrome{NC}  (policy: {backend_name})")
    print(f"  Tema:           {CYAN}{theme}{NC}")
    print(f"  Registry:       {CYAN}collective.sitechrome.site_chrome.{{header,footer}}_{{config,base_css,css}}{NC}")
    print(f"  Endpoint:       {CYAN}GET/PATCH /@site-chrome{NC}")
    print(f"  Control Panel:  {CYAN}/controlpanel/site-chrome{NC}\n")
    print("  Seccion 'Header': Items (drag&drop) · Estilos base · CSS Custom")
    print("  Seccion 'Footer': Columnas · Estilos base · CSS Custom")
    print("  Presets header: nm-apple  nm-dark  nm-wide  nm-minimal")
    print("  Fat menu automatico: hover abre dropdown (navDepth=2)")
    print(f"  {GREEN}Sin rebuild. Sin restart. Cambio instantaneo.{NC}\n")
    print(f"  {YELLOW}Verifica nginx{NC} (config del despliegue base de Plone, NO de Site Chrome):")
    print("  el HTML de Volto debe ir 'Cache-Control: no-cache' o tras un redeploy puede")
    print("  salir 'Loading chunk failed' (navegadores con HTML cacheado). Comprueba con:")
    print("    curl -sD- http://<host>/ -o /dev/null | grep -i cache-control   # esperado: no-cache")
    print("  Si falta, agregalo en el 'location /' de Volto (y deja /static/ con cache larga).\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except InstallError as e:
        print(f"{RED}✗{NC} {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        sys.exit(130)
