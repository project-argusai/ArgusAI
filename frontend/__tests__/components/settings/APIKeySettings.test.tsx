/**
 * APIKeySettings scope selection (issue #648: read-only MCP connector scope)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { APIKeySettings } from '@/components/settings/APIKeySettings';
import { apiClient } from '@/lib/api-client';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    apiKeys: {
      list: vi.fn(),
      create: vi.fn(),
      revoke: vi.fn(),
    },
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <APIKeySettings />
    </QueryClientProvider>
  );
}

async function openCreateDialog() {
  const user = userEvent.setup();
  renderSettings();
  await user.click(await screen.findByRole('button', { name: /create key/i }));
  const dialog = await screen.findByRole('dialog');
  const checkbox = (label: RegExp) =>
    within(dialog).getByText(label).closest('label')!.querySelector('button[role="checkbox"]') as HTMLElement;
  return { user, dialog, checkbox };
}

describe('APIKeySettings scopes', () => {
  beforeEach(() => {
    vi.mocked(apiClient.apiKeys.list).mockResolvedValue([]);
  });

  it('offers the read-only assistant connector (MCP) scope', async () => {
    const { dialog } = await openCreateDialog();
    expect(within(dialog).getByText('Assistant connector (MCP)')).toBeInTheDocument();
    expect(within(dialog).getByText(/Keys that also have Write or Admin are refused/)).toBeInTheDocument();
  });

  it('selecting MCP clears admin and write scopes, and selecting write clears MCP', async () => {
    const { user, checkbox } = await openCreateDialog();

    await user.click(checkbox(/^Admin$/));
    expect(checkbox(/^Admin$/)).toHaveAttribute('data-state', 'checked');

    await user.click(checkbox(/Assistant connector/));
    expect(checkbox(/Assistant connector/)).toHaveAttribute('data-state', 'checked');
    expect(checkbox(/^Admin$/)).toHaveAttribute('data-state', 'unchecked');

    await user.click(checkbox(/^Write Cameras$/));
    expect(checkbox(/^Write Cameras$/)).toHaveAttribute('data-state', 'checked');
    expect(checkbox(/Assistant connector/)).toHaveAttribute('data-state', 'unchecked');

    await user.click(checkbox(/Assistant connector/));
    expect(checkbox(/^Write Cameras$/)).toHaveAttribute('data-state', 'unchecked');
  });
});
