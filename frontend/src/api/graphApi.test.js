//// filepath: c:\projects\ultimate-web-stack\frontend\src\api\graphApi.test.js
import { getProfilePhoto, getAllGroups } from './graphApi';
import { retrieveTokenForGraph } from '@/auth/entraAuth';
import appInsights from '@/log/appInsights';

// Add the following block to mock the entire module so that retrieveTokenForGraph becomes a jest mock:
jest.mock('@/auth/entraAuth', () => ({
  retrieveTokenForGraph: jest.fn(),
  loginRequest: {}
}));

global.fetch = jest.fn();

// Ensure window.getProfilePhoto is undefined so our own implementation runs.
delete window.getProfilePhoto;

// Remove any explicit mock for graphApi so the real implementation is used
jest.unmock('@/api/graphApi');

describe('graphApi', () => {
  let originalConsoleError;
  let originalConsoleLog;

  beforeEach(() => {
    // Save original console methods
    originalConsoleError = console.error;
    originalConsoleLog = console.log;
    
    // Replace with silent mocks for tests
    console.error = jest.fn();
    console.log = jest.fn();
    
    jest.clearAllMocks();
  });

  afterEach(() => {
    // Restore original console methods
    console.error = originalConsoleError;
    console.log = originalConsoleLog;
  });

  describe('getProfilePhoto', () => {
    it('calls trackEvent and fetches profile photo successfully', async () => {
      const mockBlob = new Blob(['fake image data'], { type: 'image/png' });
      const expectedUrl = 'blob:http://localhost/fake-url';

      // Create a fake instance that supports acquireTokenSilent
      const mockInstance = {
        acquireTokenSilent: jest.fn().mockResolvedValue({ accessToken: 'fake-token' })
      };
      // A fake active account with an Admin role
      const mockAccount = { 
        username: 'testuser',
        idTokenClaims: { roles: ['Admin'] }
      };

      global.URL.createObjectURL = jest.fn().mockReturnValue(expectedUrl);
      fetch.mockResolvedValueOnce({
        ok: true,
        blob: jest.fn().mockResolvedValue(mockBlob)
      });

      const result = await getProfilePhoto(mockInstance, mockAccount);
      expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'Profile - Getting profile image' });
      expect(global.fetch).toHaveBeenCalledWith('https://graph.microsoft.com/v1.0/me/photo/$value', {
        headers: { Authorization: 'Bearer fake-token' }
      });
      expect(result).toBe(expectedUrl);
    });

    it('returns undefined if no active account', async () => {
      // Expect undefined (not null) when activeAccount is falsy
      const result = await getProfilePhoto({}, null);
      expect(result).toBeUndefined();
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('handles fetch errors gracefully', async () => {
      fetch.mockRejectedValue(new Error('Network error'));
      await getProfilePhoto({}, { username: 'testuser' });
      expect(appInsights.trackException).toHaveBeenCalled();
      // Optionally verify the console.error was called without seeing the output
      expect(console.error).toHaveBeenCalled();
    });

    it('returns undefined when Graph returns a non-ok response for the photo', async () => {
      // Mirror the production path: Graph 404s when the user has no
      // profile photo. The helper logs and falls through (no throw, no
      // exception track) so the caller's component can fall back to the
      // dummy avatar without an error toast.
      const instance = {
        acquireTokenSilent: jest.fn().mockResolvedValue({ accessToken: 'fake-token' }),
      };
      const account = { username: 'no-photo-user' };
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      });

      const result = await getProfilePhoto(instance, account);

      expect(result).toBeUndefined();
      expect(console.error).toHaveBeenCalledWith(
        'Failed to fetch profile photo:',
        'Not Found',
      );
      expect(appInsights.trackException).not.toHaveBeenCalled();
    });
  });

  describe('window overrides', () => {
    // `getProfilePhoto` and `getAllGroups` both default to the inline
    // implementation but allow `window.getProfilePhoto` /
    // `window.getAllGroups` to replace them — the cypress/vite mock build
    // uses that seam to swap in canned responses. Both branches of each
    // ternary need to be hit for full coverage.
    afterEach(() => {
      delete window.getProfilePhoto;
      delete window.getAllGroups;
      jest.resetModules();
    });

    it('uses window.getProfilePhoto when set (ternary truthy branch)', async () => {
      jest.resetModules();
      const override = jest.fn().mockResolvedValue('http://override.example/avatar.png');
      window.getProfilePhoto = override;

      // Re-import so the module's top-level ternary picks up the override.
      // eslint-disable-next-line global-require
      const fresh = require('./graphApi');
      const result = await fresh.getProfilePhoto({ acquireTokenSilent: jest.fn() }, { username: 'u' });
      expect(override).toHaveBeenCalled();
      expect(result).toBe('http://override.example/avatar.png');
    });

    it('uses window.getAllGroups when set (ternary truthy branch)', async () => {
      jest.resetModules();
      const override = jest.fn().mockResolvedValue([{ id: 'override-1' }]);
      window.getAllGroups = override;

      // eslint-disable-next-line global-require
      const fresh = require('./graphApi');
      const result = await fresh.getAllGroups({ getActiveAccount: jest.fn() });
      expect(override).toHaveBeenCalled();
      expect(result).toEqual([{ id: 'override-1' }]);
    });
  });

  describe('getAllGroups', () => {
    it('requests token with Group.Read.All and fetches group data', async () => {
      // Provide an instance with a getActiveAccount() function
      const mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue({
          idTokenClaims: { roles: ['Admin'] }
        })
      };

      // Instead of spyOn, assign a new mock implementation directly.
      retrieveTokenForGraph.mockResolvedValue('fake-group-token');

      fetch.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ value: [{ id: 'group1' }] })
      });

      const result = await getAllGroups(mockInstance);
      expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'Api Call - getAllGroups (Graph API)' });
      // Issue #141: the third argument gates the MSAL popup. The mount-time
      // fetch must pass `interactive: false` so a user missing Graph consent
      // gets a rejected promise instead of a browser window per navigation.
      expect(retrieveTokenForGraph).toHaveBeenCalledWith(
        mockInstance,
        ['Group.Read.All'],
        { interactive: false },
      );
      expect(global.fetch).toHaveBeenCalledWith('https://graph.microsoft.com/v1.0/groups', {
        headers: {
          Authorization: 'Bearer fake-group-token',
          'Content-Type': 'application/json'
        }
      });
      expect(result).toEqual([{ id: 'group1' }]);
    });

    it('forwards interactive: true only when the caller opts in (issue #141)', async () => {
      // The "Grant access" button on the dashboard is the one caller allowed
      // to open a popup, because it runs from a real user gesture. Anything
      // else — notably the Dashboard mount effect — must stay non-interactive.
      const mockInstance = { getActiveAccount: jest.fn().mockReturnValue({}) };
      retrieveTokenForGraph.mockResolvedValue('fake-group-token');
      fetch.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ value: [] })
      });

      await getAllGroups(mockInstance, { interactive: true });

      expect(retrieveTokenForGraph).toHaveBeenCalledWith(
        mockInstance,
        ['Group.Read.All'],
        { interactive: true },
      );
    });

    it.each([
      ['no options', undefined],
      ['an options object without the flag', { timeoutMs: 100 }],
      ['a truthy-but-not-true value', { interactive: 'yes' }],
    ])('does not allow a popup for %s (issue #141)', async (_label, options) => {
      // `interactive` is compared with === true on purpose: a stray truthy
      // value from a caller must not be enough to open a browser window.
      const mockInstance = { getActiveAccount: jest.fn().mockReturnValue({}) };
      retrieveTokenForGraph.mockResolvedValue('fake-group-token');
      fetch.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ value: [] })
      });

      await getAllGroups(mockInstance, options);

      expect(retrieveTokenForGraph).toHaveBeenCalledWith(
        mockInstance,
        ['Group.Read.All'],
        { interactive: false },
      );
    });

    it('tracks exception if fetch fails', async () => {
      const mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue({
          idTokenClaims: { roles: ['Admin'] }
        })
      };
      retrieveTokenForGraph.mockResolvedValue('fake-group-token');
      fetch.mockRejectedValue(new Error('Network error'));
      await expect(getAllGroups(mockInstance)).rejects.toThrow();
      expect(appInsights.trackException).toHaveBeenCalled();
      // Optionally verify the console.error was called without seeing the output
      expect(console.error).toHaveBeenCalled();
    });

    it('reads the response body text and throws on a non-ok response', async () => {
      // The branch `if (!response.ok)` calls `await response.text()` to
      // include Graph's error body in the thrown message. Distinct from
      // a network failure (which fetch rejects).
      const mockInstance = {
        getActiveAccount: jest.fn().mockReturnValue({}),
      };
      retrieveTokenForGraph.mockResolvedValue('fake-group-token');
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        text: jest.fn().mockResolvedValue('Insufficient privileges to complete the operation.'),
      });

      await expect(getAllGroups(mockInstance)).rejects.toThrow(
        /Graph API error \(403\): Insufficient privileges/,
      );
      expect(appInsights.trackException).toHaveBeenCalled();
    });
  });
});