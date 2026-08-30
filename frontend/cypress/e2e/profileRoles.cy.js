// E2E coverage for src/components/EntraProfile.jsx —
// role-badge rendering and dropdown open/close transitions.
//
// EntraProfile has several conditional branches that need browser
// exercise:
//   * account?.idTokenClaims?.roles?.length > 0  → render one badge per role
//   * account?.idTokenClaims?.roles?.length === 0 → render single "None" badge
//   * dropdown-open → suppress the hover tooltip (CustomToggle onMouseEnter)
//   * location.pathname change → reset tooltip state
//   * logoutPopup → page reload (mock: sets timeout + reload)
//
// The existing profile.cy.js exercises sign-in and "Change Account"
// but does not look at the role badges explicitly. This spec covers the
// badge-rendering branches for both Admin and plain User.

import { setMockRole } from '../support/msalMock';

describe('EntraProfile — role badges', () => {
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

  it('shows the Admin role badge for an Admin user', () => {
    cy.setMockRole('Admin');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.get('[data-testid="profile-dropdown"]').click();
    cy.get('[data-testid="profile-dropdown-menu"]').should('be.visible');
    cy.get('[data-testid="role-badge-Admin"]').should('be.visible');
    cy.get('[data-testid="role-badge-none"]').should('not.exist');
  });

  it('shows the "None" badge for a User with no roles', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.get('[data-testid="profile-dropdown"]').click();
    cy.get('[data-testid="profile-dropdown-menu"]').should('be.visible');
    cy.get('[data-testid="role-badge-none"]').should('be.visible');
    cy.get('[data-testid="role-badge-Admin"]').should('not.exist');
  });

  it('opens and closes the profile dropdown repeatedly', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.get('[data-testid="profile-dropdown"]').click();
    cy.get('[data-testid="profile-dropdown-menu"]').should('be.visible');
    cy.get('[data-testid="profile-dropdown"]').click();
    cy.get('[data-testid="profile-dropdown-menu"]').should('not.be.visible');
  });
});
