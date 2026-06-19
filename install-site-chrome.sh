#!/bin/bash
# ============================================================
#  Site Chrome Manager — Installer  v1.0
#  (rename de MF-Nav-Menu; administra Header + Footer del sitio)
#  - Detecta el backend automaticamente (sin hardcodeo)
#  - Crea o usa un tema Volto existente
#  - Endpoint REST /@site-chrome (GET publico / PATCH Manager)
#  - 6 registry keys: site_chrome.{header,footer}_{config,base_css,css}
#  - Navigation.jsx (header, fat menu) + Footer.jsx (footer por config)
#  - Control Panel: Header | Footer, cada uno con sus tabs
#  - Migracion lazy desde MF-Nav-Menu (conserva el menu existente)
#  - CSS sin rebuild (Registry + viewlet en <head>), SSR sin flash
# ============================================================
# Historial:
#   v1.0  Rename a Site Chrome. Endpoint unificado @site-chrome,
#         footer por config (columnas/copyright/legal), CSRF fix en PATCH,
#         filtro por permiso View en el header, migracion lazy nav-menu.
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }
hr()   { echo -e "${CYAN}────────────────────────────────────────${NC}"; }

# Ruta del proyecto: resolver a path absoluto desde el inicio
_RAW_PATH="${PLONE_BASE:-${1:-/opt/plone/web-plone}}"
PLONE_BASE="$(cd "$_RAW_PATH" 2>/dev/null && pwd || echo "$_RAW_PATH")"

_SCRIPT_URL="https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/install-site-chrome.sh"

# Si stdin no es un terminal (ejecutando via curl | bash), guardar a archivo
# y re-ejecutar con stdin del terminal desde el inicio — antes de cualquier read.
# SITE_CHROME_LOCAL=1 omite esto (correr local/CI desde el repo, sin curl):
# en ese modo las respuestas se leen del stdin que se le pase (pipe/heredoc).
if [ ! -t 0 ] && [ "${SITE_CHROME_LOCAL:-}" != "1" ]; then
  _TMPSCRIPT="/tmp/_install-site-chrome-$$.sh"
  if command -v curl &>/dev/null; then
    curl -fsSL "$_SCRIPT_URL" -o "$_TMPSCRIPT"
  elif command -v wget &>/dev/null; then
    wget -qO "$_TMPSCRIPT" "$_SCRIPT_URL"
  else
    echo "Error: instala curl o wget" >&2; exit 1
  fi
  chmod +x "$_TMPSCRIPT"
  exec bash "$_TMPSCRIPT" "$@" < /dev/tty
fi

# Re-ejecutar como el DUEÑO del proyecto (no un 'plone' hardcodeado), solo si NO lo somos
# ya. Detecta el owner de PLONE_BASE -> en despliegues por-slug es el usuario del tenant
# (p.ej. bernuy). Si ya somos ese usuario, NO se hace nada: así se evita el `cp` sobre el
# MISMO archivo /tmp tras el re-exec de curl|bash (que daba "are the same file").
PLONE_USER="$(stat -c '%U' "$PLONE_BASE" 2>/dev/null || true)"
if [ -n "$PLONE_USER" ] && [ "$(whoami)" != "$PLONE_USER" ]; then
  TMPSCRIPT="/tmp/_install-site-chrome-asuser-$$.sh"
  cp "$(readlink -f "$0")" "$TMPSCRIPT"
  chmod +r "$TMPSCRIPT"
  exec sudo -u "$PLONE_USER" env PLONE_BASE="$PLONE_BASE" bash "$TMPSCRIPT"
fi

cd "$PLONE_BASE" || err "No se encontro $PLONE_BASE"

# Detectar si los archivos fuente estan disponibles localmente
_SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
_SRC_BASE_URL="https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/src"

_get_src() {
  local rel="$1"
  local local_path="${_SCRIPT_DIR}/src/${rel}"
  if [[ -f "$local_path" ]]; then
    cat "$local_path"
  else
    curl -fsSL "${_SRC_BASE_URL}/${rel}"
  fi
}

# Auto-eliminar si somos la copia temporal en /tmp
[[ "$0" == /tmp/_install-site-chrome-*.sh ]] && rm -f "$0"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Site Chrome Manager — Installer        ║${NC}"
echo -e "${CYAN}║                    v1.0                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. DETECTAR BACKEND ──────────────────────────────────────────────
hr
info "Detectando configuracion..."

BACKEND_NAME=$(ls backend/src/ | grep -v '__pycache__' | grep -v '.egg-info' | head -1)
[[ -z "$BACKEND_NAME" ]] && err "No se encontro paquete backend en backend/src/"
log "Backend: $BACKEND_NAME"

