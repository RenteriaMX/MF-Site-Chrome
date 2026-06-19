/**
 * SiteChromeControlPanel v1.0
 * Seccion superior:  Header | Footer
 *   Header → Items · Estilos base · CSS Custom   (= nav menu, sin cambios)
 *   Footer → Columnas · Estilos base · CSS
 * Lee /@site-chrome (GET) y guarda por seccion (PATCH {section, ...}).
 * Todo se aplica sin rebuild.
 */
import React, { useState, useEffect, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { getSiteChrome, patchSiteChrome } from '../siteChromeSSR';
import { Button, Form, Input, Select, Message, Icon, Tab } from 'semantic-ui-react';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Link, useLocation } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { defineMessages, useIntl } from 'react-intl';
import { useClient } from '@plone/volto/hooks/client/useClient';
import VIcon from '@plone/volto/components/theme/Icon/Icon';
import Toolbar from '@plone/volto/components/manage/Toolbar/Toolbar';
import backSVG from '@plone/volto/icons/back.svg';
import './SiteChromeControlPanel.css';

const messages = defineMessages({
  back: { id: 'Back', defaultMessage: 'Back' },
});

const uid = () => Math.random().toString(36).slice(2, 8);

const TYPE_OPTIONS = [
  { key: 'anchor', value: 'anchor', text: 'Ancla - scroll en la misma pagina (#seccion)' },
  { key: 'plone',  value: 'plone',  text: 'Pagina Plone - enlace a una pagina del sitio'  },
];
const EMPTY_FORM = { label: '', type: 'anchor', href: '#', anchorPage: '/', slug: '', cssClass: '', noFatMenu: false };

const DEFAULT_BASE_CSS = `/* ═══════════════════════════════════════════════════════
   ESTILOS BASE DEL FAT MENU
   Edita aqui para cambiar colores, sombras, tipografia.
   Guarda → cambio instantaneo sin rebuild.
   ═══════════════════════════════════════════════════════ */

/* ── Estilo base del panel ───────────────────────────── */
.nm-fat-panel {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  overflow: hidden;
}

.nm-fat-trigger:hover,
.nm-fat-trigger.active { opacity: 0.85; }

.nm-fat-inner { padding: 0.5rem 0; }

.nm-fat-header {
  display: block;
  padding: 0.6rem 1rem;
  font-weight: 700;
  font-size: 0.9rem;
  color: #333;
  text-decoration: none;
  border-bottom: 1px solid #eee;
  margin-bottom: 0.3rem;
}
.nm-fat-header:hover { background: #f5f5f5; color: #000; }

.nm-fat-list a {
  padding: 0.5rem 1rem;
  color: #444;
}
.nm-fat-list a:hover { background: #f0f4ff; color: #222; }

.nm-sub-title { font-size: 0.9rem; font-weight: 500; }
.nm-sub-arrow { color: #aaa; font-weight: 300; }
.nm-sub-desc  { display: block; font-size: 0.78rem; color: #888; margin-top: 0.15rem; line-height: 1.3; }


/* ── Preset: nm-apple (frosted glass, ancho completo) ─ */
.nm-fat-panel.nm-apple {
  position: fixed;
  left: 0; right: 0; top: auto;
  min-width: 100vw;
  border-radius: 0;
  border-left: none; border-right: none;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  box-shadow: 0 12px 32px rgba(0,0,0,0.08);
}
.nm-fat-panel.nm-apple .nm-fat-inner {
  max-width: 980px;
  margin: 0 auto;
  padding: 1.5rem 2rem;
  display: flex;
  gap: 3rem;
  align-items: flex-start;
}
.nm-fat-panel.nm-apple .nm-fat-header {
  border: none; font-size: 1.1rem; color: #1d1d1f; min-width: 160px;
}
.nm-fat-panel.nm-apple .nm-fat-list {
  display: flex; flex-wrap: wrap; gap: 0.2rem 2rem; flex: 1;
}
.nm-fat-panel.nm-apple .nm-fat-list li { min-width: 160px; }
.nm-fat-panel.nm-apple .nm-fat-list a  { padding: 0.4rem 0.5rem; border-radius: 4px; }
.nm-fat-panel.nm-apple .nm-fat-list a:hover { background: rgba(0,0,0,0.04); }
.nm-fat-panel.nm-apple .nm-sub-title { color: #1d1d1f; font-size: 0.85rem; font-weight: 400; }
.nm-fat-panel.nm-apple .nm-sub-desc  { color: #6e6e73; font-size: 0.75rem; }


/* ── Preset: nm-dark ──────────────────────────────────── */
.nm-fat-panel.nm-dark {
  background: #1c1c1e;
  border-color: #3a3a3c;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
}
.nm-fat-panel.nm-dark .nm-fat-header,
.nm-fat-panel.nm-dark .nm-sub-title { color: #f5f5f7; }
.nm-fat-panel.nm-dark .nm-sub-arrow { color: #6e6e73; }
.nm-fat-panel.nm-dark .nm-sub-desc  { color: #98989d; }
.nm-fat-panel.nm-dark .nm-fat-list a:hover  { background: rgba(255,255,255,0.06); }
.nm-fat-panel.nm-dark .nm-fat-header:hover  { background: rgba(255,255,255,0.04); }


/* ── Preset: nm-wide (ancho completo simple) ──────────── */
.nm-fat-panel.nm-wide {
  position: fixed;
  left: 0; right: 0;
  min-width: 100vw;
  border-radius: 0;
  border-left: none; border-right: none;
}
.nm-fat-panel.nm-wide .nm-fat-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem 2rem;
  display: flex; gap: 2rem; flex-wrap: wrap;
}
.nm-fat-panel.nm-wide .nm-fat-list {
  display: flex; flex-wrap: wrap; gap: 0 2rem; flex: 1;
}


/* ── Preset: nm-minimal ───────────────────────────────── */
.nm-fat-panel.nm-minimal {
  border: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  border-radius: 4px;
}
.nm-fat-panel.nm-minimal .nm-fat-header { display: none; }
.nm-fat-panel.nm-minimal .nm-fat-list a { padding: 0.35rem 0.75rem; font-size: 0.88rem; }
.nm-fat-panel.nm-minimal .nm-sub-arrow  { display: none; }`;

