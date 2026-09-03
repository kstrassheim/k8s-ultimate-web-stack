import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import Experiments from './Experiments';
import { 
  getAllExperiments, 
  createExperiment, 
  updateExperiment, 
  deleteExperiment,
  experimentsSocket,
  formatExperimentTimestamp,
  formatWorldLineChange
} from '@/api/futureGadgetApi';
import { useMsal } from '@azure/msal-react';
import notyfService from '@/log/notyfService';

// Mock dependencies
jest.mock('@azure/msal-react', () => ({
  useMsal: jest.fn()
}));

jest.mock('@/api/futureGadgetApi', () => ({
  getAllExperiments: jest.fn(),
  getExperimentById: jest.fn(),
  createExperiment: jest.fn(),
  updateExperiment: jest.fn(),
  deleteExperiment: jest.fn(),
  formatExperimentTimestamp: jest.fn(),
  formatWorldLineChange: jest.fn(),
  experimentsSocket: {
    connect: jest.fn(),
    disconnect: jest.fn(),
    subscribe: jest.fn(() => jest.fn()), // Returns unsubscribe function
    subscribeToStatus: jest.fn(() => jest.fn())
  }
}));

jest.mock('@/log/notyfService', () => ({
  success: jest.fn(),
  error: jest.fn(),
  info: jest.fn(),
  warning: jest.fn() // Add this line
}));

jest.mock('@/log/appInsights', () => ({
  trackEvent: jest.fn(),
  trackException: jest.fn()
}));

// Global mock data
const mockExperiments = [
  {
    id: 'exp-1',
    name: 'Phone Microwave',
    description: 'Send messages to the past',
    status: 'completed',
    creator_id: 'okabe',
    world_line_change: 0.337192,
    timestamp: '2025-04-07T14:00:00Z'
  },
  {
    id: 'exp-2',
    name: 'Divergence Meter',
    description: 'Measures world line divergence',
    status: 'in_progress',
    creator_id: 'kurisu',
    world_line_change: 0.571024,
    timestamp: '2025-04-06T12:30:00Z'
  }
];

