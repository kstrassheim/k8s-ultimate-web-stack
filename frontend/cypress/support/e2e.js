// ***********************************************************
// This example support/e2e.js is processed and
// loaded automatically before your test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
// ***********************************************************

import 'cypress-wait-until';
import './msalMock';
// NOTE: @cypress/code-coverage support is registered via cypress.config.js setupNodeEvents.
// Do NOT import '@cypress/code-coverage/support' here as that causes duplicate registration.

// Example of global behavior modification
Cypress.on('uncaught:exception', (err, runnable) => {
  // returning false here prevents Cypress from
  // failing the test on uncaught exceptions
  return false
});

// For tasks, define them in cypress.config.js instead of here
// Do NOT use Cypress.on('task', {...}) in this file