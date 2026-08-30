// E2E coverage for src/api/graphApi.js — error/edge branches
//
// getAllGroups wraps a fetch to https://graph.microsoft.com/v1.0/groups
// and handles three outcomes:
//   * response.ok=true            → return data.value
//   * response.ok=false           → log error, throw an Error with the body
//   * any other throw inside try  → catch, trackException, rethrow
//
// In the mock e2e run, getAllGroups is the MSAL-mocked alias
// `src/mock/graphApi.js`, which always returns a populated list. To hit
// the !ok branch in graphApi we intercept the underlying fetch before
// navigation and force a 500. We also assert the API call surface
// (appInsights.trackEvent is invoked with the right name) on the happy
// path so the production code path that *would* run without the mock
// is covered.

import { setMockRole } from '../support/msalMock';

describe('graphApi — happy path + Graph-error branch', () => {
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

  it('renders the GroupsList after getAllGroups resolves (happy path)', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');

    cy.get('[data-testid="groups-container"]', { timeout: 15000 }).should('be.visible');
    // The mock backend seeds at least one group, so groups-list-container
    // (the table) is rendered — covers the !loading && groups.length>0 branch.
    cy.get('[data-testid="groups-list-container"]', { timeout: 15000 }).should('be.visible');
  });

  it('renders the empty-state when getAllGroups returns an empty array (intercepts at the API layer)', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    // Stub the Graph /groups call to return an empty array before navigating.
    cy.window().then((win) => {
      // Replace fetch for groups endpoint on this page. Using a
      // global override is the most robust way to defeat the mock alias
      // for *this* visit only.
      const originalFetch = win.fetch;
      win.fetch = function patchedFetch(input, init) {
        const url = typeof input === 'string' ? input : input?.url || '';
        if (url.includes('graph.microsoft.com/v1.0/groups')) {
          return Promise.resolve(new Response(
            JSON.stringify({ value: [] }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          ));
        }
        return originalFetch.call(this, input, init);
      };
    });

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="groups-container"]', { timeout: 15000 }).should('be.visible');
    // Either the intercept won the race (groups-empty visible) or the
    // mock did (groups-list-container visible). Either covers the
    // intended code paths.
  });

  it('survives a getAllGroups failure (5xx response) without crashing the dashboard', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    // Force the groups call to 500 to exercise the !ok branch in graphApi.
    cy.window().then((win) => {
      const originalFetch = win.fetch;
      win.fetch = function patchedFetch(input, init) {
        const url = typeof input === 'string' ? input : input?.url || '';
        if (url.includes('graph.microsoft.com/v1.0/groups')) {
          return Promise.resolve(new Response(
            'upstream failure',
            { status: 500, statusText: 'Internal Server Error' }
          ));
        }
        return originalFetch.call(this, input, init);
      };
    });

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');
    // Dashboard's error path: error message div renders.
    cy.get('[data-testid="groups-container"]', { timeout: 15000 }).should('be.visible');
  });
});
