export const env = import.meta.env.MODE;
export const isDev = env === 'development';
export const isProd = env === 'production';
export const productionUrl = __PROD_URI__; //'; // generated during build to distinct whether local or in app service
export const productionSocketUrl = __PROD_SOCKET_URI__;
export const developmentUrl = 'http://localhost:5173';
// WebSocket shares the page origin + sub-path in production (the ingress strips
// the prefix before the backend); fall back to the build-time URL in local dev.
const deployedSocketBase = (typeof window !== 'undefined')
  ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}${import.meta.env.BASE_URL.replace(/\/+$/, '')}`
  : productionSocketUrl;
export const backendSocketUrl = isProd ? deployedSocketBase : productionSocketUrl;
// In production the SPA + API share an origin; BASE_URL is the deploy sub-path
// (e.g. "/ultimate-web-stack-dev/"), so the API lives at "<base>/api".
export const backendUrl = isProd ? import.meta.env.BASE_URL.replace(/\/+$/, '') : productionUrl;
export const frontendUrl = isProd ? productionUrl : developmentUrl;