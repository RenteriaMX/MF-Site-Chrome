# -*- coding: utf-8 -*-
from plone.app.layout.viewlets import common
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
import logging

from collective.sitechrome.services.site_chrome import (
    HEADER_BASE_CSS_KEY,
    HEADER_CSS_KEY,
    FOOTER_BASE_CSS_KEY,
    FOOTER_CSS_KEY,
    _sanitize_css,
)

logger = logging.getLogger(__name__)

CSS_KEYS = [
    HEADER_BASE_CSS_KEY,
    HEADER_CSS_KEY,
    FOOTER_BASE_CSS_KEY,
    FOOTER_CSS_KEY,
]


class SiteChromeCSSViewlet(common.ViewletBase):
    """Inyecta el CSS de header + footer del Site Chrome en el <head>.

    El template usa tal:content (escapa HTML) y ademas se aplica _sanitize_css
    (SC-3/SC-4/SC-5) para que el CSS inyectado nunca sea registry crudo.
    """

    index = ViewPageTemplateFile('site_chrome_viewlet.pt')

    def update(self):
        super().update()
        self.chrome_css = ''
        try:
            from plone import api
            parts = []
            for key in CSS_KEYS:
                val = api.portal.get_registry_record(key) or ''
                val = _sanitize_css(val)
                if val and val.strip():
                    parts.append(val)
            if parts:
                self.chrome_css = '\n'.join(parts)
        except Exception:
            logger.debug('SiteChromeCSSViewlet: registry keys not found yet')
