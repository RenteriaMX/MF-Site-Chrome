"""
Setup handlers for collective.sitechrome
"""

import logging

from plone import api
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

from collective.sitechrome.services import site_chrome as sc

logger = logging.getLogger("collective.sitechrome")

# (key, default_value) de las 6 keys del registry.
_RECORDS = [
    (sc.HEADER_CONFIG_KEY,   '[{"id":"home","label":"Home","type":"plone","slug":""}]'),
    (sc.HEADER_BASE_CSS_KEY, ''),
    (sc.HEADER_CSS_KEY,      ''),
    (sc.FOOTER_CONFIG_KEY,   '{"mode":"columns","columns":[],"copyright":"","legal_links":[],"html":"","show_default":true}'),
    (sc.FOOTER_BASE_CSS_KEY, ''),
    (sc.FOOTER_CSS_KEY,      ''),
]


@implementer(INonInstallable)
class HiddenProfiles:
    def getNonInstallableProfiles(self):
        return [
            "collective.sitechrome:uninstall",
        ]

    def getNonInstallableProducts(self):
        return []


def post_install(context):
    """Crea las 6 registry keys (si faltan) y migra valores de una instalacion
    previa (env SITE_CHROME_LEGACY_NS, p.ej. 'ama') cuando la key nueva esta vacia."""
    suffixes = [
        'header_config', 'header_base_css', 'header_css',
        'footer_config', 'footer_base_css', 'footer_css',
    ]
    for (key, default), suffix in zip(_RECORDS, suffixes):
        existing = sc._get_raw(key)
        if existing:
            continue
        legacy_val = None
        legacy_key = sc._legacy_key(suffix)
        if legacy_key:
            legacy_val = sc._get_raw(legacy_key)
            if legacy_val:
                logger.info("[site-chrome] migrando %s desde %s", key, legacy_key)
        sc._set_text(key, legacy_val or default, 'Site Chrome')
    logger.info("[site-chrome] registry keys verificadas (%s.*)", sc._NS)


def uninstall(context):
    """Uninstall handler: elimina las 6 registry keys del Site Chrome."""
    try:
        from plone.registry.interfaces import IRegistry
        from zope.component import getUtility
        registry = getUtility(IRegistry)
    except Exception:
        logger.warning("[site-chrome] registry no disponible en uninstall")
        return
    removed = 0
    for key, _default in _RECORDS:
        if key in registry.records:
            del registry.records[key]
            removed += 1
    logger.info("[site-chrome] %d registry key(s) eliminadas.", removed)