describe('Experiments Component', () => {
  // Add these variables at the top of your describe block
  let originalConsoleLog;
  
  // Save original console.log and mock it before each test
  beforeEach(() => {
    // Store original console method before mocking
    originalConsoleLog = console.log;
    console.log = jest.fn();
    
    // Rest of your existing beforeEach code...
    // Reset all mocks
    jest.clearAllMocks();
    
    // Mock useMsal hook
    useMsal.mockImplementation(() => ({
      instance: {
        getActiveAccount: () => ({ username: 'okabe.rintaro@future-gadget-lab.org' }),
        setActiveAccount: jest.fn(),
      }
    }));
    
    // Mock API functions
    getAllExperiments.mockResolvedValue(mockExperiments);
    formatExperimentTimestamp.mockImplementation(exp => {
      if (exp.id === 'exp-1') return '7.4.2025, 14:00:00';
      if (exp.id === 'exp-2') return '6.4.2025, 12:30:00';
      return 'Unknown';
    });
    formatWorldLineChange.mockImplementation(change => {
      if (change === 0.337192) return '0.337192';
      if (change === 0.571024) return '0.571024';
      return '0.000000';
    });
    
    // Mock WebSocket
    experimentsSocket.subscribeToStatus.mockImplementation(callback => {
      // Immediately call with connected status
      callback('connected');
      return jest.fn(); // Return unsubscribe function
    });
  });

  // Restore original console.log after each test
  afterEach(() => {
    console.log = originalConsoleLog;
  });

  it('shows a loading indicator initially then renders experiments with world line and timestamp columns', async () => {
    render(<Experiments />);
    
    // Check for loading indicator
    expect(screen.getByText('Processing experiment data...')).toBeInTheDocument();
    
    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
      expect(screen.getByText('Divergence Meter')).toBeInTheDocument();
    });
    
    // Check for timestamp and world line columns
    expect(screen.getByText('7.4.2025, 14:00:00')).toBeInTheDocument();
    expect(screen.getByText('0.337192')).toBeInTheDocument();
    expect(screen.getByText('0.571024')).toBeInTheDocument();
  });

  it('opens the create form with world line and timestamp fields', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Click new experiment button
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    
    // Check form is shown with world line and timestamp fields
    expect(screen.getByTestId('experiment-form-title')).toHaveTextContent('Create New Experiment');
    expect(screen.getByLabelText(/world line change/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/timestamp/i)).toBeInTheDocument();
    
    // Verify the Now button is present for timestamp
    expect(screen.getByTitle('Set current time')).toBeInTheDocument();
  });

  it('creates an experiment with world line change value', async () => {
    createExperiment.mockResolvedValue({
      id: 'new-exp-1',
      name: 'Test Experiment',
      world_line_change: 0.123456
    });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Click new experiment button
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    
    // Fill the form
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Test Experiment' }
    });
    
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Test description' }
    });
    
    fireEvent.change(screen.getByLabelText(/world line change/i), {
      target: { value: '0.123456' }
    });
    
    // Submit the form
    fireEvent.click(screen.getByTestId('experiment-form-submit'));
    
    // Wait for API call
    await waitFor(() => {
      expect(createExperiment).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          name: 'Test Experiment',
          description: 'Test description',
          world_line_change: '0.123456'
        })
      );
    });
    
    // Check success notification
    expect(notyfService.success).toHaveBeenCalledWith('Experiment created successfully');
  });

  it('edits an experiment with world line change but timestamp remains read-only', async () => {
    // Mock getExperimentById to return a specific experiment
    const mockExperiment = {
      id: 'exp-1',
      name: 'Phone Microwave',
      description: 'Send messages to the past',
      status: 'completed',
      creator_id: 'okabe',
      world_line_change: 0.337192,
      timestamp: '2025-04-07T14:00:00Z'
    };
    
    const updatedExperiment = {
      ...mockExperiment,
      name: 'Updated Phone Microwave',
      world_line_change: 0.409431
    };
    
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue(mockExperiment);
    updateExperiment.mockResolvedValue(updatedExperiment);
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Click edit button for the first experiment
    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent('Edit Experiment');
    });
    
    // Verify the timestamp field is disabled
    expect(screen.getByLabelText(/timestamp/i)).toBeDisabled();
    
    // Update world line change
    fireEvent.change(screen.getByLabelText(/world line change/i), {
      target: { value: '0.409431' }
    });
    
    // Update name
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Updated Phone Microwave' }
    });
    
    // Submit the form
    fireEvent.click(screen.getByTestId('experiment-form-submit'));
    
    // Wait for API call
    await waitFor(() => {
      expect(updateExperiment).toHaveBeenCalledWith(
        expect.anything(), // The MSAL instance
        'exp-1',
        expect.objectContaining({
          name: 'Updated Phone Microwave',
          world_line_change: '0.409431'
        })
      );
    });
  });

  it('displays formatted world line value in table', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Verify the formatWorldLineChange was called with correct values
    expect(formatWorldLineChange).toHaveBeenCalledWith(0.337192);
    expect(formatWorldLineChange).toHaveBeenCalledWith(0.571024);
    
    // Check formatted values in the table
    const worldLineValues = screen.getAllByTestId('experiment-worldline');
    expect(worldLineValues[0]).toHaveTextContent('0.337192');
    expect(worldLineValues[1]).toHaveTextContent('0.571024');
  });

  it('displays formatted timestamp in table', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Verify formatExperimentTimestamp was called with correct experiments
    expect(formatExperimentTimestamp).toHaveBeenCalledWith(expect.objectContaining({
      id: 'exp-1',
      timestamp: '2025-04-07T14:00:00Z'
    }));
    
    // Check formatted values in the table
    const timestampValues = screen.getAllByTestId('experiment-timestamp');
    expect(timestampValues[0]).toHaveTextContent('7.4.2025, 14:00:00');
    expect(timestampValues[1]).toHaveTextContent('6.4.2025, 12:30:00');
  });

  it('handles WebSocket update with world line change data', async () => {
    // Set up WebSocket message handler
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation(handler => {
      messageHandler = handler;
      return jest.fn(); // Return unsubscribe function
    });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });
    
    // Simulate WebSocket message with updated experiment - match the exact format used in component
    act(() => {
      messageHandler({
        type: 'update', // Direct format, no rawData wrapper
        id: 'exp-1',
        name: 'Phone Microwave (Modified)',
        description: 'Send messages to the past - updated',
        status: 'completed',
        creator_id: 'okabe',
        world_line_change: 0.422761,
        timestamp: '2025-04-07T14:00:00Z',
        actor: 'different.user@futuregadgetlab.org' // Different user to trigger notification
      });
    });
    
    // Verify UI updates
    await waitFor(() => {
      expect(screen.getByText('Phone Microwave (Modified)')).toBeInTheDocument();
    });
    
    // Update the expected notification message to match the actual format
    expect(notyfService.info).toHaveBeenCalledWith(
      'Experiment "Phone Microwave (Modified)" updated by different user'
    );
  });

  it('displays error message when API fails', async () => {
    // Mock API to throw error
    getAllExperiments.mockRejectedValue(new Error('Network error'));
    
    render(<Experiments />);
    
    // Wait for error message
    await waitFor(() => {
      expect(screen.getByTestId('experiments-error')).toHaveTextContent('Failed to load experiments: Network error');
    });
    
    // Verify error notification
    expect(notyfService.error).toHaveBeenCalledWith('Failed to load experiments: Network error');
  });

  it('reacts to a WebSocket create message', async () => {
    // Set up WebSocket message handler
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation(handler => {
      messageHandler = handler;
      return jest.fn(); // Return unsubscribe function
    });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });
    
    // Simulate WebSocket message with new experiment - using direct format
    act(() => {
      messageHandler({
        type: 'create', // Direct format without rawData wrapper
        id: 'exp-3',
        name: 'Time Leap Machine',
        description: 'Send memories to the past',
        status: 'planned',
        creator_id: 'kurisu',
        world_line_change: 0.523299,
        timestamp: '2025-04-08T09:30:00Z',
        actor: 'different.user@futuregadgetlab.org' // Add actor to trigger notification
      });
    });
    
    // Use waitFor to handle async state updates
    await waitFor(() => {
      expect(screen.getByText('Time Leap Machine')).toBeInTheDocument();
    });
    
    // Update expected notification message to match the current format
    expect(notyfService.info).toHaveBeenCalledWith(
      'New experiment "Time Leap Machine" created by different user'
    );
  });

  it('opens delete confirmation and deletes an experiment', async () => {
    deleteExperiment.mockResolvedValue({ message: 'Successfully deleted' });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });
    
    // Click delete button
    fireEvent.click(screen.getByTestId('delete-btn-exp-1'));
    
    // Verify delete confirmation is shown - use a regex to match partial text
    expect(screen.getByText(/Are you sure you want to delete the experiment/)).toBeInTheDocument();
    expect(screen.getByTestId('delete-experiment-name')).toHaveTextContent('Phone Microwave');
    
    // Confirm delete
    fireEvent.click(screen.getByTestId('confirm-delete-btn'));
    
    // Wait for API call
    await waitFor(() => {
      expect(deleteExperiment).toHaveBeenCalledWith(expect.anything(), 'exp-1');
    });
    
    // Verify success notification
    expect(notyfService.success).toHaveBeenCalledWith('Experiment deleted successfully');
  });

  it('handles WebSocket message edge cases with new fields', async () => {
    // Set up WebSocket message handler
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation(handler => {
      messageHandler = handler;
      return jest.fn(); // Return unsubscribe function
    });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });
    
    // Test missing type
    act(() => {
      messageHandler({
        rawData: {
          data: { id: 'test' }
        }
      });
    });
    
    // Test missing data
    act(() => {
      messageHandler({
        rawData: {
          type: 'update'
        }
      });
    });
    
    // Test missing ID in data for update
    act(() => {
      messageHandler({
        rawData: {
          type: 'update',
          data: { name: 'No ID' }
        }
      });
    });
    
    // These should not throw errors and should not affect the UI
    expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    expect(screen.queryByText('No ID')).not.toBeInTheDocument();
  });

  it('validates ISO date format for timestamps', async () => {
    createExperiment.mockResolvedValue({ id: 'test-123', name: 'Date Validation Test' });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Open the create form
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    
    // Fill required fields
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Date Validation Test' }
    });
    
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Testing timestamp validation' }
    });
    
    // Try an invalid date format
    fireEvent.change(screen.getByLabelText(/timestamp/i), {
      target: { value: '2025-04-07 12:34:56' } // Space instead of T
    });
    
    // Submit the form - should show validation error
    fireEvent.click(screen.getByTestId('experiment-form-submit'));
    
    // Check for validation error
    expect(screen.getByText('Please enter a valid ISO date format')).toBeInTheDocument();
    
    // Now try with valid format
    fireEvent.change(screen.getByLabelText(/timestamp/i), {
      target: { value: '2025-04-07T12:34:56.789Z' }
    });
    
    // Submit the form again
    fireEvent.click(screen.getByTestId('experiment-form-submit'));
    
    // Should call API with valid data
    await waitFor(() => {
      expect(createExperiment).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          name: 'Date Validation Test',
          timestamp: '2025-04-07T12:34:56.789Z'
        })
      );
    });
  });

  it('allows setting the current timestamp with Now button', async () => {
    // Mock Date.now() and toISOString()
    const originalDate = global.Date;
    const mockDate = new Date('2025-04-07T09:30:00.000Z');
    global.Date = jest.fn(() => mockDate);
    global.Date.prototype = originalDate.prototype;
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Open create form
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    
    // Click the Now button
    fireEvent.click(screen.getByTitle('Set current time'));
    
    // Check that timestamp field has current date in ISO format
    expect(screen.getByLabelText(/timestamp/i)).toHaveValue('2025-04-07T09:30:00.000Z');
    
    // Restore original Date
    global.Date = originalDate;
  });

  it('disables timestamp field in edit mode', async () => {
    // Mock getExperimentById
    const mockExperiment = {
      id: 'exp-1',
      name: 'Phone Microwave',
      timestamp: '2025-04-07T14:00:00Z'
    };
    
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue(mockExperiment);
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Click edit button
    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent('Edit Experiment');
    });
    
    // Verify timestamp field is disabled
    const timestampField = screen.getByLabelText(/timestamp/i);
    expect(timestampField).toBeDisabled();
    
    // Verify Now button is not shown in edit mode
    expect(screen.queryByTitle('Set current time')).not.toBeInTheDocument();
  });
});

