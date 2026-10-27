import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '../../test-utils'

const get = vi.fn()
const put = vi.fn()
vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')
  return { ApiError: actual.ApiError, apiClient: { aiAudit: { get: (p: string) => get(p), put: (p: string, b: unknown) => put(p, b) } } }
})

import { ApiError } from '@/lib/api-client'
import { AuditReview } from '@/components/ai-audit/AuditReview'
import { AuditHelpText } from '@/components/ai-audit/AuditHelpText'

const NOW = new Date(2026, 0, 7, 12)
const item = (id: string, extra: Record<string, unknown> = {}) => ({
  id, event_id: `event-${id}`, event_type: 'person', created_at: '2026-01-07T10:00:00Z', source: 'audit',
  similarity: 0.8, label_match: true, local_ms: 2000, cloud_ms: 3000, verdict: null, ...extra,
})
const detail = (id: string, extra: Record<string, unknown> = {}) => ({
  ...item(id), local_text: `Local text ${id}`, cloud_text: `Cloud text ${id}`,
  local_provider: 'ollama', cloud_provider: 'openai', verdict_at: null, text_expires_at: '2026-02-06T00:00:00Z', ...extra,
})
const summary = {
  days: [{ date: '2026-01-07', pairs: 3, audit_pairs: 2, fallback_pairs: 1, mean_similarity: 0.79, label_agreement: 0.93, local_p50_ms: 2100, local_p95_ms: 5200, reviewed: 1, agree: 1, disagree: 0, unsure: 0, skipped_cap: 0, skipped_budget: 0 }],
  readiness: { informational: true, pairs_total: 3, agree_rate: 1 },
}

function route(pages: Record<string, unknown>) {
  get.mockImplementation(async (p: string) => {
    if (p.startsWith('/summary')) return summary
    if (p.startsWith('/pairs/')) return detail(p.split('/')[2])
    for (const [k, v] of Object.entries(pages)) if (p.includes(k)) return v
    return pages.default ?? { items: [], next_cursor: null }
  })
}

describe('AuditReview', () => {
  beforeEach(() => { get.mockReset(); put.mockReset() })

  it('shows the summary with informational readiness and defaults to unreviewed', async () => {
    route({ default: { items: [item('p1')], next_cursor: null } })
    render(<AuditReview now={NOW} />)
    expect(await screen.findByTestId('readiness')).toHaveTextContent(/informational/i)
    expect(screen.getByText('79%')).toBeInTheDocument()
    await screen.findByRole('list', { name: /audit pairs/i })
    expect(get).toHaveBeenCalledWith('/pairs?verdict=unreviewed&limit=50')
    expect(get).toHaveBeenCalledWith('/summary?from=2026-01-01&to=2026-01-07')
  })

  it('shows empty and error states', async () => {
    route({ default: { items: [], next_cursor: null } })
    const { unmount } = render(<AuditReview now={NOW} />)
    expect(await screen.findByText(/nothing left to review/i)).toBeInTheDocument()
    unmount()
    get.mockImplementation(async (p: string) => { if (p.startsWith('/summary')) throw new Error('x'); throw new ApiError('boom', 500) })
    render(<AuditReview now={NOW} />)
    expect(await screen.findByText(/couldn’t load audit pairs/i)).toBeInTheDocument()
    expect(screen.getByText(/couldn’t load the daily summary/i)).toBeInTheDocument()
  })

  it('filters and pages with the cursor', async () => {
    route({
      'cursor=c2': { items: [item('p9')], next_cursor: null },
      'event_type=package': { items: [item('p5', { event_type: 'package' })], next_cursor: null },
      default: { items: [item('p1')], next_cursor: 'c2' },
    })
    const { user } = render(<AuditReview now={NOW} />)
    await screen.findByRole('list', { name: /audit pairs/i })
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(get).toHaveBeenCalledWith('/pairs?verdict=unreviewed&limit=50&cursor=c2'))
    await user.click(screen.getByRole('button', { name: /previous/i }))
    await user.selectOptions(screen.getByLabelText(/event type/i), 'package')
    await waitFor(() => expect(get).toHaveBeenCalledWith('/pairs?verdict=unreviewed&event_type=package&limit=50'))
    await user.selectOptions(screen.getByLabelText(/verdict/i), 'disagree')
    await waitFor(() => expect(get).toHaveBeenCalledWith('/pairs?verdict=disagree&event_type=package&limit=50'))
  })

  it('shows texts side by side and moves to the next unreviewed pair after a verdict (keyboard)', async () => {
    route({ default: { items: [item('p1'), item('p2', { verdict: 'agree' }), item('p3')], next_cursor: null } })
    put.mockImplementation(async (p: string, b: { verdict: string }) => detail(p.split('/')[2], { verdict: b.verdict }))
    const { user } = render(<AuditReview now={NOW} />)
    const list = await screen.findByRole('list', { name: /audit pairs/i })
    await user.click(within(list).getAllByRole('button')[0])
    expect(await screen.findByTestId('local-text')).toHaveTextContent('Local text p1')
    expect(screen.getByTestId('cloud-text')).toHaveTextContent('Cloud text p1')
    await user.keyboard('d')
    expect(put).toHaveBeenCalledWith('/pairs/p1/verdict', { verdict: 'disagree' })
    await waitFor(() => expect(screen.getByTestId('local-text')).toHaveTextContent('Local text p3'))
    await user.click(screen.getByRole('button', { name: /^agree/i }))
    expect(put).toHaveBeenLastCalledWith('/pairs/p3/verdict', { verdict: 'agree' })
  })

  it('shows a clear message when the text has expired', async () => {
    route({ default: { items: [item('p1')], next_cursor: null } })
    put.mockRejectedValue(new ApiError('Not found', 404))
    const { user } = render(<AuditReview now={NOW} />)
    const list = await screen.findByRole('list', { name: /audit pairs/i })
    await user.click(within(list).getByRole('button'))
    await user.click(await screen.findByRole('button', { name: /^unsure/i }))
    expect(await screen.findByText(/text has expired/i)).toBeInTheDocument()
  })
})

describe('AuditHelpText', () => {
  it('says plainly what is sent to cloud', () => {
    render(<AuditHelpText />)
    const t = screen.getByTestId('ai-audit-help').textContent ?? ''
    expect(t).toMatch(/more of your household images to the cloud/i)
    expect(t).toMatch(/person, vehicle, package and doorbell ring/i)
    expect(t).toMatch(/up to 200 a\s+day/i)
    expect(t).toMatch(/already enabled/i)
  })
})