const DEFAULT_FOOTER_BASE_CSS = `/* ═══════════════════════════════════════════════════════
   ESTILOS BASE DEL FOOTER
   Guarda → cambio instantaneo sin rebuild.
   ═══════════════════════════════════════════════════════ */
.sc-footer {
  background: #5a6b8c;
  color: #fff;
  padding: 1rem 0 2rem;
}
.sc-footer a { color: #fff; text-decoration: underline; }
.sc-footer a:hover { opacity: 0.85; }
.sc-footer-col-title { color: #fff; }
.sc-footer-bottom { font-size: 0.85rem; opacity: 0.95; }`;

/* ─────────────────────── HEADER (nav menu) ─────────────────────── */

const SortableItem = ({ item, onEdit, onDelete, onCss, cssOpen }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id });
  const style = {
    transform: CSS.Transform.toString(transform), transition,
    opacity: isDragging ? 0.4 : 1,
    boxShadow: isDragging ? '0 4px 12px rgba(0,0,0,0.15)' : 'none',
    zIndex: isDragging ? 999 : 'auto',
  };
  return (
    <div ref={setNodeRef} style={style} className="nm-item">
      <span className="nm-handle" {...attributes} {...listeners} title="Arrastrar para reordenar">
        <Icon name="bars" />
      </span>
      <span className="nm-label">{item.label}</span>
      <span className="nm-meta">
        {item.type === 'anchor'
          ? <><Icon name="anchor" />{item.href}</>
          : <><Icon name="linkify" />{item.slug || '(raiz)'}{item.noFatMenu ? ' (sin submenu)' : ''}</>}
        {item.cssClass && <span className="nm-css-badge"> {item.cssClass}</span>}
      </span>
      <div className="nm-actions">
        <Button size="mini" color={cssOpen ? 'teal' : 'grey'} onClick={() => onCss(item)} title="CSS Class">&#127912;</Button>
        <Button size="mini" color="blue"  onClick={() => onEdit(item)}>&#9998;</Button>
        <Button size="mini" color="red"   onClick={() => onDelete(item.id)}>&#10005;</Button>
      </div>
    </div>
  );
};

