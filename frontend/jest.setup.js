import '@testing-library/jest-dom';
import { jestPreviewConfigure, debug } from 'jest-preview';
import { TextEncoder, TextDecoder } from 'util';
import path from 'path';
import PublicClientApplication from './mock/azureMsalBrowser';

// Provide TextEncoder/TextDecoder in the JSDOM environment for libraries like React Router
if (!global.TextEncoder) {
  global.TextEncoder = TextEncoder;
}

if (!global.TextDecoder) {
  global.TextDecoder = TextDecoder;
}


global.import = { meta: { env: { MODE: 'test', PROD: false, DEV: false, BASE_URL: '/' } } };

// src/config.js reads three values from its host environment:
//   - `import.meta.env.MODE` — rewritten by jest.config-transformer.cjs to
//     `globalThis.__VITE_MODE__` so the module is loadable in jest (Vite
//     normally inlines this at build time).
//   - `__PROD_URI__` and `__PROD_SOCKET_URI__` — Vite `define` substitutions
//     in vite.config.js, populated here as globals so the same values the
//     production build would inline are available to the loaded module.
// config.test.js mutates these globals per test to drive each branch.
globalThis.__VITE_MODE__ = 'test';
globalThis.__PROD_URI__ = 'http://localhost:8000';
globalThis.__PROD_SOCKET_URI__ = 'ws://localhost:8000';

// react-router@8 eagerly imports `dist/production/lib/dom/ssr/routeModules.js`
// from its main entry. That file uses `import.meta.hot` (Vite HMR syntax)
// which @swc/jest passes through unchanged when emitting CommonJS, then
// Node's CJS parser fails on ("Cannot use 'import.meta' outside a module").
// `loadRouteModule` is only invoked by react-router in framework-mode routing
// (when a route has a `route.module` property from the Vite/react-router
// plugin). The unit tests for /components/* and /pages/* use
// `<MemoryRouter>` + `<Routes>` / `<Route>` directly (declarative client-side
// routing, no framework mode) and never call `loadRouteModule`, so a no-op
// stub is functionally equivalent for the test surface.
//
// virtual:true skips the file resolution — jest registers the mock under the
// key react-router would import from, so any internal `import "./routeModules.js"`
// hits the stub instead of the real file.
jest.doMock(
  path.resolve(__dirname, 'node_modules/react-router/dist/production/lib/dom/ssr/routeModules.js'),
  () => ({ loadRouteModule: async () => ({}) }),
  { virtual: true }
);

// Create a mock MSAL instance using the full implementation
const mockMsalInstance = new PublicClientApplication({
    auth: {
      clientId: 'test-client-id',
      authority: 'https://login.microsoftonline.com/common'
    }
  });

// Mock the MSAL components
jest.mock('@azure/msal-react', () => ({
    useMsal: jest.fn().mockReturnValue({
      instance: mockMsalInstance,
      accounts: mockMsalInstance.getAllAccounts(),
      inProgress: "none"
    }),
    // Keep the component mocks
    MsalProvider: ({ children }) => children,
    AuthenticatedTemplate: ({ children }) => children,
    UnauthenticatedTemplate: ({ children }) => children
  }));

// Also mock the appInsights instance directly
// Add this to your jest.setup.js
// Fix the AppInsights mock by directly returning the mock implementation
jest.mock('@/log/appInsights', () => {
  // Get the original mock
  const originalMock = jest.requireActual('./mock/appInsights').default;
  
  // Create a new object with the same properties
  const spiedMock = { ...originalMock };
  
  // Add spies to all functions while preserving their implementation
  Object.keys(originalMock).forEach(key => {
    if (typeof originalMock[key] === 'function') {
      // Create a spy that calls the original implementation
      spiedMock[key] = jest.fn().mockImplementation((...args) => 
        originalMock[key](...args)
      );
    }
  });
  
  return spiedMock;
});

// Mock graph API with spy wrappers
jest.mock('@/api/graphApi', () => {
  const actualMock = jest.requireActual('./mock/graphApi');
  
  // Create an object to hold all spied functions
  const spiedMock = { ...actualMock };
  
  // Spy on all functions exported from the mock
  Object.keys(actualMock).forEach(key => {
    if (typeof actualMock[key] === 'function') {
      spiedMock[key] = jest.fn().mockImplementation(actualMock[key]);
    }
  });
  
  return spiedMock;
});

// Mock API with spy wrappers
jest.mock('@/api/api', () => {
  const actualMock = jest.requireActual('./mock/api');
  
  // Create an object to hold all spied functions
  const spiedMock = { ...actualMock };
  
  // Spy on all functions exported from the mock
  Object.keys(actualMock).forEach(key => {
    if (typeof actualMock[key] === 'function') {
      spiedMock[key] = jest.fn().mockImplementation(actualMock[key]);
    }
  });
  
  return spiedMock;
});

// Mock config.js entirely - this is the most reliable approach
jest.mock('@/config', () => ({
    env: 'dev',
    isDev: false,
    isProd: false,
    productionUrl: '',
    developmentUrl: 'http://localhost:5173',
    backendUrl: '',
    frontendUrl: 'http://localhost:5173'
  }));

// Configure jest-preview
jestPreviewConfigure({
    port: 3336,
    autoOpen: true,
    cssFiles: ['src/index.css', 'src/App.css'], // Add your CSS files // Add your CSS files
    //debugOptions: { autoRefresh: true, pauseOnError: true }
    webServerOptions: { headers: {'Cache-Control': 'no-store'}}
  });

global.debug = debug;

beforeEach(() => {
  jest.clearAllMocks();
});

// Automatically open preview after each test
afterEach(() => {
  debug();
});
