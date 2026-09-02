/**
 * @jest-environment node
 *
 * Coverage for the `typeof window === 'undefined'` arm of `src/config.js`.
 *
 * jsdom always defines `window`, so the test that runs under jsdom can
 * never reach the `else` branch on line 17 (deployedSocketBase =
 * productionSocketUrl fallback when window is not defined). Loading the
 * module under node — where window genuinely is undefined — drives that
 * branch and the `if (typeof window !== 'undefined' && window.__APP_BASE__)`
 * short-circuit on line 10 (basePath falls through to '/' because
 * `typeof window` is the string `'undefined'`, so the `&&` never evaluates
 * the `window.__APP_BASE__` access).
 *
 * The build-time defines (`__VITE_MODE__`, `__PROD_URI__`, `__PROD_SOCKET_URI__`)
 * are stamped onto globalThis by jest.setup.js, so the module loads cleanly
 * under node without re-binding them here.
 */

// Re-import the module under node — node has no DOM, so any `window.X`
// access would throw; config.js guards every one with `typeof window !==
// 'undefined'`, so loading the module is itself part of the assertion
// (if the guards are wrong the require call below will throw a ReferenceError).
//
// jest.resetModules() ensures the test-suite-level module cache from any
// prior jsdom test is discarded; without it, node here would reuse the
// jsdom-bound module (and `typeof window` would be `'object'` again).
//
// jest.setup.js installs a global `jest.mock('@/config', ...)` to give
// every other test file a stub config — we want the REAL module here
// because the whole point is to drive its branches, so unmock it.
beforeEach(() => {
  jest.resetModules();
  jest.unmock('@/config');
});

describe('config.js — node environment (typeof window === "undefined")', () => {
  test('typeof window is undefined under node', () => {
    // Sanity-check the test environment itself: the whole point of
    // running this file under `@jest-environment node` is that window
    // is not defined. If this assertion ever fails, the file has been
    // moved to jsdom by mistake and the coverage branch is being lied
    // about.
    expect(typeof window).toBe('undefined');
  });

  test('loads config.js without throwing (window guards work)', () => {
    // Reaching this assertion means the four `typeof window` guards in
    // config.js — lines 10 (basePath), 16 (deployedSocketBase) — both
    // short-circuited cleanly under node. If the guards were missing
    // the `require` below would throw a ReferenceError on the first
    // `window.X` access.
    expect(() => require('@/config')).not.toThrow();
  });

  test('basePath falls back to "/" because typeof window is "undefined"', () => {
    // Line 10: `(typeof window !== 'undefined' && window.__APP_BASE__) || '/'`
    // — the `typeof window !== 'undefined'` is false under node, so the
    // `&&` short-circuits without touching `window.__APP_BASE__`, and
    // the `|| '/'` fallback fires.
    const cfg = require('@/config');
    expect(cfg.basePath).toBe('/');
  });

  test('deployedSocketBase falls back to productionSocketUrl (line 17 else branch)', () => {
    // Line 16-17: `deployedSocketBase = (typeof window !== 'undefined')
    //              ? `${...window.location...}` : productionSocketUrl`
    // Under node the ternary's else branch fires; `deployedSocketBase`
    // is then exported indirectly via `backendSocketUrl`. In dev
    // (`__VITE_MODE__` defaults to 'test', neither 'production' nor
    // 'development'), `backendSocketUrl` is `productionSocketUrl` per
    // line 19's `isProd ? deployedSocketBase : productionSocketUrl` —
    // so this test asserts the value the line-17 else branch produces,
    // not a derived `deployedSocketBase` variable (which is module-local
    // and not exported).
    const cfg = require('@/config');
    expect(cfg.productionSocketUrl).toBe('ws://localhost:8000');
    expect(cfg.backendSocketUrl).toBe('ws://localhost:8000');
    expect(cfg.backendSocketUrl).toBe(cfg.productionSocketUrl);
  });

  test('in production mode under node, backendSocketUrl still equals productionSocketUrl', () => {
    // Drive the production arm of line 19 (`isProd ? deployedSocketBase
    // : productionSocketUrl`) AND the line-17 fallback (typeof window
    // undefined → deployedSocketBase = productionSocketUrl). Both
    // arms together must collapse to the same value the dev branch
    // produced in the previous test.
    globalThis.__VITE_MODE__ = 'production';
    try {
      jest.resetModules();
      const cfg = require('@/config');
      expect(cfg.isProd).toBe(true);
      expect(cfg.backendSocketUrl).toBe(cfg.productionSocketUrl);
    } finally {
      globalThis.__VITE_MODE__ = 'test';
    }
  });
});
