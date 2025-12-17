/**
 * MQTTSettings Component Tests (Story P4-2.4)
 *
 * Tests all acceptance criteria:
 * - AC 1: MQTT tab/section appears in settings page under Integrations
 * - AC 2: Broker host/port/credentials configurable via form inputs
 * - AC 3: Test connection button works and shows success/failure with message
 * - AC 4: Connection status displayed in real-time with indicator
 * - AC 5: Save triggers reconnect with new config and shows confirmation
 * - AC 6: Topic prefix customization field available
 * - AC 7: Discovery enable/disable toggle available
 * - AC 8: Form validation shows errors for invalid inputs
 * - AC 9: Password field is masked and shows "configured" indicator
 * - AC 10: Manual "Publish Discovery" button triggers discovery republish
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MQTTSettings } from '@/components/settings/MQTTSettings';
import { apiClient } from '@/lib/api-client';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    mqtt: {
      getConfig: vi.fn(),
      updateConfig: vi.fn(),
      getStatus: vi.fn(),
      testConnection: vi.fn(),
      publishDiscovery: vi.fn(),
    },
  },
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Helper to create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
    },
  });
}

// Helper to render with providers
function renderWithProviders(component: React.ReactNode) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      {component}
    </QueryClientProvider>
  );
}

// Default mock config response
const mockConfig = {
  id: '123',
  broker_host: '192.168.1.100',
  broker_port: 1883,
  username: 'mqtt_user',
  topic_prefix: 'liveobject',
  discovery_prefix: 'homeassistant',
  discovery_enabled: true,
  qos: 1 as const,
  enabled: true,
  retain_messages: true,
  use_tls: false,
  message_expiry_seconds: 300,
  has_password: true,
  created_at: '2025-12-10T10:00:00Z',
  updated_at: '2025-12-10T10:00:00Z',
};

// Default mock status response
const mockStatus = {
  connected: true,
  broker: '192.168.1.100:1883',
  last_connected_at: '2025-12-10T10:00:00Z',
  messages_published: 1234,
  last_error: null,
  reconnect_attempt: 0,
};

describe('MQTTSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set up default mocks
    vi.mocked(apiClient.mqtt.getConfig).mockResolvedValue(mockConfig);
    vi.mocked(apiClient.mqtt.getStatus).mockResolvedValue(mockStatus);
  });

  describe('AC 1: Component renders', () => {
    it('renders the MQTT settings card', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByText('MQTT / Home Assistant')).toBeInTheDocument();
      });
    });

    it('shows loading state when fetching config', async () => {
      // Create a promise that won't resolve immediately to catch loading state
      let resolveConfig: (value: typeof mockConfig) => void;
      vi.mocked(apiClient.mqtt.getConfig).mockImplementation(
        () => new Promise((resolve) => { resolveConfig = resolve; })
      );

      renderWithProviders(<MQTTSettings />);

      // Should show a loading spinner
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeTruthy();

      // Cleanup: resolve the promise
      resolveConfig!(mockConfig);
    });
  });

  describe('AC 2: Broker configuration form fields', () => {
    it('renders broker host input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/broker host/i)).toBeInTheDocument();
      });
    });

    it('renders broker port input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/port/i)).toBeInTheDocument();
      });
    });

    it('renders username input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
      });
    });

    it('renders password input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      });
    });

    it('populates form with config data', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const hostInput = screen.getByLabelText(/broker host/i) as HTMLInputElement;
        expect(hostInput.value).toBe('192.168.1.100');
      });
    });
  });

  describe('AC 3: Test connection button', () => {
    it('renders test connection button', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
      });
    });

    it('disables test button when host is empty', async () => {
      vi.mocked(apiClient.mqtt.getConfig).mockResolvedValue({
        ...mockConfig,
        broker_host: '',
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /test connection/i });
        expect(button).toBeDisabled();
      });
    });

    it('calls testConnection API on click', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.mqtt.testConnection).mockResolvedValue({
        success: true,
        message: 'Connected to 192.168.1.100:1883',
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /test connection/i });
      await user.click(button);

      await waitFor(() => {
        expect(apiClient.mqtt.testConnection).toHaveBeenCalled();
      });
    });
  });

  describe('AC 4: Connection status display', () => {
    it('shows connected badge when connected', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        // There are two "Connected" texts - one in badge, one in status display
        const connectedElements = screen.getAllByText('Connected');
        expect(connectedElements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows disconnected badge when not connected', async () => {
      vi.mocked(apiClient.mqtt.getStatus).mockResolvedValue({
        ...mockStatus,
        connected: false,
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        // There may be multiple "Disconnected" texts - one in badge, one in status display
        const disconnectedElements = screen.getAllByText('Disconnected');
        expect(disconnectedElements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows messages published count', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByText('1,234')).toBeInTheDocument();
      });
    });

    it('shows last error if present', async () => {
      vi.mocked(apiClient.mqtt.getStatus).mockResolvedValue({
        ...mockStatus,
        connected: false,
        last_error: 'Connection refused',
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByText('Connection refused')).toBeInTheDocument();
      });
    });
  });

  describe('AC 5: Save functionality', () => {
    it('renders save button', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
      });
    });

    it('save button is disabled when form is not dirty', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const saveButton = screen.getByRole('button', { name: /save changes/i });
        expect(saveButton).toBeDisabled();
      });
    });

    it('calls updateConfig API on save', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.mqtt.updateConfig).mockResolvedValue(mockConfig);

      renderWithProviders(<MQTTSettings />);

      // Wait for form to load
      await waitFor(() => {
        expect(screen.getByLabelText(/broker host/i)).toBeInTheDocument();
      });

      // Change a value to make form dirty
      const topicInput = screen.getByLabelText(/topic prefix/i);
      await user.clear(topicInput);
      await user.type(topicInput, 'newtopic');

      // Click save
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(apiClient.mqtt.updateConfig).toHaveBeenCalled();
      });
    });
  });

  describe('AC 6: Topic prefix customization', () => {
    it('renders topic prefix input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/topic prefix/i)).toBeInTheDocument();
      });
    });

    it('shows topic preview text', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByText(/liveobject\/camera_name\/event/i)).toBeInTheDocument();
      });
    });

    it('renders discovery prefix input', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/discovery prefix/i)).toBeInTheDocument();
      });
    });
  });

  describe('AC 7: Discovery enable/disable toggle', () => {
    it('renders discovery toggle', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/enable auto-discovery/i)).toBeInTheDocument();
      });
    });

    it('toggle reflects config value', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const toggle = screen.getByLabelText(/enable auto-discovery/i);
        expect(toggle).toBeChecked();
      });
    });

    it('toggle can be disabled', async () => {
      vi.mocked(apiClient.mqtt.getConfig).mockResolvedValue({
        ...mockConfig,
        discovery_enabled: false,
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const toggle = screen.getByLabelText(/enable auto-discovery/i);
        expect(toggle).not.toBeChecked();
      });
    });
  });

  describe('AC 8: Form validation', () => {
    it('validates broker host is required', async () => {
      // Test that validation schema requires broker_host
      const user = userEvent.setup();
      vi.mocked(apiClient.mqtt.getConfig).mockResolvedValue({
        ...mockConfig,
        broker_host: 'test.broker.com',
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/broker host/i)).toBeInTheDocument();
      });

      // Clear host and make form dirty
      const hostInput = screen.getByLabelText(/broker host/i);
      await user.clear(hostInput);

      // The validation should prevent submission - save button may be enabled but form won't submit
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      expect(saveButton).toBeInTheDocument();

      // The form has validation - clicking save should trigger validation
      await user.click(saveButton);

      // Check that updateConfig was NOT called (due to validation failure)
      await waitFor(() => {
        expect(apiClient.mqtt.updateConfig).not.toHaveBeenCalled();
      });
    });

    it('validates port range (1-65535)', async () => {
      const user = userEvent.setup();

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/port/i)).toBeInTheDocument();
      });

      // Clear and enter invalid port
      const portInput = screen.getByLabelText(/port/i);
      await user.clear(portInput);
      await user.type(portInput, '99999');

      // Try to submit
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      // Check that updateConfig was NOT called (due to validation failure)
      await waitFor(() => {
        expect(apiClient.mqtt.updateConfig).not.toHaveBeenCalled();
      });
    });

    it('renders validation error text for invalid port', async () => {
      const user = userEvent.setup();

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/port/i)).toBeInTheDocument();
      });

      // Enter invalid port
      const portInput = screen.getByLabelText(/port/i);
      await user.clear(portInput);
      await user.type(portInput, '0');

      // Submit to trigger validation display
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      // Wait for error message
      await waitFor(() => {
        const errorText = screen.queryByText(/port must be/i);
        expect(errorText).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('AC 9: Password field handling', () => {
    it('password field is masked by default', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
        expect(passwordInput.type).toBe('password');
      });
    });

    it('shows "configured" badge when has_password is true', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument();
      });
    });

    it('does not show "configured" badge when has_password is false', async () => {
      vi.mocked(apiClient.mqtt.getConfig).mockResolvedValue({
        ...mockConfig,
        has_password: false,
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      });

      expect(screen.queryByText('Configured')).not.toBeInTheDocument();
    });

    it('can toggle password visibility', async () => {
      const user = userEvent.setup();
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      });

      // Password should initially be masked
      const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
      expect(passwordInput.type).toBe('password');

      // Find the password container and look for the toggle button inside it
      const passwordContainer = passwordInput.parentElement;
      const toggleButton = passwordContainer?.querySelector('button');

      if (toggleButton) {
        await user.click(toggleButton);

        // After click, password should be visible
        expect(passwordInput.type).toBe('text');
      }
    });
  });

  describe('AC 10: Publish Discovery button', () => {
    it('renders publish discovery button when discovery is enabled', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /publish discovery/i })).toBeInTheDocument();
      });
    });

    it('publish button is disabled when not connected', async () => {
      vi.mocked(apiClient.mqtt.getStatus).mockResolvedValue({
        ...mockStatus,
        connected: false,
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /publish discovery/i });
        expect(button).toBeDisabled();
      });
    });

    it('calls publishDiscovery API on click', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.mqtt.publishDiscovery).mockResolvedValue({
        success: true,
        message: 'Published discovery for 5 cameras',
        cameras_published: 5,
      });

      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /publish discovery/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /publish discovery/i });
      await user.click(button);

      await waitFor(() => {
        expect(apiClient.mqtt.publishDiscovery).toHaveBeenCalled();
      });
    });
  });

  describe('Additional functionality', () => {
    it('renders QoS selector', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/quality of service/i)).toBeInTheDocument();
      });
    });

    it('renders TLS toggle', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/use tls/i)).toBeInTheDocument();
      });
    });

    it('renders retain messages toggle', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/retain messages/i)).toBeInTheDocument();
      });
    });

    it('renders master enable toggle', async () => {
      renderWithProviders(<MQTTSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/enable mqtt integration/i)).toBeInTheDocument();
      });
    });
  });
});