SITE_ID=$(grep -rh "RAZZLE_INTERNAL_API_PATH" \
    /etc/systemd/system/plone-*.service \
    "${HOME}/.config/systemd/user/plone-*.service" 2>/dev/null \
  | grep -o 'http://[^"]*' | sed 's|http://[^/]*/||; s|/.*||' | head -1 || echo "")
[[ -z "$SITE_ID" ]] && SITE_ID="Plone"
log "Site ID: $SITE_ID"

# Detectar servicios systemd del proyecto (user services o system services)
_detect_svcs() {
  local pattern="$1" dir="$2"
  [[ -d "$dir" ]] || return
  grep -rl "$PLONE_BASE" "${dir}"/*.service 2>/dev/null \
    | while read -r f; do
        grep -qE "$pattern" "$f" && echo "$f" | sed 's|.*/||; s|\.service$||'
      done
}

USER_SVC_DIR="${HOME}/.config/systemd/user"
SYS_SVC_DIR="/etc/systemd/system"

# Detectar cada tipo de servicio de forma independiente
mapfile -t BACKEND_SVCS < <(_detect_svcs "runwsgi" "$USER_SVC_DIR")
mapfile -t VOLTO_SVCS   < <(_detect_svcs "server\.js|start:prod" "$USER_SVC_DIR")
BACKEND_MODE="--user"
VOLTO_MODE="--user"

