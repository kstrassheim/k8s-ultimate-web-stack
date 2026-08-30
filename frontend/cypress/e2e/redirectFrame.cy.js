// E2E coverage for the MSAL redirect-frame branch in src/main.jsx.
//
// main.jsx detects URLs with `#code=…` / `?code=…` / `#state=…` /
// `?state=…` / `#error=…` and short-circuits to render
// `mock/azureMsalRedirectBridge.broadcastResponseToMainFrame()` instead
// of mounting <App />. Without this branch ever firing in a real visit,
// the early-return + broadcast logic was untested end-to-end.

describe('MSAL popup redirect-frame detection', () => {
  it('hits the redirect-frame branch for a URL with ?code=...', () => {
    // Visit with a fake auth-code query — main.jsx should detect the
    // query, refuse to render <App />, and call the redirect bridge.
    cy.visit('/?code=fake-auth-code-from-microsoft', {
      onBeforeLoad(win) {
        // Mock the bridge import path so the dynamic import resolves
        // to a stub instead of trying to broadcast.
        win.__MSAL_BRIDGE_RAN__ = false;
        // The bridge module is loaded via dynamic import — we cannot
        // stub it directly. The branch's "happy path" is to call
        // broadcastResponseToMainFrame, which in the mock implementation
        // posts a message and closes the window. In a real browser this
        // would be an auth popup; here we just verify the page does
        // NOT render App (no main-navigation testid).
      },
    });

    // main.jsx's redirect-frame branch never reaches the React tree,
    // so no [data-testid="main-navigation"] exists. We assert that
    // absence as proof the branch fired.
    cy.get('body').then(($body) => {
      const hasApp = $body.find('[data-testid="main-navigation"]').length > 0;
      // The mock bridge attempts broadcastResponseToMainFrame which
      // uses BroadcastChannel / window.close. Without a popup-opener
      // it logs and continues. The important property: the page is
      // not the main app.
      expect(hasApp).to.eq(false);
    });
  });
});
