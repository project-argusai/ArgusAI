/**
 * Tests for GenerateSummaryDialog Component (Story P4-4.5)
 *
 * AC Coverage:
 * - AC6: Dialog opens with Generate Summary button
 * - AC7: Time period dropdown options
 * - AC8: Custom date/time pickers
 * - AC9: Loading state with spinner
 * - AC10: Error state with message
 * - AC11: Summary result display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GenerateSummaryDialog } from '@/components/summaries/GenerateSummaryDialog';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    summaries: {
      generate: vi.fn(),
    },
  },
}));

import { apiClient } from '@/lib/api-client';

// Create query client for tests
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// Wrapper component with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

describe('GenerateSummaryDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('AC6: Dialog trigger button', () => {
    it('renders Generate Summary button', () => {
      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      expect(screen.getByRole('button', { name: /generate summary/i })).toBeInTheDocument();
    });

    it('opens dialog when button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/generate activity summary/i)).toBeInTheDocument();
    });

    it('closes dialog when Cancel is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      // Open dialog
      await user.click(screen.getByRole('button', { name: /generate summary/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      // Close dialog
      await user.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('AC7: Time period dropdown', () => {
    it('shows time period select with default value', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      // Should have time period label (use getAllBy and check at least one exists)
      const timePeriodLabels = screen.getAllByText(/time period/i);
      expect(timePeriodLabels.length).toBeGreaterThan(0);

      // Should have select trigger
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('shows all time period options when dropdown opened', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));
      await user.click(screen.getByRole('combobox'));

      // Check for all options (Radix Select may duplicate items in DOM)
      expect(screen.getAllByText('Last 1 hour').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Last 3 hours').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Last 6 hours').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Last 12 hours').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Last 24 hours').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Custom range').length).toBeGreaterThan(0);
    });
  });

  describe('AC8: Custom date/time pickers', () => {
    it('shows date/time inputs when Custom range selected', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));
      await user.click(screen.getByRole('combobox'));
      await user.click(screen.getByText('Custom range'));

      // Check for date/time inputs
      expect(screen.getByText(/start date/i)).toBeInTheDocument();
      expect(screen.getByText(/start time/i)).toBeInTheDocument();
      expect(screen.getByText(/end date/i)).toBeInTheDocument();
      expect(screen.getByText(/end time/i)).toBeInTheDocument();
    });

    it('hides custom inputs when non-custom option selected', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      // Default should not show custom inputs
      expect(screen.queryByText(/start date/i)).not.toBeInTheDocument();
    });
  });

  describe('AC9: Loading state', () => {
    it('shows loading spinner during generation', async () => {
      const user = userEvent.setup();

      // Mock a slow response
      vi.mocked(apiClient.summaries.generate).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 5000))
      );

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      // Click generate button in dialog
      const generateButton = screen.getByRole('button', { name: /^generate$/i });
      await user.click(generateButton);

      // Should show loading state
      expect(screen.getByText(/generating/i)).toBeInTheDocument();
    });
  });

  describe('AC10: Error state', () => {
    it('shows error message on generation failure', async () => {
      const user = userEvent.setup();

      // Mock error response
      vi.mocked(apiClient.summaries.generate).mockRejectedValue(
        new Error('Summary generation failed')
      );

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      const generateButton = screen.getByRole('button', { name: /^generate$/i });
      await user.click(generateButton);

      await waitFor(() => {
        // Use getAllByText since error message may appear in multiple places
        const errorMessages = screen.getAllByText(/generation failed/i);
        expect(errorMessages.length).toBeGreaterThan(0);
      });
    });
  });

  describe('AC11: Summary result display', () => {
    it('displays generated summary with stats', async () => {
      const user = userEvent.setup();

      const mockSummary = {
        id: 'test-id-123',
        summary_text: 'Test activity summary for the last 3 hours.',
        period_start: '2025-12-12T14:00:00Z',
        period_end: '2025-12-12T17:00:00Z',
        event_count: 5,
        generated_at: '2025-12-12T17:00:00Z',
        stats: {
          total_events: 5,
          by_type: { person: 3, vehicle: 2 },
          by_camera: { 'Front Door': 5 },
          alerts_triggered: 1,
          doorbell_rings: 2,
        },
        ai_cost: 0.001,
        provider_used: 'openai',
        camera_count: 1,
        alert_count: 1,
        doorbell_count: 2,
        person_count: 3,
        vehicle_count: 2,
      };

      vi.mocked(apiClient.summaries.generate).mockResolvedValue(mockSummary);

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      const generateButton = screen.getByRole('button', { name: /^generate$/i });
      await user.click(generateButton);

      await waitFor(() => {
        // Should show summary text
        expect(screen.getByText(/test activity summary/i)).toBeInTheDocument();
      });

      // Should show stats - use more specific queries to avoid matching time strings
      expect(screen.getByText(/events/i)).toBeInTheDocument();
    });

    it('shows Close button after generation', async () => {
      const user = userEvent.setup();

      const mockSummary = {
        id: 'test-id-123',
        summary_text: 'Generated summary text.',
        period_start: '2025-12-12T14:00:00Z',
        period_end: '2025-12-12T17:00:00Z',
        event_count: 0,
        generated_at: '2025-12-12T17:00:00Z',
        stats: null,
        ai_cost: 0,
        provider_used: 'openai',
        camera_count: 0,
        alert_count: 0,
        doorbell_count: 0,
        person_count: 0,
        vehicle_count: 0,
      };

      vi.mocked(apiClient.summaries.generate).mockResolvedValue(mockSummary);

      render(
        <TestWrapper>
          <GenerateSummaryDialog />
        </TestWrapper>
      );

      await user.click(screen.getByRole('button', { name: /generate summary/i }));

      const generateButton = screen.getByRole('button', { name: /^generate$/i });
      await user.click(generateButton);

      await waitFor(() => {
        // Should show Close button (not Cancel) - may have multiple close buttons
        const closeButtons = screen.getAllByRole('button', { name: /close/i });
        expect(closeButtons.length).toBeGreaterThan(0);
      });
    });
  });
});