# Fallback individual: si no se encontro en user services, buscar en system
if [[ ${#BACKEND_SVCS[@]} -eq 0 ]]; then
  mapfile -t BACKEND_SVCS < <(_detect_svcs "runwsgi" "$SYS_SVC_DIR")
  BACKEND_MODE="system"
fi
if [[ ${#VOLTO_SVCS[@]} -eq 0 ]]; then
  mapfile -t VOLTO_SVCS < <(_detect_svcs "server\.js" "$SYS_SVC_DIR")
  VOLTO_MODE="system"
fi
SYSTEMD_MODE="$BACKEND_MODE"

[[ ${#BACKEND_SVCS[@]} -eq 0 ]] && BACKEND_SVCS=("plone-backend-1")
[[ ${#VOLTO_SVCS[@]} -eq 0 ]]   && VOLTO_SVCS=("plone-volto")
log "Servicios backend : ${BACKEND_SVCS[*]}"
log "Servicios volto   : ${VOLTO_SVCS[*]}"
log "Modo backend      : $BACKEND_MODE"
log "Modo volto        : $VOLTO_MODE"

BACKEND_DIR="backend/src/$BACKEND_NAME"

# ── 2. SELECCIONAR / CREAR TEMA ──────────────────────────────────────
hr
info "Seleccion de tema Volto..."
echo ""

mapfile -t EXISTING < <(ls frontend/packages/ | grep '^volto-' || true)

if [ ${#EXISTING[@]} -eq 0 ]; then
  warn "No se encontraron temas existentes."
  SELECTION="n"
else
  echo "Paquetes disponibles (elige el tema del sitio):"
  for i in "${!EXISTING[@]}"; do
    PKG="${EXISTING[$i]}"
    DESC=$(python3 -c "import json; d=json.load(open('frontend/packages/${PKG}/package.json')); print(d.get('description','')[:40])" 2>/dev/null || echo "")
    printf "  [%d] %-22s  %s\n" "$((i+1))" "$PKG" "$DESC"
  done
fi

echo "  [n] Crear nuevo tema"
echo ""
read -rp "Seleccion [1]: " SELECTION
SELECTION="${SELECTION:-1}"

if [[ "$SELECTION" =~ ^[0-9]+$ ]] && [ "$SELECTION" -ge 1 ] && [ "$SELECTION" -le "${#EXISTING[@]}" ]; then
  THEME_NAME="${EXISTING[$((SELECTION-1))]}"
  CREATE_NEW=false
  log "Usando tema existente: $THEME_NAME"
else
  while true; do
    read -rp "Nombre del nuevo tema (debe empezar con 'volto-'): " THEME_NAME
    [[ "$THEME_NAME" =~ ^volto- ]] && break
    warn "El nombre debe empezar con 'volto-'"
  done
  CREATE_NEW=true
  log "Se creara nuevo tema: $THEME_NAME"
fi

THEME_DIR="frontend/packages/$THEME_NAME"

echo ""
echo -e "  Backend:  ${CYAN}$BACKEND_NAME${NC}"
echo -e "  Tema:     ${CYAN}$THEME_NAME${NC}  (nuevo: $CREATE_NEW)"
echo -e "  Site ID:  ${CYAN}$SITE_ID${NC}"
echo ""
read -rp "Continuar? (s/n) [s]: " CONFIRM
[[ "${CONFIRM:-s}" =~ ^[nN]$ ]] && { info "Cancelado."; exit 0; }

# ══════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════
hr
info "Configurando backend..."

# ── 3. Registry XML (6 keys con namespace site_chrome) ──────────────
REGISTRY_NS="${BACKEND_NAME}.site_chrome"
REGISTRY_FILE="${BACKEND_DIR}/profiles/default/registry/main.xml"

python3 - "$REGISTRY_FILE" "$REGISTRY_NS" << 'PYEOF'
import sys
import xml.etree.ElementTree as ET

registry_file = sys.argv[1]
ns = sys.argv[2]
keys = [
    ('{}.header_config'.format(ns),   'Site Chrome Header Config',
     '[{"id":"home","label":"Home","type":"plone","slug":""}]'),
    ('{}.header_base_css'.format(ns), 'Site Chrome Header Base CSS', ''),
    ('{}.header_css'.format(ns),      'Site Chrome Header CSS', ''),
    ('{}.footer_config'.format(ns),   'Site Chrome Footer Config',
     '{"columns":[],"copyright":"","legal_links":[],"show_default":true}'),
    ('{}.footer_base_css'.format(ns), 'Site Chrome Footer Base CSS', ''),
    ('{}.footer_css'.format(ns),      'Site Chrome Footer CSS', ''),
]

ET.register_namespace('i18n', 'http://xml.zope.org/namespaces/i18n')
tree = ET.parse(registry_file)
root = tree.getroot()

existing_keys = {r.get('name') for r in root.findall('record')}
added = []

for key, title, default_val in keys:
    if key not in existing_keys:
        record = ET.SubElement(root, 'record')
        record.set('name', key)
        field = ET.SubElement(record, 'field')
        field.set('type', 'plone.registry.field.Text')
        ET.SubElement(field, 'title').text = title
        ET.SubElement(field, 'required').text = 'False'
        ET.SubElement(record, 'value').text = default_val
        added.append(key)

if added:
    try:
        ET.indent(tree, space='  ')
    except AttributeError:
        pass  # Python < 3.9
    with open(registry_file, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        ET.ElementTree(root).write(f, encoding='unicode')
    print('Registry records creados: {}'.format(', '.join(added)))
else:
    print('Registry records ya existen')
PYEOF
log "Registry records verificados (site_chrome.*)"

# ── 4. Endpoint REST /@site-chrome ──────────────────────────────────
RESTAPI_DIR="${BACKEND_DIR}/restapi"
mkdir -p "$RESTAPI_DIR"
touch "${RESTAPI_DIR}/__init__.py"

# Limpiar endpoint viejo del nav-menu si existe
rm -f "${RESTAPI_DIR}/navigation_menu.py"

_get_src "backend/site_chrome.py" > "${RESTAPI_DIR}/site_chrome.py"
_get_src "backend/restapi_configure.zcml" > "${RESTAPI_DIR}/configure.zcml"

MAIN_ZCML="${BACKEND_DIR}/configure.zcml"
if grep -q 'package=".restapi"' "$MAIN_ZCML"; then
  warn ".restapi ya registrado en configure.zcml"
else
  python3 - "$MAIN_ZCML" << 'PYEOF'
import sys, re
zcml_file = sys.argv[1]
with open(zcml_file) as f:
    content = f.read()
if '.restapi' in content:
    print('configure.zcml ya incluye .restapi')
    sys.exit(0)
include_line = '\n  <include package=".restapi" />\n'
content = re.sub(r'(\s*</configure>\s*)$', include_line + r'\1', content.rstrip() + '\n')
with open(zcml_file, 'w') as f:
    f.write(content)
print('Registrado .restapi en configure.zcml')
PYEOF
  log "Registrado .restapi en configure.zcml"
fi

log "Endpoint /@site-chrome creado"

# ══════════════════════════════════════════
#  FRONTEND
# ══════════════════════════════════════════
hr
info "Configurando frontend..."

# ── 5. Scaffold nuevo tema si aplica ────────────────────────────────
if [ "$CREATE_NEW" = true ]; then
  info "Creando estructura del tema $THEME_NAME..."
  mkdir -p "${THEME_DIR}/src/components"

  cat > "${THEME_DIR}/package.json" << JSONEOF
{
  "name": "${THEME_NAME}",
  "version": "1.0.0",
  "description": "Tema Plone",
  "main": "src/index.ts",
  "license": "MIT",
  "keywords": ["volto-addon", "volto", "plone"],
  "addons": [],
  "dependencies": {
    "@dnd-kit/core": "^6.1.0",
    "@dnd-kit/sortable": "^8.0.0",
    "@dnd-kit/utilities": "^3.2.2"
  },
  "peerDependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@plone/registry": "workspace:*",
    "@plone/scripts": "workspace:*",
    "@plone/types": "workspace:*",
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "typescript": "^5.7.3"
  }
}
JSONEOF

  cat > "${THEME_DIR}/tsconfig.json" << 'EOF'
{
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
EOF

  python3 - "frontend/package.json" "$THEME_NAME" << 'PYEOF'
import sys, json
pkg_file, theme = sys.argv[1], sys.argv[2]
with open(pkg_file) as f:
    data = json.load(f)
data.setdefault('dependencies', {})[theme] = 'workspace:*'
with open(pkg_file, 'w') as f:
    json.dump(data, f, indent=2)
print('Registrado en frontend/package.json: {}'.format(theme))
PYEOF

  python3 - "frontend/volto.config.js" "$THEME_NAME" << 'PYEOF'
import sys, re
cfg_file, theme = sys.argv[1], sys.argv[2]
with open(cfg_file) as f:
    content = f.read()
def add_addon(m):
    inner = m.group(1).strip().rstrip(',')
    sep = ', ' if inner else ''
    return "const addons = [{}'{}'{}]".format(inner + sep if inner else '', theme, '')
content = re.sub(r"const addons\s*=\s*\[([^\]]*)\]", add_addon, content)
with open(cfg_file, 'w') as f:
    f.write(content)
print('Registrado en volto.config.js: {}'.format(theme))
PYEOF

  _get_src "frontend/index.ts.template" > "${THEME_DIR}/src/index.ts"

  log "Tema $THEME_NAME creado y registrado"
else
  python3 - "${THEME_DIR}/package.json" << 'PYEOF'
import sys, json
pkg_file = sys.argv[1]
with open(pkg_file) as f:
    data = json.load(f)
deps = data.setdefault('dependencies', {})
added = []
for pkg, ver in [('@dnd-kit/core','^6.1.0'),('@dnd-kit/sortable','^8.0.0'),('@dnd-kit/utilities','^3.2.2')]:
    if pkg not in deps:
        deps[pkg] = ver
        added.append(pkg)
with open(pkg_file, 'w') as f:
    json.dump(data, f, indent=2)
print('@dnd-kit agregado: {}'.format(', '.join(added)) if added else '@dnd-kit ya instalado')
PYEOF
fi

# ── 5b. Limpiar instalacion previa de MF-Nav-Menu en este tema ──────
# Archivos renombrados en el rename a Site Chrome
rm -f "${THEME_DIR}/src/controlpanels/NavigationMenuControlPanel.jsx" \
      "${THEME_DIR}/src/controlpanels/NavigationMenuControlPanel.css" \
      "${THEME_DIR}/src/navMenuSSR.js"
rm -f "${BACKEND_DIR}/viewlets/nav_css_viewlet.py" \
      "${BACKEND_DIR}/viewlets/nav_css_viewlet.pt"

# ── 6. Navigation.jsx (header / fat menu) ───────────────────────────
NAV_DIR="${THEME_DIR}/src/customizations/volto/components/theme/Navigation"
mkdir -p "$NAV_DIR"
_get_src "frontend/Navigation.jsx" > "${NAV_DIR}/Navigation.jsx"
_get_src "frontend/Navigation.css" > "${NAV_DIR}/Navigation.css"
log "Navigation.jsx + css creados (header)"

# ── 6b. Footer.jsx (footer por config) ──────────────────────────────
FOOTER_DIR="${THEME_DIR}/src/customizations/volto/components/theme/Footer"
mkdir -p "$FOOTER_DIR"
_get_src "frontend/Footer.jsx" > "${FOOTER_DIR}/Footer.jsx"
_get_src "frontend/Footer.css" > "${FOOTER_DIR}/Footer.css"
log "Footer.jsx + css creados (footer)"

# ── 7. Limpiar copias conflictivas en otros addons ─────────────────
for other_pkg in frontend/packages/*/; do
  [[ "$other_pkg" == "${THEME_DIR}/" ]] && continue
  rm -f "${other_pkg}src/controlpanels/SiteChromeControlPanel.jsx" \
        "${other_pkg}src/controlpanels/SiteChromeControlPanel.css" \
        "${other_pkg}src/controlpanels/NavigationMenuControlPanel.jsx" \
        "${other_pkg}src/controlpanels/NavigationMenuControlPanel.css" \
        "${other_pkg}src/customizations/volto/components/theme/Navigation/Navigation.jsx" \
        "${other_pkg}src/customizations/volto/components/theme/Navigation/Navigation.css" \
        "${other_pkg}src/customizations/volto/components/theme/Footer/Footer.jsx" \
        "${other_pkg}src/customizations/volto/components/theme/Footer/Footer.css" \
        "${other_pkg}src/navMenuSSR.js" \
        "${other_pkg}src/siteChromeSSR.js" 2>/dev/null || true
  # Limpiar referencias en index.ts (viejas y nuevas)
  if [[ -f "${other_pkg}src/index.ts" ]]; then
    python3 - "${other_pkg}src/index.ts" << 'CLEANEOF'
import sys, re
f = sys.argv[1]
with open(f) as fh:
    c = fh.read()
if 'NavigationMenuControlPanel' not in c and 'SiteChromeControlPanel' not in c:
    sys.exit(0)
c = re.sub(r"import NavigationMenuControlPanel[^\n]*\n", '', c)
c = re.sub(r"import SiteChromeControlPanel[^\n]*\n", '', c)
c = re.sub(r"import \{ (?:navMenuReducer|siteChromeReducer)[^\n]*\n", '', c)
c = re.sub(r"\s*\{[^}]*(?:navigation-menu|site-chrome)[^}]*\},?\n?", '\n', c)
with open(f, 'w') as fh:
    fh.write(c)
print(f'  Limpiado index.ts en {f}')
CLEANEOF
  fi
done

# ── 8. SiteChromeControlPanel.jsx (Header | Footer) ─────────────────
CP_DIR="${THEME_DIR}/src/controlpanels"
mkdir -p "$CP_DIR"
_get_src "frontend/SiteChromeControlPanel.jsx" > "${CP_DIR}/SiteChromeControlPanel.jsx"
_get_src "frontend/SiteChromeControlPanel.css" > "${CP_DIR}/SiteChromeControlPanel.css"
log "Control Panel creado (Header | Footer)"

# ── 9. siteChromeSSR.js (Redux SSR header+footer, sin flash) ────────
_get_src "frontend/siteChromeSSR.js" > "${THEME_DIR}/src/siteChromeSSR.js"
log "siteChromeSSR.js creado (Redux SSR)"

# ── 9b. Viewlet backend (CSS header+footer en <head>) ───────────────
VIEWLET_DIR="${BACKEND_DIR}/viewlets"
mkdir -p "$VIEWLET_DIR"
cat > "${VIEWLET_DIR}/__init__.py" << 'INITEOF'
# -*- coding: utf-8 -*-
INITEOF

_get_src "backend/site_chrome_viewlet.py" | sed "s/%%BACKEND_NAME%%/${BACKEND_NAME}/g" > "${VIEWLET_DIR}/site_chrome_viewlet.py"
_get_src "backend/site_chrome_viewlet.pt" > "${VIEWLET_DIR}/site_chrome_viewlet.pt"
_get_src "backend/viewlet_configure.zcml" | sed "s/%%BACKEND_NAME%%/${BACKEND_NAME}/g" > "${VIEWLET_DIR}/configure.zcml"

# Registrar viewlets en configure.zcml principal si no existe
MAIN_ZCML="${BACKEND_DIR}/configure.zcml"
if ! grep -q 'viewlets' "$MAIN_ZCML" 2>/dev/null; then
  python3 - "$MAIN_ZCML" << 'VIEWZCMLEOF'
import sys
p = sys.argv[1]
with open(p) as f:
    c = f.read()
if '.viewlets' not in c:
    c = c.replace('</configure>', '  <include package=".viewlets" />\n\n</configure>')
    with open(p, 'w') as f:
        f.write(c)
    print('viewlets registrado en configure.zcml')
VIEWZCMLEOF
fi
log "Viewlet backend creado (CSS en <head>)"

# ── 10. index.ts ─────────────────────────────────────────────────────
INDEX_FILE="${THEME_DIR}/src/index.ts"

python3 - "$INDEX_FILE" << 'PYEOF'
import sys, re, os

index_file = sys.argv[1]
current = ''
if os.path.exists(index_file):
    with open(index_file) as f:
        current = f.read()

already = ('SiteChromeControlPanel' in current and 'siteChromeReducer' in current
           and 'navigation-menu' not in current and 'NavigationMenuControlPanel' not in current)
if already:
    print('index.ts ya actualizado')
    sys.exit(0)

# Quitar imports viejos del nav-menu (rename a site-chrome)
current = re.sub(r"^import NavigationMenuControlPanel[^\n]*\n", '', current, flags=re.M)
current = re.sub(r"^import \{ navMenuReducer[^\n]*\n", '', current, flags=re.M)

# Agregar solo los imports que faltan
our_imports = []
if "import type { ConfigType }" not in current:
    our_imports.append("import type { ConfigType } from '@plone/registry';")
if 'SiteChromeControlPanel' not in current:
    our_imports.append("import SiteChromeControlPanel from './controlpanels/SiteChromeControlPanel';")
if 'siteChromeReducer' not in current:
    our_imports.append("import { siteChromeReducer, siteChromeAsyncExtender } from './siteChromeSSR';")

if our_imports:
    last_import = None
    for m in re.finditer(r'^import\s.+;$', current, re.MULTILINE):
        last_import = m
    if last_import:
        pos = last_import.end()
        current = current[:pos] + '\n' + '\n'.join(our_imports) + current[pos:]
    else:
        current = '\n'.join(our_imports) + '\n\n' + current

def find_matching_brace(text, open_pos):
    """Cuenta llaves para encontrar el cierre correcto, ignorando strings y comentarios."""
    depth = 1
    i = open_pos + 1
    in_str = None
    skip = False
    n = len(text)
    while i < n and depth > 0:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if skip:
            skip = False
        elif in_str:
            if c == '\\':
                skip = True
            elif c == in_str:
                in_str = None
        elif c == '/' and nxt == '/':
            j = text.find('\n', i)
            if j < 0:
                break
            i = j
            continue
        elif c == '/' and nxt == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                break
            i = j + 2
            continue
        elif c in ('"', "'", '`'):
            in_str = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1

FUNC_PATTERNS = [
    r'(?:export\s+default\s+)?function\s+applyConfig\s*\([^)]*\)\s*(?::\s*\w+\s*)?\{',
    r'const\s+applyConfig\s*=\s*\([^)]*\)\s*(?::\s*\w+\s*)?=>\s*\{',
    r'const\s+applyConfig\s*=\s*\([^)]*\)\s*=>\s*\{',
]

func_match = None
for pat in FUNC_PATTERNS:
    func_match = re.search(pat, current)
    if func_match:
        break

# Si no existe la funcion, crear desde cero
if not func_match:
    current = current.rstrip()
    if current:
        current += '\n\n'
    current += 'function applyConfig(config: ConfigType) {\n  return config;\n}\n\nexport default applyConfig;\n'
    func_match = re.search(FUNC_PATTERNS[0], current)

open_pos = func_match.end() - 1   # posicion del '{'
close_pos = find_matching_brace(current, open_pos)
if close_pos < 0:
    print('ERROR: llaves desbalanceadas en ' + index_file)
    sys.exit(1)

body = current[open_pos + 1:close_pos]

# Limpiar entradas previas del instalador (nav-menu y site-chrome).
body = re.sub(r'\s*config\.settings\.navDepth\s*=.*?;', '', body)
body = re.sub(r'\s*installSettings\(config\);', '', body)
# Comentario SSR del instalador (cualquier version)
body = re.sub(r'[ \t]*//[^\n]*SSR:[^\n]*\n', '', body)
# Entradas del reducer/extender en objetos posiblemente compartidos: quitar SOLO
# las nuestras, sin tocar reducers/extenders ajenos (p.ej. schema del usuario).
body = re.sub(r'\s*navMenu:\s*navMenuReducer,?', '', body)
body = re.sub(r'\s*siteChrome:\s*siteChromeReducer,?', '', body)
body = re.sub(r"\s*\{\s*path:\s*'/',\s*extend:\s*navMenuAsyncExtender\s*\},?", '', body)
body = re.sub(r"\s*\{\s*path:\s*'/',\s*extend:\s*siteChromeAsyncExtender\s*\},?", '', body)
# controlpanels y addonRoutes son arrays propios del instalador: strip completo.
body = re.sub(r'\s*config\.settings\.controlpanels\s*=\s*\[.*?\];', '', body, flags=re.DOTALL)
body = re.sub(r'\s*config\.addonRoutes\s*=\s*\[.*?\];', '', body, flags=re.DOTALL)

# Reducer/extender: si el objeto/array ya existe (posiblemente con entradas
# ajenas), insertar la nuestra dentro; si no, crear assignment nuevo.
if re.search(r'config\.addonReducers\s*=\s*\{', body):
    body = re.sub(r'(config\.addonReducers\s*=\s*\{)',
                  r'\1\n    siteChrome: siteChromeReducer,', body, count=1)
    add_reducer = False
else:
    add_reducer = True

if re.search(r'config\.settings\.asyncPropsExtenders\s*=\s*\[', body):
    body = re.sub(r'(config\.settings\.asyncPropsExtenders\s*=\s*\[)',
                  r"\1\n    { path: '/', extend: siteChromeAsyncExtender },", body, count=1)
    add_extender = False
else:
    add_extender = True

entries = []
entries.append("  config.settings.navDepth = 2;")
entries.append("""  config.settings.controlpanels = [
    ...(config.settings.controlpanels || []),
    {
      '@id': '/controlpanel/site-chrome',
      group: 'General',
      title: 'Site Chrome',
      description: 'Administra header (menu) y footer - sin rebuild.',
      icon: 'list layout',
    },
  ];""")
entries.append("""  config.addonRoutes = [
    ...(config.addonRoutes || []),
    {
      path: '/controlpanel/site-chrome',
      component: SiteChromeControlPanel,
    },
  ];""")
if add_reducer:
    entries.append("  // SSR: header + footer en el servidor para el HTML inicial (sin flash)\n"
                   "  config.addonReducers = { ...(config.addonReducers || {}), siteChrome: siteChromeReducer };")
if add_extender:
    entries.append("""  config.settings.asyncPropsExtenders = [
    ...(config.settings.asyncPropsExtenders || []),
    { path: '/', extend: siteChromeAsyncExtender },
  ];""")

new_entries = "\n\n" + "\n\n".join(entries) + "\n"

ret_match = re.search(r'\n(\s*return config;)', body)
if ret_match:
    insert_at = ret_match.start()
    body = body[:insert_at] + new_entries + body[insert_at:]
else:
    body = body.rstrip() + new_entries + '\n  return config;\n'

new_content = current[:open_pos + 1] + body + current[close_pos:]

with open(index_file, 'w') as f:
    f.write(new_content)
print('index.ts actualizado (site-chrome: control panel + reducer SSR)')
PYEOF

log "index.ts actualizado"

# ══════════════════════════════════════════
#  BUILD + RESTART
# ══════════════════════════════════════════
hr
echo ""
read -rp "Compilar y reiniciar ahora? (s/n) [s]: " BUILD_NOW
BUILD_NOW="${BUILD_NOW:-s}"

if [[ "$BUILD_NOW" =~ ^[sS]$ ]]; then
  info "Instalando dependencias..."
  cd frontend && pnpm install
  info "Compilando (esto tarda unos minutos)..."
  pnpm build > /tmp/_sitechrome_build_$$.log 2>&1 &
  _BUILD_PID=$!
  _build_anim() {
    local pid="$1"
    local colors=("\033[1;36m" "\033[1;35m" "\033[1;33m" "\033[1;32m")
    local dim="\033[2;37m" rst="\033[0m"
    local idx=0 secs=0
    while kill -0 "$pid" 2>/dev/null; do
      local line="  "
      for j in 0 1 2 3; do
        if [ $j -eq $((idx % 4)) ]; then
          line+="${colors[$j]}●${rst} "
        else
          line+="${dim}○${rst} "
        fi
      done
      printf "\r${line} ${dim}compilando${rst}  %02d:%02d" $((secs/60)) $((secs%60)) > /dev/tty
      sleep 1
      ((idx++)) || true; ((secs++)) || true
    done
    printf "\r%60s\r" > /dev/tty
  }
  _build_anim "$_BUILD_PID" &
  _ANIM_PID=$!
  wait $_BUILD_PID && _BUILD_EXIT=0 || _BUILD_EXIT=$?
  kill $_ANIM_PID 2>/dev/null || true; wait $_ANIM_PID 2>/dev/null || true
  if [[ $_BUILD_EXIT -ne 0 ]]; then
    err "Build fallido. Ver log: /tmp/_sitechrome_build_$$.log"
  fi
  log "Build completado"
  cd ..
  info "Reiniciando servicios (backend=$BACKEND_MODE volto=$VOLTO_MODE)..."
  # XDG_RUNTIME_DIR es necesario para systemctl --user en sesiones no interactivas
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  _restart_svc() {
    local mode="$1"; shift
    # Expandir PLANTILLAS (nombres que terminan en '@') a sus instancias reales:
    # plone-ama-backend@ -> plone-ama-backend@8100 plone-ama-backend@8102. Una
    # plantilla NO se puede reiniciar sin instancia ("missing the instance name").
    local svcs=() s inst
    for s in "$@"; do
      if [[ "$s" == *@ ]]; then
        if [[ "$mode" == "--user" ]]; then
          inst=$(systemctl --user list-units --all --no-legend "${s}*.service" 2>/dev/null | awk '{print $1}')
        else
          inst=$(systemctl list-units --all --no-legend "${s}*.service" 2>/dev/null | awk '{print $1}')
        fi
        if [[ -n "$inst" ]]; then
          while read -r u; do [[ -n "$u" ]] && svcs+=("$u"); done <<< "$inst"
        else
          svcs+=("$s")
        fi
      else
        svcs+=("$s")
      fi
    done
    if [[ "$mode" == "--user" ]]; then
      systemctl --user restart "${svcs[@]}"
    else
      sudo -n systemctl restart "${svcs[@]}"
    fi
  }
  RESTART_OK=true
  _restart_svc "$BACKEND_MODE" "${BACKEND_SVCS[@]}" || RESTART_OK=false
  _restart_svc "$VOLTO_MODE"   "${VOLTO_SVCS[@]}"   || RESTART_OK=false
  if [[ "$RESTART_OK" == true ]]; then
    log "Reiniciados: ${BACKEND_SVCS[*]} ${VOLTO_SVCS[*]}"
  else
    warn "Reinicio manual requerido:"
    echo ""
    if [[ "$BACKEND_MODE" == "--user" ]]; then
      echo -e "  ${CYAN}systemctl --user restart ${BACKEND_SVCS[*]}${NC}"
    else
      echo -e "  ${CYAN}sudo systemctl restart ${BACKEND_SVCS[*]}${NC}"
    fi
    if [[ "$VOLTO_MODE" == "--user" ]]; then
      echo -e "  ${CYAN}systemctl --user restart ${VOLTO_SVCS[*]}${NC}"
    else
      echo -e "  ${CYAN}sudo systemctl restart ${VOLTO_SVCS[*]}${NC}"
    fi
    echo ""
    read -rp "Presiona Enter cuando hayas reiniciado..." _WAIT
  fi
else
  warn "Compilacion pendiente:"
  echo "  cd frontend && pnpm install && pnpm build && cd .."
  if [[ "$BACKEND_MODE" == "--user" ]]; then
    echo "  systemctl --user restart ${BACKEND_SVCS[*]}"
  else
    echo "  sudo systemctl restart ${BACKEND_SVCS[*]}"
  fi
  if [[ "$VOLTO_MODE" == "--user" ]]; then
    echo "  systemctl --user restart ${VOLTO_SVCS[*]}"
  else
    echo "  sudo systemctl restart ${VOLTO_SVCS[*]}"
  fi
fi

# ══════════════════════════════════════════
#  RESUMEN
# ══════════════════════════════════════════
hr
echo ""
echo -e "${GREEN}Instalacion completada — Site Chrome v1.0${NC}"
echo ""
echo -e "  Backend:        ${CYAN}$BACKEND_NAME${NC}"
echo -e "  Tema:           ${CYAN}$THEME_NAME${NC}"
echo -e "  Registry:       ${CYAN}${BACKEND_NAME}.site_chrome.{header,footer}_{config,base_css,css}${NC}"
echo -e "  Endpoint:       ${CYAN}GET/PATCH /@site-chrome${NC}"
echo -e "  Control Panel:  ${CYAN}/controlpanel/site-chrome${NC}"
echo ""
echo -e "  Seccion 'Header': Items (drag&drop) · Estilos base · CSS Custom"
echo -e "  Seccion 'Footer': Columnas · Estilos base · CSS Custom"
echo -e "  Presets header: nm-apple  nm-dark  nm-wide  nm-minimal"
echo -e "  Fat menu automatico: hover abre dropdown (navDepth=2)"
echo -e "  ${GREEN}Sin rebuild. Sin restart. Cambio instantaneo.${NC}"
echo ""
echo -e "  ${YELLOW}Verifica nginx${NC} (config del despliegue base de Plone, NO de Site Chrome):"
echo -e "  el HTML de Volto debe ir 'Cache-Control: no-cache' o tras un redeploy puede"
echo -e "  salir 'Loading chunk failed' (navegadores con HTML cacheado). Comprueba con:"
echo -e "    curl -sD- http://<host>/ -o /dev/null | grep -i cache-control   # esperado: no-cache"
echo -e "  Si falta, agregalo en el 'location /' de Volto (y deja /static/ con cache larga)."
echo ""
