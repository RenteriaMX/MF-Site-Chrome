/**
 * Site Chrome SSR — fetch header + footer config/CSS durante el render en
 * servidor, para que estén en el HTML inicial (sin flash).
 */

// Action types
const GET_SITE_CHROME = 'GET_SITE_CHROME';
const PATCH_SITE_CHROME = 'PATCH_SITE_CHROME';

// Action creators (usan el middleware de Volto: path de API + auth correctos)
export function getSiteChrome() {
  return {
    type: GET_SITE_CHROME,
    request: {
      op: 'get',
      path: '/@site-chrome',
    },
  };
}

export function patchSiteChrome(data) {
  return {
    type: PATCH_SITE_CHROME,
    request: {
      op: 'patch',
      path: '/@site-chrome',
      data,
    },
  };
}

// Reducer
const initialState = {
  header: { items: null, base_css: '', css: '' },
  footer: { config: null, base_css: '', css: '' },
  loaded: false,
};

export function siteChromeReducer(state = initialState, action = {}) {
  switch (action.type) {
    case `${GET_SITE_CHROME}_PENDING`:
      return { ...state, loaded: false };
    case `${GET_SITE_CHROME}_SUCCESS`: {
      const data = action.result || {};
      const header = data.header || {};
      const footer = data.footer || {};
      return {
        header: {
          items: header.items || null,
          base_css: header.base_css || '',
          css: header.css || '',
        },
        footer: {
          config: footer.config || null,
          base_css: footer.base_css || '',
          css: footer.css || '',
        },
        loaded: true,
      };
    }
    case `${GET_SITE_CHROME}_FAIL`:
      return { ...state, loaded: true };
    default:
      return state;
  }
}

// asyncPropsExtender — dispara el fetch durante SSR
export function siteChromeAsyncExtender(routesList) {
  const dominated = routesList.filter((r) => r.key !== 'site-chrome');
  return [
    ...dominated,
    {
      key: 'site-chrome',
      promise: ({ store: { dispatch } }) => {
        if (typeof __SERVER__ !== 'undefined' && __SERVER__) {
          return dispatch(getSiteChrome());
        }
      },
    },
  ];
}
