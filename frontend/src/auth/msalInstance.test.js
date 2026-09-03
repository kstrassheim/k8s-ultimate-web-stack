// `src/auth/msalInstance.js` wires MSAL Browser v3+ — initialises the
// `PublicClientApplication`, registers a logout/login/silent-success event
// listener, and feeds `handleRedirectPromise` into the active-account set.
// All of that is reachable from a unit test that mocks `@azure/msal-browser`
// and `@/auth/entraAuth`; the assertions below exercise the success and
// "no redirect response" branches, the LOGOUT_SUCCESS path, and the
// LOGIN_SUCCESS / ACQUIRE_TOKEN_SUCCESS / SSO_SILENT_SUCCESS active-account
// promotion, plus the catch-handler fallback when MSAL initialisation itself
// throws. `msalInitialization` is consumed by `main.jsx`; here we just
// resolve it to await the underlying `initialize()` promise.
//
// Each test re-imports `msalInstance.js` inside `jest.isolateModules` so
// the module-level `new PublicClientApplication(...)` constructor call picks
// up the per-test fake class — jest's module cache otherwise leaks the
// real MSAL constructor (which requires Web Crypto) across tests.

jest.mock('@/auth/entraAuth', () => ({
  msalConfig: () => ({ auth: { clientId: 'test-client' } }),
}));

jest.mock('@/log/appInsights', () => ({
  trackEvent: jest.fn(),
  trackException: jest.fn(),
}));

let originalConsoleError;

const loadMsalInstance = (pcaFactory, eventTypeMap = {}) => {
  let mod;
  jest.isolateModules(() => {
    jest.doMock('@azure/msal-browser', () => ({
      PublicClientApplication: pcaFactory,
      EventType: {
        LOGOUT_SUCCESS: 'msal:logoutSuccess',
        LOGIN_SUCCESS: 'msal:loginSuccess',
        ACQUIRE_TOKEN_SUCCESS: 'msal:acquireTokenSuccess',
        SSO_SILENT_SUCCESS: 'msal:ssoSilentSuccess',
        ...eventTypeMap,
      },
    }));
    // eslint-disable-next-line global-require
    mod = require('@/auth/msalInstance');
  });
  return mod;
};

const makeFakePCA = (overrides = {}) => {
  // Optionally seed the initial active account so the early-return
  // `if (currentActiveAccount) return` branch inside
  // `setInitialActiveAccount` fires on the first call. Without this,
  // the test would observe a setActiveAccount(pool[0]) call instead of
  // the early return.
  let activeAccount = overrides.initialActiveAccount || null;
  const setActiveAccountCalls = [];
  class FakePCA {
    constructor() {
      this.eventCallbacks = [];
      this._getAllAccountsResult = overrides.allAccounts || [];
    }
    initialize() { return Promise.resolve(); }
    addEventCallback(cb) {
      this.eventCallbacks.push(cb);
      return 'cb-id';
    }
    handleRedirectPromise() {
      return Promise.resolve(overrides.redirectResponse || null);
    }
    getActiveAccount() { return activeAccount; }
    getAllAccounts() { return this._getAllAccountsResult; }
    setActiveAccount(account) {
      setActiveAccountCalls.push(account);
      activeAccount = account;
      return Promise.resolve();
    }
    // Test helpers — return internal state for assertions.
    _fireEvent(event) {
      for (const cb of this.eventCallbacks) cb(event);
    }
    _getActiveAccount() { return activeAccount; }
    _setActiveAccountDirect(value) { activeAccount = value; }
    _setActiveAccountCalls() { return setActiveAccountCalls; }
  }
  return FakePCA;
};

beforeEach(() => {
  jest.resetModules();
  originalConsoleError = console.error;
  console.error = jest.fn();
});

afterEach(() => {
  console.error = originalConsoleError;
});

