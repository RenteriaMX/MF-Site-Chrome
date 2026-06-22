#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bloc2footer.py — Convierte un export de Blocs (https://blocsapp.com/) en el
payload que Site Chrome guarda para un footer en modo HTML.

Entrada:  carpeta export de Blocs (index.html + style.css + css/bootstrap.min.css)
Salida:   { "html", "base_css", "css" } scopeado bajo un selector raiz,
          listo para PATCH /@site-chrome  (section=footer, mode=html).

Diseno:
  - HTML: extrae los bloques de contenido (<!-- bloc-N --> ... END) y descarta
    el scaffolding de pagina (preloader, scrollToTop, blocs vacios).
  - CSS: toma SOLO las reglas cuyos selectores usan clases presentes en el HTML
    (o son selectores de elemento permitidos / :root). Asi nunca embarcamos los
    228K de Bootstrap completos: solo el subset que el bloc realmente usa.
  - Scoping: cada selector se prefija con el wrapper (.sc-footer-blocs) para que
    el diseno de Blocs quede aislado y no contamine el resto de Volto.
  - Split en dos capas (calza con las registry keys footer_base_css/footer_css):
      * css       = seccion "Custom Styling" de style.css del usuario
      * base_css  = framework Blocs + colour swatches + subset Bootstrap
  - Normaliza el token interno 'blocsapp-transition' -> 'transition'.

Uso:
  python3 tools/bloc2footer.py Web
  python3 tools/bloc2footer.py Web --scope .sc-footer-blocs --bloc bloc-1 \
      --out footer.json --preview footer.preview.html
