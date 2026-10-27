import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
const put = vi.fn()
vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')
  return { ApiError: actual.ApiError, apiClient: { aiAudit: { get: (p: string) => get(p), put: (p: string, b: unknown) => put(p, b) } } }
})

import { ApiError } from '@/lib/api-client'
import { aiAuditApi, parsePairPage, parsePairDetail, parseSummary, pairsQuery, verdictErrorMessage } from '@/lib/ai-audit'

describe('ai-audit adapter', () => {
  beforeEach(() => { get.mockReset(); put.mockReset() })

  it('parses a page and drops malformed items', () => {
    const page = parsePairPage({
      items: [
        { id: 'pair-1', event_id: 'event-1', event_type: 'person', created_at: '2026-01-01T10:00:00Z', source: 'audit', similarity: 0.8, label_match: true, local_ms: 2000, cloud_ms: 3000, verdict: null },
        { id: '' }, 'junk',
        { id: 'pair-2', event_type: 'bogus', verdict: 'maybe', similarity: 'x' },
      ],
      next_cursor: 'cur-2',
    })
    expect(page.items.map((p) => p.id)).toEqual(['pair-1', 'pair-2'])
    expect(page.items[0]).toMatchObject({ eventType: 'person', source: 'audit', labelMatch: true, localMs: 2000 })
    expect(page.items[1]).toMatchObject({ eventType: null, verdict: null, similarity: null })
    expect(page.nextCursor).toBe('cur-2')
    expect(parsePairPage(null)).toEqual({ items: [], nextCursor: null })
  })

  it('parses detail fields', () => {
    const d = parsePairDetail({ id: 'pair-1', local_text: 'A person at the door.', cloud_text: 'Someone at the door.', local_provider: 'ollama', cloud_provider: 'openai', verdict: 'agree', verdict_at: '2026-01-02T00:00:00Z', text_expires_at: '2026-01-31T00:00:00Z' })
    expect(d).toMatchObject({ localText: 'A person at the door.', cloudProvider: 'openai', verdict: 'agree', textExpiresAt: '2026-01-31T00:00:00Z' })
  })

  it('parses summary and treats readiness as informational', () => {
    const s = parseSummary({ days: [{ date: '2026-01-01', pairs: 4, mean_similarity: 0.7, skipped_cap: 1 }, { nope: 1 }], readiness: { pairs_total: 9, agree_rate: 0.9 } })
    expect(s.days).toHaveLength(1)
    expect(s.days[0]).toMatchObject({ pairs: 4, reviewed: 0, skippedCap: 1, labelAgreement: null })
    expect(s.readiness).toEqual({ informational: true, pairsTotal: 9, agreeRate: 0.9 })
  })

  it('builds the pairs query', () => {
    expect(pairsQuery({ verdict: 'unreviewed' })).toBe('?verdict=unreviewed&limit=50')
    expect(pairsQuery({ verdict: 'agree', eventType: 'doorbell_ring', date: '2026-01-01', cursor: 'c1', limit: 10 }))
      .toBe('?date=2026-01-01&verdict=agree&event_type=doorbell_ring&limit=10&cursor=c1')
  })

  it('calls the S4b endpoints', async () => {
    get.mockResolvedValue({ items: [], next_cursor: null })
    await aiAuditApi.listPairs({ verdict: 'unreviewed' })
    expect(get).toHaveBeenCalledWith('/pairs?verdict=unreviewed&limit=50')
    put.mockResolvedValue({ id: 'pair-1', verdict: 'disagree' })
    const r = await aiAuditApi.setVerdict('pair-1', 'disagree')
    expect(put).toHaveBeenCalledWith('/pairs/pair-1/verdict', { verdict: 'disagree' })
    expect(r.verdict).toBe('disagree')
    get.mockResolvedValue({ days: [] })
    await aiAuditApi.getSummary('2026-01-01', '2026-01-07')
    expect(get).toHaveBeenLastCalledWith('/summary?from=2026-01-01&to=2026-01-07')
  })

  it('gives a clear message for expired text', () => {
    expect(verdictErrorMessage(new ApiError('nf', 404))).toMatch(/expired/i)
    expect(verdictErrorMessage(new ApiError('bad', 422))).toMatch(/not accepted/i)
    expect(verdictErrorMessage(new Error('x'))).toMatch(/could not save/i)
  })
})
