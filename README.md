# MF-Site-Chrome

**Site Chrome Manager para Plone 6 / Volto** — administra el **header (menú de navegación)** y el **footer** del sitio desde el panel de administración, sin necesidad de rebuild.

> Antes era **MF-Nav-Menu** (solo header). A partir de v1.0 unifica header + footer bajo un mismo módulo y endpoint. Las instalaciones de MF-Nav-Menu se **migran solas** (ver más abajo).

## Características

- **Sin rebuild** — cambios visibles al instante desde Site Setup
- **Header**: fat menu automático (hover con subpáginas), anclas con scroll suave, enlaces a páginas Plone
- **Footer**: columnas de enlaces + copyright + enlaces legales, o footer estándar de Plone
- **Control Panel** con dos secciones: **Header** y **Footer**, cada una con Items/Columnas · Estilos base · CSS Custom
- **Presets header**: `nm-apple`, `nm-dark`, `nm-wide`, `nm-minimal`
- **SSR sin flash** — CSS de header y footer inyectado en `<head>` del HTML desde el backend
- **Seguro**: el header oculta enlaces a páginas que el usuario no puede ver (permiso `View`); el PATCH funciona con auth por token (CSRF resuelto)
- **Multi-proyecto** — detecta automáticamente backend, tema y servicios systemd

## Requisitos

- Plone 6 + Volto (React)
- Python 3.8+
- pnpm
- Usuario `plone` con acceso al proyecto

## Quick Install

```bash
curl -sL https://raw.githubusercontent.com/RenteriaMX/MF-Site-Chrome/main/install-site-chrome.sh | bash -s /ruta/al/proyecto
```

> El script se re-ejecuta automáticamente como el usuario `plone`. No es necesario correrlo ya como plone.

## Qué instala

### Backend
| Archivo | Descripción |
|---------|-------------|
| `restapi/site_chrome.py` | Endpoint `/@site-chrome` (GET público / PATCH Manager) |
| `restapi/configure.zcml` | Registro del endpoint en Zope |
| `viewlets/site_chrome_viewlet.py` | Inyecta CSS de header + footer en `<head>` (SSR sin flash) |
| `profiles/default/registry/main.xml` | 6 registry keys (header + footer: config, base_css, css) |

### Frontend (en el tema seleccionado)
| Archivo | Descripción |
|---------|-------------|
| `src/customizations/.../Navigation/Navigation.jsx` | Fat menu del header (hover, anchor y plone) |
| `src/customizations/.../Footer/Footer.jsx` | Footer por config (columnas/copyright/legal) |
| `src/controlpanels/SiteChromeControlPanel.jsx` | Panel con secciones Header / Footer |
| `src/siteChromeSSR.js` | Redux reducer + action para SSR (header + footer) |
| `src/index.ts` | Actualizado con navDepth=2, ruta del control panel y reducer |

## Uso del Control Panel

Después de instalar, accede desde **Site Setup → Site Chrome** o directamente en:

```
https://tu-sitio/controlpanel/site-chrome
```

El panel tiene un selector superior **Header | Footer**.

### Header → Items del menú
- Arrastra para reordenar
- Items tipo **Ancla** (scroll a `#id`) o **Página Plone** (enlace por slug)
- Botón 🎨 asigna un preset CSS por item
- Estilos base (presets editables) y CSS Custom

### Footer → Columnas
- Columnas de enlaces (título + lista de label/href)
- `copyright` y enlaces legales
- Casilla "usar footer estándar de Plone" como red de seguridad
- Estilos base (`.sc-footer`) y CSS Custom

Todo se guarda y aplica **sin rebuild**.

## Modelo de datos

### Header item
```json
{ "id": "contacto", "label": "Contacto", "type": "anchor", "href": "#contacto", "anchorPage": "/" }
```

| Campo | Descripción |
|-------|-------------|
| `type: "plone"` | Enlace a página Plone por slug. Con subpáginas → fat menu automático |
| `type: "anchor"` | Scroll suave a un `#id`. Cross-page con `anchorPage` |
| `noFatMenu: true` | Desactiva el fat menu para ese item |
| `cssClass` | Clase CSS aplicada al panel desplegable (ej: `nm-apple`) |

### Footer config
```json
{
  "columns": [
    { "id": "c1", "title": "Recursos", "links": [ { "id": "l1", "label": "Mapa", "href": "/sitemap" } ] }
  ],
  "copyright": "© 2000-2026 ...",
  "legal_links": [ { "id": "g1", "label": "GNU GPL", "href": "https://..." } ],
  "show_default": false
}
```

## Presets de header

| Preset | Descripción |
|--------|-------------|
| `nm-apple` | Frosted glass, ancho completo estilo Apple |
| `nm-dark` | Fondo oscuro |
| `nm-wide` | Ancho completo simple |
| `nm-minimal` | Sin cabecera, compacto |

## Registry keys generadas

```
{BACKEND}.site_chrome.header_config     # Items del menú (JSON)
{BACKEND}.site_chrome.header_base_css   # CSS base + presets del header
{BACKEND}.site_chrome.header_css        # CSS custom del header
{BACKEND}.site_chrome.footer_config     # Config del footer (JSON)
{BACKEND}.site_chrome.footer_base_css   # CSS base del footer
{BACKEND}.site_chrome.footer_css        # CSS custom del footer
```

## Migración desde MF-Nav-Menu

Si el proyecto ya tenía MF-Nav-Menu instalado:

- El header se conserva: si las keys nuevas `site_chrome.header_*` están vacías, el endpoint lee como fallback las viejas `navigation.menu_*` (migración **lazy**, sin `zconsole`). En el primer guardado desde el panel, los valores pasan a las keys nuevas.
- El instalador elimina los archivos renombrados de la instalación anterior (control panel, reducer, viewlet, endpoint viejos) y limpia las referencias en `index.ts`.
- Requiere re-correr el instalador y un `pnpm build` (entra el shadow de `Footer.jsx`).

## Detección automática de servicios

1. Busca primero en `~/.config/systemd/user/` (user services)
2. Si no encuentra, busca en `/etc/systemd/system/` (system services)
3. Detecta todas las instancias del backend
4. Reinicia cada tipo de servicio con el modo correcto (`--user` o `sudo`)

## Versiones

| Versión | Cambios principales |
|---------|---------------------|
| 1.0 | Rename a Site Chrome. Header + footer, endpoint unificado `@site-chrome`, footer por config, fix CSRF en PATCH, filtro por permiso `View`, migración lazy |
| 0.9 | (MF-Nav-Menu) Anchors cross-page, SSR Redux, viewlet backend |
| 0.8 | 3 registry keys, 3 tabs en control panel, presets editables |

## Licencia

MIT
