/**
 * Alert rule ids are UUID strings. Delete, edit, toggle, and test must not
 * coerce them with Number(), which produces NaN and DELETE /alert-rules/NaN.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeleteRuleDialog } from '@/components/rules/DeleteRuleDialog';
import { RulesList } from '@/components/rules/RulesList';
import { RuleFormDialog } from '@/components/rules/RuleFormDialog';
import { RuleTestResults } from '@/components/rules/RuleTestResults';
import { apiClient } from '@/lib/api-client';
import { mockAlertRule } from '../../test-utils';

const RULE_ID = '30abecb2-8aa8-4ee3-b103-74b6980c6415';
const EVENT_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    alertRules: {
      list: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      toggle: vi.fn(),
      test: vi.fn(),
    },
    entities: {
      list: vi.fn(),
    },
    events: {
      get: vi.fn(),
    },
  },
  ApiError: class ApiError extends Error {
    statusCode: number;
    constructor(message: string, statusCode: number) {
      super(message);
      this.statusCode = statusCode;
    }
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function renderWithQuery(ui: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function expectUuid(value: unknown) {
  expect(value).toBe(RULE_ID);
  expect(typeof value).toBe('string');
  expect(Number.isNaN(value)).toBe(false);
}

describe('alert rule UUID actions', () => {
  const rule = mockAlertRule({ id: RULE_ID, name: 'Driveway person' });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.alertRules.list).mockResolvedValue({ data: [rule], total_count: 1 });
    vi.mocked(apiClient.alertRules.delete).mockResolvedValue(undefined);
    vi.mocked(apiClient.alertRules.update).mockImplementation(async (id, patch) => ({
      ...rule,
      ...patch,
      id,
    }));
    vi.mocked(apiClient.alertRules.test).mockResolvedValue({
      rule_id: RULE_ID,
      events_tested: 1,
      events_matched: 1,
      matching_event_ids: [EVENT_ID],
    });
    vi.mocked(apiClient.entities.list).mockResolvedValue({ entities: [], total: 0, limit: 100, offset: 0 });
    vi.mocked(apiClient.events.get).mockResolvedValue({
      id: EVENT_ID,
      camera_id: 'cam-1',
      timestamp: '2026-10-02T10:00:00Z',
      description: 'Person at the door',
      confidence: 90,
      objects_detected: ['person'],
      thumbnail_path: null,
    } as Awaited<ReturnType<typeof apiClient.events.get>>);
  });

  it('deletes with the UUID string', async () => {
    renderWithQuery(<DeleteRuleDialog rule={rule} onClose={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(apiClient.alertRules.delete).toHaveBeenCalledTimes(1);
    });
    expectUuid(vi.mocked(apiClient.alertRules.delete).mock.calls[0][0]);
  });

  it('toggles enabled with the UUID string', async () => {
    renderWithQuery(
      <RulesList onCreateRule={vi.fn()} onEditRule={vi.fn()} onDeleteRule={vi.fn()} />
    );

    const toggle = await screen.findByRole('switch', { name: /disable rule "driveway person"/i });
    await userEvent.click(toggle);

    await waitFor(() => {
      expect(apiClient.alertRules.update).toHaveBeenCalled();
    });
    const [id, patch] = vi.mocked(apiClient.alertRules.update).mock.calls[0];
    expectUuid(id);
    expect(patch).toEqual({ is_enabled: false });
  });

  it('saves an edit with the UUID string', async () => {
    renderWithQuery(
      <RuleFormDialog open onOpenChange={vi.fn()} onClose={vi.fn()} rule={rule} />
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Update Rule' }));

    await waitFor(() => {
      expect(apiClient.alertRules.update).toHaveBeenCalled();
    });
    expectUuid(vi.mocked(apiClient.alertRules.update).mock.calls[0][0]);
  });

  it('tests the rule and loads matching events with UUID strings', async () => {
    renderWithQuery(<RuleTestResults ruleId={RULE_ID} />);

    await userEvent.click(screen.getByRole('button', { name: 'Test Rule' }));

    await waitFor(() => {
      expect(apiClient.alertRules.test).toHaveBeenCalledWith(RULE_ID, { limit: 50 });
    });
    expect(Number.isNaN(vi.mocked(apiClient.alertRules.test).mock.calls[0][0])).toBe(false);

    await waitFor(() => {
      expect(apiClient.events.get).toHaveBeenCalledWith(EVENT_ID);
    });
    expect(typeof vi.mocked(apiClient.events.get).mock.calls[0][0]).toBe('string');
  });
});
