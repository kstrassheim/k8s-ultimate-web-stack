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
// Browser-side coverage hooks: read window.__coverage__ from the app iframe
// after each test and forward it to the node-side tasks registered by
// codeCoverageTask(on, config) in cypress.config.js. The two sides do not
// overlap — without this import, coverage is collected by nothing.
import '@cypress/code-coverage/support';

// Example of global behavior modification
Cypress.on('uncaught:exception', (err, runnable) => {
  // returning false here prevents Cypress from
  // failing the test on uncaught exceptions
  return false
});

// For tasks, define them in cypress.config.js instead of here
// Do NOT use Cypress.on('task', {...}) in this file