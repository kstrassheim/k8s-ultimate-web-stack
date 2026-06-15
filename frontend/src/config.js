export const env = import.meta.env.MODE;
export const isDev = env === 'development';
export const isProd = env === 'production';
export const productionUrl = __PROD_URI__; //'; // generated during build to distinct whether local or in app service
export const productionSocketUrl = __PROD_SOCKET_URI__;
export const developmentUrl = 'http://localhost:5173';
export const backendSocketUrl = __PROD_SOCKET_URI__;
// In production the SPA + API share an origin; BASE_URL is the deploy sub-path
// (e.g. "/ultimate-web-stack-dev/"), so the API lives at "<base>/api".
export const backendUrl = isProd ? import.meta.env.BASE_URL.replace(/\/+$/, '') : productionUrl;
export const frontendUrl = isProd ? productionUrl : developmentUrl;