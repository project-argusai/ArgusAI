import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import {
  applyReanalyzedEvent,
  applyReanalyzedEventToCache,
  mergeReanalyzedEvent,
  resolveOpenEvent,
} from '@/lib/reanalyzed-event'
import type { IEvent, IEventsResponse } from '@/types/event'

function event(overrides: Partial<IEvent> = {}): IEvent {
  return {
    id: 'event-1',
    camera_id: 'cam-1',
    timestamp: '2026-10-05T15:15:00Z',
    description: 'At 10:15 AM a red SUV entering the driveway in the first frame.',
    confidence: 40,
    objects_detected: ['vehicle'],
    thumbnail_path: null,
    thumbnail_base64: null,
    alert_triggered: false,
    created_at: '2026-10-05T15:15:00Z',
    source_type: 'protect',
    smart_detection_type: 'vehicle',
    is_doorbell_ring: false,
    reanalysis_count: 0,
    ...overrides,
  }
}

describe('mergeReanalyzedEvent', () => {
  it('copies the new description onto the matching event only', () => {
    const current = event()
    const other = event({ id: 'event-2', description: 'Someone else' })
    const update = event({
      description: "At 3:15 PM a red sedan is parked in the driveway.",
      reanalysis_count: 1,
      ai_confidence: 90,
      low_confidence: false,
    })

    const merged = mergeReanalyzedEvent(current, update)
    expect(merged.description).toBe("At 3:15 PM a red sedan is parked in the driveway.")
    expect(merged.reanalysis_count).toBe(1)
    expect(merged.camera_id).toBe(current.camera_id)
    expect(mergeReanalyzedEvent(other, update)).toBe(other)
  })
})

describe('applyReanalyzedEventToCache', () => {
  it('updates the matching event inside infinite query pages', () => {
    const pages = {
      pages: [
        {
          events: [event(), event({ id: 'event-2', description: 'Leave me' })],
          total_count: 2,
          offset: 0,
        } satisfies IEventsResponse,
      ],
      pageParams: [0],
    }

    const next = applyReanalyzedEventToCache(pages, {
      id: 'event-1',
      description: 'John Smith is at the door.',
      reanalysis_count: 2,
    }) as typeof pages

    expect(next.pages[0].events[0].description).toBe('John Smith is at the door.')
    expect(next.pages[0].events[0].reanalysis_count).toBe(2)
    expect(next.pages[0].events[1].description).toBe('Leave me')
    expect(next.pageParams).toEqual([0])
  })

  it('updates a recent-events list and a single event record', () => {
    const list = { events: [event()], total_count: 1, offset: 0 }
    const patchedList = applyReanalyzedEventToCache(list, {
      id: 'event-1',
      description: 'Updated list copy',
    }) as typeof list
    expect(patchedList.events[0].description).toBe('Updated list copy')

    const single = applyReanalyzedEventToCache(event(), {
      id: 'event-1',
      description: 'Updated detail copy',
    }) as IEvent
    expect(single.description).toBe('Updated detail copy')
  })
})

describe('applyReanalyzedEvent', () => {
  it('writes the update into events and event queries', () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['events', { source: 'protect' }], {
      pages: [{ events: [event()], total_count: 1, offset: 0 }],
      pageParams: [0],
    })
    queryClient.setQueryData(['event', 'event-1'], event())

    applyReanalyzedEvent(queryClient, {
      id: 'event-1',
      description: 'Isaac is in the driveway.',
      reanalysis_count: 1,
    })

    const infinite = queryClient.getQueryData<{ pages: Array<{ events: IEvent[] }> }>([
      'events',
      { source: 'protect' },
    ])
    const single = queryClient.getQueryData<IEvent>(['event', 'event-1'])
    expect(infinite?.pages[0].events[0].description).toBe('Isaac is in the driveway.')
    expect(single?.description).toBe('Isaac is in the driveway.')
    expect(single?.reanalysis_count).toBe(1)
  })
})

describe('resolveOpenEvent', () => {
  it('keeps the reanalyze response until the list copy is newer', () => {
    const selected = event({
      description: 'John Smith is at the door.',
      reanalysis_count: 1,
      reanalyzed_at: '2026-10-05T19:00:00Z',
    })
    const staleList = [event()]

    expect(resolveOpenEvent(selected, staleList)?.description).toBe('John Smith is at the door.')
  })

  it('uses the refreshed list event once its reanalysis count is newer', () => {
    const selected = event()
    const listed = event({
      description: 'John Smith is at the door.',
      reanalysis_count: 1,
    })

    expect(resolveOpenEvent(selected, [listed])?.description).toBe('John Smith is at the door.')
  })

  it('returns null when nothing is open and the snapshot when the id is not in the list', () => {
    expect(resolveOpenEvent(null, [event()])).toBeNull()
    const selected = event({ id: 'missing', description: 'Still here' })
    expect(resolveOpenEvent(selected, [event()])).toBe(selected)
  })
})
