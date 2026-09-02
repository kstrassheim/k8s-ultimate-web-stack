// Custom transformer for src/config.js.
//
// Vite substitutes `import.meta.env.MODE` at build time with a literal
// ("production" or "development"); in jest the substitution never happens,
// so `import.meta.env.MODE` resolves to `undefined.MODE` and the module
// fails to load — leaving the entire file at 0% coverage. This transformer
// runs ahead of @swc/jest and rewrites the single Vite-only expression to
// a globalThis lookup, so the file loads and exercises the same branches
// in jest that Vite would inline in production. The substitution is purely
// textual and matches the exact string Vite injects, so there is no risk
// of accidentally rewriting something else.
//
// `__PROD_URI__` and `__PROD_SOCKET_URI__` are handled separately by
// jest.setup.js, which stamps them as `globalThis` values before any test
// runs; the test file controls them via `jest.replaceProperty(...)`.

const swcJest = require('@swc/jest');

const base = swcJest.createTransformer();

const VITE_MODE_PATTERN = /import\.meta\.env\.MODE/g;

function preprocess(src) {
  return src.replace(VITE_MODE_PATTERN, 'globalThis.__VITE_MODE__');
}

module.exports = {
  process(src, filename, ...rest) {
    return base.process(preprocess(src), filename, ...rest);
  },
  processAsync(src, filename, ...rest) {
    return base.processAsync(preprocess(src), filename, ...rest);
  },
  getCacheKey(src, filename, ...rest) {
    // Invalidate the cache when the source changes; include the
    // substitution marker so a refactor that drops the Vite pattern
    // produces a different cache key.
    return `${base.getCacheKey(src, filename, ...rest)}|vite-mode-sub`;
  },
  canInstrument: base.canInstrument,
};