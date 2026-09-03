/**
 * @jest-environment jsdom
 * @jest-environment-options {"url": "https://test.example.com/"}
 */
// src/config.test.js

const DEV_PROD_URI = 'http://localhost:8000';
const DEV_SOCKET_URI = 'ws://localhost:8000';
const DEPLOYED_BASE = '/ultimate-web-stack-prod/';

// Per-test helper: mutate the three host inputs that config.js reads
// at module-load time, then load the module fresh under a fresh module
// registry so each test sees its own inputs.
function loadConfigWith({ mode, appBase, prodUri = DEV_PROD_URI, socketUri = DEV_SOCKET_URI } = {}) {
  const restore = [];
  restore.push(jest.replaceProperty(globalThis, '__VITE_MODE__', mode));
  restore.push(jest.replaceProperty(globalThis, '__PROD_URI__', prodUri));
  restore.push(jest.replaceProperty(globalThis, '__PROD_SOCKET_URI__', socketUri));

  if (appBase === null) {
    delete window.__APP_BASE__;
  } else if (appBase !== undefined) {
    window.__APP_BASE__ = appBase;
  }

  let cfg;
  let error;
  try {
    jest.resetModules();
    jest.unmock('@/config');
    cfg = require('@/config');
  } catch (e) {
    error = e;
  }
  restore.forEach((r) => r.restore());
  if (error) throw error;
  return cfg;
}