const ItemsTab = ({ items, setItems, saving, onSave, msg, setMsg }) => {
  const [showForm,   setShowForm]   = useState(false);
  const [showCssFor, setShowCssFor] = useState(null);
  const [editId,     setEditId]     = useState(null);
  const [form,       setForm]       = useState(EMPTY_FORM);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    setItems((prev) => arrayMove(prev,
      prev.findIndex((i) => i.id === active.id),
      prev.findIndex((i) => i.id === over.id),
    ));
  };

  const handleDelete = (id) => setItems((prev) => prev.filter((i) => i.id !== id));

  const openEdit = (item) => {
    setEditId(item.id);
    setForm({ label: item.label, type: item.type, href: item.href || '#', anchorPage: item.anchorPage || '/', slug: item.slug || '', cssClass: item.cssClass || '', noFatMenu: item.noFatMenu || false });
    setShowForm(true); setShowCssFor(null);
  };

  const openCss = (item) => {
    setShowCssFor(showCssFor === item.id ? null : item.id);
    setShowForm(false); setEditId(null);
  };

  const openAdd = () => { setEditId(null); setForm(EMPTY_FORM); setShowForm(true); setShowCssFor(null); };

  const handleSaveItem = () => {
    if (!form.label.trim()) return;
    const newItem = {
      id:    editId || form.label.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
      label: form.label.trim(),
      type:  form.type,
      ...(form.type === 'anchor' ? { href: form.href, anchorPage: form.anchorPage || '/' } : { slug: form.slug }),
      ...(form.type === 'plone' && form.noFatMenu ? { noFatMenu: true } : {}),
      ...(form.cssClass ? { cssClass: form.cssClass } : {}),
    };
    setItems((prev) => editId ? prev.map((i) => (i.id === editId ? newItem : i)) : [...prev, newItem]);
    setShowForm(false); setEditId(null); setForm(EMPTY_FORM);
  };

  const applyPreset = (itemId, preset) =>
    setItems((prev) => prev.map((i) => i.id === itemId ? { ...i, cssClass: preset || undefined } : i));

  const setF = (key) => (_, { value }) => setForm((p) => ({ ...p, [key]: value }));

  return (
    <div>
      <p className="nm-desc">
        <Icon name="bars" /> Arrastra para reordenar &middot;
        &#127912; CSS Class &middot; &#9998; Editar &middot; &#10005; Eliminar &middot;
        <strong> Guardar aplica sin rebuild.</strong>
      </p>

      {msg && (
        <Message positive={msg.type === 'success'} negative={msg.type === 'error'} onDismiss={() => setMsg(null)}>
          {msg.text}
        </Message>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          <div className="nm-list">
            {items.length === 0
              ? <p className="nm-empty">Sin items. Agrega el primero.</p>
              : items.map((item) => (
                  <React.Fragment key={item.id}>
                    <SortableItem item={item} onEdit={openEdit} onDelete={handleDelete} onCss={openCss} cssOpen={showCssFor === item.id} />
                    {showCssFor === item.id && (
                      <div className="nm-css-panel">
                        <p className="nm-css-title">CSS Class para <strong>{item.label}</strong></p>
                        <Form.Field>
                          <Input
                            value={item.cssClass || ''}
                            onChange={(_, { value }) => applyPreset(item.id, value)}
                            placeholder="Ej: nm-apple  o  mi-clase-custom"
                          />
                        </Form.Field>
                        <div className="nm-css-presets">
                          <span className="nm-css-label">Presets:</span>
                          {['nm-apple','nm-dark','nm-wide','nm-minimal'].map((p) => (
                            <button key={p}
                              className={'nm-preset-btn' + (item.cssClass === p ? ' active' : '')}
                              onClick={() => applyPreset(item.id, item.cssClass === p ? '' : p)}>
                              {p}
                            </button>
                          ))}
                          <button className="nm-preset-btn nm-preset-clear" onClick={() => applyPreset(item.id, '')}>
                            &#10005; quitar
                          </button>
                        </div>
                        <p className="nm-css-hint">Clase aplicada en el panel desplegable. Ej: <code>.nm-fat-panel.nm-apple</code></p>
                      </div>
                    )}
                  </React.Fragment>
                ))}
          </div>
        </SortableContext>
      </DndContext>

      {showForm ? (
        <div className="nm-form-wrap">
          <h3>{editId ? 'Editar item' : 'Agregar item'}</h3>
          <Form>
            <Form.Group widths="equal">
              <Form.Field>
                <label>Label (texto del menu)</label>
                <Input value={form.label} onChange={setF('label')} placeholder="Ej: Eventos" />
              </Form.Field>
              <Form.Field>
                <label>Tipo</label>
                <Select options={TYPE_OPTIONS} value={form.type} onChange={setF('type')} />
              </Form.Field>
            </Form.Group>
            {form.type === 'anchor' ? (
              <>
              <Form.Field>
                <label>ID de la seccion</label>
                <Input value={form.href} onChange={setF('href')} placeholder="#mission" />
                <small className="nm-hint-field">El elemento HTML debe tener id="mission"</small>
              </Form.Field>
              <Form.Field>
                <label>Pagina destino</label>
                <Input value={form.anchorPage} onChange={setF('anchorPage')} placeholder="/" />
                <small className="nm-hint-field">Ruta de la pagina donde esta el ancla. "/" = Home.</small>
              </Form.Field>
              </>
            ) : (
              <>
              <Form.Field>
                <label>Slug Plone</label>
                <Input value={form.slug} onChange={setF('slug')} placeholder="eventos  (vacio = Home)" />
                <small className="nm-hint-field">Ultimo segmento de la URL. Vacio = raiz (Home).</small>
              </Form.Field>
              <Form.Field>
                <label style={{ display:'flex', alignItems:'center', gap:'0.5rem', fontWeight:'normal' }}>
                  <input type="checkbox" checked={form.noFatMenu || false} onChange={(e) => setForm((f) => ({...f, noFatMenu: e.target.checked}))} />
                  Solo link (sin submenu desplegable)
                </label>
                <small className="nm-hint-field">Si tiene subpaginas, no mostrara el fat menu.</small>
              </Form.Field>
              </>
            )}
            <div style={{ display:'flex', gap:'0.5rem', marginTop:'1rem' }}>
              <Button primary onClick={handleSaveItem}><Icon name="check" /> Guardar item</Button>
              <Button onClick={() => { setShowForm(false); setEditId(null); }}>Cancelar</Button>
            </div>
          </Form>
        </div>
      ) : (
        <Button className="nm-add-btn" onClick={openAdd} secondary>
          <Icon name="plus" /> Agregar item
        </Button>
      )}

      <div className="nm-save-bar">
        <Button primary size="large" loading={saving} onClick={onSave}>
          <Icon name="save" /> Guardar menu
        </Button>
        <span className="nm-hint">Cambios visibles al instante - sin rebuild.</span>
      </div>
    </div>
  );
};

const CssEditorTab = ({ value, setValue, label, desc, snippets, defaultValue, saveLabel, saving, onSave, msg, setMsg }) => (
  <div>
    <p className="nm-desc">{desc}</p>

    {msg && (
      <Message positive={msg.type === 'success'} negative={msg.type === 'error'} onDismiss={() => setMsg(null)}>
        {msg.text}
      </Message>
    )}

    <div className="nm-css-editor-wrap">
      <div className="nm-css-editor-toolbar">
        <span><strong>{label}</strong></span>
        <div className="nm-css-snippets">
          {snippets && snippets.length > 0 && <span>Snippets:</span>}
          {(snippets || []).map(({ label: sl, code }) => (
            <button key={sl} className="nm-snippet-btn"
              onClick={() => setValue((prev) => prev ? prev + '\n\n' + code : code)}>
              {sl}
            </button>
          ))}
          {defaultValue !== undefined && (
            <button className="nm-snippet-btn nm-snippet-btn-warn" onClick={() => {
              if (window.confirm('Restaurar estilos base originales? Se perderan tus cambios.')) setValue(defaultValue);
            }}>
              &#8635; restaurar default
            </button>
          )}
        </div>
      </div>
      <textarea
        className="nm-css-editor"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        spellCheck={false}
      />
    </div>
    <div className="nm-save-bar">
      <Button primary size="large" loading={saving} onClick={onSave}>
        <Icon name="save" /> {saveLabel}
      </Button>
      <span className="nm-hint">Se aplica al instante - sin rebuild.</span>
    </div>
  </div>
);

/* ─────────────────────── FOOTER ─────────────────────── */

const FooterColumnsTab = ({ cfg, setCfg, saving, onSave, msg, setMsg }) => {
  const columns = cfg.columns || [];
  const legal   = cfg.legal_links || [];

  const patch = (p) => setCfg((c) => ({ ...c, ...p }));

  const addColumn = () =>
    patch({ columns: [...columns, { id: uid(), title: 'Columna', links: [] }] });
  const setColumn = (cid, p) =>
    patch({ columns: columns.map((c) => (c.id === cid ? { ...c, ...p } : c)) });
  const delColumn = (cid) =>
    patch({ columns: columns.filter((c) => c.id !== cid) });

  const addLink = (cid) => {
    const col = columns.find((c) => c.id === cid);
    setColumn(cid, { links: [...(col.links || []), { id: uid(), label: 'Link', href: '/' }] });
  };
  const setLink = (cid, lid, p) => {
    const col = columns.find((c) => c.id === cid);
    setColumn(cid, { links: (col.links || []).map((l) => (l.id === lid ? { ...l, ...p } : l)) });
  };
  const delLink = (cid, lid) => {
    const col = columns.find((c) => c.id === cid);
    setColumn(cid, { links: (col.links || []).filter((l) => l.id !== lid) });
  };

  const addLegal = () => patch({ legal_links: [...legal, { id: uid(), label: 'Link', href: '/' }] });
  const setLegal = (lid, p) => patch({ legal_links: legal.map((l) => (l.id === lid ? { ...l, ...p } : l)) });
  const delLegal = (lid) => patch({ legal_links: legal.filter((l) => l.id !== lid) });

  return (
    <div>
      <p className="nm-desc">
        Columnas de enlaces, copyright y enlaces legales del footer.
        <strong> Guardar aplica sin rebuild.</strong>
      </p>

      {msg && (
        <Message positive={msg.type === 'success'} negative={msg.type === 'error'} onDismiss={() => setMsg(null)}>
          {msg.text}
        </Message>
      )}

      <div className={cfg.show_default || cfg.mode === 'html' ? 'sc-cp-disabled' : ''}>
        {columns.map((col) => (
          <div className="sc-cp-col" key={col.id}>
            <div className="sc-cp-col-head">
              <Input
                value={col.title || ''}
                onChange={(_, { value }) => setColumn(col.id, { title: value })}
                placeholder="Titulo de la columna"
              />
              <Button size="mini" color="red" onClick={() => delColumn(col.id)}>&#10005; Columna</Button>
            </div>
            {(col.links || []).map((link) => (
              <div className="sc-cp-link" key={link.id}>
                <Input
                  value={link.label || ''}
                  onChange={(_, { value }) => setLink(col.id, link.id, { label: value })}
                  placeholder="Texto"
                />
                <Input
                  value={link.href || ''}
                  onChange={(_, { value }) => setLink(col.id, link.id, { href: value })}
                  placeholder="/ruta  o  https://..."
                />
                <Button size="mini" color="red" onClick={() => delLink(col.id, link.id)}>&#10005;</Button>
              </div>
            ))}
            <Button size="mini" secondary onClick={() => addLink(col.id)}>
              <Icon name="plus" /> Link
            </Button>
          </div>
        ))}

        <Button className="nm-add-btn" secondary onClick={addColumn}>
          <Icon name="plus" /> Agregar columna
        </Button>

        <Form.Field style={{ marginTop: '1.5rem' }}>
          <label>Copyright</label>
          <textarea
            className="sc-cp-copyright"
            value={cfg.copyright || ''}
            onChange={(e) => patch({ copyright: e.target.value })}
            placeholder="© 2000-2026 por ..."
          />
        </Form.Field>

        <div className="sc-cp-legal">
          <label>Enlaces legales</label>
          {legal.map((link) => (
            <div className="sc-cp-link" key={link.id}>
              <Input
                value={link.label || ''}
                onChange={(_, { value }) => setLegal(link.id, { label: value })}
                placeholder="Texto"
              />
              <Input
                value={link.href || ''}
                onChange={(_, { value }) => setLegal(link.id, { href: value })}
                placeholder="/ruta  o  https://..."
              />
              <Button size="mini" color="red" onClick={() => delLegal(link.id)}>&#10005;</Button>
            </div>
          ))}
          <Button size="mini" secondary onClick={addLegal}>
            <Icon name="plus" /> Enlace legal
          </Button>
        </div>
      </div>

      <div className="nm-save-bar">
        <Button primary size="large" loading={saving} onClick={onSave}>
          <Icon name="save" /> Guardar footer
        </Button>
        <span className="nm-hint">Cambios visibles al instante - sin rebuild.</span>
      </div>
    </div>
  );
};

const FOOTER_MODES = [
  { value: 'default', label: 'Default Plone',  hint: 'Footer estandar de Plone (red de seguridad).' },
  { value: 'columns', label: 'Columnas',        hint: 'Columnas de enlaces + copyright + legales.' },
  { value: 'html',    label: 'HTML (Blocs)',    hint: 'Markup de Blocs aislado bajo .sc-footer-blocs.' },
];

const currentMode = (cfg) => (cfg.show_default ? 'default' : (cfg.mode || 'columns'));

const FooterModeSelector = ({ cfg, setCfg, onModeChange }) => {
  const mode = currentMode(cfg);
  const choose = (m) => {
    if (m === mode) return;
    setCfg((c) => ({
      ...c,
      show_default: m === 'default',
      mode: m === 'default' ? (c.mode || 'columns') : m,
    }));
    if (onModeChange) onModeChange(m);
  };
  return (
    <div className="sc-cp-modebar">
      <span className="sc-cp-modebar-label">Modo del footer:</span>
      {FOOTER_MODES.map((m) => (
        <label key={m.value} className={'sc-cp-mode' + (mode === m.value ? ' active' : '')}>
          <input type="radio" name="footer-mode" checked={mode === m.value} onChange={() => choose(m.value)} />
          <span>{m.label}</span>
          <small>{m.hint}</small>
        </label>
      ))}
    </div>
  );
};

const HtmlTab = ({ cfg, setCfg, setBaseCss, setCss, saving, onSave, msg, setMsg }) => {
  const [text, setText] = useState('');
  const [drag, setDrag] = useState(false);
  const fileRef = useRef(null);
  const patch = (p) => setCfg((c) => ({ ...c, ...p }));

  const apply = ({ html, base_css, css }) => {
    patch({ html, mode: 'html', show_default: false });
    if (typeof base_css === 'string') setBaseCss(base_css);
    if (typeof css === 'string') setCss(css);
    setMsg({ type: 'success', text: 'Importado. base_css/css quedaron en sus pestañas. Revisa y Guarda.' });
  };

  // footer.json -> { html, base_css, css }
  const fromJson = (raw) => {
    const data = JSON.parse(raw);
    if (typeof data.html !== 'string') throw new Error('el JSON debe tener la clave "html"');
    return { html: data.html, base_css: data.base_css || '', css: data.css || '' };
  };

  // footer.html (artefacto del conversor): primero los datos incrustados
  // (split limpio base_css/css); si no, se extrae del DOM (base_css solo).
  const fromHtml = (raw) => {
    const doc = new DOMParser().parseFromString(raw, 'text/html');
    const embed = doc.querySelector('#sc-footer-data');
    if (embed && embed.textContent.trim()) {
      const d = JSON.parse(embed.textContent);
      if (typeof d.html === 'string') {
        return { html: d.html, base_css: d.base_css || '', css: d.css || '' };
      }
    }
    const root = doc.querySelector('.sc-footer-blocs');
    if (!root) throw new Error('no se encontraron datos ni <div class="sc-footer-blocs">');
    const styles = Array.from(doc.querySelectorAll('style')).map((s) => s.textContent).join('\n');
    return { html: root.innerHTML.trim(), base_css: styles, css: '' };
  };

  const importText = (raw) => {
    const t = (raw || '').trim();
    if (!t) { setMsg({ type: 'error', text: 'Nada que importar.' }); return; }
    try {
      apply(t[0] === '{' ? fromJson(t) : fromHtml(t));
    } catch (e) {
      setMsg({ type: 'error', text: 'No se pudo importar: ' + e.message });
    }
  };

  const readFile = (file) => {
    if (!file) return;
    const r = new FileReader();
    r.onload = () => { setText(String(r.result)); importText(String(r.result)); };
    r.onerror = () => setMsg({ type: 'error', text: 'No se pudo leer el archivo.' });
    r.readAsText(file);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) readFile(file);
  };

  return (
    <div>
      <p className="nm-desc">
        Arrastra el <code>footer.html</code> que genera <code>tools/bloc2footer.py</code>
        (el mismo archivo que abres para ver el footer). Se renderiza aislado bajo
        <code> .sc-footer-blocs</code>; el CSS va en las pestañas <strong>Estilos base</strong>
        y <strong>CSS Custom</strong>. <strong>Guardar aplica sin rebuild.</strong>
      </p>

      {msg && (
        <Message positive={msg.type === 'success'} negative={msg.type === 'error'} onDismiss={() => setMsg(null)}>
          {msg.text}
        </Message>
      )}

      <div
        className={'sc-cp-import' + (drag ? ' sc-cp-dragover' : '')}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <div className="sc-cp-drop">
          <Icon name="cloud upload" size="big" />
          <p><strong>Arrastra el archivo aquí</strong> — <code>footer.html</code> (o <code>footer.json</code>)</p>
          <input
            ref={fileRef}
            type="file"
            accept=".json,.html,.htm,application/json,text/html"
            style={{ display: 'none' }}
            onChange={(e) => readFile(e.target.files && e.target.files[0])}
          />
          <Button size="small" secondary onClick={() => fileRef.current && fileRef.current.click()}>
            <Icon name="folder open" /> Elegir archivo…
          </Button>
        </div>

        <details className="sc-cp-paste">
          <summary>… o pegar el contenido manualmente</summary>
          <textarea
            className="nm-css-editor sc-cp-import-box"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='{ "html": "...", "base_css": "...", "css": "..." }'
            spellCheck={false}
          />
          <Button size="small" secondary onClick={() => importText(text)}>
            <Icon name="upload" /> Importar
          </Button>
        </details>
      </div>

      <Form.Field style={{ marginTop: '1.25rem' }}>
        <label>HTML del footer</label>
        <textarea
          className="nm-css-editor"
          value={cfg.html || ''}
          onChange={(e) => patch({ html: e.target.value, mode: 'html' })}
          placeholder={'<div class="bloc ..."> ... </div>'}
          spellCheck={false}
        />
      </Form.Field>

      <div className="nm-save-bar">
        <Button primary size="large" loading={saving} onClick={onSave}>
          <Icon name="save" /> Guardar footer
        </Button>
        <span className="nm-hint">Cambios visibles al instante - sin rebuild.</span>
      </div>
    </div>
  );
};

