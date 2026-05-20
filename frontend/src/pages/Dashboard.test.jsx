import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import Dashboard from './Dashboard';
import { isNewDashboardEnabled } from '@/config';

// We need to test two states: flag true and flag false
// Since the config reads from import.meta.env at module evaluation time,
// we need to test the actual current state (which in CI is the default undefined = false)

describe('Dashboard Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('when VITE_NEW_DASHBOARD is not set or false', () => {
    test('shows Dashboard Unavailable message', () => {
      render(<Dashboard />);

      expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard-unavailable')).toBeInTheDocument();
      expect(screen.getByText('Dashboard Unavailable')).toBeInTheDocument();
      expect(screen.getByText('The new dashboard is not currently enabled. Check back soon!')).toBeInTheDocument();
    });

    test('does not render WorldlineMonitor when flag is false', () => {
      render(<Dashboard />);

      // WorldlineMonitor should NOT be rendered
      expect(screen.queryByTestId('worldline-container')).not.toBeInTheDocument();
    });
  });
});