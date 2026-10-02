/**
 * Delete All Data confirmation uses GET /system/storage `event_count`.
 * A load that is still in flight or that failed must not be shown as zero.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SettingsPage from '@/app/settings/page';
import { apiClient } from '@/lib/api-client';
import { deleteAllDataDescription } from '@/lib/storage-event-count';

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
    protect: {
      listControllers: vi.fn(),
    },
  },
}));

vi.mock('@/contexts/SettingsContext', () => ({
  useSettings: () => ({ refreshSystemName: vi.fn() }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'user-1' }, canManageUsers: false }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
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
  description_prompt: 'Describe what you see in this image in one concise sentence.',
  motion_sensitivity: 50,
  detection_method: 'background_subtraction' as const,
  cooldown_period: 60,
  min_motion_area: 5,
  save_debug_images: false,
  retention_days: 30,
  thumbnail_storage: 'filesystem' as const,
  auto_cleanup: true,
};

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  );
}

async function openDeleteDialog() {
  const button = await screen.findByRole('button', { name: /delete all data/i });
  await userEvent.click(button);
  return screen.findByRole('dialog');
}

async function waitForStoredEventCount(text: string) {
  await waitFor(() => {
    const label = screen.getByText('Total Events:');
    const value = label.parentElement?.querySelector('.font-medium');
    expect(value).toHaveTextContent(text);
  });
}

describe('Delete All Data confirmation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.settings.get).mockResolvedValue(settingsFixture);
    vi.mocked(apiClient.settings.getAIProvidersStatus).mockResolvedValue({
      providers: [],
      order: [],
    });
    vi.mocked(apiClient.protect.listControllers).mockResolvedValue([]);
  });

  it('shows the storage event_count, not a missing total_events field', async () => {
    vi.mocked(apiClient.settings.storage).mockResolvedValue({
      event_count: 1072,
      database_mb: 12.5,
      thumbnails_mb: 4,
      total_mb: 16.5,
    });

    renderSettings();
    await waitForStoredEventCount((1072).toLocaleString());

    const dialog = await openDeleteDialog();
    expect(dialog).toHaveTextContent(deleteAllDataDescription(1072));
    expect(dialog).not.toHaveTextContent(/all 0 events/i);
    expect(apiClient.settings.deleteAllData).not.toHaveBeenCalled();
  });

  it('says the count is unavailable while storage stats are still loading', async () => {
    vi.mocked(apiClient.settings.storage).mockImplementation(() => new Promise(() => {}));

    renderSettings();
    const dialog = await openDeleteDialog();

    expect(dialog).toHaveTextContent(deleteAllDataDescription(null));
    expect(dialog).toHaveTextContent(/unavailable/i);
    expect(dialog).not.toHaveTextContent(/all 0 events/i);
    expect(dialog).not.toHaveTextContent(/\b0 events\b/);
  });

  it('says the count is unavailable when storage stats fail to load', async () => {
    let rejectStorage: (error: Error) => void = () => {};
    vi.mocked(apiClient.settings.storage).mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectStorage = reject;
        })
    );

    renderSettings();
    await screen.findByRole('button', { name: /delete all data/i });
    await act(async () => {
      rejectStorage(new Error('storage unavailable'));
    });
    const dialog = await openDeleteDialog();

    expect(dialog).toHaveTextContent(deleteAllDataDescription(null));
    expect(dialog).toHaveTextContent(/unavailable/i);
    expect(dialog).not.toHaveTextContent(/all 0 events/i);
    expect(dialog).not.toHaveTextContent(/\b0 events\b/);
  });

  it('does not treat a legacy total_events field as the event count', async () => {
    vi.mocked(apiClient.settings.storage).mockResolvedValue({
      database_mb: 1,
      thumbnails_mb: 1,
      total_mb: 2,
      total_events: 1072,
    } as unknown as Awaited<ReturnType<typeof apiClient.settings.storage>>);

    renderSettings();
    await waitForStoredEventCount('unavailable');
    const dialog = await openDeleteDialog();

    expect(dialog).toHaveTextContent(deleteAllDataDescription(null));
    expect(dialog).not.toHaveTextContent(/1,072|1072/);
    expect(dialog).not.toHaveTextContent(/all 0 events/i);
  });

  it('still shows zero when the loaded event count is zero', async () => {
    vi.mocked(apiClient.settings.storage).mockResolvedValue({
      event_count: 0,
      database_mb: 0,
      thumbnails_mb: 0,
      total_mb: 0,
    });

    renderSettings();
    await waitForStoredEventCount('0');
    const dialog = await openDeleteDialog();

    expect(dialog).toHaveTextContent(deleteAllDataDescription(0));
    expect(dialog).toHaveTextContent(/all 0 events/i);
  });
});
