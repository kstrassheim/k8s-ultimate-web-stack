import {
  msalConfig,
  loginRequest,
  retrieveTokenForBackend,
  retrieveTokenForGraph,
  GRAPH_SCOPES,
  GraphConsentRequiredError,
  isGraphConsentRequiredError,
  isInteractionRequiredError,
  resetGraphConsentState,
} from '@/auth/entraAuth';
import appInsights from '@/log/appInsights'; // mock or spy as needed
import { LogLevel, InteractionRequiredAuthError } from '@azure/msal-browser';

describe('entraAuth Module', () => {
  let originalConsoleLog;
  
  beforeAll(() => {
    // Save original console.log
    originalConsoleLog = console.log;
    // Replace with silent mock
    console.log = jest.fn();
  });
  
  afterAll(() => {
    // Restore original console.log
    console.log = originalConsoleLog;
  });

  describe('msalConfig', () => {
    it('should return the correct MSAL configuration object', () => {
      const config = msalConfig();
      expect(config.auth).toHaveProperty('clientId');
      expect(config.auth).toHaveProperty('authority');
      expect(config.auth).toHaveProperty('redirectUri');
      expect(typeof config.system.loggerOptions.loggerCallback).toBe('function');
    });

    it('routes LogLevel.Error messages to console.error and other levels to console.info', () => {
      // The loggerCallback's ternary `level === LogLevel.Error ? 'error' :
      // 'info'` has two halves. Capture both halves explicitly. The
      // outer `beforeAll` silences console.log but the test spies on
      // console.error and console.info directly.
      const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      const infoSpy = jest.spyOn(console, 'info').mockImplementation(() => {});
      try {
        const config = msalConfig();
        const callback = config.system.loggerOptions.loggerCallback;

        // PII messages are dropped regardless of level.
        callback(LogLevel.Error, 'something failed', true);
        callback(LogLevel.Info, 'informational', true);

        // Error level → console.error.
        callback(LogLevel.Error, 'auth failed', false);
        // Non-error level → console.info.
        callback(LogLevel.Info, 'still working', false);

        expect(errSpy).toHaveBeenCalledWith('auth failed');
        expect(infoSpy).toHaveBeenCalledWith('still working');
        // The PII messages should NOT have been logged.
        expect(errSpy).not.toHaveBeenCalledWith('something failed');
        expect(infoSpy).not.toHaveBeenCalledWith('informational');
      } finally {
        errSpy.mockRestore();
        infoSpy.mockRestore();
      }
    });
  });

  describe('loginRequest', () => {
    it('should export scopes from tfconfig as requested_graph_api_delegated_permissions', () => {
      expect(Array.isArray(loginRequest.scopes)).toBeTruthy();
    });

    it('falls back to ["User.Read"] when requested_graph_api_delegated_permissions is absent', () => {
      // The mock terraform config sets requested_graph_api_delegated_permissions
      // to two values, so the `??` fallback has never fired. Force the
      // module to re-evaluate under a config where the property is
      // missing — that's the only way to exercise the dead branch.
      jest.isolateModules(() => {
        jest.doMock('@/../terraform.config.json', () => ({
          client_id: { value: 'x' },
          tenant_id: { value: 'y' },
          oauth2_permission_scope_uri: { value: 'scope' },
          // requested_graph_api_delegated_permissions intentionally omitted
        }));
        jest.doMock('@/log/appInsights', () => ({
          trackEvent: jest.fn(), trackException: jest.fn(),
        }));
        // eslint-disable-next-line global-require
        const { loginRequest: fresh } = require('@/auth/entraAuth');
        expect(fresh.scopes).toEqual(['User.Read']);
      });
    });
  });

  describe('retrieveTokenForBackend', () => {
    let mockInstance;
    let mockActiveAccount;
    let mockAcquireTokenSilent;

    beforeEach(() => {
      mockActiveAccount = { username: 'testUser' };
      mockAcquireTokenSilent = jest.fn().mockResolvedValue({ accessToken: 'mockBackendToken' });
      mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue(mockActiveAccount),
        acquireTokenSilent: mockAcquireTokenSilent
      };
      jest.spyOn(appInsights, 'trackEvent').mockImplementation(() => {});
    });

    it('should call acquireTokenSilent with expected scopes', async () => {
      const token = await retrieveTokenForBackend(mockInstance, ['extra.scope']);
      expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'MSAL Retrieving Token' });
      expect(mockInstance.getActiveAccount).toHaveBeenCalled();
      expect(mockAcquireTokenSilent).toHaveBeenCalledWith({
        scopes: ['mock-api://00000000-0000-0000-0000-000000000001/user_impersonation', 'extra.scope'],
        account: mockActiveAccount
      });
      expect(token).toBe('mockBackendToken');
    });

    it('uses the default empty extraScopes when called without arguments', () => {
      // Default-parameter coverage — the test passes the call without
      // an explicit second argument, so `extraScopes = []` is materialised.
      mockInstance.acquireTokenSilent.mockResolvedValueOnce({ accessToken: 't' });
      return retrieveTokenForBackend(mockInstance).then(() => {
        const passed = mockAcquireTokenSilent.mock.calls[0][0];
        expect(passed.scopes).toEqual([
          'mock-api://00000000-0000-0000-0000-000000000001/user_impersonation',
        ]);
      });
    });
  });

  describe('retrieveTokenForGraph', () => {
    let mockInstance;
    let mockActiveAccount;
    let mockAcquireTokenSilent;

    beforeEach(() => {
      mockActiveAccount = { username: 'testUser' };
      mockAcquireTokenSilent = jest.fn().mockResolvedValue({ accessToken: 'mockGraphToken' });
      mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue(mockActiveAccount),
        acquireTokenSilent: mockAcquireTokenSilent
      };
      jest.spyOn(appInsights, 'trackEvent').mockImplementation(() => {});
    });

    it('should request Graph scopes, plus any extra scopes passed in', async () => {
      const token = await retrieveTokenForGraph(mockInstance, ['Mail.Read']);
      expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'MSAL Retrieving Graph Token' });
      expect(mockInstance.getActiveAccount).toHaveBeenCalled();
      // Issue #151: concrete scopes, and `extraScopes` is honoured rather than
      // silently discarded. The old `https://graph.microsoft.com/.default`
      // meant "every delegated permission already consented for this user",
      // which fails with InteractionRequiredAuthError on *every* call for a
      // user who has not consented — one popup per navigation.
      expect(mockAcquireTokenSilent).toHaveBeenCalledWith({
        scopes: ['User.Read', 'Mail.Read'],
        account: mockActiveAccount
      });
      expect(token).toBe('mockGraphToken');
    });

    it('never requests the .default scope (issue #141)', async () => {
      await retrieveTokenForGraph(mockInstance);
      const { scopes } = mockAcquireTokenSilent.mock.calls[0][0];
      expect(scopes).not.toContain('https://graph.microsoft.com/.default');
      expect(scopes).toEqual(GRAPH_SCOPES);
    });

    it('de-duplicates a scope the caller repeats', async () => {
      await retrieveTokenForGraph(mockInstance, ['User.Read', 'Group.Read.All']);
      expect(mockAcquireTokenSilent.mock.calls[0][0].scopes)
        .toEqual(['User.Read', 'Group.Read.All']);
    });
  });

  describe('retrieveTokenForGraph — interaction handling (issue #141)', () => {
    let mockInstance;
    let mockActiveAccount;
    let mockAcquireTokenSilent;
    let mockAcquireTokenPopup;

    const interactionRequired = () => {
      const error = new Error('consent needed');
      error.name = 'InteractionRequiredAuthError';
      return error;
    };

    beforeEach(() => {
      resetGraphConsentState();
      mockActiveAccount = { username: 'testUser', homeAccountId: 'home-1' };
      mockAcquireTokenSilent = jest.fn().mockRejectedValue(interactionRequired());
      mockAcquireTokenPopup = jest.fn().mockResolvedValue({ accessToken: 'popupToken' });
      mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue(mockActiveAccount),
        acquireTokenSilent: mockAcquireTokenSilent,
        acquireTokenPopup: mockAcquireTokenPopup,
      };
      jest.spyOn(appInsights, 'trackEvent').mockImplementation(() => {});
      jest.spyOn(appInsights, 'trackException').mockImplementation(() => {});
    });

    afterEach(() => {
      resetGraphConsentState();
    });

    it('does NOT open a popup when consent is missing and nobody asked for one', async () => {
      // The reported bug: acquireTokenPopup is window.open, and in an
      // installed Edge PWA that window opens outside the app frame. Called
      // from a mount effect it fires once per navigation.
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);
      expect(mockAcquireTokenPopup).not.toHaveBeenCalled();
    });

    it('memoises the outcome so repeated navigations cannot become repeated popups', async () => {
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);

      // Only the first attempt reached MSAL at all; the rest short-circuited.
      expect(mockAcquireTokenSilent).toHaveBeenCalledTimes(1);
      expect(mockAcquireTokenPopup).not.toHaveBeenCalled();
    });

    it('opens a popup when a user gesture explicitly opts in', async () => {
      const token = await retrieveTokenForGraph(mockInstance, [], { interactive: true });
      expect(mockAcquireTokenPopup).toHaveBeenCalledWith({ scopes: GRAPH_SCOPES });
      expect(token).toBe('popupToken');
    });

    it('retries silently after an interactive grant succeeds', async () => {
      await retrieveTokenForGraph(mockInstance, [], { interactive: true });

      // The memoised block is cleared by the successful grant, so the next
      // background fetch is allowed to try silent acquisition again.
      mockAcquireTokenSilent.mockResolvedValueOnce({ accessToken: 'freshToken' });
      await expect(retrieveTokenForGraph(mockInstance)).resolves.toBe('freshToken');
    });

    it('bypasses the memoised block for an interactive retry', async () => {
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);
      const token = await retrieveTokenForGraph(mockInstance, [], { interactive: true });
      expect(token).toBe('popupToken');
    });

    it('re-throws a non-interaction error untouched, and does not block the account', async () => {
      const boom = new Error('graph is down');
      mockAcquireTokenSilent.mockRejectedValue(boom);

      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow('graph is down');
      expect(mockAcquireTokenPopup).not.toHaveBeenCalled();

      // Not a consent problem, so a later call must still reach MSAL.
      mockAcquireTokenSilent.mockResolvedValueOnce({ accessToken: 'ok' });
      await expect(retrieveTokenForGraph(mockInstance)).resolves.toBe('ok');
    });

    it('keys the memo per account, so a second user is not pre-blocked', async () => {
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(GraphConsentRequiredError);

      mockInstance.getActiveAccount.mockReturnValue({
        username: 'otherUser', homeAccountId: 'home-2',
      });
      mockAcquireTokenSilent.mockResolvedValueOnce({ accessToken: 'otherToken' });
      await expect(retrieveTokenForGraph(mockInstance)).resolves.toBe('otherToken');
    });

    it('falls back to the empty-string account key when no id or username is available', async () => {
      // The `accountKeyOf` helper's `||` chain has three arms:
      // `homeAccountId` → `username` → `''`. The last branch is the
      // fallback for an account object that has neither identifier —
      // exercise that branch by calling retrieveTokenForGraph with such
      // an account while the memo is empty, then again to make the
      // consent block apply under the empty-string key.
      resetGraphConsentState();
      mockAcquireTokenSilent.mockRejectedValue(
        Object.assign(new Error('consent'), { name: 'InteractionRequiredAuthError' }),
      );
      mockInstance.getActiveAccount.mockReturnValue({}); // no id, no username
      await expect(retrieveTokenForGraph(mockInstance)).rejects.toThrow(
        GraphConsentRequiredError,
      );
    });
  });

  describe('error predicates (issue #141)', () => {
    it.each([
      ['a real InteractionRequiredAuthError', new InteractionRequiredAuthError('x')],
      ['an error carrying only the name', Object.assign(new Error('x'), { name: 'InteractionRequiredAuthError' })],
      ['an AuthError with errorCode consent_required', Object.assign(new Error('x'), { errorCode: 'consent_required' })],
      ['an AuthError with errorCode interaction_required', Object.assign(new Error('x'), { errorCode: 'interaction_required' })],
      ['an AuthError with errorCode login_required', Object.assign(new Error('x'), { errorCode: 'login_required' })],
    ])('isInteractionRequiredError recognises %s', (_label, error) => {
      // Matching on `instanceof` alone would silently stop recognising the
      // mock-build and errorCode shapes and put us back to re-throwing where
      // we used to prompt.
      expect(isInteractionRequiredError(error)).toBe(true);
    });

    it.each([
      ['a plain error', new Error('network')],
      ['an unrelated errorCode', Object.assign(new Error('x'), { errorCode: 'no_tokens_found' })],
      ['null', null],
      ['undefined', undefined],
    ])('isInteractionRequiredError rejects %s', (_label, error) => {
      expect(isInteractionRequiredError(error)).toBe(false);
    });

    it('isGraphConsentRequiredError matches by identity and by name', () => {
      // The Cypress/vite mock build swaps the module graph, so a
      // GraphConsentRequiredError can cross a boundary `instanceof` does not
      // survive — the name check is what keeps the Dashboard's degraded path
      // working there.
      expect(isGraphConsentRequiredError(new GraphConsentRequiredError(['User.Read']))).toBe(true);
      expect(isGraphConsentRequiredError({ name: 'GraphConsentRequiredError' })).toBe(true);
      expect(isGraphConsentRequiredError(new Error('other'))).toBe(false);
      expect(isGraphConsentRequiredError(null)).toBe(false);
    });

    it('GraphConsentRequiredError carries the scopes and the original cause', () => {
      const cause = new Error('original');
      const error = new GraphConsentRequiredError(['User.Read', 'Group.Read.All'], { cause });
      expect(error.scopes).toEqual(['User.Read', 'Group.Read.All']);
      expect(error.cause).toBe(cause);
    });
  });
});