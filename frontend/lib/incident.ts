/**
 * #675 / #720: adapter for the combined incident data on a grouped event.
 *
 * The backend shape comes from the #717 design note (`event.incident =
 * {id, status, combined_description, combined_identification,
 * matched_entity_ids}` or null). #718 is still in progress, so every field
 * name lives here and nowhere else. Anything missing or malformed reads as
 * "no combined description" and the card falls back to the per-camera view.
 */
import type { IEvent } from '@/types/event';

export type IncidentStatus = 'pending' | 'done' | 'fallback' | 'failed';

export interface IncidentView {
  id: string;
  status: IncidentStatus | null;
  /** Combined description, only when the combined pass finished. */
  combinedDescription: string | null;
  /** Entity ids for chips: union of members' matched_entity_ids only. */
  matchedEntityIds: string[];
}

const FIELDS = {
  container: 'incident',
  id: 'id',
  status: 'status',
  combinedDescription: 'combined_description',
  matchedEntityIds: 'matched_entity_ids',
} as const;

const STATUSES: readonly IncidentStatus[] = ['pending', 'done', 'fallback', 'failed'];

function parseIds(raw: unknown): string[] {
  let value = raw;
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item === 'string' && item) seen.add(item);
  }
  return [...seen];
}

export function readIncident(event: IEvent): IncidentView | null {
  const raw = (event as unknown as Record<string, unknown>)[FIELDS.container];
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const id = typeof obj[FIELDS.id] === 'string' ? (obj[FIELDS.id] as string) : event.correlation_group_id ?? '';
  const statusRaw = obj[FIELDS.status];
  const status = STATUSES.includes(statusRaw as IncidentStatus) ? (statusRaw as IncidentStatus) : null;
  const descRaw = obj[FIELDS.combinedDescription];
  const desc = typeof descRaw === 'string' && descRaw.trim() ? descRaw.trim() : null;
  // Only a finished pass (or an unknown status with text present) counts.
  const usable = status === 'done' || (status === null && desc !== null);
  return {
    id,
    status,
    combinedDescription: usable ? desc : null,
    matchedEntityIds: parseIds(obj[FIELDS.matchedEntityIds]),
  };
}

/** Combined description to show, or null to keep the per-camera display. */
export function combinedDescriptionFor(event: IEvent): string | null {
  return readIncident(event)?.combinedDescription ?? null;
}
