"""
Endpoint /@site-chrome  (Site Chrome Manager)
  GET   - retorna { header: {items, base_css, css},
                    footer: {config, base_css, css} }
  PATCH - body { section: 'header'|'footer', ... } guarda solo esa seccion.

Registry keys (namespace site_chrome, prefijo = nombre del paquete backend):
  <pkg>.site_chrome.header_config / header_base_css / header_css
  <pkg>.site_chrome.footer_config / footer_base_css / footer_css
"""
import json
import logging
import re
from plone import api
from plone.restapi.services import Service

logger = logging.getLogger(__name__)

_PKG = __name__.split('.')[0]
_NS = '{}.site_chrome'.format(_PKG)

HEADER_CONFIG_KEY   = '{}.header_config'.format(_NS)
HEADER_BASE_CSS_KEY = '{}.header_base_css'.format(_NS)
HEADER_CSS_KEY      = '{}.header_css'.format(_NS)
FOOTER_CONFIG_KEY   = '{}.footer_config'.format(_NS)
FOOTER_BASE_CSS_KEY = '{}.footer_base_css'.format(_NS)
FOOTER_CSS_KEY      = '{}.footer_css'.format(_NS)

# Migracion lazy desde el modulo anterior (MF-Nav-Menu). Si la key nueva del
# header esta vacia, se lee la vieja como fallback (sin zconsole). En el primer
# PATCH del control panel los valores se escriben ya en las keys nuevas.
OLD_HEADER_CONFIG_KEY   = '{}.navigation.menu_config'.format(_PKG)
OLD_HEADER_BASE_CSS_KEY = '{}.navigation.menu_base_css'.format(_PKG)
OLD_HEADER_CSS_KEY      = '{}.navigation.menu_css'.format(_PKG)

DEFAULT_HEADER = [
    {'id': 'home', 'label': 'Home', 'type': 'plone', 'slug': ''},
]
DEFAULT_FOOTER = {
    'mode': 'columns',          # 'columns' | 'html'  (show_default tiene prioridad)
    'columns': [],
    'copyright': '',
    'legal_links': [],
    'html': '',                 # modo html: markup de un bloc de Blocs (scopeado en CSS)
    'show_default': True,
}

def _sanitize_css(v):
    """SC-4: neutraliza vectores de CSS injection en base_css/css.

    El CSS se renderiza en <style dangerouslySetInnerHTML>. Quitamos el cierre
    </style> (breakout) y construcciones activas (expression(), @import, url
    javascript:, behavior/-moz-binding).
    """
    if not v:
        return v
    v = re.sub(r'</\s*style', '', v, flags=re.IGNORECASE)            # breakout </style>
    v = re.sub(r'expression\s*\(', '', v, flags=re.IGNORECASE)        # IE expression()
    v = re.sub(r'(?:java|vb)script\s*:', '', v, flags=re.IGNORECASE)  # url(javascript:..)
    v = re.sub(r'@\s*import\b', '', v, flags=re.IGNORECASE)           # @import externo
    v = re.sub(r'(behavior|-moz-binding)\s*:', '', v, flags=re.IGNORECASE)
    return v


