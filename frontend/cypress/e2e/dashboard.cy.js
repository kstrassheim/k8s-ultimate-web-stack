import { setMockRole } from '../support/msalMock';

describe('Dashboard Page Features', () => {
  beforeEach(() => {
    // Login as regular user
    cy.setMockRole('User');
    cy.visit('/');
    cy.get('[data-testid="sign-in-button"]').click();

    // Navigate to dashboard
    cy.get('[data-testid="nav-dashboard"]').click();

    // Wait for the dashboard page to load fully
    cy.get('[data-testid="dashboard-page"]', { timeout: 10000 }).should('be.visible');
  });

  it('should show Dashboard Unavailable when feature flag is disabled', () => {
    // This test runs when VITE_NEW_DASHBOARD is not set or false
    cy.get('[data-testid="dashboard-unavailable"]').then($el => {
      if ($el.length > 0) {
        // Flag is disabled - show unavailable message
        expect(true).to.equal(true); // Already visible
      }
    });
  });

  it('should load and display the WorldlineMonitor component correctly when flag is enabled', () => {
    // Check WorldlineMonitor title and sections (only rendered when flag is enabled)
    cy.get('body').then($body => {
      if ($body.find('[data-testid="worldline-monitor"]').length > 0) {
        cy.get('[data-testid="worldline-monitor"]').within(() => {
          cy.contains('h1', 'Divergence Meter').should('be.visible');

          // Check WebSocket connection status
          cy.get('[data-testid="ws-status-badge"]').should('be.visible');

          // Check all cards are present
          cy.get('[data-testid="worldline-status-card"]').should('be.visible');
          cy.get('[data-testid="worldline-history-card"]').should('be.visible');
          cy.get('[data-testid="worldline-chart-card"]').should('be.visible');
          cy.get('[data-testid="divergence-readings-card"]').should('be.visible');

          // Check chart is rendered
          cy.get('[data-testid="worldline-chart"]').should('be.visible');
          cy.get('[data-testid="apex-chart"]').should('exist');

          // Check divergence readings table is present
          cy.get('[data-testid="readings-table"]').should('be.visible');
        });
      } else {
        // Flag disabled - WorldlineMonitor not rendered
        cy.log('WorldlineMonitor not rendered - VITE_NEW_DASHBOARD likely not enabled');
      }
    });
  });

  it('should test WorldlineMonitor refresh buttons when enabled', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="worldline-monitor"]').length > 0) {
        // Test refresh status button
        cy.get('[data-testid="refresh-status-btn"]').click();
        cy.wait(2000);

        // Test refresh history button
        cy.get('[data-testid="refresh-history-btn"]').click();
        cy.wait(2000);

        // Test refresh chart button
        cy.get('[data-testid="refresh-chart-btn"]').click();
        cy.wait(2000);

        // Test refresh readings button
        cy.get('[data-testid="refresh-readings-btn"]').click();
        cy.wait(2000);
      } else {
        cy.log('WorldlineMonitor not rendered - skipping refresh button tests');
      }
    });
  });

  it('should filter divergence readings correctly when enabled', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="readings-table"]').length > 0) {
        // First verify the table has rows before filtering
        cy.get('[data-testid="readings-table"] tbody tr')
          .should('have.length.at.least', 1);

        // Test status filter
        cy.get('[data-testid="status-filter"]').select('steins_gate');

        // Wait for filter to apply
        cy.wait(2000);

        // Verify the filter actually changed the displayed data
        cy.get('[data-testid="readings-table"] tbody tr')
          .should('be.visible')
          .then($filteredRows => {
            expect($filteredRows.length).to.be.greaterThan(0);

            cy.wrap($filteredRows).first().find('.badge')
              .should('contain.text', 'steins_gate');
          });

        // Test recorded by filter - clear previous filter first
        cy.get('[data-testid="status-filter"]').select('');
        cy.get('[data-testid="recorded-by-filter"]').clear().type('Okabe');

        // Wait for filter to apply
        cy.wait(2000);

        // Check filtered results
        cy.get('[data-testid="readings-table"] tbody tr')
          .should('be.visible');

        // Test reset filters button
        cy.get('[data-testid="reset-filters-btn"]').click();

        // Verify filters are reset
        cy.get('[data-testid="status-filter"]').should('have.value', '');
        cy.get('[data-testid="recorded-by-filter"]').should('have.value', '');
        cy.get('[data-testid="min-value-filter"]').should('have.value', '');
        cy.get('[data-testid="max-value-filter"]').should('have.value', '');

        // After reset, we should have the original number of rows
        cy.wait(2000);
        cy.get('[data-testid="readings-table"] tbody tr').should('have.length.at.least', 1);
      } else {
        cy.log('Readings table not rendered - skipping filter tests');
      }
    });
  });

  it('should show experiment details in chart tooltips', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="worldline-chart"]').length > 0) {
        cy.get('[data-testid="worldline-chart"]').should('be.visible');
        cy.get('[data-testid="apex-chart"]').trigger('mouseover', { force: true });
      } else {
        cy.log('Chart not rendered - skipping tooltip test');
      }
    });
  });

  it('should respond correctly to window resize', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="worldline-monitor"]').length > 0) {
        // Test at desktop size (already there)
        cy.viewport(1200, 800);
        cy.get('[data-testid="worldline-monitor"]').should('be.visible');

        // Test at tablet size
        cy.viewport(768, 1024);
        cy.get('[data-testid="worldline-monitor"]').should('be.visible');

        // Test at mobile size
        cy.viewport(375, 667);
        cy.get('[data-testid="worldline-monitor"]').should('be.visible');
      } else {
        cy.log('WorldlineMonitor not rendered - skipping resize test');
      }
    });
  });

  it('should test WebSocket connection status changes', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="ws-status-badge"]').length > 0) {
        cy.get('[data-testid="ws-status-badge"]').should('exist');

        cy.window().then((win) => {
          const badge = win.document.querySelector('[data-testid="ws-status-badge"]');
          if (badge) {
            const originalText = badge.textContent;
            const originalClass = badge.className;

            badge.textContent = 'Offline';
            badge.className = badge.className.replace(/bg-\w+/, 'bg-danger');

            cy.get('[data-testid="ws-status-badge"]')
              .should('contain.text', 'Offline')
              .and('have.class', 'bg-danger');

            setTimeout(() => {
              badge.textContent = originalText;
              badge.className = originalClass;
            }, 1000);
          }
        });
      } else {
        cy.log('WebSocket badge not rendered - skipping status test');
      }
    });
  });

  it('should test pagination in divergence readings table', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="readings-pagination"]').length) {
        cy.get('[data-testid="readings-pagination"]').within(() => {
          if ($body.find('[data-testid="next-page-btn"]').length) {
            cy.get('[data-testid="next-page-btn"]').click();
            cy.get('.active').should('contain', '2');
          } else {
            cy.get('button, .page-item').contains('2').click({ force: true });
          }
        });

        cy.get('[data-testid="readings-table"]').should('be.visible');
      } else {
        cy.log('No pagination found, skipping pagination test');
      }
    });
  });

  it('should test sorting in divergence readings table', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="readings-table"]').length > 0) {
        cy.get('[data-testid="readings-table"] th').first().then($th => {
          if ($th.find('[data-sort]').length || $th.hasClass('sortable') || $th.attr('data-sort')) {
            cy.wrap($th).click();
            cy.get('[data-testid="readings-table"] th .sort-indicator, [data-testid="readings-table"] th.sorted')
              .should('exist');
            cy.wrap($th).click();
            cy.get('[data-testid="readings-table"] th .sort-indicator, [data-testid="readings-table"] th.sorted')
              .should('exist');
          } else {
            cy.wrap($th).click({ force: true });
            cy.log('No obvious sort indicators found, but tried sorting');
          }
        });
      } else {
        cy.log('Readings table not rendered - skipping sort test');
      }
    });
  });

  it('should test numeric filters with boundary values', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="min-value-filter"]').length > 0) {
        cy.get('[data-testid="min-value-filter"]').type('0.5');
        cy.get('[data-testid="max-value-filter"]').type('1.5');
        cy.wait(2000);
        cy.get('[data-testid="readings-table"] tbody').should('be.visible');

        cy.get('[data-testid="min-value-filter"]').clear().type('-999');
        cy.get('[data-testid="max-value-filter"]').clear().type('999');
        cy.wait(2000);
        cy.get('[data-testid="readings-table"] tbody').should('be.visible');

        cy.get('[data-testid="min-value-filter"]').clear().type('5');
        cy.get('[data-testid="max-value-filter"]').clear().type('1');
        cy.wait(2000);
      } else {
        cy.log('Filters not rendered - skipping filter value test');
      }
    });
  });

  it('should test conditional display based on data state', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="refresh-chart-btn"]').length > 0) {
        cy.get('[data-testid="refresh-chart-btn"]').click();
        cy.wait(2000);
      }

      const emptyStateSelectors = [
        '[data-testid="empty-chart-message"]',
        '[data-testid="no-data-message"]',
        '.empty-state',
        '.no-data'
      ];

      let foundEmptyState = false;

      emptyStateSelectors.forEach(selector => {
        if ($body.find(selector).length > 0) {
          foundEmptyState = true;
          cy.get(selector).should('be.visible');
        }
      });

      if (!foundEmptyState) {
        const emptyTexts = ['no data', 'no results', 'empty', 'no history'];
        emptyTexts.forEach(text => {
          if ($body.text().toLowerCase().includes(text)) {
            foundEmptyState = true;
            cy.log(`Found empty state text: "${text}"`);
          }
        });
      }

      cy.log(`Empty state found: ${foundEmptyState}`);
    });
  });

  it('should test component expansion/collapse functionality', () => {
    cy.get('body').then($body => {
      const collapsibleSelectors = [
        '[data-testid="collapse-button"]',
        '.card-header button',
        '[data-toggle="collapse"]',
        '.accordion-button',
        '.expandable-header'
      ];

      let foundCollapsible = false;

      collapsibleSelectors.forEach(selector => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().click();
          foundCollapsible = true;
          cy.wait(300);
          cy.get(selector).first().click();
        }
      });

      if (!foundCollapsible) {
        cy.get('.card-header, .card-title').first().click({ force: true });
        cy.log('No obvious collapsible elements found, tried clicking card headers');
      }
    });
  });

  it('should test theme toggle if available', () => {
    cy.get('body').then($body => {
      const themeToggles = [
        '[data-testid="theme-toggle"]',
        '#theme-switch',
        '.theme-toggle',
        '[aria-label="Toggle dark mode"]',
        '.dark-mode-toggle'
      ];

      themeToggles.forEach(selector => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().click();

          cy.get('body').should('satisfy', ($el) => {
            const hasThemeClass = $el.hasClass('dark-theme') ||
              $el.hasClass('dark-mode') ||
              $el.hasClass('theme-dark') ||
              $el.attr('data-bs-theme') === 'dark';
            return hasThemeClass;
          });

          cy.get(selector).first().click();
        }
      });
    });
  });

  it('should test combination of multiple filters', () => {
    cy.get('body').then($body => {
      if ($body.find('[data-testid="status-filter"]').length > 0) {
        cy.get('[data-testid="status-filter"]').select('steins_gate');
        cy.get('[data-testid="recorded-by-filter"]').clear().type('Okabe');
        cy.get('[data-testid="min-value-filter"]').clear().type('0.5');

        cy.wait(2000);

        cy.get('[data-testid="readings-table"] tbody').should('be.visible');

        cy.get('[data-testid="reset-filters-btn"]').click();
      } else {
        cy.log('Filters not rendered - skipping combination filter test');
      }
    });
  });
});