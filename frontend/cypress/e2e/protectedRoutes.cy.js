// E2E coverage for src/components/ProtectedRoute.jsx + ProtectedLink.jsx
//
// ProtectedRoute has three branches:
//   1. no active account           → redirect to /access-denied (unauth branch)
//   2. insufficient roles          → redirect to /access-denied with requiredRoles
//   3. account + all roles match   → render children (the wrapped page)
//
// ProtectedLink has three render branches that mirror ProtectedRoute's
// authentication check but inline in JSX:
//   1. no account, showIfUnauthenticated=false → null (hidden)
//   2. requiredRoles=[] (empty)                 → render children
//   3. account, all roles match                 → render children
//   4. account, missing a required role         → null
//
// All three branches of both components need to be exercised. The existing
// nav.spec covers branch 3 implicitly; this spec hits branches 1, 2, and 4.

import { setMockRole } from '../support/msalMock';

describe('ProtectedRoute — auth/role gating', () => {
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

  it('redirects an unauthenticated visitor to /access-denied (no-account branch)', () => {
    cy.setMockRole('None');
    // Dashboard requires any authenticated user (requiredRoles=[]); an
    // unauthenticated user hits the no-account branch and gets bounced
    // via <Navigate> to /access-denied with state.requiredRoles unset.
    cy.visit('/dashboard');
    cy.url({ timeout: 10000 }).should('include', '/access-denied');
  });

  it('redirects a User trying to reach the Admin-only Experiments page (insufficient-permissions branch)', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/experiments');
    cy.url({ timeout: 10000 }).should('include', '/access-denied');
    cy.get('[data-testid="access-denied-required-roles"]').should('contain.text', 'Admin');
  });

  it('renders the wrapped child for an authenticated user with the required role', () => {
    cy.setMockRole('Admin');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/experiments');
    cy.get('[data-testid="experiments-heading"]', { timeout: 10000 }).should('be.visible');
    cy.url().should('include', '/experiments');
  });
});

describe('ProtectedLink — visibility branches', () => {
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

  it('hides an Admin-only nav link from unauthenticated visitors', () => {
    cy.setMockRole('None');
    cy.visit('/');
    // App.jsx wraps the Experiments nav item in <ProtectedLink requiredRoles=["Admin"]>
    cy.get('[data-testid="nav-experiments"]').should('not.exist');
    // Sanity: the unauthenticated sign-in button IS visible.
    cy.get('[data-testid="sign-in-button"]').should('be.visible');
  });

  it('hides an Admin-only nav link from a User (insufficient roles)', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="nav-experiments"]').should('not.exist');
  });

  it('shows an Admin-only nav link to an Admin', () => {
    cy.setMockRole('Admin');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="nav-experiments"]').should('be.visible');
  });
});
