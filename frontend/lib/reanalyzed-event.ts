/**
 * Apply a successful re-analyze to the events cache and the open selection.
 *
 * The events page keeps the open event as a snapshot. The list is an infinite
 * query under ['events', filters]. These helpers copy the fields re-analyze
 * changes onto the matching event so the card and the open detail show the
 * new description without waiting for a refetch.
 */

import type { QueryClient } from '@tanstack/react-query';
import type { IEvent } from '@/types/event';

const REANALYZE_FIELDS = [
  'description',
  'confidence',
  'objects_detected',
  'provider_used',
  'fallback_reason',
  'analysis_mode',
  'frame_count_used',
  'ai_confidence',
  'low_confidence',
  'vague_reason',
  'reanalyzed_at',
  'reanalysis_count',
  'has_annotations',
  'bounding_boxes',
] as const satisfies readonly (keyof IEvent)[];

export type ReanalyzedEventUpdate = Partial<IEvent> & { id: string };

function hasField(update: ReanalyzedEventUpdate, field: keyof IEvent): boolean {
  return Object.prototype.hasOwnProperty.call(update, field) && update[field] !== undefined;
}

function taken<K extends (typeof REANALYZE_FIELDS)[number]>(
  current: IEvent,
  update: ReanalyzedEventUpdate,
  field: K,
): IEvent[K] {
  if (hasField(update, field)) {
    return update[field] as IEvent[K];
  }
  return current[field];
}

/** Copy re-analyze fields onto an existing event. Other events are unchanged. */
export function mergeReanalyzedEvent(current: IEvent, update: ReanalyzedEventUpdate): IEvent {
  if (current.id !== update.id) return current;
  return {
    ...current,
    description: taken(current, update, 'description'),
    confidence: taken(current, update, 'confidence'),
    objects_detected: taken(current, update, 'objects_detected'),
    provider_used: taken(current, update, 'provider_used'),
    fallback_reason: taken(current, update, 'fallback_reason'),
    analysis_mode: taken(current, update, 'analysis_mode'),
    frame_count_used: taken(current, update, 'frame_count_used'),
    ai_confidence: taken(current, update, 'ai_confidence'),
    low_confidence: taken(current, update, 'low_confidence'),
    vague_reason: taken(current, update, 'vague_reason'),
    reanalyzed_at: taken(current, update, 'reanalyzed_at'),
    reanalysis_count: taken(current, update, 'reanalysis_count'),
    has_annotations: taken(current, update, 'has_annotations'),
    bounding_boxes: taken(current, update, 'bounding_boxes'),
  };
}

function isEventList(value: object): value is { events: IEvent[] } {
  return Array.isArray((value as { events?: unknown }).events);
}

function isInfiniteEvents(value: object): value is { pages: Array<{ events?: IEvent[] }> } {
  return Array.isArray((value as { pages?: unknown }).pages);
}

function isEventRecord(value: object): value is IEvent {
  return typeof (value as { id?: unknown }).id === 'string'
    && typeof (value as { description?: unknown }).description === 'string';
}

/**
 * Patch infinite event pages, a plain event list, or a single event record.
 * Unknown cache shapes are returned unchanged.
 */
export function applyReanalyzedEventToCache(
  data: unknown,
  update: ReanalyzedEventUpdate,
): unknown {
  if (!data || typeof data !== 'object') return data;

  if (isInfiniteEvents(data)) {
    return {
      ...data,
      pages: data.pages.map((page) => {
        if (!page || !Array.isArray(page.events)) return page;
        return {
          ...page,
          events: page.events.map((event) => mergeReanalyzedEvent(event, update)),
        };
      }),
    };
  }

  if (isEventList(data)) {
    return {
      ...data,
      events: data.events.map((event) => mergeReanalyzedEvent(event, update)),
    };
  }

  if (isEventRecord(data)) {
    return mergeReanalyzedEvent(data, update);
  }

  return data;
}

/** Write the re-analyze result into every events query that holds this id. */
export function applyReanalyzedEvent(
  queryClient: QueryClient,
  update: ReanalyzedEventUpdate,
): void {
  void queryClient.cancelQueries({ queryKey: ['events'] });
  void queryClient.cancelQueries({ queryKey: ['event', update.id] });
  queryClient.setQueriesData(
    { queryKey: ['events'] },
    (old) => applyReanalyzedEventToCache(old, update),
  );
  queryClient.setQueriesData(
    { queryKey: ['event', update.id] },
    (old) => applyReanalyzedEventToCache(old, update),
  );
}

/**
 * Event shown in the open detail.
 *
 * The list copy wins once it has a newer re-analysis. Until that lands, the
 * snapshot from the re-analyze response wins so the modal does not keep the
 * sentence from the click.
 */
export function resolveOpenEvent(
  selected: IEvent | null,
  events: IEvent[],
): IEvent | null {
  if (!selected) return null;
  const listed = events.find((event) => event.id === selected.id);
  if (!listed) return selected;

  const selectedCount = selected.reanalysis_count ?? 0;
  const listedCount = listed.reanalysis_count ?? 0;
  if (listedCount > selectedCount) return listed;
  if (selectedCount > listedCount) return selected;

  const selectedAt = selected.reanalyzed_at ? Date.parse(selected.reanalyzed_at) : 0;
  const listedAt = listed.reanalyzed_at ? Date.parse(listed.reanalyzed_at) : 0;
  if (Number.isFinite(listedAt) && listedAt > selectedAt) return listed;
  return selected;
}
