import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { useMsal } from '@azure/msal-react';
import Dashboard from './Dashboard';
import { getUserData } from '@/api/api';
import { getAllGroups } from '@/api/graphApi';
import { GraphConsentRequiredError } from '@/auth/entraAuth';
import { 
  getWorldlineStatus,
  getWorldlineHistory,
  getDivergenceReadings,
  worldlineSocket
} from '@/api/futureGadgetApi';
import appInsights from '@/log/appInsights';
import notyfService from '@/log/notyfService';

// Mock WorldlineMonitor component to simplify testing
jest.mock('@/pages/components/WorldlineMonitor', () => {
  return function DummyWorldlineMonitor() {
    return <div data-testid="worldline-monitor-mock">WorldlineMonitor Component</div>;
  };
});

// Mock the notyfService
jest.mock('@/log/notyfService', () => ({
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}));

// Mock the Future Gadget Lab API calls
jest.mock('@/api/futureGadgetApi', () => ({
  getWorldlineStatus: jest.fn(),
  getWorldlineHistory: jest.fn(),
  getDivergenceReadings: jest.fn(),
  worldlineSocket: {
    connect: jest.fn(),
    disconnect: jest.fn(),
    subscribe: jest.fn().mockReturnValue(jest.fn()),
    subscribeToStatus: jest.fn().mockReturnValue(jest.fn())
  },
  formatDivergenceReading: jest.fn(reading => String(reading.reading)),
  formatWorldLineChange: jest.fn(change => String(change))
}));

// Use the mockMsalInstance that's already defined in your setup
const { instance: mockMsalInstance } = useMsal();

