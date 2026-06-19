/**
 * Navigation.jsx v1.1 (Site Chrome Manager — header)
 * - Fat menu abre con HOVER — delay 180ms
 * - CSS injection: base_css + css desde Plone Registry (sin rebuild)
 * - Tipos: anchor (scroll), plone sin hijos (link), plone con hijos (fat menu)
 * - Sin flash, slug case-insensitive, ESC cierra
 * - Fuente de verdad: store Redux (state.siteChrome.header), poblado por SSR.
 *   Sin fetch propio ni cache; el refresco tras PATCH lo dispara el Control Panel.
 */
import { useEffect, useState, useRef } from 'react';
import PropTypes from 'prop-types';
import { useDispatch, useSelector, shallowEqual } from 'react-redux';
import { defineMessages, useIntl } from 'react-intl';
import { Menu } from 'semantic-ui-react';
import cx from 'classnames';
import { useHistory, useLocation } from 'react-router-dom';
import BodyClass from '@plone/volto/helpers/BodyClass/BodyClass';
import { getBaseUrl, flattenToAppURL } from '@plone/volto/helpers/Url/Url';
import { hasApiExpander } from '@plone/volto/helpers/Utils/Utils';
import config from '@plone/volto/registry';
import { getNavigation } from '@plone/volto/actions/navigation/navigation';
import { CSSTransition } from 'react-transition-group';
import NavItems from '@plone/volto/components/theme/Navigation/NavItems';
import './Navigation.css';

const messages = defineMessages({
  closeMobileMenu: { id: 'Close menu', defaultMessage: 'Close menu' },
  openMobileMenu:  { id: 'Open menu',  defaultMessage: 'Open menu'  },
});

// SC-3: allowlist de esquema para hrefs de configuración (manager-controlled).
// Bloquea javascript:/data:/vbscript: (incluida ofuscación con espacios/control
// chars); permite relativos, anclas y esquemas seguros (http/https/mailto/tel).
const safeHref = (href) => {
  const s = String(href ?? '').trim();
  if (!s) return '#';
  // Quita espacios/control chars que podrian ofuscar el esquema (java\tscript:)
  const stripped = s.replace(/\s+/g, '');
  const m = stripped.match(/^([a-z][a-z0-9+.-]*):/i);
  if (m && !/^(?:https?|mailto|tel)$/i.test(m[1])) return '#';
  return s;
};

