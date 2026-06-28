# Seguridad — MF-Site-Chrome

El backend (add-on **`collective.sitechrome`**) expone `/@site-chrome`:
**GET público** (lo necesita el SSR de Volto) y **PATCH solo Manager**
(`cmf.ManagePortal`). Guarda config + CSS de header/footer y HTML opcional del
footer en el registry, y los inyecta en la página (CSS en `<style>`, HTML del
footer en un `<div>`).

Superficies de inyección y sus defensas:

| Superficie | Sink | Defensa |
|---|---|---|
| CSS header/footer | `<style dangerouslySetInnerHTML>` (Volto) y `<style tal:content>` (viewlet) | `sanitize_css` (SC-4) + escape del viewlet |
| `url()` externo en CSS | igual que arriba | **SC-5**: neutralizado a `url(about:blank)` (anti beacon/exfil) salvo opt-in |
| HTML del footer (modo Blocs) | `<div dangerouslySetInnerHTML>` | `sanitize_html` (SC-1): allowlist `safe_html` de Plone + fallback blocklist |
| `href` de items del menú | `<a href>` | `safeHref`: allowlist de esquema (http/https/mailto/tel) |

### Endurecimientos clave (v2)

- **SC-3 — sanitizar al leer/renderizar, no solo al escribir.** `GET /@site-chrome`
  pasa el CSS por `sanitize_css` y el HTML del footer por `sanitize_html` **antes
  de responder**. Así el sink `dangerouslySetInnerHTML` nunca recibe registry
  crudo aunque alguien escriba las keys por fuera del PATCH (ZMI, migración,
  otro add-on). El viewlet también sanitiza al inyectar.
- **SC-5 — `url()` externo neutralizado.** Un Manager no puede insertar beacons
  de tracking/exfiltración vía `background:url(https://…)`. Las `url()` relativas
  (same-origin) se conservan.
- **SC-6 — auditoría.** Cada PATCH registra `user=… action=patch section=…` en el
  logger `collective.sitechrome.audit`.
- **SC-2 — CSRF.** `plone.protect` solo se desactiva con Bearer **sin** cookie de
  sesión `__ac`; si hay cookie clásica, se mantiene la protección.

## Variables de entorno

| Var | Default | Efecto |
|---|---|---|
| `SITE_CHROME_ALLOW_EXTERNAL_URL` | (desactivado) | `1` permite `url()` externo en CSS (fuentes/imágenes de CDN). Úsalo solo si confías plenamente en quien edita el chrome. |
| `SITE_CHROME_LEGACY_NS` | (vacío) | Namespace de una instalación previa (p.ej. `ama`) para migrar valores al activar el add-on. En server nuevo, déjalo vacío. |

## Auditoría (logging config de la instancia)

```
[logger_sitechrome_audit]
level=INFO
handlers=auditfile
qualname=collective.sitechrome.audit
```

## CSP

El CSS no ejecuta JS en navegadores modernos, pero como defensa en profundidad
sobre el sink `dangerouslySetInnerHTML`, una CSP que excluya orígenes de script
externos no estorba al chrome (que es solo CSS/HTML same-origin):
```nginx
add_header Content-Security-Policy "script-src 'self'; object-src 'none'; base-uri 'self'" always;
```

## Tests

```bash
cd backend/collective.sitechrome && PYTHONPATH=src python3 -m pytest tests/ -q
```
Cubre `sanitize_css` (breakout `</style>`, `expression()`, `@import`,
`javascript:`, `behavior:`, `url()` externo) y `sanitize_html` (fallback
blocklist) sin requerir Plone.