// Add these tests to your existing test file

describe('WebSocket Experiment Notifications', () => {
  let originalConsoleLog;
  
  beforeEach(() => {
    // Store original console method before mocking
    originalConsoleLog = console.log;
    console.log = jest.fn();
    
    // Rest of your existing beforeEach code...
    jest.clearAllMocks();
    
    // Mock useMsal for Kurisu (to test cross-user notifications)
    useMsal.mockImplementation(() => ({
      instance: {
        getActiveAccount: () => ({ 
          username: 'makise.kurisu@futuregadgetlab.org',
        }),
        setActiveAccount: jest.fn(),
      }
    }));
    
    getAllExperiments.mockResolvedValue(mockExperiments);
    
    // Set up WebSocket message handler with direct capture
    experimentsSocket.subscribe.mockImplementation(handler => {
      window.testMessageHandler = handler; // Store handler globally for tests
      return jest.fn();
    });
  });

  // Restore original console.log after each test
  afterEach(() => {
    console.log = originalConsoleLog;
  });
  
  it('shows notifications when another user creates an experiment', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Simulate receiving a WebSocket message for experiment created by Okabe
    act(() => {
      window.testMessageHandler({
        type: 'create',
        id: 'exp-new-1',
        name: 'Time Leap Machine',
        description: 'Send memories to the past',
        status: 'in_progress',
        creator_id: 'Rintaro Okabe',
        world_line_change: 0.523299,
        timestamp: '2025-04-08T09:30:00Z',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify UI updates with the new experiment
    expect(screen.getByText('Time Leap Machine')).toBeInTheDocument();
    
    // Verify notification shows with formatted username
    expect(notyfService.info).toHaveBeenCalledWith(
      'New experiment "Time Leap Machine" created by okabe rintaro'
    );
  });
  
  it('shows notifications when another user updates an experiment', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Simulate receiving a WebSocket message for experiment updated by Okabe
    act(() => {
      window.testMessageHandler({
        type: 'update',
        id: 'exp-1',
        name: 'Phone Microwave Mark II',
        description: 'Updated version with better controls',
        status: 'completed',
        creator_id: 'Rintaro Okabe',
        world_line_change: 0.409431,
        timestamp: '2025-04-07T14:00:00Z',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify UI updates with the updated experiment name
    expect(screen.getByText('Phone Microwave Mark II')).toBeInTheDocument();
    
    // Verify notification shows with formatted username
    expect(notyfService.info).toHaveBeenCalledWith(
      'Experiment "Phone Microwave Mark II" updated by okabe rintaro'
    );
  });
  
  it('shows special warning when experiment being edited is updated by another user', async () => {
    // Mock the getExperimentById to simulate opening edit form
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue(mockExperiments[0]);
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Open the edit form for the first experiment
    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent('Edit Experiment');
    });
    
    // Simulate receiving a WebSocket message for the same experiment being updated by Okabe
    act(() => {
      window.testMessageHandler({
        type: 'update',
        id: 'exp-1',
        name: 'Phone Microwave Mark II',
        description: 'Updated version with better controls',
        status: 'completed',
        creator_id: 'Rintaro Okabe',
        world_line_change: 0.409431,
        timestamp: '2025-04-07T14:00:00Z',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify the warning notification was shown
    expect(notyfService.warning).toHaveBeenCalledWith(
      'This experiment has been updated by okabe rintaro. Your form has been refreshed with the latest data.'
    );
    
    // Verify the form was updated with new data
    const nameInput = screen.getByLabelText(/experiment name/i);
    expect(nameInput.value).toBe('Phone Microwave Mark II');
  });
  
  it('shows notifications when another user deletes an experiment', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getAllByText('Phone Microwave')[0]).toBeInTheDocument();
    });
    
    // Simulate receiving a WebSocket message for experiment deleted by Okabe
    act(() => {
      window.testMessageHandler({
        type: 'delete',
        id: 'exp-1',
        name: 'Phone Microwave',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify the experiment is removed from the UI
    expect(screen.queryByText('Phone Microwave')).not.toBeInTheDocument();
    
    // Verify notification shows
    expect(notyfService.info).toHaveBeenCalledWith(
      'Experiment "Phone Microwave" deleted by okabe rintaro'
    );
  });

  it('shows warning when experiment being edited is deleted by another user', async () => {
    // Mock the getExperimentById to simulate opening edit form
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue({
      ...mockExperiments[0],
      id: 'exp-1' // Ensure ID matches exactly what will be in delete message
    });
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Open the edit form for the first experiment
    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent('Edit Experiment');
    });
    
    // Simulate receiving a WebSocket message for the same experiment being deleted by Okabe
    act(() => {
      window.testMessageHandler({
        type: 'delete',
        id: 'exp-1',
        name: 'Phone Microwave',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Wait for the form to close - the key fix is using waitFor
    await waitFor(() => {
      expect(screen.queryByTestId('experiment-form-title')).not.toBeInTheDocument();
    });
    
    // Verify warning notification
    expect(notyfService.warning).toHaveBeenCalledWith(
      'The experiment you were editing has been deleted by okabe rintaro'
    );
  });
  
  it('does not show notifications for own actions', async () => {
    // Mock useMsal to simulate being Okabe
    useMsal.mockImplementation(() => ({
      instance: {
        getActiveAccount: () => ({ 
          username: 'okabe.rintaro@futuregadgetlab.org',
        }),
        setActiveAccount: jest.fn(),
      }
    }));
    
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Clear any notification calls from initial load
    notyfService.info.mockClear();
    
    // Simulate receiving a WebSocket message for experiment created by Okabe (current user)
    act(() => {
      window.testMessageHandler({
        type: 'create',
        id: 'exp-new-1',
        name: 'Time Leap Machine',
        description: 'Send memories to the past',
        status: 'in_progress',
        creator_id: 'Rintaro Okabe',
        world_line_change: 0.523299,
        timestamp: '2025-04-08T09:30:00Z',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify the new experiment is added
    expect(screen.getByText('Time Leap Machine')).toBeInTheDocument();
    
    // But no notification is shown for your own actions
    expect(notyfService.info).not.toHaveBeenCalled();
  });

  it('handles both WebSocket message formats (rawData and direct)', async () => {
    render(<Experiments />);
    
    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });
    
    // Format 1: rawData wrapper (original format)
    act(() => {
      window.testMessageHandler({
        rawData: {
          type: 'create',
          id: 'exp-new-1',
          name: 'Time Leap Machine',
          description: 'Send memories to the past',
          actor: 'okabe.rintaro@futuregadgetlab.org'
        }
      });
    });
    
    // Verify the experiment is added
    expect(screen.getByText('Time Leap Machine')).toBeInTheDocument();
    
    // Format 2: Direct format from server
    act(() => {
      window.testMessageHandler({
        type: 'create',
        id: 'exp-new-2',
        name: 'Divergence Meter V2',
        description: 'More accurate divergence measurements',
        actor: 'okabe.rintaro@futuregadgetlab.org'
      });
    });
    
    // Verify the second experiment is also added
    expect(screen.getByText('Divergence Meter V2')).toBeInTheDocument();
  });

  it('formats usernames correctly from email addresses', async () => {
    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Test with Future Gadget Lab email format
    act(() => {
      window.testMessageHandler({
        type: 'create',
        id: 'exp-new-1',
        name: 'D-Mail System',
        actor: 'hashida.itaru@futuregadgetlab.org'
      });
    });

    // Verify notification formats username correctly
    expect(notyfService.info).toHaveBeenCalledWith(
      expect.stringContaining('hashida itaru')
    );
  });
});

// ----------------------------------------------------------------------
// Branch coverage tests for Experiments.jsx. Each test here targets a
// specific uncovered branch identified in the lcov report: error paths,
// the WebSocket "unknown format" / "duplicate" branches, the modal
// cancel button, the form helpers, and the helper functions at the
// bottom of the file. The behavioural assertions keep each test
// meaningful rather than mechanically driving the branch.
// ----------------------------------------------------------------------

describe('Experiments.jsx branch coverage', () => {
  // The default mock for @azure/msal-react is `useMsal: jest.fn()` (no
  // implementation), so without an explicit mockImplementation the
  // component's `const { instance } = useMsal()` line fails with
  // `Cannot destructure property 'instance' of undefined`. Re-establish
  // the implementation that the original describe block uses.
  let originalConsoleError;
  beforeEach(() => {
    originalConsoleError = console.error;
    console.error = jest.fn();

    // Restore the same useMsal mock the rest of the file uses — the
    // `instance.getActiveAccount()?.username` access in openCreateForm
    // needs the same shape (with `getActiveAccount`).
    useMsal.mockImplementation(() => ({
      instance: {
        getActiveAccount: () => ({
          username: 'okabe.rintaro@future-gadget-lab.org',
        }),
        setActiveAccount: jest.fn(),
      },
    }));

    // Restore the experiment + status setup the rest of the file uses.
    getAllExperiments.mockResolvedValue(mockExperiments);
    experimentsSocket.subscribeToStatus.mockImplementation((callback) => {
      callback('connected');
      return jest.fn();
    });
  });
  afterEach(() => {
    console.error = originalConsoleError;
  });

  test('Reload button calls fetchExperiments with showMessage=true and surfaces the success toast', async () => {
    // Default mock state from the existing beforeEach: getAllExperiments
    // resolves, status callback fires 'connected'.
    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Clear the success notifications fired by the mount-time fetch so we
    // can pin down the one triggered by the Reload click.
    notyfService.success.mockClear();

    // Line 317: the Reload button's onClick is `() => fetchExperiments(true)`.
    fireEvent.click(screen.getByTestId('reload-experiments-btn'));

    await waitFor(() => {
      // Line 45: the showMessage=true branch fires the success toast.
      expect(notyfService.success).toHaveBeenCalledWith(
        'Experiments loaded successfully',
      );
    });
  });

  test('fetchExperimentById swallows the error and returns null on rejection', async () => {
    // Reject getExperimentById; opening the edit form must NOT throw and
    // must surface the standard "Failed to load experiment details" toast.
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockRejectedValue(new Error('boom'));

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    notyfService.error.mockClear();
    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));

    // Lines 63-64: the catch branch fires the error toast and returns null,
    // so no form opens (the title element is still absent).
    await waitFor(() => {
      expect(notyfService.error).toHaveBeenCalledWith(
        'Failed to load experiment details: boom',
      );
    });
    expect(
      screen.queryByTestId('experiment-form-title'),
    ).not.toBeInTheDocument();
  });

  test('handleCreateExperiment surfaces an error toast on create failure', async () => {
    createExperiment.mockRejectedValue(new Error('create-failed'));

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Will fail to create' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'forced create failure' },
    });
    fireEvent.click(screen.getByTestId('experiment-form-submit'));

    // Line 78: handleCreateExperiment's catch branch fires the toast.
    await waitFor(() => {
      expect(notyfService.error).toHaveBeenCalledWith(
        'Failed to create experiment: create-failed',
      );
    });
    // The form must stay open so the user can retry.
    expect(screen.getByTestId('experiment-form-title')).toBeInTheDocument();
  });

  test('handleUpdateExperiment surfaces an error toast on update failure', async () => {
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue({
      id: 'exp-1',
      name: 'Phone Microwave',
      description: 'Send messages to the past',
      status: 'completed',
      creator_id: 'okabe',
      world_line_change: 0.337192,
      timestamp: '2025-04-07T14:00:00Z',
    });
    updateExperiment.mockRejectedValue(new Error('update-failed'));

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent(
        'Edit Experiment',
      );
    });

    notyfService.error.mockClear();
    fireEvent.click(screen.getByTestId('experiment-form-submit'));

    // Line 95: handleUpdateExperiment's catch branch fires the toast.
    await waitFor(() => {
      expect(notyfService.error).toHaveBeenCalledWith(
        'Failed to update experiment: update-failed',
      );
    });
  });

  test('handleDeleteExperiment surfaces an error toast on delete failure', async () => {
    deleteExperiment.mockRejectedValue(new Error('delete-failed'));

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    notyfService.error.mockClear();
    fireEvent.click(screen.getByTestId('delete-btn-exp-1'));
    fireEvent.click(screen.getByTestId('confirm-delete-btn'));

    // Line 114: handleDeleteExperiment's catch branch fires the toast.
    await waitFor(() => {
      expect(notyfService.error).toHaveBeenCalledWith(
        'Failed to delete experiment: delete-failed',
      );
    });
  });

  test('WebSocket "unknown format" message is logged and discarded', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Lines 180-181: a payload with no `rawData` wrapper AND no top-level
    // `type` field falls into the `console.error` / `return` branch.
    act(() => {
      messageHandler({ something: 'unrecognisable' });
    });

    expect(console.error).toHaveBeenCalledWith(
      'Unknown WebSocket message format:',
      expect.objectContaining({ something: 'unrecognisable' }),
    );
  });

  test('WebSocket duplicate-create messages do not double-insert an experiment', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });

    // First message: a fresh create from a different user — the table gains
    // a row.
    act(() => {
      messageHandler({
        type: 'create',
        id: 'exp-dup',
        name: 'Time Leap Machine',
        actor: 'kurisu.makise@futuregadgetlab.org',
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Time Leap Machine')).toBeInTheDocument();
    });

    // Same id again: the `if (prev.some(exp => exp.id === data.id)) return prev;`
    // guard on line 203 must short-circuit so the table stays at one row.
    const rowsBefore = screen.getAllByTestId(/^experiment-row-/).length;
    act(() => {
      messageHandler({
        type: 'create',
        id: 'exp-dup',
        name: 'Time Leap Machine (renamed)',
        actor: 'kurisu.makise@futuregadgetlab.org',
      });
    });
    const rowsAfter = screen.getAllByTestId(/^experiment-row-/).length;
    expect(rowsAfter).toBe(rowsBefore);
    // The renamed copy must NOT have been applied — the guard returned the
    // previous state object unchanged.
    expect(screen.queryByText('Time Leap Machine (renamed)')).not.toBeInTheDocument();
  });

  test('Delete confirmation modal Cancel button closes the modal without calling the API', async () => {
    // The Cancel button at line 429 calls `setShowDeleteModal(false)`.
    deleteExperiment.mockClear();

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('delete-btn-exp-1'));
    expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('cancel-delete-btn'));

    await waitFor(() => {
      expect(
        screen.queryByTestId('delete-confirmation-modal'),
      ).not.toBeInTheDocument();
    });
    expect(deleteExperiment).not.toHaveBeenCalled();
  });

  test('Experiment form modal X close button invokes onHide', async () => {
    // Lines 402-417: react-bootstrap's Modal.Header closeButton is wired
    // up via the Modal's onHide prop. The onHide callback is the only path
    // that fires the `setShowForm(false)` arrow function literal — a
    // successful form submit does its own internal close. Click the close
    // button to drive onHide, then assert the form is gone.
    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toBeInTheDocument();
    });

    // The Modal renders with a close button (the X) — find by its
    // accessible role.
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    fireEvent.click(closeButtons[0]);

    await waitFor(() => {
      expect(
        screen.queryByTestId('experiment-form-title'),
      ).not.toBeInTheDocument();
    });
  });

  test('Delete confirmation modal X close button invokes onHide', async () => {
    // Lines 420-436: same wiring for the second modal — the Modal.Header
    // closeButton must invoke onHide which calls setShowDeleteModal(false).
    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('delete-btn-exp-1'));
    await waitFor(() => {
      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
    });

    // The delete modal also has a close button (X).
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    fireEvent.click(closeButtons[0]);

    await waitFor(() => {
      expect(
        screen.queryByTestId('delete-confirmation-modal'),
      ).not.toBeInTheDocument();
    });
  });

  test('Collaborators input parses comma-separated entries into the form data', async () => {
    createExperiment.mockResolvedValue({
      id: 'exp-collabs',
      name: 'Collab Experiment',
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Collab Experiment' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Tests collaborators parsing' },
    });

    // Lines 484-485: handleCollaboratorsChange splits the comma-separated
    // string, trims each entry, drops empties, and writes the resulting
    // array back into formData.
    fireEvent.change(screen.getByLabelText(/collaborators/i), {
      target: { value: 'alice@example.com, bob@example.com, , carol@example.com' },
    });
    fireEvent.click(screen.getByTestId('experiment-form-submit'));

    await waitFor(() => {
      expect(createExperiment).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          name: 'Collab Experiment',
          collaborators: [
            'alice@example.com',
            'bob@example.com',
            'carol@example.com',
          ],
        }),
      );
    });
  });

  test('Submitting the form without filling required fields surfaces the validity error', async () => {
    createExperiment.mockClear();

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Open the create form but submit it untouched — the required-name and
    // required-description fields fail React-Bootstrap's checkValidity()
    // pass, hitting the `form.checkValidity() === false` branch (lines
    // 500-502) and short-circuiting before onSubmit fires.
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    fireEvent.click(screen.getByTestId('experiment-form-submit'));

    // The form must still be open (no successful submit) and the API
    // must NOT have been called.
    expect(screen.getByTestId('experiment-form-title')).toBeInTheDocument();
    expect(createExperiment).not.toHaveBeenCalled();
  });

  test('Status badges render the correct Bootstrap color for every status', async () => {
    // getStatusBadgeColor is not exported, so drive it through the rendered
    // table. Render one experiment per status and assert each badge has the
    // expected Bootstrap class.
    const fullCoverage = require('@/api/futureGadgetApi');
    fullCoverage.getAllExperiments.mockResolvedValue([
      { id: 'p', name: 'P', status: 'planned', creator_id: 'o', world_line_change: 0, timestamp: '' },
      { id: 'ip', name: 'IP', status: 'in_progress', creator_id: 'o', world_line_change: 0, timestamp: '' },
      { id: 'c', name: 'C', status: 'completed', creator_id: 'o', world_line_change: 0, timestamp: '' },
      { id: 'f', name: 'F', status: 'failed', creator_id: 'o', world_line_change: 0, timestamp: '' },
      { id: 'a', name: 'A', status: 'abandoned', creator_id: 'o', world_line_change: 0, timestamp: '' },
      { id: 'u', name: 'U', status: 'unknown_status', creator_id: 'o', world_line_change: 0, timestamp: '' },
    ]);

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByTestId('experiments-table')).toBeInTheDocument();
    });

    // 'planned' -> info, 'in_progress' -> primary, 'completed' -> success,
    // 'failed' -> danger, 'abandoned' -> secondary, default -> light.
    const badges = screen.getAllByTestId('experiment-status');
    const colorByStatus = Object.fromEntries(
      badges.map((badge) => [badge.textContent, badge.className]),
    );
    expect(colorByStatus.planned).toMatch(/bg-info/);
    expect(colorByStatus.in_progress).toMatch(/bg-primary/);
    expect(colorByStatus.completed).toMatch(/bg-success/);
    expect(colorByStatus.failed).toMatch(/bg-danger/);
    expect(colorByStatus.abandoned).toMatch(/bg-secondary/);
    expect(colorByStatus.unknown_status).toMatch(/bg-light/);
  });

  test('formatUsername falls back to the raw string when no email pattern is present', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    // Use a username with no `@` — exercises the `return username` branch
    // at line 706.
    useMsal.mockImplementation(() => ({
      instance: {
        getActiveAccount: () => ({
          username: 'not-an-email',
        }),
        setActiveAccount: jest.fn(),
      },
    }));

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    act(() => {
      messageHandler({
        type: 'create',
        id: 'exp-plain',
        name: 'Plain Username Test',
        actor: 'plain-username',
      });
    });

    // formatUsername returns the raw string verbatim when no email pattern
    // matches.
    expect(notyfService.info).toHaveBeenCalledWith(
      'New experiment "Plain Username Test" created by plain-username',
    );
  });

  // Line 226: the `if (!isOwnAction && formMode === 'edit')` short-circuit
  // when the form is in create mode. Receiving an `update` for an experiment
  // the user is NOT editing falls through to the `else if (!isOwnAction)`
  // info branch (line 231) — both sides of the AND expression get exercised.
  test('WebSocket update while in create mode falls through to the generic info toast', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Open the create form so formMode === 'create'. The current user is
    // Okabe (per the outer beforeEach).
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent(
        'Create New Experiment',
      );
    });

    notyfService.info.mockClear();
    notyfService.warning.mockClear();

    // Another user updates an existing experiment while the local form is
    // open in create mode. The formMode check (`formMode === 'edit'`)
    // short-circuits the warning branch; the else-arm info toast fires.
    act(() => {
      messageHandler({
        type: 'update',
        id: 'exp-1',
        name: 'Phone Microwave (live update)',
        actor: 'kurisu.makise@futuregadgetlab.org',
      });
    });

    expect(notyfService.warning).not.toHaveBeenCalled();
    expect(notyfService.info).toHaveBeenCalledWith(
      'Experiment "Phone Microwave (live update)" updated by kurisu makise',
    );
  });

  // Lines 236-253: the delete branch must reject any unknown WebSocket
  // type so it does not silently fall into the delete handler.
  test('WebSocket messages with an unknown type are ignored by the grid', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Phone Microwave')).toBeInTheDocument();
    });

    const rowsBefore = screen.getAllByTestId(/^experiment-row-/).length;
    notyfService.info.mockClear();

    // An unknown type (e.g. 'pong') should not match create/update/delete
    // and therefore must not change the grid or surface any notification.
    act(() => {
      messageHandler({
        type: 'pong',
        id: 'exp-1',
      });
    });

    const rowsAfter = screen.getAllByTestId(/^experiment-row-/).length;
    expect(rowsAfter).toBe(rowsBefore);
    expect(notyfService.info).not.toHaveBeenCalled();
  });

  // Lines 286-287: handleSubmit dispatches to handleUpdateExperiment when
  // formMode === 'edit'. Drive the update path with a real submit so the
  // if/else branches both get a hit.
  test('handleSubmit dispatches to handleUpdateExperiment in edit mode', async () => {
    const { getExperimentById } = require('@/api/futureGadgetApi');
    const mockExperiment = {
      id: 'exp-1',
      name: 'Phone Microwave',
      description: 'Send messages to the past',
      status: 'completed',
      creator_id: 'okabe',
      world_line_change: 0.337192,
      timestamp: '2025-04-07T14:00:00Z',
    };
    getExperimentById.mockResolvedValue(mockExperiment);
    updateExperiment.mockResolvedValue({ ...mockExperiment, name: 'Updated' });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent(
        'Edit Experiment',
      );
    });

    updateExperiment.mockClear();
    fireEvent.click(screen.getByTestId('experiment-form-submit'));

    await waitFor(() => {
      expect(updateExperiment).toHaveBeenCalledWith(
        expect.anything(),
        'exp-1',
        expect.any(Object),
      );
    });
  });

  // Lines 443-451: ExperimentForm's useEffect on `[experiment]` resets the
  // local formData state when the experiment prop changes. Drive that by
  // opening the create form (experiment is the initial blank object),
  // then opening the edit form (a different experiment object) — the
  // useEffect must run and reset formData to the new experiment's values.
  test('ExperimentForm resets formData when the experiment prop changes', async () => {
    const { getExperimentById } = require('@/api/futureGadgetApi');
    getExperimentById.mockResolvedValue({
      id: 'exp-1',
      name: 'Phone Microwave',
      description: 'Send messages to the past',
      status: 'completed',
      creator_id: 'okabe',
      world_line_change: 0.337192,
      timestamp: '2025-04-07T14:00:00Z',
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // First open create: experiment prop is a fresh blank record.
    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('experiment-form-title')).toHaveTextContent(
        'Create New Experiment',
      );
    });
    expect(screen.getByLabelText(/experiment name/i)).toHaveValue('');

    // Close + open the edit form: experiment prop flips to the fetched
    // record, the useEffect fires, and the formData is reset to the
    // fetched values.
    const createCloseButtons = screen.getAllByRole('button', { name: /close/i });
    fireEvent.click(createCloseButtons[0]);
    await waitFor(() => {
      expect(
        screen.queryByTestId('experiment-form-title'),
      ).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-btn-exp-1'));
    await waitFor(() => {
      expect(screen.getByLabelText(/experiment name/i)).toHaveValue(
        'Phone Microwave',
      );
    });
  });

  // Line 469: isValidISODate's regex-mismatch branch (the function returns
  // false when the input does not even match the ISO date shape). Drive it
  // by typing a clearly non-ISO string into the timestamp field.
  test('isValidISODate flags a non-ISO timestamp immediately on change', async () => {
    createExperiment.mockResolvedValue({
      id: 'iso-test',
      name: 'ISO Validation',
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'ISO Validation' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Tests the ISO regex branch' },
    });

    // Type a string that does not match the ISO regex — the
    // `setTimestampError(...)` call on line 460 fires.
    fireEvent.change(screen.getByLabelText(/timestamp/i), {
      target: { value: 'definitely-not-an-iso' },
    });

    expect(
      screen.getByText(/enter a valid ISO date/i),
    ).toBeInTheDocument();
  });

  // Line 700: formatUsername's `if (!username)` branch — when the actor is
  // null/undefined, the helper must return 'Unknown user' so the
  // notification does not surface a stray 'undefined' string.
  test('formatUsername handles a missing actor gracefully', async () => {
    let messageHandler;
    experimentsSocket.subscribe.mockImplementation((handler) => {
      messageHandler = handler;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    act(() => {
      messageHandler({
        type: 'create',
        id: 'exp-unknown-actor',
        name: 'Anonymous Experiment',
        // No actor field — formatUsername must return 'Unknown user'.
      });
    });

    expect(notyfService.info).toHaveBeenCalledWith(
      'New experiment "Anonymous Experiment" created by Unknown user',
    );
  });

  // Line 258: subscribeToStatus with a falsy status must not change the
  // connectionStatus state. The badge stays whatever the initial value
  // was (default 'disconnected').
  test('subscribeToStatus with an empty status does not update the badge', async () => {
    let statusHandler;
    experimentsSocket.subscribeToStatus.mockImplementation((callback) => {
      statusHandler = callback;
      return jest.fn();
    });

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    // Drive the false branch of `if (status)` with an empty string.
    act(() => {
      statusHandler('');
    });

    // The badge stays in the disconnected state — the empty status was
    // filtered out by the guard.
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Disconnected');
  });

  // Lines 286-287: the badge label and color ternary when the status is
  // not 'connected'. Override the default 'connected' status callback
  // for this test so the initial state stays 'disconnected' and the
  // false branches of both ternaries get a hit.
  test('Status badge renders Disconnected with danger color when not connected', async () => {
    experimentsSocket.subscribeToStatus.mockImplementation(() => jest.fn());

    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('Disconnected');
    expect(badge.className).toMatch(/bg-danger/);
  });

  // Line 469: isValidISODate's empty-string short-circuit. Typing into
  // the timestamp field and then clearing it must clear the error message
  // because the empty string is treated as "valid (will be auto-generated)".
  test('isValidISODate treats an empty timestamp as valid', async () => {
    render(<Experiments />);

    await waitFor(() => {
      expect(screen.getByText('Future Gadget Lab Experiments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('new-experiment-btn'));
    fireEvent.change(screen.getByLabelText(/experiment name/i), {
      target: { value: 'Empty Timestamp Test' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Tests the empty-string branch' },
    });

    // Find the timestamp input explicitly via its id so the regex does
    // not accidentally match the Form.Text helper text below the field.
    const timestampInput = document.getElementById('experiment-timestamp');

    // Type an invalid value first to surface the error message.
    fireEvent.change(timestampInput, { target: { value: 'invalid' } });
    expect(
      screen.getByText(/enter a valid ISO date/i),
    ).toBeInTheDocument();

    // Clear the field — empty string is treated as valid (auto-generated),
    // so the error message must be removed AND the form must accept the
    // submit (the empty timestamp short-circuit fires).
    fireEvent.change(timestampInput, { target: { value: '' } });
    expect(
      screen.queryByText(/enter a valid ISO date/i),
    ).not.toBeInTheDocument();

    // The empty timestamp also passes `isValidISODate`'s check inside
    // handleSubmit, which keeps the submit from being rejected as
    // malformed. Confirm by attempting a submit; the API call must not
    // throw on the timestamp.
    createExperiment.mockResolvedValue({
      id: 'empty-ts',
      name: 'Empty Timestamp Test',
    });
    fireEvent.click(screen.getByTestId('experiment-form-submit'));
    await waitFor(() => {
      expect(createExperiment).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          timestamp: '',
        }),
      );
    });
  });
});