const AnchorItem = ({ item, onClick }) => {
  const history = useHistory();
  const { pathname } = useLocation();
  const handleClick = (e) => {
    e.preventDefault();
    const anchor = item.href.replace(/^#+/, '');
    const targetPage = item.anchorPage || '/';
    const normalizedPath = pathname.replace(/\/+$/, '') || '/';
    const normalizedTarget = targetPage.replace(/\/+$/, '') || '/';
    if (normalizedPath === normalizedTarget) {
      const el = document.getElementById(anchor);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    } else {
      history.push(targetPage + '#' + anchor);
      setTimeout(() => {
        const el = document.getElementById(anchor);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 400);
    }
    if (onClick) onClick();
  };
  return (
    <a href={safeHref(item.href)} className="item" onClick={handleClick}>
      {item.label}
    </a>
  );
};

const FatMenuItem = ({ ploneItem, cssClass, onClose }) => {
  const history    = useHistory();
  const [isOpen, setIsOpen] = useState(false);
  const closeTimer = useRef(null);
  const url = flattenToAppURL(ploneItem.url || ploneItem['@id'] || '');

  const handleEnter = () => { clearTimeout(closeTimer.current); setIsOpen(true); };
  const handleLeave = () => { closeTimer.current = setTimeout(() => setIsOpen(false), 180); };

  useEffect(() => {
    const onEsc = (e) => { if (e.key === 'Escape') setIsOpen(false); };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, []);

  return (
    <div
      className={cx('nm-fat-wrapper', { 'nm-fat-open': isOpen })}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        className={cx('item', 'nm-fat-trigger', { active: isOpen })}
        aria-expanded={isOpen}
        onClick={() => { onClose(); history.push(url); }}
      >
        {ploneItem.nav_title || ploneItem.title}
        <span className={cx('nm-chevron', { 'nm-chevron-up': isOpen })}>&#9662;</span>
      </button>

      <div
        className={cx('nm-fat-panel', { 'nm-fat-panel-open': isOpen }, cssClass || '')}
        role="region"
      >
        <div className="nm-fat-inner">
          <a
            className="nm-fat-header"
            href={safeHref(url)}
            onClick={(e) => { e.preventDefault(); onClose(); history.push(url); }}
          >
            {ploneItem.nav_title || ploneItem.title} &rarr;
          </a>
          <ul className="nm-fat-list">
            {(ploneItem.items || []).map((sub) => {
              const subUrl = flattenToAppURL(sub.url || sub['@id'] || '');
              return (
                <li key={sub['@id'] || sub.url}>
                  <a href={safeHref(subUrl)} onClick={(e) => { e.preventDefault(); onClose(); history.push(subUrl); }}>
                    <span className="nm-sub-title">
                      <span className="nm-sub-arrow">&mdash;</span>
                      {sub.nav_title || sub.title}
                    </span>
                    {sub.description && (
                      <span className="nm-sub-desc">{sub.description}</span>
                    )}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
};

const Navigation = (props) => {
  const intl     = useIntl();
  const dispatch = useDispatch();
  const { pathname, type } = props;

  const header = useSelector((state) => state.siteChrome?.header, shallowEqual);
  const token = useSelector((state) => state.userSession.token, shallowEqual);

  const [isMobileMenuOpen, setMobileMenuOpen] = useState(false);
  // Fuente de verdad: el store (poblado por SSR). Derivado, no estado local:
  // se actualiza solo cuando el store cambia (incluido el refresh tras PATCH).
  const menuConfig  = header?.items || null;
  const menuBaseCss = header?.base_css || '';
  const menuCss     = header?.css || '';
  const menuReady   = header !== undefined;

  const items = useSelector((state) => state.navigation.items, shallowEqual);
  const lang  = useSelector((state) => state.intl.locale);

  useEffect(() => {
    const { settings } = config;
    if (!hasApiExpander('navigation', getBaseUrl(pathname))) {
      dispatch(getNavigation(getBaseUrl(pathname), settings.navDepth || 2));
    }
  }, [pathname, token, dispatch]);

  const toggleMobileMenu = () => setMobileMenuOpen((v) => !v);
  const closeMobileMenu  = () => setMobileMenuOpen(false);

  const getSlug = (item) =>
    (item?.url || item?.['@id'] || '').split('/').filter(Boolean).pop()?.toLowerCase() || '';

  const findPloneItem = (cfg) => {
    const cfgSlug = (cfg.slug || '').toLowerCase();
    return cfgSlug === ''
      ? (items || []).find((i) => {
          const s = getSlug(i);
          return s === '' || (i?.url || i?.['@id'] || '').split('/').filter(Boolean).length <= 2;
        })
      : (items || []).find((i) => getSlug(i) === cfgSlug);
  };

  const renderItems = (onItemClick) => {
    if (!menuReady) return null;
    if (!menuConfig) return <NavItems items={items || []} lang={lang} />;

    return menuConfig.map((cfg) => {
      if (cfg.type === 'anchor') {
        return <AnchorItem key={cfg.id} item={cfg} onClick={onItemClick} />;
      }
      if (cfg.type === 'plone') {
        const ploneItem = findPloneItem(cfg);
        if (!ploneItem) return null;
        if (ploneItem.items?.length > 0 && !cfg.noFatMenu) {
          return (
            <FatMenuItem
              key={cfg.id}
              ploneItem={ploneItem}
              cssClass={cfg.cssClass}
              onClose={() => { if (onItemClick) onItemClick(); }}
            />
          );
        }
        return <NavItems key={cfg.id} items={[ploneItem]} lang={lang} />;
      }
      return null;
    });
  };

  return (
    <nav className="navigation" id="navigation" aria-label="Site" tabIndex="-1">
      {menuBaseCss && <style dangerouslySetInnerHTML={{ __html: menuBaseCss }} />}
      {menuCss && <style dangerouslySetInnerHTML={{ __html: menuCss }} />}

      {items?.length ? (
        <div className="hamburger-wrapper mobile tablet only">
          <button
            className={cx('hamburger hamburger--spin', { 'is-active': isMobileMenuOpen })}
            aria-label={
              isMobileMenuOpen
                ? intl.formatMessage(messages.closeMobileMenu, { type })
                : intl.formatMessage(messages.openMobileMenu,  { type })
            }
            type="button"
            onClick={toggleMobileMenu}
          >
            <span className="hamburger-box"><span className="hamburger-inner" /></span>
          </button>
        </div>
      ) : null}

      <Menu stackable pointing secondary className="computer large screen widescreen only">
        {renderItems(closeMobileMenu)}
      </Menu>

      <CSSTransition in={isMobileMenuOpen} timeout={500} classNames="mobile-menu" unmountOnExit>
        <div key="mobile-menu-key" className="mobile-menu">
          <BodyClass className="has-mobile-menu-open" />
          <div className="mobile-menu-nav">
            <Menu stackable pointing secondary onClick={closeMobileMenu}>
              {renderItems(closeMobileMenu)}
            </Menu>
          </div>
        </div>
      </CSSTransition>
    </nav>
  );
};

Navigation.propTypes = { pathname: PropTypes.string.isRequired };
export default Navigation;
