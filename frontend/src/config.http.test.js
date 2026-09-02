/**
 * @jest-environment jsdom
 * @jest-environment-options {"url": "http://test.example.com/"}
 *
 * Coverage for the `ws://...` arm of the line-17 ternary in src/config.js:
 * `window.location.protocol === 'https:' ? 'wss' : 'ws'`.
 *
 * The main config.test.js runs under jsdom at https://test.example.com/
 * (so the `wss` arm of the ternary fires for the deployed socket URL).
 * To drive the `ws` arm — i.e. when the SPA is served over plain HTTP,
 * e.g. a local dev preview — this file mounts jsdom at http://test.example.com/
 * so `window.location.protocol === 'https:'` is false and the ternary
 * picks `'ws'`.
 *
 * The build-time defines (`__VITE_MODE__`, `__PROD_URI__`, `__PROD_SOCKET_URI__`)
 * are stamped onto globalThis by jest.setup.js, so the module loads cleanly
 * under jsdom without re-binding them here.
 */

beforeEach(() => {
  jest.resetModules();
  jest.unmock('@/config');
});

describe('config.js — http jsdom (line 17 ws ternary branch)', () => {
  test('window.location.protocol is "http:" under this test environment', () => {
    // Sanity check: if this ever fails the file has been moved off the
    // http:// jsdom env and the coverage branch it asserts is being lied
    // about. Re-pinning the URL is a one-line change in the pragma.
    expect(typeof window).toBe('object');
    expect(window.location.protocol).toBe('http:');
  });

  test('loads config.js without throwing under http jsdom', () => {
    expect(() => require('@/config')).not.toThrow();
  });

  test('production-mode deployed socket URL uses ws:// (not wss://) under http', () => {
    // Line 17 ternary: with window.location.protocol === 'http:', the
    // ternary's else branch picks 'ws' instead of 'wss'. Drive the
    // production arm of config.js so the full template literal is
    // exercised and the ws prefix is asserted.
    globalThis.__VITE_MODE__ = 'production';
    window.__APP_BASE__ = '/ultimate-web-stack-prod/';
    try {
      jest.resetModules();
      const cfg = require('@/config');
      expect(cfg.isProd).toBe(true);
      expect(cfg.backendSocketUrl).toBe(
        `ws://test.example.com/ultimate-web-stack-prod`,
      );
      // The same expression picks 'wss' under https; assert it does NOT
      // here so a future flip of the protocol-pick ternary would fail
      // loudly.
      expect(cfg.backendSocketUrl.startsWith('wss://')).toBe(false);
    } finally {
      globalThis.__VITE_MODE__ = 'test';
      delete window.__APP_BASE__;
    }
  });

  test('production-mode deployed socket URL strips trailing slashes from basePath (http)', () => {
    // Same as above but with a basePath that has a trailing slash, so the
    // `.replace(/\/+$/, '')` strip on line 17 is exercised under the
    // http:// jsdom environment. The strip logic itself is also covered
    // under https in config.test.js; this test pins it specifically for
    // the http arm so the protocol flip doesn't break the strip.
    globalThis.__VITE_MODE__ = 'production';
    window.__APP_BASE__ = '/ultimate-web-stack-prod/';
    try {
      jest.resetModules();
      const cfg = require('@/config');
      expect(cfg.backendSocketUrl).toBe(
        `ws://test.example.com/ultimate-web-stack-prod`,
      );
      expect(cfg.backendSocketUrl.endsWith('//')).toBe(false);
    } finally {
      globalThis.__VITE_MODE__ = 'test';
      delete window.__APP_BASE__;
    }
  });
});