describe('config.js', () => {
  beforeEach(() => {
    // Start each test from a known window state — no `__APP_BASE__`.
    delete window.__APP_BASE__;
    // Reset host inputs to the dev defaults before each test; individual
    // tests override via loadConfigWith(...).
    globalThis.__VITE_MODE__ = 'test';
    globalThis.__PROD_URI__ = DEV_PROD_URI;
    globalThis.__PROD_SOCKET_URI__ = DEV_SOCKET_URI;
  });

  describe('development branch (MODE !== "production")', () => {
    // The dev arm covers everything except a deployed SPA: local dev,
    // tests, and any non-production build. It also covers the
    // `window === 'undefined'` no-op branch by reading
    // `typeof window !== 'undefined'` as true under jsdom, then
    // short-circuiting on the falsy `window.__APP_BASE__` so
    // `basePath` falls back to "/".

    test('reports the configured MODE and a non-production isDev/isProd pair', () => {
      const cfg = loadConfigWith({ mode: 'development' });
      expect(cfg.env).toBe('development');
      expect(cfg.isDev).toBe(true);
      expect(cfg.isProd).toBe(false);
    });

    test('falls back to "/" when window.__APP_BASE__ is unset', () => {
      // jsdom does not define window.__APP_BASE__, so the optional-chain
      // returns undefined and the `|| '/'` fallback fires.
      const cfg = loadConfigWith({ mode: 'development' });
      expect(cfg.basePath).toBe('/');
    });

    test('honours a window.__APP_BASE__ sub-path even when not in production', () => {
      // basePath is read on every load (it is not gated by isProd),
      // so a non-production build running against an injected base
      // — for example a Storybook mounted under /storybook/ —
      // would still pick the base up. Pin that the read happens.
      const cfg = loadConfigWith({
        mode: 'development',
        appBase: '/storybook/',
      });
      expect(cfg.basePath).toBe('/storybook/');
    });

    test('returns the build-time URIs verbatim for productionUrl/SocketUrl/developmentUrl', () => {
      // The three "URL" exports in dev mode come straight from the build
      // defines; nothing is rewritten.
      const cfg = loadConfigWith({
        mode: 'development',
        prodUri: DEV_PROD_URI,
        socketUri: DEV_SOCKET_URI,
      });
      expect(cfg.productionUrl).toBe(DEV_PROD_URI);
      expect(cfg.productionSocketUrl).toBe(DEV_SOCKET_URI);
      expect(cfg.developmentUrl).toBe('http://localhost:5173');
    });

    test('uses the build-time URIs for backendSocketUrl, backendUrl and frontendUrl in dev', () => {
      // In dev, the three URL exports mirror the build-time defines
      // exactly — the production rewrite (deployedSocketBase,
      // stripped basePath, shared origin) only fires when isProd is
      // true.
      const cfg = loadConfigWith({
        mode: 'development',
        prodUri: DEV_PROD_URI,
        socketUri: DEV_SOCKET_URI,
      });
      expect(cfg.backendSocketUrl).toBe(DEV_SOCKET_URI);
      expect(cfg.backendUrl).toBe(DEV_PROD_URI);
      expect(cfg.frontendUrl).toBe('http://localhost:5173');
    });
  });

  describe('production branch (MODE === "production")', () => {
    // The production arm is what a deployed SPA sees: basePath comes
    // from window.__APP_BASE__, and the URLs are rewritten to share
    // the deployed origin. Two sub-cases — basePath "/" (dedicated
    // subdomain via Cloudflare tunnel) and basePath "/<sub-path>/"
    // (nginx sub-path ingress) — exercise different parts of the
    // `.replace(/\/+$/, '')` strip and the `deployedSocketBase`
    // template.

    test('reports the configured MODE and a production isDev/isProd pair', () => {
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
      });
      expect(cfg.env).toBe('production');
      expect(cfg.isDev).toBe(false);
      expect(cfg.isProd).toBe(true);
    });

    test('uses window.__APP_BASE__ as basePath verbatim', () => {
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
      });
      expect(cfg.basePath).toBe(DEPLOYED_BASE);
    });

    test('keeps basePath "/" when window.__APP_BASE__ is absent in production', () => {
      // Production SPA at a dedicated subdomain — no sub-path injection.
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: null,
      });
      expect(cfg.basePath).toBe('/');
    });

    test('strips a trailing slash from basePath before building backendUrl', () => {
      // nginx injects "/ultimate-web-stack-prod/" with a trailing
      // slash. The component strips it via `.replace(/\/+$/, '')`
      // so the API lives at "<stripped>/api". Verify the strip:
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
      });
      expect(cfg.backendUrl).toBe('/ultimate-web-stack-prod');
    });

    test('builds the deployed socket URL from window.location + stripped basePath', () => {
      // The deployed socket URL must share the page origin + sub-path,
      // because the ingress strips the prefix before forwarding to the
      // backend's WS endpoint. The jsdom URL (set at the top of this
      // file) is https://test.example.com/, so the URL must be
      // wss://test.example.com/<stripped>:
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
      });
      expect(cfg.backendSocketUrl).toBe(
        `wss://test.example.com${DEPLOYED_BASE.replace(/\/+$/, '')}`
      );
    });

    test('switches the deployed socket URL to wss when window.location is https', () => {
      // The whole file runs under a jsdom env whose URL is
      // https://test.example.com/ (see the jest-environment-options
      // pragma at the top), so window.location.protocol is "https:"
      // for every test in this file — that exercises the wss arm of
      // the protocol-pick ternary, which a default http://localhost/
      // jsdom would never reach. The other tests in this describe
      // block assert the URL-building logic on top of that https base.
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
      });
      expect(cfg.backendSocketUrl).toBe(
        `wss://test.example.com${DEPLOYED_BASE.replace(/\/+$/, '')}`
      );
    });

    test('keeps productionUrl and developmentUrl identical to their build-time values', () => {
      // `productionUrl`, `productionSocketUrl` and `developmentUrl` are
      // pure build-time constants; production does NOT rewrite them.
      // `frontendUrl` is intentionally the build-time production URL,
      // not a re-derivation from basePath, so backend / other services
      // that need the canonical deployed origin keep working:
      const cfg = loadConfigWith({
        mode: 'production',
        appBase: DEPLOYED_BASE,
        prodUri: DEV_PROD_URI,
        socketUri: DEV_SOCKET_URI,
      });
      expect(cfg.productionUrl).toBe(DEV_PROD_URI);
      expect(cfg.productionSocketUrl).toBe(DEV_SOCKET_URI);
      expect(cfg.developmentUrl).toBe('http://localhost:5173');
      expect(cfg.frontendUrl).toBe(DEV_PROD_URI);
    });
  });
});