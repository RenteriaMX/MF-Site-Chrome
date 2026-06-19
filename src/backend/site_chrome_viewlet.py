# -*- coding: utf-8 -*-
from plone.app.layout.viewlets import common
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
import logging

logger = logging.getLogger(__name__)

_NS = '%%BACKEND_NAME%%.site_chrome'
CSS_KEYS = [
    '{}.header_base_css'.format(_NS),
    '{}.header_css'.format(_NS),
    '{}.footer_base_css'.format(_NS),
    '{}.footer_css'.format(_NS),
]


class SiteChromeCSSViewlet(common.ViewletBase):
    """Inyecta el CSS de header + footer del Site Chrome en el <head>."""

    index = ViewPageTemplateFile('site_chrome_viewlet.pt')

    def update(self):
        super().update()
        self.chrome_css = ''
        try:
            from plone import api
            parts = []
            for key in CSS_KEYS:
                val = api.portal.get_registry_record(key) or ''
                if val.strip():
                    parts.append(val)
            if parts:
                self.chrome_css = '\n'.join(parts)
        except Exception:
            logger.debug('SiteChromeCSSViewlet: registry keys not found yet')