"""

import argparse
import json
import os
import re
import sys

# Elementos cuyo styling base si queremos arrastrar (font-family, etc.).
ALLOWED_ELEMENTS = {
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'label', 'button',
    'svg', 'img', 'ul', 'ol', 'li', 'span', 'strong', 'em', 'small',
}

# Selectores de scaffolding de pagina que NUNCA queremos en un footer.
SCAFFOLD_TOKENS = {
    'page-preloader', 'preloader-complete', 'page-container', 'scrollToTop',
    'showScrollTop', 'scroll-to-top-btn-icon', 'navbar', 'navbar-toggler',
    'navbar-toggle', 'navbar-dark', 'svg-menu-icon', 'menu-icon-thin-bars',
    'menu-icon-thick-bars', 'menu-icon-rounded-bars', 'menu-icon-filled',
    'dropdown-menu', 'carousel', 'card-columns', 'blocsapp-device-iphone5',
    'close-lightbox', 'scroll-fx-lock-init',
}


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

def extract_blocs(html, wanted=None):
    """Devuelve el HTML de los bloques de contenido.

    Blocs envuelve cada bloque en  <!-- bloc-N --> ... <!-- bloc-N END -->.
    Si `wanted` se da (lista de ids), solo esos; si no, todos los bloc-N con
    contenido textual (descarta bloc-0 vacio y el boton scrollToTop).
    """
    pat = re.compile(
        r'<!--\s*(bloc-\d+)\s*-->(.*?)<!--\s*\1\s*END\s*-->',
        re.DOTALL | re.IGNORECASE,
    )
    out = []
    for m in pat.finditer(html):
        bloc_id, body = m.group(1), m.group(2)
        if wanted and bloc_id not in wanted:
            continue
        # descarta bloques sin texto visible (canvas vacio)
        text = re.sub(r'<[^>]+>', '', body)
        if not wanted and not text.strip():
            continue
        out.append(body.strip())
    return '\n'.join(out).strip()


def used_classes(html):
    classes = set()
    for m in re.finditer(r'class\s*=\s*"([^"]*)"', html):
        for c in m.group(1).split():
            classes.add(c)
    return classes


# Tags HTML estandar que NO tratamos como "elemento permitido" sueltos: evita
# arrastrar reglas genericas de layout de pagina (div/span/section/...).
STANDARD_HTML = {
    'html', 'body', 'div', 'span', 'section', 'article', 'header', 'footer',
    'nav', 'main', 'aside', 'figure', 'figcaption', 'table', 'thead', 'tbody',
    'tr', 'td', 'th', 'form', 'input', 'select', 'option', 'textarea',
    'br', 'hr', 'path', 'g', 'defs', 'use',
}


def custom_tags(html):
    """Tags no estandar usados en el HTML (custom elements de Blocs, p.ej.
    <blocsicon>). Sus reglas (blocsicon{}, blocsicon svg{}) deben conservarse o
    los SVG sin width/height se inflan. Excluye los tags estructurales."""
    tags = {m.lower() for m in re.findall(r'<([a-zA-Z][a-zA-Z0-9-]*)', html)}
    return {t for t in tags if t not in STANDARD_HTML}


# --------------------------------------------------------------------------- #
# CSS — tokenizer consciente de llaves / strings / comentarios
# --------------------------------------------------------------------------- #

def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)


def split_top_level(css):
    """Parte un stylesheet en una lista de nodos top-level.

    Cada nodo es: ('rule', prelude, body) | ('at', prelude, body) |
                  ('stmt', text, None)   (ej. @import ...;)
    `body` es el contenido crudo entre llaves (puede tener reglas anidadas).
    """
    nodes = []
    i, n, buf = 0, len(css), ''
    while i < n:
        c = css[i]
        if c == '{':
            prelude = buf.strip()
            buf = ''
            depth, j = 1, i + 1
            while j < n and depth > 0:
                if css[j] == '{':
                    depth += 1
                elif css[j] == '}':
                    depth -= 1
                j += 1
            body = css[i + 1:j - 1]
            kind = 'at' if prelude.startswith('@') else 'rule'
            nodes.append((kind, prelude, body))
            i = j
        elif c == ';' and buf.strip().startswith('@'):
            nodes.append(('stmt', buf.strip() + ';', None))
            buf = ''
            i += 1
        elif c == '}':
            i += 1  # llave huerfana
        else:
            buf += c
            i += 1
    if buf.strip():
        nodes.append(('stmt', buf.strip(), None))
    return nodes


def selector_classes(sel):
    return set(re.findall(r'\.([A-Za-z0-9_-]+)', sel))


def is_pure_element(sel, allowed=ALLOWED_ELEMENTS):
    s = sel.strip()
    if not s or any(ch in s for ch in '.#[:*>+~'):
        return False
    return all(tok in allowed for tok in re.split(r'\s+', s))


def keep_selector(sel, used, allowed=ALLOWED_ELEMENTS):
    s = sel.strip()
    if not s:
        return False
    if s in (':root',):
        return True
    cls = selector_classes(s)
    if cls & SCAFFOLD_TOKENS:
        return False
    if cls:
        return bool(cls & used)
    # sin clases: solo elementos permitidos (font-family base, custom de Blocs, etc.)
    return is_pure_element(s, allowed)


def scope_selector(sel, scope):
    s = sel.strip()
    if s == ':root':
        return scope                      # vars CSS sobre el wrapper
    if s in ('html', 'body'):
        return None                       # estilos de pagina: descartar
    if s.startswith(scope):
        return s
    return scope + ' ' + s


def scope_rule(prelude, body, scope, used, allowed=ALLOWED_ELEMENTS):
    """Filtra+scopea una regla simple. Devuelve texto o '' si se descarta."""
    sels = [p for p in prelude.split(',') if p.strip()]
    kept = [s for s in sels if keep_selector(s, used, allowed)]
    if not kept:
        return ''
    scoped = []
    for s in kept:
        ss = scope_selector(s, scope)
        if ss:
            scoped.append(ss)
    if not scoped:
        return ''
    body = body.strip().replace('blocsapp-transition', 'transition')
    return '%s{%s}' % (','.join(scoped), body)


def scope_stylesheet(css, scope, used, allowed=ALLOWED_ELEMENTS):
    """Aplica filtro+scoping a un stylesheet completo (incluye @media)."""
    out = []
    for kind, prelude, body in split_top_level(strip_comments(css)):
        if kind == 'rule':
            r = scope_rule(prelude, body, scope, used, allowed)
            if r:
                out.append(r)
        elif kind == 'at':
            head = prelude.split('(')[0].strip().split()[0].lower()
            if head in ('@media', '@supports'):
                inner = scope_stylesheet(body, scope, used, allowed)
                if inner.strip():
                    out.append('%s{%s}' % (prelude, inner))
            # @keyframes / @font-face / otros: se descartan (page FX)
        # 'stmt' (@import/@charset): se descartan
    return '\n'.join(out)


_VAR_USE = re.compile(r'var\(\s*(--[A-Za-z0-9_-]+)')
_VAR_DEF = re.compile(r'^\s*(--[A-Za-z0-9_-]+)\s*:(.*)$', re.DOTALL)


def collect_var_defs(css):
    """Mapa {nombre_var: valor} de todas las declaraciones --x:... en el CSS."""
    defs = {}
    for kind, prelude, body in split_top_level(css):
        if kind == 'at':
            defs.update(collect_var_defs(body))
        elif kind == 'rule':
            for decl in body.split(';'):
                m = _VAR_DEF.match(decl)
                if m:
                    defs[m.group(1)] = m.group(2)
    return defs


def real_var_usages(css):
    """var(--x) usados en valores de propiedades reales (NO dentro de otra --x:).

    Asi la semilla no cuenta referencias que solo viven dentro de definiciones
    de variables que a su vez estan muertas.
    """
    used = set()
    for kind, prelude, body in split_top_level(css):
        if kind == 'at':
            used |= real_var_usages(body)
        elif kind == 'rule':
            for decl in body.split(';'):
                if _VAR_DEF.match(decl):
                    continue  # es una definicion --x:...; no cuenta como uso
                used.update(_VAR_USE.findall(decl))
        else:
            used.update(_VAR_USE.findall(prelude))
    return used


def referenced_vars(html, custom_css, base_css):
    """Variables a conservar: usos reales + expansion transitiva por definicion.

    Se re-deriva del export en cada corrida; nada queda hardcodeado. Un footer
    nuevo que use otras variables las conserva automaticamente.
    """
    used = set(_VAR_USE.findall(html))
    used |= set(_VAR_USE.findall(custom_css))
    used |= real_var_usages(base_css)
    defs = collect_var_defs(base_css)
    changed = True
    while changed:
        changed = False
        for name, val in defs.items():
            if name in used:
                for ref in _VAR_USE.findall(val):
                    if ref not in used:
                        used.add(ref)
                        changed = True
    return used


def trim_unused_vars(css, used):
    """Elimina declaraciones --x:... cuyo nombre no esta en `used`.

    Solo toca reglas que definen variables; las demas quedan intactas.
    """
    out = []
    for kind, prelude, body in split_top_level(css):
        if kind == 'at':
            inner = trim_unused_vars(body, used)
            if inner.strip():
                out.append('%s{%s}' % (prelude, inner))
        elif kind == 'rule':
            if '--' not in body:
                out.append('%s{%s}' % (prelude, body))
                continue
            kept = []
            for decl in body.split(';'):
                m = _VAR_DEF.match(decl)
                if m and m.group(1) not in used:
                    continue
                if decl.strip():
                    kept.append(decl.strip())
            if kept:
                out.append('%s{%s}' % (prelude, ';'.join(kept) + ';'))
        else:
            out.append(prelude)
    return '\n'.join(out)


def split_sections(style_css):
    """Parte style.css de Blocs por sus banners  /* = NOMBRE ... */.

    Devuelve dict {nombre_lower: css}. El texto antes del primer banner va a
    la clave '' (framework base de Blocs).
    """
    banner = re.compile(r'/\*\s*=\s*([^\n]+?)\s*\n-+\s*\*/', re.DOTALL)
    sections = {}
    last_name, last_end = '', 0
    for m in banner.finditer(style_css):
        sections[last_name.strip().lower()] = \
            sections.get(last_name.strip().lower(), '') + style_css[last_end:m.start()]
        last_name, last_end = m.group(1), m.end()
    sections[last_name.strip().lower()] = \
        sections.get(last_name.strip().lower(), '') + style_css[last_end:]
    return sections


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def convert(export_dir, scope, wanted_blocs):
    def read(rel):
        p = os.path.join(export_dir, rel)
        if not os.path.exists(p):
            return ''
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    index_html = read('index.html')
    if not index_html:
        raise SystemExit('No se encontro index.html en %s' % export_dir)
    style_css = read('style.css')          # crudo: las secciones se detectan por banners /* = .. */
    bootstrap_css = read('css/bootstrap.min.css')

    html = extract_blocs(index_html, wanted_blocs)
    if not html:
        raise SystemExit('No se extrajo ningun bloque de contenido del HTML.')
    used = used_classes(html)
    # Elementos custom de Blocs (p.ej. <blocsicon>) usados: conservar sus reglas
    # sueltas (blocsicon{}, blocsicon svg{}) o los SVG sin width/height se inflan.
    allowed = ALLOWED_ELEMENTS | custom_tags(html)

    # --- CSS custom (seccion "Custom Styling" del usuario) -> footer_css
    sections = split_sections(style_css)
    custom_src = sections.get('custom styling', '')
    custom_css = scope_stylesheet(custom_src, scope, used, allowed)

    # --- base_css = todo lo demas de style.css (sin custom) + subset bootstrap
    base_src_parts = [v for k, v in sections.items() if k != 'custom styling']
    base_from_style = scope_stylesheet('\n'.join(base_src_parts), scope, used, allowed)
    base_from_bootstrap = scope_stylesheet(bootstrap_css, scope, used, allowed)

    preamble = (
        '%s *,%s *::before,%s *::after{box-sizing:border-box;}'
        % (scope, scope, scope)
    )
    base_css = '\n'.join(
        x for x in [preamble, base_from_bootstrap, base_from_style] if x.strip()
    )

    # Trim dinamico de variables CSS no usadas (referencia + transitivo).
    used_vars = referenced_vars(html, custom_css, base_css)  # usos reales + transitivo
    base_css = trim_unused_vars(base_css, used_vars)

    return {
        'html': html,
        'base_css': base_css,
        'css': custom_css,
        '_used_classes': sorted(used),
    }


def main():
    ap = argparse.ArgumentParser(description='Blocs export -> Site Chrome footer payload')
    ap.add_argument('export_dir', help='Carpeta del export de Blocs (con index.html)')
    ap.add_argument('--scope', default='.sc-footer-blocs', help='Selector raiz de scoping')
    ap.add_argument('--bloc', action='append', default=None,
                    help='ID de bloc a incluir (repetible). Default: todos con contenido.')
    ap.add_argument('--out', default=None, help='Escribe el JSON {html,base_css,css} (para API/curl)')
    ap.add_argument('--preview', default=None,
                    help='Escribe el HTML autonomo (preview + datos incrustados). '
                         'Default si no se pasa --out ni --preview: footer.html')
    args = ap.parse_args()

    # Artefacto unico por defecto: un solo .html que sirve para ver Y para importar
    # (arrastrandolo a la dropzone del control panel). Sin necesidad de zip.
    if not args.out and not args.preview:
        args.preview = 'footer.html'

    result = convert(args.export_dir, args.scope, args.bloc)

    sys.stderr.write(
        '[bloc2footer] html=%dB  base_css=%dB  css=%dB  clases_usadas=%d\n'
        % (len(result['html']), len(result['base_css']),
           len(result['css']), len(result['_used_classes']))
    )

    payload = {k: v for k, v in result.items() if not k.startswith('_')}

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        sys.stderr.write('[bloc2footer] JSON -> %s\n' % args.out)

    if args.preview:
        scope_class = args.scope.lstrip('.')
        # Datos incrustados: el control panel los lee del <script> (split limpio
        # base_css/css). Escapamos </ para no cerrar el <script> por accidente.
        data_json = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
        html_doc = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<script id="sc-footer-data" type="application/json">%s</script>'
            '<style>\n%s\n%s\n</style></head><body>'
            '<div class="%s">%s</div></body></html>'
            % (data_json, payload['base_css'], payload['css'], scope_class, payload['html'])
        )
        with open(args.preview, 'w', encoding='utf-8') as f:
            f.write(html_doc)
        sys.stderr.write('[bloc2footer] artefacto -> %s  (abrir para ver, arrastrar para importar)\n'
                         % args.preview)


if __name__ == '__main__':
    main()
