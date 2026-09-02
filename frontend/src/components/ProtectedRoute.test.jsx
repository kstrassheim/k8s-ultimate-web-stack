import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import ProtectedRoute from './ProtectedRoute';
import { useMsal } from '@azure/msal-react';
import appInsights from '@/log/appInsights';

// React Router v6.4+ future flags
const routerFutureConfig = {
  v7_startTransition: true,
  v7_relativeSplatPath: true
};

describe('ProtectedRoute Component', () => {
  afterEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
  });

  test('redirects to /access-denied when no active account is present', () => {
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => null },
    });

    render(
      <MemoryRouter initialEntries={['/test']} future={routerFutureConfig}>
        <ProtectedRoute requiredRoles={['admin']}>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    // Verify view
    expect(screen.getByTestId('protected-route-no-account')).toBeInTheDocument();
  });

  test('renders children if active account has required roles', () => {
    const account = {
      idTokenClaims: { roles: ['Admin', 'User'] },
    };
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => account },
    });

    render(
      <MemoryRouter future={routerFutureConfig}>
        <ProtectedRoute requiredRoles={['admin']}>
          <div data-testid="child">Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.getByTestId('protected-route-authorized')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toHaveTextContent('Protected Content');
  });

  test('redirects to /access-denied when active account lacks required roles', () => {
    const account = {
      idTokenClaims: { roles: ['User'] },
    };
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => account },
    });

    render(
      <MemoryRouter initialEntries={['/test']} future={routerFutureConfig}>
        <ProtectedRoute requiredRoles={['admin']}>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.getByTestId('protected-route-insufficient-permissions')).toBeInTheDocument();
    // Check sessionStorage and tracking call
    expect(sessionStorage.getItem('redirectPath')).toBe(location.pathname);
    expect(appInsights.trackEvent).toHaveBeenCalledWith({
      name: 'Protected Route - Redirecting to Access denied page',
    });
  });

  test('falls through to the [] fallback when the account has no idTokenClaims', () => {
    // The token-claims read is gated by `account.idTokenClaims?.roles ||
    // []`. When `idTokenClaims` itself is undefined (e.g. an ID token
    // issued without the role claim) the optional-chain returns
    // undefined and the `|| []` fallback fires. Without this test the
    // "idTokenClaims is undefined" arm of the optional-chain is the
    // only branch the existing suite never reaches.
    const account = {}; // no idTokenClaims at all
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => account },
    });

    render(
      <MemoryRouter initialEntries={['/test']} future={routerFutureConfig}>
        <ProtectedRoute requiredRoles={['admin']}>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    // No roles matches no required-roles → insufficient-permissions
    // branch fires, not the no-account branch.
    expect(screen.getByTestId('protected-route-insufficient-permissions')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-route-no-account')).not.toBeInTheDocument();
    expect(screen.queryByTestId('protected-route-authorized')).not.toBeInTheDocument();
  });

  test('falls through to the [] fallback when idTokenClaims has no roles field', () => {
    // Mirror of the above for the second arm of the optional-chain:
    // `idTokenClaims` is present but `idTokenClaims.roles` is undefined.
    const account = { idTokenClaims: {} };
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => account },
    });

    render(
      <MemoryRouter initialEntries={['/test']} future={routerFutureConfig}>
        <ProtectedRoute requiredRoles={['admin']}>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.getByTestId('protected-route-insufficient-permissions')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-route-no-account')).not.toBeInTheDocument();
    expect(screen.queryByTestId('protected-route-authorized')).not.toBeInTheDocument();
  });

  test('treats omitted requiredRoles as an empty role list (default param branch)', () => {
    // The destructured `requiredRoles = []` default on the function
    // signature is its own branch in istanbul's coverage view — every
    // other test passes `requiredRoles` explicitly, so without this
    // test the default arm never fires. With the default `[]`, the
    // `every()` check returns true (vacuous truth on an empty array)
    // and the authenticated branch wins.
    const account = {
      idTokenClaims: { roles: ['User'] },
    };
    useMsal.mockReturnValue({
      instance: { getActiveAccount: () => account },
    });

    render(
      <MemoryRouter future={routerFutureConfig}>
        <ProtectedRoute>
          <div data-testid="child">Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.getByTestId('protected-route-authorized')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toHaveTextContent('Protected Content');
  });
});