describe('Dashboard Component', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
  });

  const renderDashboardWithMocks = () => {
    return render(<Dashboard />);
  };

  test('renders and loads data successfully including WorldlineMonitor', async () => {
    // Make sure our mock returns something
    getAllGroups.mockResolvedValue([{ id: '1', displayName: 'Test Group' }]);
    
    renderDashboardWithMocks();
    
    // Verify WorldlineMonitor component is present at the top
    expect(screen.getByTestId('worldline-monitor-mock')).toBeInTheDocument();
    expect(screen.getByTestId('worldline-container')).toBeInTheDocument();
    expect(screen.getByTestId('worldline-container')).toHaveClass('mb-5');
    
    // Verify the separator is present between WorldlineMonitor and other content
    const separator = screen.getByRole('separator');
    expect(separator).toBeInTheDocument();
    expect(separator).toHaveClass('my-5');
    
    // Wait for ALL data to load with a longer timeout
    await waitFor(() => {
      expect(screen.getByTestId('api-message-data')).toBeInTheDocument();
      expect(screen.getByTestId('groups-container')).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // Once data is loaded, verify display containers
    expect(screen.getByTestId('api-response-card')).toBeInTheDocument();

    // Verify API calls were made
    expect(getUserData).toHaveBeenCalledTimes(1);
    expect(getUserData).toHaveBeenCalledWith(mockMsalInstance);
    expect(getAllGroups).toHaveBeenCalledTimes(1);
    // Issue #141: the mount-time fetch must stay non-interactive — a popup
    // from this effect is what escaped the installed PWA's window.
    expect(getAllGroups).toHaveBeenCalledWith(mockMsalInstance, { interactive: false });
    
    // Verify tracking was called
    expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'Home - Fetch data started' });
    expect(appInsights.trackEvent).toHaveBeenCalledWith({ name: 'Home - Fetch data completed' });
    
    // Verify Notyf success notification was shown
    expect(notyfService.success).toHaveBeenCalledWith('Data loaded successfully!');

    // Verify the content from the mock API file
    expect(screen.getByTestId('api-message-data')).toHaveTextContent('Hello from API');
  });

  test('handles API error correctly', async () => {
    // Override mock to throw an error for this test only
    const errorMessage = 'API Error';
    getUserData.mockImplementationOnce(() => {
      throw new Error(errorMessage);
    });
    
    renderDashboardWithMocks();
    
    // Verify WorldlineMonitor component is still present even with API error
    expect(screen.getByTestId('worldline-monitor-mock')).toBeInTheDocument();
    
    // Wait for error to appear
    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument();
    });
    
    // Verify exception was tracked
    expect(appInsights.trackException).toHaveBeenCalled();
    
    // Verify Notyf error notification was shown with the correct message
    expect(notyfService.error).toHaveBeenCalledWith('Failed to load data: ' + errorMessage);
  });

  test('reload button fetches fresh data', async () => {
    // Mock implementation to track when promise resolves
    getUserData.mockImplementation(async () => {
      await new Promise(resolve => setTimeout(resolve, 10)); // Small delay to simulate async
      return { message: "Hello from API" };
    });
    
    renderDashboardWithMocks();
    
    // Wait for initial data load
    await waitFor(() => {
      expect(screen.getByTestId('api-message-data')).toBeInTheDocument();
    });
    
    // Clear the mocks to check for new calls
    jest.clearAllMocks();
    
    // Click reload button
    fireEvent.click(screen.getByTestId('reload-button'));
    
    // Verify loading state
    expect(screen.getByTestId('reload-button')).toHaveTextContent(/Loading/);
    
    // Wait for the complete reload process, including notification
    await waitFor(() => {
      // Wait for loading to finish
      expect(screen.getByTestId('reload-button')).not.toHaveTextContent(/Loading/);
      
      // Check API calls
      expect(getUserData).toHaveBeenCalledTimes(1);
      expect(getAllGroups).toHaveBeenCalledTimes(1);
      
      // Now check the notification was called
      expect(notyfService.success).toHaveBeenCalledWith('Data loaded successfully!');
    }, { timeout: 3000 });
    
    // WorldlineMonitor component should stay rendered throughout
    expect(screen.getByTestId('worldline-monitor-mock')).toBeInTheDocument();
  });
  
  // Add a new test for the dashboardPage structure with WorldlineMonitor
  test('verifies dashboard layout with WorldlineMonitor at the top', () => {
    renderDashboardWithMocks();
    
    // Get the main container
    const dashboardPage = screen.getByTestId('dashboard-page');
    
    // Get both main sections
    const worldlineContainer = screen.getByTestId('worldline-container');
    const homeContainer = screen.getByTestId('home-container');
    
    // Verify structure: worldlineContainer should come before homeContainer
    expect(dashboardPage.firstChild).toBe(worldlineContainer);
    
    // Verify separator exists between the sections
    const separator = screen.getByRole('separator');
    expect(separator).toBeInTheDocument();
    
    // Verify worldline container is immediately followed by the separator
    expect(worldlineContainer.nextElementSibling).toBe(separator);
    
    // Check that separator and home container are siblings (both children of dashboardPage)
    expect(separator.parentNode).toBe(dashboardPage);
    expect(homeContainer.parentNode).toBe(dashboardPage);
    
    // Verify that separator appears before home container in the DOM
    const separatorIndex = Array.from(dashboardPage.children).indexOf(separator);
    const homeContainerIndex = Array.from(dashboardPage.children).indexOf(homeContainer);
    expect(separatorIndex).toBeLessThan(homeContainerIndex);
  });

  describe('missing Graph consent (issue #141)', () => {
    const consentError = () => new GraphConsentRequiredError(['User.Read', 'Group.Read.All']);

    beforeEach(() => {
      getUserData.mockResolvedValue({ message: 'API response' });
      getWorldlineStatus.mockResolvedValue({});
      getWorldlineHistory.mockResolvedValue([]);
      getDivergenceReadings.mockResolvedValue([]);
    });

    test('degrades to a Grant access button instead of failing the page', async () => {
      // Before the fix a user without Group.Read.All consent got a popup per
      // navigation; the page itself also failed, because the groups fetch sat
      // inside the same Promise.all as the app's own API call.
      getAllGroups.mockRejectedValue(consentError());

      render(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId('groups-consent-required')).toBeInTheDocument();
      });

      // The rest of the dashboard still loaded.
      expect(screen.getByTestId('api-response-card')).toBeInTheDocument();
      expect(screen.queryByTestId('error-message')).not.toBeInTheDocument();
      expect(notyfService.error).not.toHaveBeenCalled();
    });

    test('the Grant access button is the only path that may open a popup', async () => {
      getAllGroups.mockRejectedValueOnce(consentError());

      render(<Dashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('grant-groups-access-button')).toBeInTheDocument();
      });

      // Mount-time call was non-interactive.
      expect(getAllGroups).toHaveBeenNthCalledWith(
        1,
        mockMsalInstance,
        expect.objectContaining({ interactive: false }),
      );

      getAllGroups.mockResolvedValueOnce([{ id: '1', displayName: 'Granted Group' }]);
      fireEvent.click(screen.getByTestId('grant-groups-access-button'));

      // The click is a real user gesture, so this one may prompt.
      await waitFor(() => {
        expect(getAllGroups).toHaveBeenNthCalledWith(
          2,
          mockMsalInstance,
          expect.objectContaining({ interactive: true }),
        );
      });

      // A successful grant replaces the prompt with the groups list.
      await waitFor(() => {
        expect(screen.queryByTestId('groups-consent-required')).not.toBeInTheDocument();
      });
    });

    test('a non-consent Graph failure is still reported as an error', async () => {
      // The degraded path is only for consent. A genuine Graph outage must
      // not be silently rendered as "you need to grant access".
      getAllGroups.mockRejectedValue(new Error('Graph API error (503)'));

      render(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('groups-consent-required')).not.toBeInTheDocument();
      expect(notyfService.error).toHaveBeenCalled();
    });

    // Lines 48-50 of Dashboard.jsx: the `grantGroupAccess` catch branch.
    // A user with consent denied clicks "Grant access"; the interactive
    // call still rejects (this time with a non-consent Graph outage) and
    // the catch must surface the error in the UI plus the standard
    // notyfService.error + appInsights.trackException side effects.
    test('grantGroupAccess reports non-consent Graph failures', async () => {
      // First call (mount, non-interactive) rejects with consent error so
      // the prompt is shown.
      getAllGroups.mockRejectedValueOnce(consentError());
      // Second call (interactive, from the user clicking Grant access)
      // rejects with a non-consent outage — exercises the catch branch.
      getAllGroups.mockRejectedValueOnce(
        new Error('Graph API error (503)'),
      );

      render(<Dashboard />);

      // Wait for the prompt to render, then click it.
      const grantButton = await waitFor(() =>
        screen.getByTestId('grant-groups-access-button'),
      );
      fireEvent.click(grantButton);

      // The error must surface in the UI plus the side-effect channels.
      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent(
          'Graph API error (503)',
        );
      });
      expect(notyfService.error).toHaveBeenCalledWith(
        'Failed to load groups: Graph API error (503)',
      );
      expect(appInsights.trackException).toHaveBeenCalledWith(
        expect.objectContaining({
          exception: expect.any(Error),
        }),
      );
      // The prompt stays up because the call did not yield groups data.
      expect(screen.getByTestId('groups-consent-required')).toBeInTheDocument();
    });
  });

  // Lines 84-86 of Dashboard.jsx: the `currentUserRef.current !== currentUser`
  // branch inside the mount effect. The hook captures the active account's
  // username on first render; on a subsequent render where MSAL reports a
  // different active account, the effect must reset `initFetchCompleted` so
  // the next render triggers a fresh data fetch.
  describe('account switch (issue #141 user-change branch)', () => {
    const okabe = { username: 'okabe.rintaro@future-gadget-lab.org' };
    const kurisu = { username: 'makise.kurisu@future-gadget-lab.org' };

    let consoleLogSpy;
    beforeEach(() => {
      // console.log is not a jest mock by default; install a spy so we can
      // assert that the user-change branch surfaced the reload intent.
      consoleLogSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    });
    afterEach(() => {
      consoleLogSpy.mockRestore();
    });

    test('switching the active account reloads the dashboard data', async () => {
      // jest.clearAllMocks() in the outer beforeEach resets every mock's
      // implementation, so re-establish the success path for both the
      // user-data fetch and the groups fetch before driving the
      // account-switch path.
      getUserData.mockResolvedValue({ message: 'Hello from API' });
      getAllGroups.mockResolvedValue([]);

      // First mount: Okabe. The mount effect captures his username into
      // currentUserRef.current and runs the data fetch.
      useMsal.mockReturnValue({
        instance: {
          ...mockMsalInstance,
          getActiveAccount: jest.fn().mockReturnValue(okabe),
        },
      });

      const { rerender } = render(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId('api-message-data')).toBeInTheDocument();
      });

      // Snapshot the call counts so the rerender's effect is visible.
      const initialUserCalls = getUserData.mock.calls.length;
      const initialGroupCalls = getAllGroups.mock.calls.length;

      // Switch the active account to Kurisu and rerender. The effect's
      // dependency array includes `instance.getActiveAccount()?.username`,
      // so the effect re-runs. The branch fires (currentUserRef.current
      // was Okabe's username, currentUser is now Kurisu's), and the
      // dashboard triggers a fresh fetch.
      useMsal.mockReturnValue({
        instance: {
          ...mockMsalInstance,
          getActiveAccount: jest.fn().mockReturnValue(kurisu),
        },
      });
      rerender(<Dashboard />);

      await waitFor(() => {
        expect(getUserData.mock.calls.length).toBeGreaterThan(initialUserCalls);
        expect(getAllGroups.mock.calls.length).toBeGreaterThan(initialGroupCalls);
      });

      // The user-change branch logs to the console so an operator watching
      // devtools can see why the dashboard re-fetched.
      expect(consoleLogSpy).toHaveBeenCalledWith('User changed, reloading data...');

      // Now force an effect re-run with the SAME user so the user-change
      // branch is false on the second rerender. We do that by returning a
      // new instance object (the `instance` dep in the effect's array is a
      // fresh reference) but with the SAME active account username. The
      // effect re-runs, `currentUserRef.current === currentUser` (still
      // kurisu, from the prior switch), so the user-change branch is
      // false, and `initFetchCompleted.current` is still true from the
      // previous successful fetch — so the `if
      // (!initFetchCompleted.current)` guard's false arm runs and NO new
      // fetch is triggered.
      const callsBeforeNoFetch = getUserData.mock.calls.length;
      const logsBeforeNoFetch = consoleLogSpy.mock.calls.filter(
        (call) => call[0] === 'User changed, reloading data...',
      ).length;
      useMsal.mockReturnValue({
        instance: {
          ...mockMsalInstance,
          // Different reference (forces effect re-run) but the same
          // account — currentUserRef.current === currentUser.
          getActiveAccount: jest.fn().mockReturnValue(kurisu),
        },
      });
      rerender(<Dashboard />);

      // Give React a tick to flush any queued effects; the call count must
      // stay flat (no fetch) and no NEW user-change log must fire.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(getUserData.mock.calls.length).toBe(callsBeforeNoFetch);
      const logsAfterNoFetch = consoleLogSpy.mock.calls.filter(
        (call) => call[0] === 'User changed, reloading data...',
      ).length;
      expect(logsAfterNoFetch).toBe(logsBeforeNoFetch);
    });
  });
});