/**
 * TunnelSettings Component Tests (Story P11-1.3)
 *
 * Tests all acceptance criteria:
 * - AC 1.3.1: Settings > Integrations tab includes Tunnel section
 * - AC 1.3.2: Enable/disable toggle for tunnel
 * - AC 1.3.3: Secure input field for tunnel token (password type with show/hide toggle)
 * - AC 1.3.4: Status indicator shows connection state
 * - AC 1.3.5: Test connection button validates setup and shows feedback
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TunnelSettings } from '@/components/settings/TunnelSettings';
import { apiClient } from '@/lib/api-client';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    tunnel: {
      getStatus: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      test: vi.fn(),
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

// Default mock status response - disconnected
const mockStatusDisconnected = {
  status: 'disconnected' as const,
  is_connected: false,
  is_running: false,
  hostname: null,
  error: null,
  enabled: false,
  uptime_seconds: 0,
  last_connected: null,
  reconnect_count: 0,
};

// Mock status - connected
const mockStatusConnected = {
  status: 'connected' as const,
  is_connected: true,
  is_running: true,
  hostname: 'argusai.example.com',
  error: null,
  enabled: true,
  uptime_seconds: 3600,
  last_connected: '2025-12-26T10:00:00Z',
  reconnect_count: 2,
};

// Mock status - error
const mockStatusError = {
  status: 'error' as const,
  is_connected: false,
  is_running: false,
  hostname: null,
  error: 'Invalid tunnel token',
  enabled: true,
  uptime_seconds: 0,
  last_connected: null,
  reconnect_count: 0,
};

// Mock status - connecting
const mockStatusConnecting = {
  status: 'connecting' as const,
  is_connected: false,
  is_running: true,
  hostname: null,
  error: null,
  enabled: true,
  uptime_seconds: 0,
  last_connected: null,
  reconnect_count: 0,
};

describe('TunnelSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set up default mocks
    vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusDisconnected);
  });

  describe('AC 1.3.1: Component renders in settings', () => {
    it('renders the Tunnel settings card', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Cloudflare Tunnel')).toBeInTheDocument();
      });
    });

    it('shows loading state when fetching status', async () => {
      // Create a promise that won't resolve immediately to catch loading state
      let resolveStatus: (value: typeof mockStatusDisconnected) => void;
      vi.mocked(apiClient.tunnel.getStatus).mockImplementation(
        () => new Promise((resolve) => { resolveStatus = resolve; })
      );

      renderWithProviders(<TunnelSettings />);

      // Should show a loading spinner
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeTruthy();

      // Cleanup: resolve the promise
      resolveStatus!(mockStatusDisconnected);
    });

    it('shows description text', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Secure remote access without port forwarding')).toBeInTheDocument();
      });
    });
  });

  describe('AC 1.3.2: Enable/disable toggle', () => {
    it('renders enable toggle', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/enable tunnel/i)).toBeInTheDocument();
      });
    });

    it('toggle is off when tunnel is disabled', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        const toggle = screen.getByLabelText(/enable tunnel/i);
        expect(toggle).not.toBeChecked();
      });
    });

    it('toggle is on when tunnel is enabled', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        const toggle = screen.getByLabelText(/enable tunnel/i);
        expect(toggle).toBeChecked();
      });
    });

    it('calls start API when toggling on', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.tunnel.start).mockResolvedValue({
        success: true,
        message: 'Tunnel started',
        status: mockStatusConnected,
      });

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/enable tunnel/i)).toBeInTheDocument();
      });

      const toggle = screen.getByLabelText(/enable tunnel/i);
      await user.click(toggle);

      await waitFor(() => {
        expect(apiClient.tunnel.start).toHaveBeenCalled();
      });
    });

    it('calls stop API when toggling off', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);
      vi.mocked(apiClient.tunnel.stop).mockResolvedValue({
        success: true,
        message: 'Tunnel stopped',
        status: mockStatusDisconnected,
      });

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/enable tunnel/i)).toBeInTheDocument();
      });

      const toggle = screen.getByLabelText(/enable tunnel/i);
      await user.click(toggle);

      await waitFor(() => {
        expect(apiClient.tunnel.stop).toHaveBeenCalled();
      });
    });
  });

  describe('AC 1.3.3: Secure token input', () => {
    it('renders token input field', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/tunnel token/i)).toBeInTheDocument();
      });
    });

    it('token field is password type by default', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        const tokenInput = screen.getByLabelText(/tunnel token/i) as HTMLInputElement;
        expect(tokenInput.type).toBe('password');
      });
    });

    it('can toggle token visibility', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/tunnel token/i)).toBeInTheDocument();
      });

      // Token should initially be masked
      const tokenInput = screen.getByLabelText(/tunnel token/i) as HTMLInputElement;
      expect(tokenInput.type).toBe('password');

      // Find the toggle button inside the token input container
      const tokenContainer = tokenInput.parentElement;
      const toggleButton = tokenContainer?.querySelector('button');

      if (toggleButton) {
        await user.click(toggleButton);

        // After click, token should be visible
        expect(tokenInput.type).toBe('text');
      }
    });

    it('shows "Token configured" badge when hostname is set', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText(/token configured/i)).toBeInTheDocument();
      });
    });

    it('shows placeholder when no token is configured', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        const tokenInput = screen.getByLabelText(/tunnel token/i) as HTMLInputElement;
        expect(tokenInput.placeholder).toContain('Enter Cloudflare Tunnel token');
      });
    });
  });

  describe('AC 1.3.4: Status indicator', () => {
    it('shows disconnected status badge', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Disconnected')).toBeInTheDocument();
      });
    });

    it('shows connected status badge', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Connected')).toBeInTheDocument();
      });
    });

    it('shows connecting status badge', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnecting);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Connecting')).toBeInTheDocument();
      });
    });

    it('shows error status badge', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusError);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Error')).toBeInTheDocument();
      });
    });

    it('shows error message when in error state', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusError);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Invalid tunnel token')).toBeInTheDocument();
      });
    });

    it('shows hostname when connected', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('argusai.example.com')).toBeInTheDocument();
      });
    });

    it('shows uptime when connected', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        // 3600 seconds = 1h 0m
        expect(screen.getByText('1h 0m')).toBeInTheDocument();
      });
    });

    it('shows reconnect count when connected', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });
  });

  describe('AC 1.3.5: Test connection button', () => {
    it('renders test connection button', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
      });
    });

    it('calls start API when testing connection', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.tunnel.start).mockResolvedValue({
        success: true,
        message: 'Connection test successful',
        status: mockStatusConnected,
      });

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /test connection/i });
      await user.click(button);

      await waitFor(() => {
        expect(apiClient.tunnel.start).toHaveBeenCalled();
      });
    });

    it('shows loading state while testing', async () => {
      const user = userEvent.setup();
      let resolveStart: (value: unknown) => void;
      vi.mocked(apiClient.tunnel.start).mockImplementation(
        () => new Promise((resolve) => { resolveStart = resolve; })
      );

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /test connection/i });
      await user.click(button);

      // Should show testing state
      await waitFor(() => {
        expect(screen.getByText(/testing connection/i)).toBeInTheDocument();
      });

      // Cleanup
      resolveStart!({
        success: true,
        message: 'Test complete',
        status: mockStatusConnected,
      });
    });

    it('uses token input when testing with new token', async () => {
      const user = userEvent.setup();
      // Story P13-2.4: Test connection with token uses dedicated test endpoint
      vi.mocked(apiClient.tunnel.test).mockResolvedValue({
        success: true,
        error: null,
        latency_ms: 250,
        hostname: 'my-tunnel.trycloudflare.com',
      });

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/tunnel token/i)).toBeInTheDocument();
      });

      // Enter a token
      const tokenInput = screen.getByLabelText(/tunnel token/i);
      await user.type(tokenInput, 'my-new-token');

      // Click test connection
      const button = screen.getByRole('button', { name: /test connection/i });
      await user.click(button);

      await waitFor(() => {
        expect(apiClient.tunnel.test).toHaveBeenCalledWith('my-new-token');
      });
    });
  });

  describe('Additional functionality', () => {
    it('shows info alert when disabled', async () => {
      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText(/enable cloudflare tunnel/i)).toBeInTheDocument();
      });
    });

    it('shows connected status panel when connected', async () => {
      vi.mocked(apiClient.tunnel.getStatus).mockResolvedValue(mockStatusConnected);

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByText('Tunnel Connected')).toBeInTheDocument();
      });
    });

    it('clears token input after successful start', async () => {
      const user = userEvent.setup();
      vi.mocked(apiClient.tunnel.start).mockResolvedValue({
        success: true,
        message: 'Tunnel started',
        status: mockStatusConnected,
      });

      renderWithProviders(<TunnelSettings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/tunnel token/i)).toBeInTheDocument();
      });

      // Enter a token
      const tokenInput = screen.getByLabelText(/tunnel token/i) as HTMLInputElement;
      await user.type(tokenInput, 'test-token');
      expect(tokenInput.value).toBe('test-token');

      // Toggle on
      const toggle = screen.getByLabelText(/enable tunnel/i);
      await user.click(toggle);

      // Token should be cleared after successful start
      await waitFor(() => {
        expect(tokenInput.value).toBe('');
      });
    });
  });
});
