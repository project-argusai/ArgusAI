/**
 * CostDashboard Component Tests
 *
 * Story P3-7.2: Build Cost Dashboard UI
 *
 * Tests cover:
 * - AC1: Dashboard Tab with Key Metrics
 * - AC2: Cost Breakdown Charts
 * - AC3: Estimated Cost Indicator
 * - AC4: Empty State Handling
 * - AC5: Camera Drilldown
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { CostDashboard } from '@/components/settings/CostDashboard';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    settings: {
      getAIUsage: vi.fn(),
    },
  },
}));

import { apiClient } from '@/lib/api-client';

// Sample mock data
const mockUsageData = {
  total_cost: 0.0523,
  total_requests: 142,
  period: {
    start: '2025-11-09T00:00:00Z',
    end: '2025-12-09T23:59:59Z',
  },
  by_date: [
    { date: '2025-12-09', cost: 0.0123, requests: 45 },
    { date: '2025-12-08', cost: 0.0098, requests: 32 },
    { date: '2025-12-07', cost: 0.0102, requests: 35 },
  ],
  by_camera: [
    { camera_id: '1', camera_name: 'Front Door', cost: 0.0234, requests: 67 },
    { camera_id: '2', camera_name: 'Backyard', cost: 0.0156, requests: 45 },
  ],
  by_provider: [
    { provider: 'openai', cost: 0.0456, requests: 120 },
    { provider: 'claude', cost: 0.0067, requests: 22 },
  ],
  by_mode: [
    { mode: 'single_frame', cost: 0.0234, requests: 89 },
    { mode: 'multi_frame', cost: 0.0289, requests: 53 },
  ],
};

const emptyUsageData = {
  total_cost: 0,
  total_requests: 0,
  period: {
    start: '2025-11-09T00:00:00Z',
    end: '2025-12-09T23:59:59Z',
  },
  by_date: [],
  by_camera: [],
  by_provider: [],
  by_mode: [],
};

// Helper to render with providers
const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>
  );
};

describe('CostDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading State', () => {
    it('renders loading UI while data is being fetched', () => {
      vi.mocked(apiClient.settings.getAIUsage).mockImplementation(
        () => new Promise(() => {}) // Never resolves - keeps loading
      );

      const { container } = renderWithProviders(<CostDashboard />);

      // Should show some loading indicator (component shows skeletons or loading state)
      // Looking for the loading state structure
      expect(container.querySelector('.space-y-6')).toBeInTheDocument();
    });
  });

  describe('AC1: Dashboard Tab with Key Metrics', () => {
    it('displays total cost for the period', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        // Cost is formatted - $0.0523 shows as $0.052 (3 decimals for values < $1)
        expect(screen.getByText('$0.052')).toBeInTheDocument();
      });
    });

    it('displays total requests count', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('142')).toBeInTheDocument();
      });
    });

    it('displays period date range', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        // Look for date range in expected format - Nov 8 because start is 2025-11-09T00:00:00Z displayed in local time
        expect(screen.getByText(/Nov/i)).toBeInTheDocument();
      });
    });

    it('displays today cost card', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText(/Today's Cost/i)).toBeInTheDocument();
      });
    });

    it('displays period total card', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Period Total')).toBeInTheDocument();
      });
    });

    it('displays total requests card', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Total Requests')).toBeInTheDocument();
      });
    });

    it('has period selector with options', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        // Default period is "Last 30 Days"
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });
    });
  });

  describe('AC2: Cost Breakdown Charts', () => {
    it('displays cost by provider section', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Cost by Provider')).toBeInTheDocument();
      });
    });

    it('displays cost by camera section', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Cost by Camera')).toBeInTheDocument();
      });
    });

    it('displays daily cost trend section', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Daily Cost Trend')).toBeInTheDocument();
      });
    });

    it('shows provider distribution description', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Distribution across AI providers')).toBeInTheDocument();
      });
    });
  });

  describe('AC3: Estimated Cost Indicator', () => {
    it('displays estimated cost indicator', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        // Look for the estimated indicator text
        expect(screen.getByText(/Estimated ±20%/i)).toBeInTheDocument();
      });
    });
  });

  describe('AC4: Empty State Handling', () => {
    it('shows empty state message when no data', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(emptyUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('No AI usage recorded yet')).toBeInTheDocument();
      });
    });

    it('shows explanation of how usage tracking works', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(emptyUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(
          screen.getByText(/AI usage and costs will appear here/i)
        ).toBeInTheDocument();
      });
    });

    it('shows usage tracking info bullet points', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(emptyUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText(/Each AI analysis request is recorded/i)).toBeInTheDocument();
        expect(screen.getByText(/Costs are calculated based on provider rates/i)).toBeInTheDocument();
      });
    });

    it('does not show charts when no data', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(emptyUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('No AI usage recorded yet')).toBeInTheDocument();
      });

      // Chart sections should not be present in empty state
      expect(screen.queryByText('Cost by Provider')).not.toBeInTheDocument();
      expect(screen.queryByText('Cost by Camera')).not.toBeInTheDocument();
      expect(screen.queryByText('Daily Cost Trend')).not.toBeInTheDocument();
    });
  });

  describe('AC5: Camera Drilldown', () => {
    it('shows click instruction for camera chart', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Click a bar to see mode breakdown')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('displays error message when API fails', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockRejectedValue(
        new Error('Failed to fetch')
      );

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load AI usage data')).toBeInTheDocument();
      });
    });

    it('shows error details from API error', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockRejectedValue(
        new Error('Network error')
      );

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });
  });

  describe('Period Selection', () => {
    it('renders period selector with default value', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        // Cost formatted as $0.052 (3 decimals for values < $1)
        expect(screen.getByText('$0.052')).toBeInTheDocument();
      });

      // Period selector should be present and show default value
      const selector = screen.getByRole('combobox');
      expect(selector).toBeInTheDocument();
      expect(selector).toHaveTextContent('Last 30 Days');
    });

    it('calls API with date parameters on initial load', async () => {
      vi.mocked(apiClient.settings.getAIUsage).mockResolvedValue(mockUsageData);

      renderWithProviders(<CostDashboard />);

      await waitFor(() => {
        expect(screen.getByText('$0.052')).toBeInTheDocument();
      });

      // API should be called with date range params
      expect(apiClient.settings.getAIUsage).toHaveBeenCalledTimes(1);
      expect(apiClient.settings.getAIUsage).toHaveBeenCalledWith(
        expect.objectContaining({
          start_date: expect.any(String),
          end_date: expect.any(String),
        })
      );
    });
  });
});
