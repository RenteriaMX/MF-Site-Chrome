/**
 * Footer.jsx v1.1 (Site Chrome Manager)
 * - Fuente de verdad: store Redux (state.siteChrome.footer), poblado por SSR
 *   (siteChromeSSR) -> sin flash, sin fetch propio, sin cache module-scope.
 * - El refresco tras un PATCH lo dispara el Control Panel con
 *   dispatch(getSiteChrome()) (usa el middleware de Volto, path de API correcto).
 * - show_default | config vacia -> footer estandar de Plone.
 * - CSS (base_css + css) lo inyecta el viewlet backend en <head>.
 */
import { useSelector, shallowEqual } from 'react-redux';
import { FormattedMessage, defineMessages, useIntl } from 'react-intl';
import { Container, List, Segment } from 'semantic-ui-react';
import { UniversalLink } from '@plone/volto/components';
import { flattenToAppURL, addAppURL } from '@plone/volto/helpers/Url/Url';
import './Footer.css';

const messages = defineMessages({
  copyright: { id: 'Copyright', defaultMessage: 'Copyright' },
});

const isExternal = (href) => /^https?:\/\//i.test(href || '');

const FooterLink = ({ link }) => {
  const href = link.href || '';
  if (isExternal(href)) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {link.label}
      </a>
    );
  }
  return <UniversalLink href={flattenToAppURL(href) || '/'}>{link.label}</UniversalLink>;
};

// Reproduccion fiel del Footer nativo de Volto (Segment inverted grey, centrado).
// Se shadowea el Footer de Volto, asi que en modo "default" replicamos su markup
// exacto para que se vea identico al original (no un <div> plano).
const DefaultFooter = () => {
  const intl = useIntl();
  const siteActions = useSelector(
    (s) => s.actions?.actions?.site_actions || [],
    shallowEqual,
  );
  return (
    <Segment
      role="contentinfo"
      vertical
      padded
      inverted
      color="grey"
      textAlign="center"
      id="footer"
      aria-label="Footer"
      tabIndex="-1"
    >
      <Container>
        <Segment basic inverted color="grey" className="discreet">
          <FormattedMessage
            id="The {plonecms} is {copyright} 2000-{current_year} by the {plonefoundation} and friends."
            defaultMessage="The {plonecms} is {copyright} 2000-{current_year} by the {plonefoundation} and friends."
            values={{
              plonecms: (
                <FormattedMessage
                  id="Plone{reg} Open Source CMS/WCM"
                  defaultMessage="Plone{reg} Open Source CMS/WCM"
                  values={{ reg: <sup>&reg;</sup> }}
                />
              ),
              copyright: (
                <abbr title={intl.formatMessage(messages.copyright)}>&copy;</abbr>
              ),
              current_year: new Date().getFullYear(),
              plonefoundation: (
                <a className="item" href="http://plone.org/foundation">
                  <FormattedMessage id="Plone Foundation" defaultMessage="Plone Foundation" />
                </a>
              ),
            }}
          />{' '}
          <FormattedMessage
            id="Distributed under the {license}."
            defaultMessage="Distributed under the {license}."
            values={{
              license: (
                <a className="item" href="http://creativecommons.org/licenses/GPL/2.0/">
                  <FormattedMessage id="GNU GPL license" defaultMessage="GNU GPL license" />
                </a>
              ),
            }}
          />
        </Segment>
        <List horizontal inverted>
          {siteActions?.length
            ? siteActions.map((item) => (
                <div role="listitem" className="item" key={item.id}>
                  <UniversalLink
                    className="item"
                    href={item.url ? flattenToAppURL(item.url) : addAppURL(item.id)}
                  >
                    {item?.title}
                  </UniversalLink>
                </div>
              ))
            : null}
          <div role="listitem" className="item">
            <a className="item" href="https://plone.org">
              <FormattedMessage id="Powered by Plone & Python" defaultMessage="Powered by Plone & Python" />
            </a>
          </div>
        </List>
      </Container>
    </Segment>
  );
};

const Footer = () => {
  const footer = useSelector((s) => s.siteChrome?.footer, shallowEqual);
  const cfg = footer?.config || null;
  const baseCss = footer?.base_css || '';
  const css = footer?.css || '';

  if (!cfg || cfg.show_default) return <DefaultFooter />;

  // Modo HTML (Blocs): markup arbitrario aislado bajo .sc-footer-blocs.
  // El CSS (base_css scopeado + css) ya esta en <head> via viewlet (sin flash);
  // el <style> inline es redundancia segura. El backend sanitiza el html.
  const mode = cfg.mode || 'columns';
  if (mode === 'html') {
    if (!cfg.html) return <DefaultFooter />;
    return (
      <footer id="footer" className="footer">
        {baseCss && <style dangerouslySetInnerHTML={{ __html: baseCss }} />}
        {css && <style dangerouslySetInnerHTML={{ __html: css }} />}
        <div className="sc-footer-blocs" dangerouslySetInnerHTML={{ __html: cfg.html }} />
      </footer>
    );
  }

  const columns = cfg.columns || [];
  const legal = cfg.legal_links || [];

  return (
    <footer id="footer" className="footer sc-footer">
      {baseCss && <style dangerouslySetInnerHTML={{ __html: baseCss }} />}
      {css && <style dangerouslySetInnerHTML={{ __html: css }} />}

      {columns.length > 0 && (
        <div className="sc-footer-columns">
          {columns.map((col) => (
            <div className="sc-footer-col" key={col.id || col.title}>
              {col.title && <h4 className="sc-footer-col-title">{col.title}</h4>}
              <ul className="sc-footer-col-links">
                {(col.links || []).map((link) => (
                  <li key={link.id || link.href}>
                    <FooterLink link={link} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {(cfg.copyright || legal.length > 0) && (
        <div className="sc-footer-bottom">
          {cfg.copyright && <span className="sc-footer-copyright">{cfg.copyright}</span>}
          {legal.length > 0 && (
            <span className="sc-footer-legal">
              {legal.map((link) => (
                <FooterLink key={link.id || link.href} link={link} />
              ))}
            </span>
          )}
        </div>
      )}
    </footer>
  );
};

export default Footer;
