"""
Sanitizadores puros del Site Chrome (sin dependencias duras de Plone a nivel
modulo, para que sean testeables con pytest plano).

  - sanitize_css   SC-4 (CSS injection) + SC-5 (url() externo / exfil)
  - sanitize_html  SC-1 (allowlist via portal_transforms, fallback blocklist)
"""
import logging
import os
import re

logger = logging.getLogger("collective.sitechrome")

# SC-5: permitir url() externo en CSS solo si el operador lo habilita.
ALLOW_EXTERNAL_URL = os.environ.get(
    'SITE_CHROME_ALLOW_EXTERNAL_URL', ''
).strip() in ('1', 'true', 'True')

# url( [comillas?] (http(s):)?// ... ) -> peticion de red saliente (beacon/exfil).
_EXTERNAL_URL_RE = re.compile(r'url\(\s*[\'"]?\s*(?:https?:)?//[^)]*\)', re.IGNORECASE)


def sanitize_css(v, allow_external_url=None):
    """SC-4/SC-5: neutraliza CSS injection y exfiltracion en CSS.

    El CSS se renderiza en <style dangerouslySetInnerHTML> (Volto) y en
    <style tal:content> (viewlet clasico). Se quita el cierre </style>
    (breakout) y construcciones activas (expression(), @import, url
    javascript:, behavior/-moz-binding). Ademas (SC-5) se neutraliza url()
    externo para que un Manager no pueda insertar beacons/tracking.
    """
    if not v:
        return v
    if allow_external_url is None:
        allow_external_url = ALLOW_EXTERNAL_URL
    v = re.sub(r'</\s*style', '', v, flags=re.IGNORECASE)            # breakout </style>
    v = re.sub(r'expression\s*\(', '', v, flags=re.IGNORECASE)        # IE expression()
    v = re.sub(r'(?:java|vb)script\s*:', '', v, flags=re.IGNORECASE)  # url(javascript:..)
    v = re.sub(r'@\s*import\b', '', v, flags=re.IGNORECASE)           # @import externo
    v = re.sub(r'(behavior|-moz-binding)\s*:', '', v, flags=re.IGNORECASE)
    if not allow_external_url:
        def _neutralize(m):
            logger.warning('[site-chrome] url() externo neutralizado en CSS: %s', m.group(0)[:80])
            return 'url(about:blank)'
        v = _EXTERNAL_URL_RE.sub(_neutralize, v)
    return v


# ── HTML del footer (modo Blocs): allowlist + preservacion de iconos/imagenes ──

# Bloques de iconos (Blocs): <blocsicon>..</blocsicon> y <svg>..</svg>.
_ICON_BLOCK_RE = re.compile(
    r'<blocsicon\b[^>]*>.*?</blocsicon\s*>|<svg\b[^>]*>.*?</svg\s*>',
    re.IGNORECASE | re.DOTALL,
)
# Elementos SVG que pueden ejecutar/cargar recursos: si aparecen, NO se protege.
_ICON_NASTY = (
    '<script', '<foreignobject', '<iframe', '<embed', '<object',
    '<animate', '<set', '<use', '<image', '<a ', '<a>', '<handler', '<listener',
)


def _icon_is_safe(block):
    """True si el bloque de icono SVG no trae vectores activos (allowlist estricta:
    solo geometria tipo <path>; cualquier elemento/atributo ejecutable lo descarta)."""
    low = block.lower()
    if any(tok in low for tok in _ICON_NASTY):
        return False
    if re.search(r'\son\w+\s*=', block, re.IGNORECASE):          # manejadores on*=
        return False
    if re.search(r'(?:java|vb)script\s*:|data\s*:', block, re.IGNORECASE):
        return False
    return True


# <img> con la imagen incrustada como data: URI (bloc2footer inline_images).
_DATA_IMG_RE = re.compile(r'<img\b[^>]*\bsrc\s*=\s*"data:image/[^"]*"[^>]*>',
                          re.IGNORECASE)
# Solo raster inerte: png/jpeg/gif/webp. SVG queda fuera (data:image/svg+xml
# puede traer script si se trata como documento).
_IMG_SAFE_MIME = (
    'data:image/png;', 'data:image/jpeg;', 'data:image/jpg;',
    'data:image/gif;', 'data:image/webp;',
)


def _img_is_safe(tag):
    """True si el <img> incrusta una imagen raster inerte como data: URI y no
    trae manejadores on*= ni otro esquema activo. Asi se preserva tal cual sin
    que el allowlist (que borra data:) elimine la imagen del footer."""
    m = re.search(r'src\s*=\s*"(data:image/[^";]+;)', tag, re.IGNORECASE)
    if not m or not m.group(1).lower().startswith(_IMG_SAFE_MIME):
        return False
    if re.search(r'\son\w+\s*=', tag, re.IGNORECASE):            # manejadores on*=
        return False
    # ningun otro esquema activo en el resto del tag (otro atributo)
    rest = re.sub(r'src\s*=\s*"data:image/[^"]*"', '', tag, count=1, flags=re.IGNORECASE)
    if re.search(r'(?:java|vb)script\s*:|data\s*:', rest, re.IGNORECASE):
        return False
    return True


def _scrub_allowlist(html):
    """SC-1: allowlist de Plone (safe_html) con fallback a lista negra reforzada.

    El import de plone.api es LAZY para no acoplar el modulo a Plone en tiempo
    de import (tests). Sin Plone, cae al fallback blocklist.
    """
    # 1) Allowlist nativo de Plone (defensa primaria).
    try:
        from plone import api
        transforms = api.portal.get_tool('portal_transforms')
        result = transforms.convertTo('text/x-html-safe', html, mimetype='text/html')
        if result is not None:
            return result.getData()
    except Exception:
        logger.debug('[site-chrome] safe_html no disponible; usando fallback regex')
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


def sanitize_html(html):
    """SC-1/SC-1b/SC-1c: sanitiza el HTML del footer (modo Blocs) con ALLOWLIST,
    preservando iconos SVG limpios (SC-1b) e imagenes raster inertes data: (SC-1c).

    El allowlist safe_html de Plone elimina <svg>/<path>/<blocsicon> y data: (no
    estan en su lista) y ademas baja 'viewBox' a minusculas -> rompe iconos. Por
    eso, antes de pasar por safe_html, se EXTRAEN los bloques de icono e imagenes
    data: que NO traen vectores activos, se sustituyen por un marcador de texto,
    se corre el allowlist sobre el resto, y se reinyecta lo validado TAL CUAL. Un
    bloque sospechoso no se protege: cae al allowlist y se elimina.
    """
    if not html:
        return html
    kept = []

    def _stash_icon(m):
        block = m.group(0)
        if _icon_is_safe(block):
            kept.append(block)
            return 'SCKEEP%dENDSCKEEP' % (len(kept) - 1)     # marcador de texto plano
        return ''                                            # sospechoso: se descarta

    def _stash_img(m):
        tag = m.group(0)
        if _img_is_safe(tag):
            kept.append(tag)
            return 'SCKEEP%dENDSCKEEP' % (len(kept) - 1)     # imagen raster inerte
        return tag       # no es data-img seguro: que el allowlist lo procese normal

    protected = _ICON_BLOCK_RE.sub(_stash_icon, html)
    protected = _DATA_IMG_RE.sub(_stash_img, protected)
    cleaned = _scrub_allowlist(protected)
    cleaned = re.sub(r'SCKEEP(\d+)ENDSCKEEP',
                     lambda m: kept[int(m.group(1))], cleaned)
    return cleaned
