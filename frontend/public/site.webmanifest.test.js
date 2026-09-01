/**
 * Regression guard for issue #141 — PWA install identity.
 *
 * Edge decides whether an in-app navigation stays inside the installed app
 * window by testing the target URL against the manifest's `scope`. With `id`,
 * `start_url` and `scope` all absent they are derived at INSTALL time from
 * whatever document the user happened to be on:
 *
 *   - `start_url` defaults to that document URL *including* query and
 *     fragment, so a user who installed while sitting on a post-login URL
 *     gets a start_url still carrying `?code=…`/`#state=…` — which used to
 *     trip the popup-response branch in `src/main.jsx` on every launch;
 *   - `scope` defaults to `start_url` minus its last path segment, making
 *     the in-app/out-of-app boundary install-time dependent and unauditable;
 *   - the install `id` derives from `start_url`, so changing `start_url`
 *     later orphans existing installs instead of updating them.
 *
 * That is why the reported bug reproduced for one user and not another on
 * the same build.
 *
 * MOUNT-RELATIVE, NOT ROOT-RELATIVE
 * ---------------------------------
 * Unlike the Azure sibling repo (kstrassheim/ultimate-web-stack, which pins
 * these to "/"), this deployment serves the app at two public bases at once:
 *
 *   - the domain root, through the Cloudflare tunnel, and
 *   - an nginx subpath, resolved per-request from `x-forwarded-prefix` by
 *     `_resolve_base()` in backend/main.py, with `<base href>` +
 *     `window.__APP_BASE__` injected into index.html by `_render_index()`.
 *
 * A literal "/" here would put the entire subpath deployment OUT of scope, so
 * every in-app navigation there would open in a browser window — turning an
 * intermittent bug into a guaranteed, every-user one on that mount. "./" is
 * resolved by the browser against the manifest's own URL, which yields "/" at
 * the root mount and "/<prefix>/" behind the ingress, with correctly distinct
 * install identities per mount.
 */

const fs = require('fs');
const path = require('path');

const manifestPath = path.resolve(__dirname, 'site.webmanifest');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

describe('site.webmanifest — pinned install identity (issue #141)', () => {
  test('parses as valid JSON', () => {
    expect(typeof manifest).toBe('object');
    expect(manifest).not.toBeNull();
  });

  test.each(['id', 'start_url', 'scope'])('declares %s explicitly', (field) => {
    expect(manifest[field]).toBeDefined();
  });

  test.each(['id', 'start_url', 'scope'])(
    '%s is mount-relative, never the absolute "/" that breaks the subpath mount',
    (field) => {
      // The whole point of this repo's variant of the fix: "/" is wrong here.
      expect(manifest[field]).toBe('./');
      expect(manifest[field]).not.toBe('/');
    },
  );

  test('declares display: standalone', () => {
    expect(manifest.display).toBe('standalone');
  });

  test('icon srcs are mount-relative and do not point into public/', () => {
    // Vite flattens public/ into the dist root, so a "public/…" src resolves
    // to a public/ subdirectory of the mount, where nothing is served. The
    // SPA catch-all used to answer that miss with index.html at HTTP 200 —
    // Edge asked for a PNG and got HTML, with no error anywhere.
    // backend/main.py now 404s instead (NON_SPA_SUFFIXES).
    expect(Array.isArray(manifest.icons)).toBe(true);
    expect(manifest.icons.length).toBeGreaterThan(0);
    manifest.icons.forEach((icon) => {
      expect(icon.src).not.toMatch(/^\//);
      expect(icon.src).not.toMatch(/^\.?\/?public\//);
      expect(icon.type).toBe('image/png');
    });
  });

  test('preserves the build-rewritten name fields', () => {
    // `generateWebManifest()` overwrites name / short_name from
    // terraform.config.json at build time; the values here are placeholders.
    expect(manifest.name).toBeDefined();
    expect(manifest.short_name).toBeDefined();
  });

  test('index.html links the manifest through the runtime base', () => {
    // %BASE_URL% is emitted by Vite as "./" (base: "./"), which resolves
    // against the <base href> the backend injects — so the manifest is
    // fetched from the mount the user is actually on. A root-relative
    // "/site.webmanifest" would break the subpath deployment.
    const indexHtml = fs.readFileSync(
      path.resolve(__dirname, '..', 'index.html'),
      'utf8',
    );
    expect(indexHtml).toMatch(/<link rel="manifest" href="%BASE_URL%site\.webmanifest"/);
  });
});

describe('vite.config.js — generateWebManifest preserves the identity (issue #141)', () => {
  const viteConfigSource = fs.readFileSync(
    path.resolve(__dirname, '..', 'vite.config.js'),
    'utf8',
  );

  test.each(['id', 'start_url', 'scope'])(
    "assigns manifest.%s = './' so a regenerated manifest keeps it",
    (field) => {
      // generateWebManifest() reads the checked-in file as a template and
      // rewrites name/short_name. Without these assignments a build against a
      // template that predates this fix would ship an identity-less manifest
      // and quietly re-open the bug.
      expect(viteConfigSource).toMatch(
        new RegExp(`manifest\\.${field}\\s*=\\s*'\\./'`),
      );
    },
  );

  test('normalises icon srcs off any public/ prefix', () => {
    expect(viteConfigSource).toMatch(/manifest\.icons\s*=/);
  });
});
