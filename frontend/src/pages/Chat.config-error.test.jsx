/**
 * Coverage for the "WebSocketClient is missing subscribe" defensive
 * branch in src/pages/Chat.jsx (lines 30-33): when the WebSocketClient
 * instance lacks a `subscribe` function the component sets an error
 * and bails out before subscribing. The defensive branch never fires
 * with the production WebSocketClient (which always ships subscribe);
 * to drive the branch from a test, this file mounts the component
 * against a mock that does NOT define `subscribe`.
 *
 * Lives in a separate file so its mock factory does not collide with
 * the message/status mock used by the rest of Chat.test.jsx — jest's
 * top-level `jest.mock` is per-module, and `jest.isolateModules` inside
 * the existing file would force re-importing every mock the rest of
 * the suite needs. A standalone file is cheaper and keeps the
 * coverage assertion explicit.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock @azure/msal-react so the component can pull instance.
jest.mock('@azure/msal-react', () => ({
  useMsal: () => ({ instance: { name: 'mock-msal-instance' } }),
}));

// Mock @/api/socket with a WebSocketClient that does NOT have a
// `subscribe` method. This is the only thing that drives the
// defensive branch in Chat.jsx — any real WebSocketClient in the
// production codebase would always expose subscribe.
jest.mock('@/api/socket', () => ({
  WebSocketClient: jest.fn().mockImplementation(() => ({
    connect: jest.fn().mockResolvedValue(true),
    // Deliberately no `subscribe` method.
    subscribeToStatus: jest.fn().mockImplementation(() => jest.fn()),
    send: jest.fn(),
    disconnect: jest.fn(),
    getStatus: jest.fn().mockReturnValue('disconnected'),
  })),
}));

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

// Silence the console.error the defensive branch intentionally fires.
let originalConsoleError;
beforeEach(() => {
  originalConsoleError = console.error;
  console.error = jest.fn();
});
afterEach(() => {
  console.error = originalConsoleError;
});

describe('Chat — WebSocketClient missing subscribe (defensive branch)', () => {
  test('sets the configuration error and never subscribes', async () => {
    // Import AFTER mocks are registered so the mock is picked up.
    const { default: Chat } = require('./Chat');
    render(<Chat />);

    // The defensive branch sets `error` to a fixed string when
    // `subscribe` is missing on the WebSocketClient instance.
    const errorMessage = await screen.findByText(/WebSocket client configuration error/i);
    expect(errorMessage).toBeInTheDocument();

    // The page should still render the chat shell — only the
    // subscription is aborted, not the whole component.
    expect(screen.getByText('Live Chat')).toBeInTheDocument();

    // The defensive branch intentionally logs to console.error so the
    // operator sees the configuration drift; assert it ran.
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining('WebSocketClient is missing subscribe method'),
    );
  });
});
