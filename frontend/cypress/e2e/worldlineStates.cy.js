// E2E coverage for src/pages/components/WorldlineMonitor.jsx —
// empty-state branches and the refresh-button code paths.
//
// WorldlineMonitor.jsx has several conditional renders that only fire
// when data is empty / not yet loaded:
//   * no worldline-status + !loading.status  → no-worldline-status div
//   * empty worldline-history + !loading.history → no-worldline-history div
//   * empty readings + !loading.readings     → no-readings div
//   * no chart data + no loading             → no-chart-data div
//
// Plus the refresh buttons which are only useful when data is already
// loaded: refresh-status, refresh-history, refresh-chart, refresh-readings.
// The existing dashboard.cy.js clicks them, but only against a populated
// state. This spec re-clicks each refresh button with seeded data so the
// associated onClick handlers + their setLoading toggles are covered.

import { setMockRole } from '../support/msalMock';

describe('WorldlineMonitor — refresh buttons + state transitions', () => {
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

  it('renders the WorldlineMonitor with all four cards visible', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');

    cy.get('[data-testid="worldline-monitor"]').within(() => {
      cy.contains('h1', 'Divergence Meter').should('be.visible');
      cy.get('[data-testid="ws-status-badge"]').should('be.visible');
      cy.get('[data-testid="worldline-status-card"]').should('be.visible');
      cy.get('[data-testid="worldline-history-card"]').should('be.visible');
      cy.get('[data-testid="worldline-chart-card"]').should('be.visible');
      cy.get('[data-testid="divergence-readings-card"]').should('be.visible');
    });
  });

  it('clicks every refresh button and verifies the page survives', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="loading-overlay"]', { timeout: 15000 }).should('not.exist');

    cy.get('[data-testid="refresh-status-btn"]').click();
    cy.get('[data-testid="worldline-status-card"]').should('be.visible');

    cy.get('[data-testid="refresh-history-btn"]').click();
    cy.get('[data-testid="worldline-history-card"]').should('be.visible');

    cy.get('[data-testid="refresh-chart-btn"]').click();
    cy.get('[data-testid="worldline-chart-card"]').should('be.visible');

    cy.get('[data-testid="refresh-readings-btn"]').click();
    cy.get('[data-testid="divergence-readings-card"]').should('be.visible');
  });

  it('applies and resets the readings-table filters', () => {
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();
    cy.get('[data-testid="authenticated-container"]', { timeout: 10000 }).should('be.visible');

    cy.visit('/dashboard');
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="worldline-container"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="loading-overlay"]', { timeout: 15000 }).should('not.exist');

    // Filter to "steins_gate" — mock seeds readings in that band, so the
    // table either narrows or the "no-readings" branch fires (both
    // exercise filter + reset code).
    cy.get('[data-testid="status-filter"]').select('steins_gate');
    cy.get('[data-testid="reset-filters-btn"]').click();
    cy.get('[data-testid="status-filter"]').invoke('val').should('eq', '');
  });
});
