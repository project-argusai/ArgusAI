import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const get = vi.fn()
const update = vi.fn()
vi.mock('@/lib/api-client', () => ({ apiClient: { settings: { get: () => get(), update: (s: unknown) => update(s) } } }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { IncidentNotificationSetting, readNotifyPerIncident } from '@/components/settings/IncidentNotificationSetting'

describe('readNotifyPerIncident', () => {
  it('is off unless the value is exactly true', () => {
    expect(readNotifyPerIncident({ notify_per_incident: true })).toBe(true)
    for (const v of [undefined, null, 'true', 1, false]) {
      expect(readNotifyPerIncident({ notify_per_incident: v })).toBe(false)
    }
    expect(readNotifyPerIncident(null)).toBe(false)
  })
})

describe('IncidentNotificationSetting', () => {
  beforeEach(() => {
    get.mockReset()
    update.mockReset()
  })

  it('defaults to off when the setting is missing, with neutral copy', async () => {
    get.mockResolvedValue({})
    render(<IncidentNotificationSetting />)
    const toggle = screen.getByRole('switch', { name: /send one notification per grouped incident/i })
    await waitFor(() => expect(toggle).not.toBeDisabled())
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(/each camera sends its own notification/i)).toBeInTheDocument()
  })

  it('stays off when settings cannot be read', async () => {
    get.mockRejectedValue(new Error('down'))
    render(<IncidentNotificationSetting />)
    const toggle = screen.getByRole('switch')
    await waitFor(() => expect(toggle).not.toBeDisabled())
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('saves notify_per_incident when toggled', async () => {
    get.mockResolvedValue({ notify_per_incident: false })
    update.mockResolvedValue({})
    const user = userEvent.setup()
    render(<IncidentNotificationSetting />)
    const toggle = screen.getByRole('switch')
    await waitFor(() => expect(toggle).not.toBeDisabled())
    await user.click(toggle)
    expect(update).toHaveBeenCalledWith({ notify_per_incident: true })
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'))
  })

  it('stays off if saving fails', async () => {
    get.mockResolvedValue({})
    update.mockRejectedValue(new Error('nope'))
    const user = userEvent.setup()
    render(<IncidentNotificationSetting />)
    const toggle = screen.getByRole('switch')
    await waitFor(() => expect(toggle).not.toBeDisabled())
    await user.click(toggle)
    await waitFor(() => expect(toggle).not.toBeDisabled())
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })
})
