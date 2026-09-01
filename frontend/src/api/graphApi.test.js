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
  });
});