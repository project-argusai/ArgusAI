import { describe, expect, it } from 'vitest';
import { collapseIncidentTimeline, incidentPrimaryId } from '@/lib/incident-groups';
import type { IEvent } from '@/types/event';

function event(partial: Pick<IEvent, 'id' | 'timestamp'> & Partial<IEvent>): IEvent {
  return {
    camera_id: 'cam',
    description: partial.id,
    confidence: 80,
    objects_detected: ['vehicle'],
    thumbnail_path: null,
    thumbnail_base64: null,
    alert_triggered: false,
    created_at: partial.timestamp,
    source_type: 'protect',
    smart_detection_type: 'vehicle',
    is_doorbell_ring: false,
    ...partial,
  };
}

describe('collapseIncidentTimeline', () => {
  it('keeps one card for cameras inside the same incident', () => {
    const driveway = event({
      id: 'driveway',
      timestamp: '2026-10-01T17:28:18Z',
      camera_name: 'Driveway',
    });
    const garage = event({
      id: 'garage',
      timestamp: '2026-10-01T17:28:19Z',
      camera_name: 'Garage',
      correlation_group_id: 'group-1',
    });
    const groupedDriveway = { ...driveway, correlation_group_id: 'group-1' };
    const later = event({ id: 'later', timestamp: '2026-10-01T18:00:00Z' });

    const visible = collapseIncidentTimeline([garage, groupedDriveway, later]);

    expect(visible.map((item) => item.id)).toEqual(['driveway', 'later']);
    expect(incidentPrimaryId([garage, groupedDriveway])).toBe('driveway');
  });

  it('keeps a doorbell ring as the visible card', () => {
    const driveway = event({
      id: 'driveway',
      timestamp: '2026-10-01T17:28:18Z',
      correlation_group_id: 'group-1',
    });
    const ring = event({
      id: 'ring',
      timestamp: '2026-10-01T17:28:19Z',
      correlation_group_id: 'group-1',
      is_doorbell_ring: true,
    });

    expect(collapseIncidentTimeline([ring, driveway]).map((item) => item.id)).toEqual(['ring']);
  });

  it('does not hide a member whose other cameras are not loaded', () => {
    const garage = event({
      id: 'garage',
      timestamp: '2026-10-01T17:28:19Z',
      correlation_group_id: 'group-1',
    });

    expect(collapseIncidentTimeline([garage]).map((item) => item.id)).toEqual(['garage']);
  });
});
