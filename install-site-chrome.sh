#!/bin/bash
# OBSOLETO: el instalador ahora es install_site_chrome.py (Python). Este archivo solo conserva la compatibilidad con instrucciones y
# versiones anteriores de HEOC que descargan install-site-chrome.sh. Acepta la ruta del proyecto (o PLONE_BASE) y las opciones de
# install_site_chrome.py (--theme, --yes, --no-build, --dry-run).
D="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -f "$D/install_site_chrome.py" ]; then exec python3 "$D/install_site_chrome.py" "$@"; fi
exec python3 -c "$(curl -fsSL https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/install_site_chrome.py)" "$@"
