// E2E coverage for src/pages/AccessDenied.jsx
//
// The AccessDenied page has two distinct render branches, driven by the
// `requiredRoles` value that ProtectedRoute passes via `location.state`:
//   * requiredRoles.length > 0 → "permission" message + roles list
//   * requiredRoles missing/empty → "sign in" prompt
// Until this spec existed neither branch was being exercised through the
// browser — the prior coverage was limited to the unit test which mocks
// the router entirely.

import { setMockRole } from '../support/msalMock';

describe('AccessDenied Page — both render branches', () => {
  beforeEach(() => {
    cy.on('uncaught:exception', (err) => {
      console.error('Uncaught exception:', err);
      return false;
    });
    cy.window().then((win) => {
      win.localStorage.clear();
      win.sessionStorage.clear();
    });
  });

  it('shows the "please sign in" branch when an unauthenticated user hits a protected route', () => {
    cy.setMockRole('None');
    // Visit Dashboard which is wrapped in ProtectedRoute requiredRoles=[]
    // (empty roles means "any authenticated user"; an unauthenticated user
    // hits the no-account branch and gets bounced to /access-denied with
    // state.requiredRoles unset.)
    cy.visit('/dashboard');
    cy.url({ timeout: 10000 }).should('include', '/access-denied');
    cy.get('[data-testid="access-denied-page"]').should('be.visible');
    cy.get('[data-testid="access-denied-heading"]').should('contain.text', 'Access Denied');
    cy.get('[data-testid="access-denied-login-message"]').should('be.visible');
    cy.get('[data-testid="access-denied-signin-prompt"]').should('be.visible');
    // role message should NOT appear on the unauthenticated branch
    cy.get('[data-testid="access-denied-role-message"]').should('not.exist');
    cy.get('[data-testid="access-denied-required-roles"]').should('not.exist');
  });

  it('shows the "permission" branch when a low-privilege user hits an Admin-only route', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    // /experiments requires the Admin role; a plain User has insufficient
    // permissions and ProtectedRoute redirects with state.requiredRoles=['Admin'].
    cy.visit('/experiments');
    cy.url({ timeout: 10000 }).should('include', '/access-denied');
    cy.get('[data-testid="access-denied-page"]').should('be.visible');
    cy.get('[data-testid="access-denied-heading"]').should('contain.text', 'Access Denied');
    cy.get('[data-testid="access-denied-role-message"]').should('be.visible');
    cy.get('[data-testid="access-denied-required-roles"]').should('contain.text', 'Admin');
    // login-prompt branch should NOT appear here
    cy.get('[data-testid="access-denied-login-message"]').should('not.exist');
    cy.get('[data-testid="access-denied-signin-prompt"]').should('not.exist');
  });
});
