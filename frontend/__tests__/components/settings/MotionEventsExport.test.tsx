/**
 * Tests for MotionEventsExport Component (Story P6-4.2)
 *
 * Tests AC #1-7:
 * 1. Export section visible in Settings page
 * 2. Date range picker component
 * 3. Camera selector dropdown with "All Cameras" default
 * 4. Export button triggers file download
 * 5. Loading state during export
 * 6. Success toast notification
 * 7. Error toast notification
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MotionEventsExport } from '@/components/settings/MotionEventsExport';
import { toast } from 'sonner';

// Mock the toast library
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    cameras: {
      list: vi.fn().mockResolvedValue([
        { id: 'camera-1', name: 'Front Door Camera' },
        { id: 'camera-2', name: 'Backyard Camera' },
      ]),
    },
  },
}));

// Mock fetch for export endpoint
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock URL.createObjectURL and revokeObjectURL
global.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = vi.fn();

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe('MotionEventsExport', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    // Default successful fetch mock
    mockFetch.mockResolvedValue({
      ok: true,
      headers: new Headers({
        'Content-Disposition': 'attachment; filename=motion_events_2025-12-01_2025-12-17.csv',
      }),
      blob: vi.fn().mockResolvedValue(new Blob(['csv,data'], { type: 'text/csv' })),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // AC #1: Export section visible
  it('renders the export section with title and description', () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    expect(screen.getByText('Motion Events Export')).toBeInTheDocument();
    expect(screen.getByText(/Export raw motion detection data/)).toBeInTheDocument();
  });

  // AC #2: Date range picker
  it('renders date range picker with placeholder text', () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /select date range/i })).toBeInTheDocument();
    expect(screen.getByText('Select date range')).toBeInTheDocument();
  });

  it('opens date picker popover on click', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const dateButton = screen.getByRole('button', { name: /select date range/i });
    await user.click(dateButton);

    // Calendar should be visible in popover
    await waitFor(() => {
      expect(screen.getByText('Clear dates')).toBeInTheDocument();
    });
  });

  // AC #3: Camera selector dropdown with "All Cameras" default
  it('renders camera selector with "All Cameras" as default', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    // Wait for cameras to load
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera/i })).toBeInTheDocument();
    });

    // Should show "All Cameras" by default
    expect(screen.getByText('All Cameras')).toBeInTheDocument();
  });

  it('shows camera list when dropdown is opened', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const select = screen.getByRole('combobox', { name: /select camera/i });
    await user.click(select);

    await waitFor(() => {
      expect(screen.getByText('Front Door Camera')).toBeInTheDocument();
      expect(screen.getByText('Backyard Camera')).toBeInTheDocument();
    });
  });

  // AC #4: Export button triggers file download
  it('renders export button', () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /export motion events to csv/i })).toBeInTheDocument();
    expect(screen.getByText('Export CSV')).toBeInTheDocument();
  });

  it('triggers export on button click', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/motion-events/export?format=csv'),
        expect.objectContaining({
          method: 'GET',
          headers: { 'Accept': 'text/csv' },
        })
      );
    });
  });

  it('passes camera_id when camera is selected', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    // Open camera select and choose a camera
    const select = screen.getByRole('combobox', { name: /select camera/i });
    await user.click(select);

    await waitFor(() => {
      expect(screen.getByText('Front Door Camera')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Front Door Camera'));

    // Click export
    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('camera_id=camera-1'),
        expect.any(Object)
      );
    });
  });

  // AC #5: Loading state during export
  it('shows loading state during export', async () => {
    // Make fetch take some time
    mockFetch.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                ok: true,
                headers: new Headers({
                  'Content-Disposition': 'attachment; filename=test.csv',
                }),
                blob: () => Promise.resolve(new Blob(['data'])),
              }),
            100
          )
        )
    );

    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    // Should show loading state
    expect(screen.getByText('Exporting...')).toBeInTheDocument();
    expect(exportButton).toBeDisabled();

    // Wait for export to complete
    await waitFor(
      () => {
        expect(screen.getByText('Export CSV')).toBeInTheDocument();
      },
      { timeout: 200 }
    );
  });

  // AC #6: Success toast notification
  it('shows success toast after successful export', async () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('Motion events exported successfully')
      );
    });
  });

  // AC #7: Error toast notification
  it('shows error toast when export fails', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      statusText: 'Internal Server Error',
    });

    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Export failed')
      );
    });
  });

  it('shows error toast when network error occurs', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<MotionEventsExport />, { wrapper: createWrapper() });

    const exportButton = screen.getByRole('button', { name: /export motion events to csv/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Export failed')
      );
    });
  });

  // Additional coverage
  it('displays CSV column information', () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    expect(
      screen.getByText(/CSV columns: timestamp, camera_id, camera_name/)
    ).toBeInTheDocument();
  });

  it('has proper ARIA labels for accessibility', () => {
    render(<MotionEventsExport />, { wrapper: createWrapper() });

    expect(screen.getByLabelText(/select date range/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/select camera/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/export motion events to csv/i)).toBeInTheDocument();
  });
});
