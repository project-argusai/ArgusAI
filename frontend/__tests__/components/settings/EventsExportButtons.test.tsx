/**
 * Settings Data Management event export buttons (#602 / CR-012).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SettingsPage from '@/app/settings/page';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams('tab=data'),
  usePathname: () => '/settings',
  useParams: () => ({}),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    settings: {
      get: vi.fn(),
      update: vi.fn(),
      storage: vi.fn(),
      getAIProvidersStatus: vi.fn(),
      deleteAllData: vi.fn(),
    },
    events: {
      exportEvents: vi.fn(),
    },
    protect: {
      listControllers: vi.fn(),
    },
  },
}));

vi.mock('@/contexts/SettingsContext', () => ({
  useSettings: () => ({ refreshSystemName: vi.fn() }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'admin', role: 'admin' },
    isAuthenticated: true,
    isLoading: false,
    isAdmin: true,
    isOperator: false,
    isViewer: false,
    canManageUsers: true,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
  }),
}));

vi.mock('@/components/settings/MotionEventsExport', () => ({
  MotionEventsExport: () => null,
}));

vi.mock('@/components/settings/EntityReprocessing', () => ({
  EntityReprocessing: () => null,
}));

vi.mock('@/components/settings/BackupRestore', () => ({
  BackupRestore: () => null,
}));

const settingsFixture = {
  system_name: 'ArgusAI',
  timezone: 'UTC',
  language: 'English',
  date_format: 'MM/DD/YYYY' as const,
  time_format: '12h' as const,
  primary_model: 'gpt-4o-mini' as const,
  primary_api_key: '',
  fallback_model: null,
  description_prompt: 'Describe what you see.',
  motion_sensitivity: 50,
  detection_method: 'background_subtraction' as const,
  cooldown_period: 60,
  min_motion_area: 5,
  save_debug_images: false,
  retention_days: 30,
  thumbnail_storage: 'filesystem' as const,
  auto_cleanup: true,
};

describe('Settings events export (#602)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.settings.get).mockResolvedValue(settingsFixture as never);
    vi.mocked(apiClient.settings.storage).mockResolvedValue({
      event_count: 3,
      database_mb: 1,
      thumbnails_mb: 1,
      total_mb: 2,
    });
    vi.mocked(apiClient.settings.getAIProvidersStatus).mockResolvedValue({
      providers: [],
      order: [],
    });
    vi.mocked(apiClient.protect.listControllers).mockResolvedValue([]);

    if (!(URL as unknown as { createObjectURL?: unknown }).createObjectURL) {
      (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = () => 'blob:mock';
      (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = () => undefined;
    }
  });

  it('downloads events CSV and distinguishes export from backup in copy', async () => {
    const user = userEvent.setup();
    const blob = new Blob(['id,description\n1,hi'], { type: 'text/csv' });
    vi.mocked(apiClient.events.exportEvents).mockResolvedValue({
      blob,
      filename: 'events_export_test.csv',
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>
    );

    expect(await screen.findByText(/not a full system backup/i)).toBeInTheDocument();

    const csvButton = await screen.findByRole('button', { name: /export events \(csv\)/i });
    await user.click(csvButton);

    await waitFor(() => {
      expect(apiClient.events.exportEvents).toHaveBeenCalledWith('csv');
      expect(toast.success).toHaveBeenCalled();
    });
  });

  it('shows an error toast when export fails', async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.events.exportEvents).mockRejectedValue(new Error('boom'));

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>
    );

    const jsonButton = await screen.findByRole('button', { name: /export events \(json\)/i });
    await user.click(jsonButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});
