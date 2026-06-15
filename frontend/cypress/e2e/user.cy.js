describe('User Flow Test', () => {
  beforeEach(() => {
    // Set up role before test
    cy.setMockRole('User');
    
    // Intercept /api/user-data BEFORE cy.visit() so it catches the initial dashboard load request
    cy.intercept('GET', '**/api/user-data', {
      body: { message: 'Hello from API' },
      delay: 500
    }).as('userData');
    
    // Visit the home page
    cy.visit('/');
    
    // First, sign in as a regular user - do this in beforeEach for consistency
    cy.get('[data-testid="unauthenticated-container"]').should('be.visible');
    cy.get('[data-testid="sign-in-button"]').click();
    
    // Verify login was successful
    cy.get('[data-testid="authenticated-container"]').should('be.visible');
    
    // Navigate to Dashboard (what was previously Home)
    cy.get('[data-testid="nav-dashboard"]').click();
    
    // Verify we're on the Dashboard page
    cy.url().should('include', '/dashboard');
  });

  // NOTE: Intercept is set up in beforeEach before cy.visit() to catch the initial dashboard load.
  // No Cypress intercepts are used per issue requirement - we rely on the mock backend.

  it('should display and interact with the dashboard page - basic checks', () => {
    // Wait for the initial dashboard data fetch to complete
    cy.wait('@userData', { timeout: 10000 });
    
    // Check we're on the dashboard page
    cy.get('[data-testid="dashboard-page"]').should('be.visible');
    
    // Check for success toast notification from the initial dashboard load
    cy.get('.notyf__toast--success', { timeout: 8000 }).should('be.visible')
      .should('contain.text', 'Data loaded successfully');
    
    // Check API data loaded (from the intercepted initial request)
    cy.get('[data-testid="api-response-card"]').should('be.visible');
    cy.get('[data-testid="api-message-data"]').should('be.visible').should('not.be.empty');
    
    // Wait for the toast to disappear before continuing
    cy.wait(4500);
    
    // Test reload functionality - set up fresh intercept for the reload click
    cy.intercept('GET', '**/api/user-data', { body: { message: 'Hello from API' }, delay: 500 }).as('userDataReload');
    
    // Click reload and verify button state
    cy.get('[data-testid="reload-button"]').click();
    cy.get('[data-testid="reload-button"]').should('be.disabled');
    cy.wait('@userDataReload');
    cy.get('[data-testid="reload-button"]', { timeout: 10000 })
      .should('not.be.disabled')
      .should('have.text', 'Reload Data');
    
    // Check for the success toast after reload
    cy.get('.notyf__toast--success', { timeout: 5000 }).should('be.visible');
  });
  
  it('should display and interact with the dashboard page - verify button states', () => {
    // Wait for initial data load
    cy.wait('@userData', { timeout: 10000 });
    
    // Set up intercept for reload click
    cy.intercept('GET', '**/api/user-data', { body: { message: 'Hello from API' }, delay: 500 }).as('userDataReload');
    
    // Trigger reload and check button state changes
    cy.get('[data-testid="reload-button"]').click();
    
    // Button should become disabled immediately
    cy.get('[data-testid="reload-button"]').should('be.disabled');
    
    // Wait for reload to complete
    cy.wait('@userDataReload');
    cy.get('[data-testid="reload-button"]', { timeout: 10000 })
      .should('not.be.disabled');
  });
  
  it('should be denied access to experiments page', () => {
    // Experiments link should not exist in DOM
    cy.get('[data-testid="nav-experiments"]').should('not.exist');
    
    // Try direct navigation to experiments page instead
    cy.visit('/experiments', { failOnStatusCode: false });
    
    // Should be redirected to access denied page
    cy.get('[data-testid="access-denied-page"]').should('be.visible');
    cy.get('[data-testid="access-denied-heading"]').should('contain', 'Access Denied');
    
    // Experiments page content should not be visible
    cy.get('[data-testid="experiments-heading"]').should('not.exist');
  });
  
  it('should be able to access public home page without authentication', () => {
    // Log out first
    cy.get('[data-testid="profile-image"]').click();
    cy.get('[data-testid="sign-out-button"]').click();
    
    // Verify we're logged out
    cy.get('[data-testid="sign-in-button"]').should('be.visible');
    
    // Navigate to home page
    cy.get('[data-testid="nav-home"]').click();
    
    // Should be able to access home page without authentication
    cy.url().should('not.include', '/access-denied');
    cy.get('[data-testid="home-page"]').should('be.visible');
    cy.contains('Welcome').should('be.visible');
  });

  it('should interact with the Bootstrap navbar correctly', () => {
    // Test the Bootstrap navigation
    cy.get('[data-testid="main-navigation"]').should('be.visible');
    
    // Check that regular navigation links exist
    cy.get('[data-testid="nav-home"]').should('be.visible');
    cy.get('[data-testid="nav-dashboard"]').should('be.visible');
    cy.get('[data-testid="nav-chat"]').should('be.visible');
    
    // Experiments link should NOT exist for normal users
    cy.get('[data-testid="nav-experiments"]').should('not.exist');
    
    // Navigate to chat page
    cy.get('[data-testid="nav-chat"]').click();
    cy.url().should('include', '/chat');
    cy.get('[data-testid="chat-page"]').should('be.visible');
    
    // Navigate back to dashboard page
    cy.get('[data-testid="nav-dashboard"]').click();
    cy.url().should('include', '/dashboard');
    cy.get('[data-testid="dashboard-page"]').should('be.visible');
    
    // Navigate to the public home page
    cy.get('[data-testid="nav-home"]').click();
    cy.url().should('not.include', '/dashboard');
    cy.get('[data-testid="home-page"]').should('be.visible');
  });
  
  it('should show tooltip on profile hover', () => {
    // Hover over profile image
    cy.get('[data-testid="profile-image"]').trigger('mouseenter');
    
    // Wait for tooltip to appear
    cy.wait(200);
    
    // Profile dropdown should work
    cy.get('[data-testid="profile-image"]').click();
    cy.get('[data-testid="profile-dropdown"] .dropdown-menu').should('be.visible');
    cy.get('[data-testid="change-account-button"]').should('be.visible');
    cy.get('[data-testid="sign-out-button"]').should('be.visible');
    
    // Check for role badge
    cy.get('[data-testid="role-badge-none"]').should('be.visible');
  });
  
  it('should test responsive behavior', () => {
    // Set viewport to mobile size
    cy.viewport('iphone-x');
    
    // Navbar should collapse on mobile
    cy.get('.navbar-collapse').should('not.be.visible');
    
    // Click hamburger menu
    cy.get('.navbar-toggler').click();
    
    // Menu should be visible
    cy.get('.navbar-collapse').should('be.visible');
    
    // Check main nav links are visible in mobile view
    cy.get('[data-testid="nav-home"]').should('be.visible');
    cy.get('[data-testid="nav-dashboard"]').should('be.visible');
    cy.get('[data-testid="nav-chat"]').should('be.visible');
    
    // Experiments link should NOT exist for normal users
    cy.get('[data-testid="nav-experiments"]').should('not.exist');
    
    // Navigate through menu items
    cy.get('[data-testid="nav-chat"]').click();
    
    // Should navigate to chat page
    cy.url().should('include', '/chat');
  });
});