def _sanitize_html(html):
    """Sanitiza el HTML del footer (modo Blocs) con ALLOWLIST (fix SC-1).

    Solo un gestor (cmf.ManagePortal) puede escribir, pero como el markup se
    renderiza con dangerouslySetInnerHTML, se filtra por LISTA BLANCA usando el
    transform safe_html de Plone (portal_transforms -> text/x-html-safe), que es
    un sanitizador mantenido y basado en allowlist (no evadible como un regex).
    Si no estuviera disponible, cae a una lista negra REFORZADA como defensa en
    profundidad (cubre separadores no-espacio tipo <img/onerror=>, data:, vbscript:).
    """
    if not html:
        return html
    # 1) Allowlist nativo de Plone (defensa primaria).
    try:
        transforms = api.portal.get_tool('portal_transforms')
        result = transforms.convertTo('text/x-html-safe', html, mimetype='text/html')
        if result is not None:
            return result.getData()
    except Exception:
        logger.exception('[site-chrome] safe_html no disponible; usando fallback regex')
    # 2) Fallback lista negra reforzada (defensa en profundidad).
    html = re.sub(r'<script\b[^>]*>.*?</script\s*>', '', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<script\b[^>]*/?>', '', html, flags=re.IGNORECASE)
    # separador puede ser espacio O '/' (bypass <img/onerror=...>)
    html = re.sub(r'[/\s]on\w+\s*=\s*"[^"]*"', '', html, flags=re.IGNORECASE)
    html = re.sub(r"[/\s]on\w+\s*=\s*'[^']*'", '', html, flags=re.IGNORECASE)
    html = re.sub(r'[/\s]on\w+\s*=\s*[^\s>]+', '', html, flags=re.IGNORECASE)
    # esquemas peligrosos en href/src: javascript:, vbscript:, data:
    html = re.sub(r'(href|src)\s*=\s*(["\']?)\s*(?:java|vb)script:[^"\'>\s]*\2?',
                  r'\1=\2#\2', html, flags=re.IGNORECASE)
    html = re.sub(r'(href|src)\s*=\s*(["\']?)\s*data:[^"\'>\s]*\2?',
                  r'\1=\2#\2', html, flags=re.IGNORECASE)
    return html


def _ensure_record(key, value='', title='Site Chrome'):
    from plone.registry.interfaces import IRegistry
    from plone.registry import Record
    from plone.registry.field import Text
    from zope.component import getUtility
    registry = getUtility(IRegistry)
    if key not in registry.records:
        registry.records[key] = Record(Text(title=title), value)
    elif value:
        registry.records[key].value = value
    return registry


def _get_raw(key):
    try:
        return api.portal.get_registry_record(key)
    except Exception:
        return None


def _get_json(key, default, fallback_key=None):
    raw = _get_raw(key)
    if not raw and fallback_key:
        raw = _get_raw(fallback_key)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return default


def _get_text(key, fallback_key=None):
    raw = _get_raw(key)
    if not raw and fallback_key:
        raw = _get_raw(fallback_key)
    return raw or ''


def _set_text(key, value, title):
    try:
        api.portal.set_registry_record(key, value)
    except Exception:
        _ensure_record(key, value, title)


def _can_view(portal, slug):
    """¿El usuario actual tiene permiso View sobre la pagina del slug?
    - slug vacio (Home) -> siempre visible.
    - pagina inexistente -> visible (no rompemos anclas/enlaces externos).
    - pagina existente -> se respeta el permiso View de Plone (fuente de verdad).
    Degrada con seguridad: ante cualquier excepcion, no oculta nada.
    """
    if not slug:
        return True
    try:
        from AccessControl import getSecurityManager
        obj = portal.unrestrictedTraverse(slug.strip('/'), None)
        if obj is None:
            return True
        return bool(getSecurityManager().checkPermission('View', obj))
    except Exception:
        return True


class SiteChromeGet(Service):
    def reply(self):
        items = _get_json(HEADER_CONFIG_KEY, DEFAULT_HEADER, OLD_HEADER_CONFIG_KEY)
        # Ocultar items 'plone' cuya pagina destino el usuario no puede ver.
        # Los anclas/externos no se filtran (no hay pagina Plone que comprobar).
        try:
            portal = api.portal.get()
            items = [
                it for it in items
                if it.get('type') != 'plone' or _can_view(portal, it.get('slug', ''))
            ]
        except Exception:
            pass
        return {
            'header': {
                'items':    items,
                'base_css': _get_text(HEADER_BASE_CSS_KEY, OLD_HEADER_BASE_CSS_KEY),
                'css':      _get_text(HEADER_CSS_KEY, OLD_HEADER_CSS_KEY),
            },
            'footer': {
                'config':   _get_json(FOOTER_CONFIG_KEY, DEFAULT_FOOTER),
                'base_css': _get_text(FOOTER_BASE_CSS_KEY),
                'css':      _get_text(FOOTER_CSS_KEY),
            },
        }


class SiteChromePatch(Service):
    def reply(self):
        # CSRF (fix SC-2): plone.protect SOLO se desactiva cuando la request está
        # autenticada por Bearer (JWT) y NO trae cookie de sesión __ac. Un atacante
        # no puede forjar el header Authorization cross-site, así que ese camino no
        # tiene vector CSRF y el guardado por token (flujo Volto) sigue funcionando.
        # Si llega una cookie __ac (login clásico/ZMI), se MANTIENE plone.protect
        # para no abrir CSRF. La autorización cmf.ManagePortal (ZCML) se mantiene siempre.
        auth = self.request.getHeader('Authorization', '') or ''
        has_bearer = auth.lower().startswith('bearer ')
        has_session_cookie = bool(self.request.cookies.get('__ac'))
        if has_bearer and not has_session_cookie:
            try:
                from plone.protect.interfaces import IDisableCSRFProtection
                from zope.interface import alsoProvides
                alsoProvides(self.request, IDisableCSRFProtection)
            except Exception:
                pass

        body = self.request.get('BODY', b'')
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            self.request.response.setStatus(400)
            return {'error': 'JSON invalido: {}'.format(e)}

        section = data.get('section')
        if section not in ('header', 'footer'):
            self.request.response.setStatus(400)
            return {'error': "section debe ser 'header' o 'footer'"}

        base_css = data.get('base_css', None)
        css      = data.get('css', None)
        if base_css is not None:
            base_css = _sanitize_css(base_css)
        if css is not None:
            css = _sanitize_css(css)

        if section == 'header':
            items = data.get('items', DEFAULT_HEADER)
            _set_text(HEADER_CONFIG_KEY, json.dumps(items), 'Site Chrome Header Config')
            if base_css is not None:
                _set_text(HEADER_BASE_CSS_KEY, base_css, 'Site Chrome Header Base CSS')
            if css is not None:
                _set_text(HEADER_CSS_KEY, css, 'Site Chrome Header CSS')
        else:
            cfg = data.get('config', DEFAULT_FOOTER)
            if isinstance(cfg, dict) and cfg.get('html'):
                cfg['html'] = _sanitize_html(cfg['html'])
            _set_text(FOOTER_CONFIG_KEY, json.dumps(cfg), 'Site Chrome Footer Config')
            if base_css is not None:
                _set_text(FOOTER_BASE_CSS_KEY, base_css, 'Site Chrome Footer Base CSS')
            if css is not None:
                _set_text(FOOTER_CSS_KEY, css, 'Site Chrome Footer CSS')

        self.request.response.setStatus(204)
        return None
