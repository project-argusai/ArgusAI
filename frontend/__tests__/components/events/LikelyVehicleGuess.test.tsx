import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LikelyVehicleGuess, likelyVehicleLabel } from '@/components/events/LikelyVehicleGuess';
import type { IEvent } from '@/types/event';

const guess = {
  entity_id: 'entity-a',
  name: 'Sample Car',
  label: 'likely Sample Car (guess)',
  basis: ['left 3h earlier and not seen returning'],
  score: 3,
  is_guess: true as const,
};

function makeEvent(overrides: Partial<IEvent> = {}): IEvent {
  return {
    id: 'evt-1',
    camera_id: 'cam-1',
    timestamp: '2026-01-01T03:00:00Z',
    description: 'A vehicle with bright headlights pulls in.',
    confidence: 70,
    objects_detected: ['vehicle'],
    thumbnail_path: null,
    thumbnail_base64: null,
    alert_triggered: false,
    created_at: '2026-01-01T03:00:00Z',
    source_type: 'protect',
    smart_detection_type: 'vehicle',
    is_doorbell_ring: false,
    identification: { object_type: 'vehicle', likely_vehicle: guess },
    ...overrides,
  } as IEvent;
}

describe('LikelyVehicleGuess', () => {
  it('labels the suggestion as a guess', () => {
    render(<LikelyVehicleGuess event={makeEvent()} />);
    expect(screen.getByTestId('likely-vehicle-guess')).toHaveTextContent('likely Sample Car (guess)');
  });

  it('hides when the event already has a linked entity', () => {
    expect(likelyVehicleLabel(makeEvent({ entity_id: 'entity-b' }))).toBeNull();
  });

  it('hides without a guess', () => {
    const { container } = render(<LikelyVehicleGuess event={makeEvent({ identification: { object_type: 'vehicle' } })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