/* ─────────────────────── ROOT ─────────────────────── */

const SiteChromeControlPanel = () => {
  const intl     = useIntl();
  const { pathname } = useLocation();
  const isClient = useClient();

  // header
  const [items,   setItems]   = useState([]);
  const [css,     setCss]     = useState('');
  const [baseCss, setBaseCss] = useState('');
  // footer
  const [footerCfg,     setFooterCfg]     = useState({ mode: 'columns', columns: [], copyright: '', legal_links: [], html: '', show_default: true });
  const [footerCss,     setFooterCss]     = useState('');
  const [footerBaseCss, setFooterBaseCss] = useState('');

  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [msg,     setMsg]     = useState(null);
  const [section, setSection] = useState(0); // 0 = header, 1 = footer
  const [hTab,    setHTab]    = useState(0);
  const [fTab,    setFTab]    = useState(0);

  const dispatch = useDispatch();
  // Fuente de verdad: el store (poblado por SSR). Usamos las acciones de Volto
  // (middleware -> path de API + auth correctos) en vez de fetch crudo.
  const sc = useSelector((s) => s.siteChrome);

  useEffect(() => { dispatch(getSiteChrome()); }, [dispatch]);

  useEffect(() => {
    if (!sc) return;
    const h = sc.header || {};
    const f = sc.footer || {};
    setItems(h.items || []);
    setCss(h.css || '');
    setBaseCss(h.base_css || DEFAULT_BASE_CSS);
    setFooterCfg(f.config || { mode: 'columns', columns: [], copyright: '', legal_links: [], html: '', show_default: true });
    setFooterCss(f.css || '');
    setFooterBaseCss(f.base_css || DEFAULT_FOOTER_BASE_CSS);
    setLoading(false);
  }, [sc]);

  const patchSection = async (payload, okText) => {
    setSaving(true); setMsg(null);
    try {
      await dispatch(patchSiteChrome(payload));
      await dispatch(getSiteChrome());
      setMsg({ type: 'success', text: okText });
    } catch (e) {
      setMsg({ type: 'error', text: 'Error al guardar: ' + ((e && e.message) || String(e)) });
    } finally { setSaving(false); }
  };

  const saveHeader = () => {
    const clean = items.map((i) => { const c = {...i}; if (!c.cssClass) delete c.cssClass; return c; });
    return patchSection(
      { section: 'header', items: clean, css, base_css: baseCss },
      'Header guardado. Cambios visibles al instante.',
    );
  };

  const saveFooter = () =>
    patchSection(
      { section: 'footer', config: footerCfg, css: footerCss, base_css: footerBaseCss },
      'Footer guardado. Cambios visibles al instante.',
    );

  if (loading) return <div className="nm-loading"><Icon name="spinner" loading /> Cargando...</div>;

  const headerPanes = [
    { menuItem: 'Items del menu', render: () => (
      <Tab.Pane><ItemsTab items={items} setItems={setItems} saving={saving} onSave={saveHeader} msg={msg} setMsg={setMsg} /></Tab.Pane>
    )},
    { menuItem: 'Estilos base', render: () => (
      <Tab.Pane>
        <CssEditorTab
          value={baseCss} setValue={setBaseCss}
          label="Estilos base del fat menu"
          desc="Colores, sombras y presets del menu. Se aplica sin rebuild."
          defaultValue={DEFAULT_BASE_CSS}
          saveLabel="Guardar estilos base"
          saving={saving} onSave={saveHeader} msg={msg} setMsg={setMsg}
        />
      </Tab.Pane>
    )},
    { menuItem: 'CSS Custom', render: () => (
      <Tab.Pane>
        <CssEditorTab
          value={css} setValue={setCss}
          label="CSS personalizado"
          desc="CSS que se inyecta encima de los estilos base del menu."
          snippets={[
            { label: 'hover color',   code: '.nm-fat-list a:hover { background: #e8f4ff; color: #0071e3; }' },
            { label: 'chevron color', code: '.nm-chevron { color: #0071e3; }' },
          ]}
          saveLabel="Guardar CSS"
          saving={saving} onSave={saveHeader} msg={msg} setMsg={setMsg}
        />
      </Tab.Pane>
    )},
  ];

  const footerColumnsPane = { menuItem: 'Columnas', render: () => (
    <Tab.Pane><FooterColumnsTab cfg={footerCfg} setCfg={setFooterCfg} saving={saving} onSave={saveFooter} msg={msg} setMsg={setMsg} /></Tab.Pane>
  )};
  const footerHtmlPane = { menuItem: 'HTML (Blocs)', render: () => (
    <Tab.Pane>
      <HtmlTab
        cfg={footerCfg} setCfg={setFooterCfg}
        setBaseCss={setFooterBaseCss} setCss={setFooterCss}
        saving={saving} onSave={saveFooter} msg={msg} setMsg={setMsg}
      />
    </Tab.Pane>
  )};
  const footerBaseCssPane = { menuItem: 'Estilos base', render: () => (
    <Tab.Pane>
      <CssEditorTab
        value={footerBaseCss} setValue={setFooterBaseCss}
        label="Estilos base del footer"
        desc="Colores y tipografia del footer (.sc-footer). Se aplica sin rebuild."
        defaultValue={DEFAULT_FOOTER_BASE_CSS}
        saveLabel="Guardar estilos base"
        saving={saving} onSave={saveFooter} msg={msg} setMsg={setMsg}
      />
    </Tab.Pane>
  )};
  const footerCustomCssPane = { menuItem: 'CSS Custom', render: () => (
    <Tab.Pane>
      <CssEditorTab
        value={footerCss} setValue={setFooterCss}
        label="CSS personalizado del footer"
        desc="CSS que se inyecta encima de los estilos base del footer."
        snippets={[
          { label: 'columnas gap', code: '.sc-footer-columns { gap: 3rem; }' },
          { label: 'centrar',      code: '.sc-footer-bottom { text-align: center; }' },
        ]}
        saveLabel="Guardar CSS"
        saving={saving} onSave={saveFooter} msg={msg} setMsg={setMsg}
      />
    </Tab.Pane>
  )};
  // El modo gobierna que pestañas se muestran: Columnas|HTML + estilos compartidos.
  const footerPanesFor = (fmode) => [
    fmode === 'html' ? footerHtmlPane : footerColumnsPane,
    footerBaseCssPane,
    footerCustomCssPane,
  ];

  const sectionPanes = [
    { menuItem: 'Header', render: () => (
      <Tab.Pane>
        <Tab panes={headerPanes} activeIndex={hTab} onTabChange={(_, { activeIndex }) => { setHTab(activeIndex); setMsg(null); }} />
      </Tab.Pane>
    )},
    { menuItem: 'Footer', render: () => {
      const fmode = currentMode(footerCfg);
      return (
        <Tab.Pane>
          <FooterModeSelector
            cfg={footerCfg} setCfg={setFooterCfg}
            onModeChange={() => { setFTab(0); setMsg(null); }}
          />
          {fmode === 'default' ? (
            <div className="sc-cp-mode-note">
              <p>
                Se mostrara el <strong>footer estandar de Plone</strong> (red de seguridad).
                No hay nada que configurar aqui — cambia el modo a <strong>Columnas</strong> o
                <strong> HTML (Blocs)</strong> para personalizarlo.
              </p>
              {msg && (
                <Message size="small" positive={msg.type === 'success'} negative={msg.type === 'error'}>
                  {msg.text}
                </Message>
              )}
              <Button primary loading={saving} onClick={saveFooter}>
                <Icon name="undo" /> Restaurar footer por defecto de Plone
              </Button>
              <span className="sc-cp-mode-hint">Guarda para descartar columnas/HTML y volver al footer nativo.</span>
            </div>
          ) : (
            <Tab panes={footerPanesFor(fmode)} activeIndex={fTab} onTabChange={(_, { activeIndex }) => { setFTab(activeIndex); setMsg(null); }} />
          )}
        </Tab.Pane>
      );
    }},
  ];

  return (
    <div className="nm-controlpanel">
      <h1><Icon name="list layout" /> Site Chrome</h1>
      <Tab
        menu={{ secondary: true, pointing: true }}
        panes={sectionPanes}
        activeIndex={section}
        onTabChange={(_, { activeIndex }) => { setSection(activeIndex); setMsg(null); }}
      />
      {isClient &&
        createPortal(
          <Toolbar
            pathname={pathname}
            hideDefaultViewButtons
            inner={
              <Link to="/controlpanel" className="item">
                <VIcon
                  name={backSVG}
                  aria-label={intl.formatMessage(messages.back)}
                  className="contents circled"
                  size="30px"
                  title={intl.formatMessage(messages.back)}
                />
              </Link>
            }
          />,
          document.getElementById('toolbar'),
        )}
    </div>
  );
};

export default SiteChromeControlPanel;
