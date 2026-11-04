/**
 * Night vehicle context guess: "likely X (guess)".
 *
 * Shown only when the event has no linked entity. It is a suggestion from
 * recent departures and usual arrival times, never an entity link.
 */
import type { IEvent } from '@/types/event';

export function likelyVehicleLabel(event: Pick<IEvent, 'identification' | 'entities' | 'entity_id'>): string | null {
  const guess = event.identification?.likely_vehicle;
  if (!guess || guess.is_guess !== true || !guess.name) return null;
  if (event.entity_id || (event.entities && event.entities.length > 0)) return null;
  return `likely ${guess.name} (guess)`;
}

export function LikelyVehicleGuess({ event }: { event: IEvent }) {
  const label = likelyVehicleLabel(event);
  if (!label) return null;
  const basis = event.identification?.likely_vehicle?.basis ?? [];
  return (
    <span
      className="inline-flex items-center rounded-full border border-dashed border-muted-foreground/50 px-2 py-0.5 text-xs italic text-muted-foreground"
      title={basis.length ? `Guess, not a confirmed match: ${basis.join('; ')}` : 'Guess, not a confirmed match'}
      data-testid="likely-vehicle-guess"
    >
      {label}
    </span>
  );
}
