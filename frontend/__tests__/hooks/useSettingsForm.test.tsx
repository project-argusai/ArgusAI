import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useSettingsForm } from '@/hooks/useSettingsForm';
import { CSRF_ORIGIN_DENIED_MESSAGE } from '@/lib/csrf-error';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

function Harness({
  saveFn,
}: {
  saveFn: (data: { label: string }) => Promise<unknown>;
}) {
  const { formData, updateField, save } = useSettingsForm({
    initialData: { label: '' },
    saveFn,
  });

  return (
    <div>
      <label htmlFor="label">Label</label>
      <input
        id="label"
        value={formData.label}
        onChange={(event) => updateField('label', event.target.value)}
      />
      <button type="button" onClick={() => save().catch(() => undefined)}>
        Save settings
      </button>
    </div>
  );
}

function renderHarness(saveFn: (data: { label: string }) => Promise<unknown>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return render(<Harness saveFn={saveFn} />, { wrapper: Wrapper });
}

describe('useSettingsForm CSRF rejection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps the typed value and explains how to retry', async () => {
    const user = userEvent.setup();
    const saveFn = vi.fn().mockRejectedValue(
      Object.assign(new Error('Request origin is not allowed'), {
        errorCode: 'CSRF_ORIGIN_DENIED',
      }),
    );
    renderHarness(saveFn);

    const input = screen.getByLabelText('Label');
    await user.type(input, 'Front door camera');
    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(CSRF_ORIGIN_DENIED_MESSAGE);
    });
    expect(input).toHaveValue('Front door camera');
    expect(saveFn).toHaveBeenCalledWith({ label: 'Front door camera' });
  });
});
