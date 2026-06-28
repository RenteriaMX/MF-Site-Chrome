"""
Endpoint /@site-chrome  (Site Chrome Manager)
  GET   - retorna { header: {items, base_css, css},
                    footer: {config, base_css, css} }
  PATCH - body { section: 'header'|'footer', ... } guarda solo esa seccion.

Add-on collective.sitechrome (split del backend de MF-Site-Chrome): namespace fijo
y propio, perfiles GenericSetup install/uninstall, y endurecimiento de seguridad:
  - SC-1  HTML del footer sanitizado por ALLOWLIST (portal_transforms safe_html)
  - SC-2  CSRF: plone.protect solo se desactiva con Bearer sin cookie de sesion
  - SC-3  sanitizacion tambien AL LEER/RENDERIZAR (no solo al escribir), para que
          el sink dangerouslySetInnerHTML nunca reciba registry crudo escrito por
          otra via (ZMI, migracion, otro add-on)
  - SC-4  CSS injection: neutraliza </style>, expression(), javascript:, @import,
          behavior/-moz-binding
  - SC-5  url() externo en CSS neutralizado por defecto (anti beacon/exfil/tracking
          por un Manager rogue); se permite con SITE_CHROME_ALLOW_EXTERNAL_URL=1
  - SC-6  log de auditoria de cada PATCH (quien cambio header/footer)

Registry keys (namespace fijo collective.sitechrome.site_chrome):
  <ns>.header_config / header_base_css / header_css
  <ns>.footer_config / footer_base_css / footer_css
"""
import json
import logging
import os
from plone import api
from plone.restapi.services import Service

from collective.sitechrome.services.sanitizers import sanitize_css, sanitize_html

logger = logging.getLogger(__name__)

# Alias internos (los importa el viewlet y el setuphandlers).
_sanitize_css = sanitize_css
_sanitize_html = sanitize_html

# SC-6: log de auditoria dedicado (enrutable a su propio handler/archivo).
audit = logging.getLogger("collective.sitechrome.audit")

# Namespace propio y fijo del add-on.
_NS = 'collective.sitechrome.site_chrome'

HEADER_CONFIG_KEY   = '{}.header_config'.format(_NS)
HEADER_BASE_CSS_KEY = '{}.header_base_css'.format(_NS)
HEADER_CSS_KEY      = '{}.header_css'.format(_NS)
FOOTER_CONFIG_KEY   = '{}.footer_config'.format(_NS)
FOOTER_BASE_CSS_KEY = '{}.footer_base_css'.format(_NS)
FOOTER_CSS_KEY      = '{}.footer_css'.format(_NS)

# Migracion lazy desde una instalacion previa (el backend de MF-Site-Chrome vivia
# dentro del policy package, p.ej. namespace "ama.site_chrome"). Si se define el
# env SITE_CHROME_LEGACY_NS (p.ej. "ama"), las keys nuevas vacias leen las viejas
# como fallback. En un server nuevo no hay nada que migrar y queda inerte.
_LEGACY_NS = os.environ.get('SITE_CHROME_LEGACY_NS', '').strip()


def _legacy_key(suffix):
    return '{}.site_chrome.{}'.format(_LEGACY_NS, suffix) if _LEGACY_NS else None


OLD_HEADER_CONFIG_KEY   = _legacy_key('header_config')
OLD_HEADER_BASE_CSS_KEY = _legacy_key('header_base_css')
OLD_HEADER_CSS_KEY      = _legacy_key('header_css')

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


def _current_user_id():
    try:
        user = api.user.get_current()
        return (user.getId() if user else None) or '<anon>'
    except Exception:
        return '<unknown>'


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
        # SC-3: sanitizar AL LEER. El sink final es dangerouslySetInnerHTML, asi que
        # nunca devolvemos CSS/HTML crudo aunque el registry lo haya escrito otra via.
        footer_cfg = _get_json(FOOTER_CONFIG_KEY, DEFAULT_FOOTER)
        if isinstance(footer_cfg, dict) and footer_cfg.get('html'):
            footer_cfg['html'] = _sanitize_html(footer_cfg['html'])
        return {
            'header': {
                'items':    items,
                'base_css': _sanitize_css(_get_text(HEADER_BASE_CSS_KEY, OLD_HEADER_BASE_CSS_KEY)),
                'css':      _sanitize_css(_get_text(HEADER_CSS_KEY, OLD_HEADER_CSS_KEY)),
            },
            'footer': {
                'config':   footer_cfg,
                'base_css': _sanitize_css(_get_text(FOOTER_BASE_CSS_KEY)),
                'css':      _sanitize_css(_get_text(FOOTER_CSS_KEY)),
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

        # SC-6: pista de auditoria (quien cambio que seccion del chrome).
        audit.info('user=%s action=patch section=%s', _current_user_id(), section)

        self.request.response.setStatus(204)
        return None
