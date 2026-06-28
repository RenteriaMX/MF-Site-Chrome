# collective.sitechrome

Add-on backend de **Site Chrome** para Plone/Volto: administra el **header**
(menú) y el **footer** del sitio sin recompilar el frontend.

Es el split del backend de **MF-Site-Chrome** a un paquete instalable propio
(antes vivía como archivos sueltos dentro del policy package del sitio). El
**frontend** sigue siendo *component shadowing* dentro del tema Volto (ver el
instalador `install-site-chrome.sh` del repo).

## Qué provee

- Endpoint REST **`/@site-chrome`**
  - `GET` público (lo consume el SSR de Volto) — devuelve `header`/`footer` con
    items + CSS, **ya sanitizados** (SC-3).
  - `PATCH` solo `cmf.ManagePortal` — guarda header o footer; sanitiza CSS/HTML.
- **Viewlet** que inyecta el CSS de header/footer en `<head>` (sin rebuild),
  también sanitizado.
- **Perfiles GenericSetup**: `default` (crea las 6 registry keys) y `uninstall`
  (las elimina). El add-on aparece en *Site Setup → Add-ons*.

## Registry keys

```
collective.sitechrome.site_chrome.header_config | header_base_css | header_css
collective.sitechrome.site_chrome.footer_config | footer_base_css | footer_css
```

## Instalación

Vía el instalador del repo (recomendado): `install-site-chrome.sh` hace
`pip install -e packages/collective.sitechrome` y activa el add-on.

Manual:
```bash
cd <proyecto>/backend
cp -r <repo>/backend/collective.sitechrome packages/
.venv/bin/pip install -e packages/collective.sitechrome
# reiniciar backend y, en Site Setup → Add-ons, instalar "collective.sitechrome"
```

Sin activar el perfil GS el add-on igual funciona: el servicio y el viewlet se
cargan por `z3c.autoinclude` y las registry keys se crean *lazy* en el primer
`PATCH`. El perfil solo siembra los defaults limpios.

## Seguridad

Ver [`../../SECURITY.md`](../../SECURITY.md). Resumen: sanitización al leer y al
escribir (SC-3/SC-4), `url()` externo neutralizado (SC-5), CSRF conservador
(SC-2) y auditoría del PATCH (SC-6). Flags: `SITE_CHROME_ALLOW_EXTERNAL_URL`,
`SITE_CHROME_LEGACY_NS`.

## Tests

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
```
