// E2E coverage for src/pages/404.jsx
//
// The 404 page renders for any path that doesn't match the other <Route>s.
// It fires appInsights.trackEvent({ name: '404 - NotFound page' }) on mount,
// surfaces a "Goto Home" link, and is the *only* route element that handles
// the wildcard path in App.jsx. Until this spec existed the page was
// produced as part of `Routes` but never visited end-to-end, so the
// trackEvent + link assertions stayed at zero coverage.

describe('NotFound (404) Page', () => {
  beforeEach(() => {
    cy.on('uncaught:exception', (err) => {
      console.error('Uncaught exception:', err);
      return false;
    });
  });

  it('renders the 404 page for an unknown route', () => {
    cy.visit('/this-route-does-not-exist');
    cy.get('[data-testid="not-found-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="not-found-heading"]').should('contain.text', '404');
  });

  it('renders the 404 page for a deeply nested unknown route', () => {
    cy.visit('/some/deeply/nested/unknown/path/with/segments');
    cy.get('[data-testid="not-found-page"]', { timeout: 10000 }).should('be.visible');
    cy.get('[data-testid="not-found-heading"]').should('contain.text', '404');
  });

  it('offers a working link back to Home', () => {
    cy.visit('/totally-unknown');
    cy.get('[data-testid="not-found-page"]').should('be.visible');
    cy.get('[data-testid="not-found-home-link"]')
      .should('be.visible')
      .and('have.attr', 'href')
      .then((href) => {
        // href is a string in React Router — check the path portion
        expect(href).to.match(/\/$/);
      });
    cy.get('[data-testid="not-found-home-link"]').click();
    cy.url().should('match', /\/(?:home)?$/);
    cy.get('[data-testid="home-page"]', { timeout: 10000 }).should('be.visible');
  });
});