describe('msalInstance', () => {
  it('initialises MSAL with the configured auth settings', async () => {
    let ctorArgs = null;
    const FakePCA = makeFakePCA();
    class TrackingPCA extends FakePCA {
      constructor(...args) {
        super();
        ctorArgs = args;
      }
    }

    const mod = loadMsalInstance(TrackingPCA);
    await mod.msalInitialization;

    expect(ctorArgs).toHaveLength(1);
    expect(ctorArgs[0]).toEqual(expect.objectContaining({ auth: { clientId: 'test-client' } }));
  });

  it('falls back to the first account in getAllAccounts when the redirect carries none', async () => {
    const FakePCA = makeFakePCA({ allAccounts: [{ homeAccountId: 'existing-1', username: 'u' }] });
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    // After init, the active account should have been promoted from the
    // "first of getAllAccounts" pool.
    // Pull a fresh instance via the module's exported default so we can
    // see what the listener recorded.
    const inst = mod.default;
    expect(inst._getActiveAccount()).toEqual({ homeAccountId: 'existing-1', username: 'u' });
  });

  it('uses the redirect response account when handleRedirectPromise resolves with one', async () => {
    const redirectAccount = { homeAccountId: 'redirect-1', username: 'redirect-user' };
    const FakePCA = makeFakePCA({ redirectResponse: { account: redirectAccount } });
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    expect(mod.default._getActiveAccount()).toBe(redirectAccount);
  });

  it('does not call setActiveAccount when there is no existing account AND no redirect response', async () => {
    const FakePCA = makeFakePCA({ allAccounts: [], redirectResponse: null });
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    expect(mod.default._getActiveAccount()).toBeNull();
    expect(mod.default._setActiveAccountCalls()).toEqual([]);
  });

  it('registers an event callback that flips the active account on LOGIN_SUCCESS', async () => {
    const FakePCA = makeFakePCA();
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    const loginAccount = { homeAccountId: 'login-1', username: 'login-user' };
    mod.default._fireEvent({
      eventType: 'msal:loginSuccess',
      payload: { account: loginAccount },
    });
    expect(mod.default._getActiveAccount()).toBe(loginAccount);
  });

  it('promotes the active account on ACQUIRE_TOKEN_SUCCESS and SSO_SILENT_SUCCESS', async () => {
    const FakePCA = makeFakePCA();
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    const tokenAccount = { homeAccountId: 'tok-1', username: 'tok-user' };
    mod.default._fireEvent({
      eventType: 'msal:acquireTokenSuccess',
      payload: { account: tokenAccount },
    });
    expect(mod.default._getActiveAccount()).toBe(tokenAccount);

    const ssoAccount = { homeAccountId: 'sso-1', username: 'sso-user' };
    mod.default._fireEvent({
      eventType: 'msal:ssoSilentSuccess',
      payload: { account: ssoAccount },
    });
    expect(mod.default._getActiveAccount()).toBe(ssoAccount);
  });

  it('clears the active account on LOGOUT_SUCCESS', async () => {
    const FakePCA = makeFakePCA();
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    // Seed an existing account first.
    mod.default._setActiveAccountDirect({ homeAccountId: 'login-1' });
    mod.default._fireEvent({ eventType: 'msal:logoutSuccess' });
    expect(mod.default._getActiveAccount()).toBeNull();
  });

  it('ignores events that carry no payload.account', async () => {
    const FakePCA = makeFakePCA();
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    mod.default._fireEvent({ eventType: 'msal:loginSuccess' });
    expect(mod.default._getActiveAccount()).toBeNull();
  });

  it('ignores events whose eventType is not in the success set', async () => {
    const FakePCA = makeFakePCA();
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    // loginFailure / loginStart / etc. are NOT in the promotion set, so the
    // active account must stay untouched even when an account is present.
    const stranger = { homeAccountId: 'x' };
    mod.default._fireEvent({ eventType: 'msal:loginFailure', payload: { account: stranger } });
    expect(mod.default._getActiveAccount()).toBeNull();
  });

  it('logs the MSAL initialization failure via console.error when initialize rejects', async () => {
    class FailingPCA extends makeFakePCA() {
      initialize() { return Promise.reject(new Error('msal boot failed')); }
    }
    const mod = loadMsalInstance(FailingPCA);

    // The .catch on msalInitialization swallows the error, so awaiting
    // resolves successfully — but the failure path's console.error is
    // recorded for the operator.
    await expect(mod.msalInitialization).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalledWith(
      'MSAL initialization failed',
      expect.any(Error),
    );
  });

  it('returns early from setInitialActiveAccount when an account is already active', async () => {
    // Seed an existing active account so the inner `if (currentActiveAccount)`
    // early-return fires — setInitialActiveAccount is the ONLY path that
    // touches the `getAllAccounts()` pool, and it must NOT clobber an
    // already-pinned account.
    const existing = { homeAccountId: 'preexisting' };
    const FakePCA = makeFakePCA({
      initialActiveAccount: existing,
      allAccounts: [{ homeAccountId: 'pool-1' }, { homeAccountId: 'pool-2' }],
      redirectResponse: null,
    });
    const mod = loadMsalInstance(FakePCA);
    await mod.msalInitialization;

    // No setActiveAccount call should have happened — the early-return
    // branch fired because getActiveAccount() returned the seeded account
    // at the top of setInitialActiveAccount.
    expect(mod.default._setActiveAccountCalls()).toEqual([]);
    expect(mod.default._getActiveAccount()).toBe(existing);
  });
});
