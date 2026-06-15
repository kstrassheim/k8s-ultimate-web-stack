export const env = import.meta.env.MODE;
export const isDev = env === 'development';
export const isProd = env === 'production';
// Deploy sub-path (Vite base), e.g. "/ultimate-web-stack-dev/"; "/" locally.
// import.meta is only referenced here (config is the single holder); other
// modules import basePath so they stay transformable by the test runner.
export const basePath = import.meta.env.BASE_URL || '/';
export const productionUrl = __PROD_URI__; //'; // generated during build to distinct whether local or in app service
export const productionSocketUrl = __PROD_SOCKET_URI__;
export const developmentUrl = 'http://localhost:5173';
// WebSocket shares the page origin + sub-path in production (the ingress strips
// the prefix before the backend); fall back to the build-time URL in local dev.
const deployedSocketBase = (typeof window !== 'undefined')
  ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}${basePath.replace(/\/+$/, '')}`
  : productionSocketUrl;
export const backendSocketUrl = isProd ? deployedSocketBase : productionSocketUrl;
// In production the SPA + API share an origin; basePath is the deploy sub-path,
// so the API lives at "<base>/api".
export const backendUrl = isProd ? basePath.replace(/\/+$/, '') : productionUrl;
export const frontendUrl = isProd ? productionUrl : developmentUrl;
