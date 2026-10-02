/**
 * The alert-rule client must put the UUID in the path unchanged.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiClient } from '@/lib/api-client';

const RULE_ID = '30abecb2-8aa8-4ee3-b103-74b6980c6415';
const EVENT_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: async () => body,
  };
}

describe('alert rule id URLs', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the UUID in get, update, delete, toggle, and test paths', async () => {
    const rule = { id: RULE_ID, name: 'Driveway person', is_enabled: true };
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/test') || init?.method === 'PUT' || init?.method === 'PATCH') {
        return jsonResponse(rule);
      }
      if (init?.method === 'DELETE') {
        return jsonResponse(null, 204);
      }
      return jsonResponse(rule);
    });

    await apiClient.alertRules.get(RULE_ID);
    await apiClient.alertRules.update(RULE_ID, { name: 'Driveway person' });
    await apiClient.alertRules.delete(RULE_ID);
    await apiClient.alertRules.toggle(RULE_ID, false);
    await apiClient.alertRules.test(RULE_ID, { limit: 50 });
    await apiClient.events.get(EVENT_ID);

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual([
      `/api/v1/alert-rules/${RULE_ID}`,
      `/api/v1/alert-rules/${RULE_ID}`,
      `/api/v1/alert-rules/${RULE_ID}`,
      `/api/v1/alert-rules/${RULE_ID}/toggle`,
      `/api/v1/alert-rules/${RULE_ID}/test`,
      `/api/v1/events/${EVENT_ID}`,
    ]);
    expect(urls.join(' ')).not.toContain('NaN');

    const methods = fetchMock.mock.calls.map((call) => (call[1] as RequestInit | undefined)?.method);
    expect(methods).toEqual([undefined, 'PUT', 'DELETE', 'PATCH', 'POST', undefined]);
  });
});
