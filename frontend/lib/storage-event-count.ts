/**
 * Copy and count resolution for the Delete All Data confirmation.
 *
 * GET /api/v1/system/storage returns `event_count`. A missing load must not
 * be rendered as zero.
 */

export type StorageStatsStatus = 'loading' | 'ready' | 'error';

export function loadedStorageEventCount(
  status: StorageStatsStatus,
  stats: { event_count?: unknown } | null,
): number | null {
  if (status !== 'ready' || stats == null) {
    return null;
  }
  const count = stats.event_count;
  if (typeof count !== 'number' || !Number.isFinite(count)) {
    return null;
  }
  return count;
}

export function deleteAllDataDescription(eventCount: number | null): string {
  if (eventCount === null) {
    return 'This will permanently delete all events and thumbnails. The event count is unavailable. This action cannot be undone.';
  }
  return `This will permanently delete all ${eventCount.toLocaleString()} events and thumbnails. This action cannot be undone.`;
}
