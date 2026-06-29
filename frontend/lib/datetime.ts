/**
 * Centralized timestamp handling — the single source of truth for turning
 * backend timestamps into `Date` objects for display.
 *
 * Backend contract: ALL timestamps are UTC. However, the API is backed by
 * SQLite, whose `DateTime` columns serialize WITHOUT a timezone marker
 * (e.g. `"2026-06-29T09:08:20"` rather than `"...Z"`). The browser's
 * `new Date("2026-06-29T09:08:20")` interprets a naive datetime as *local*
 * time, which renders UTC values shifted by the viewer's offset. Different
 * components historically disagreed (some appended `Z`, most didn't), which is
 * exactly the "discrepancy between areas" users saw.
 *
 * `parseApiDate` forces the correct interpretation; the `format*` helpers then
 * render in the browser's local timezone. Use these EVERYWHERE instead of
 * `new Date(apiValue)` so every surface agrees.
 */
import { formatDistanceToNow, format as dfFormat } from 'date-fns';

/** Matches an explicit timezone suffix: `Z`, `+00:00`, `-0500`, etc. */
const HAS_TZ = /(?:Z|[+-]\d{2}:?\d{2})$/;
/** Matches a date-only value like `2026-06-29`. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parse a backend timestamp into a `Date`, interpreting naive datetimes as UTC.
 *
 * - Already tz-qualified (`...Z` / `...+00:00`) → used as-is.
 * - Date-only (`YYYY-MM-DD`) → local midnight (avoids the off-by-one day that
 *   UTC-parsing date-only strings causes for negative offsets).
 * - Naive datetime → treated as UTC (the backend convention).
 * - `Date` / epoch number → returned/parsed directly.
 *
 * Returns `null` for nullish/blank/unparseable input so callers can guard.
 */
export function parseApiDate(
  value: string | number | Date | null | undefined,
): Date | null {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }

  const s = value.trim();
  if (!s) return null;

  let iso: string;
  if (HAS_TZ.test(s)) {
    iso = s; // already unambiguous
  } else if (DATE_ONLY.test(s)) {
    iso = `${s}T00:00:00`; // local midnight — keep the calendar date stable
  } else {
    iso = `${s.replace(' ', 'T')}Z`; // naive datetime → UTC
  }

  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Relative time (e.g. "5 minutes ago"), UTC-correct. Empty string for nullish
 * input so it can be dropped straight into JSX.
 */
export function formatRelative(
  value: string | number | Date | null | undefined,
  options: { addSuffix?: boolean } = { addSuffix: true },
): string {
  const d = parseApiDate(value);
  return d ? formatDistanceToNow(d, options) : '';
}

/**
 * Absolute date/time formatted in the browser's local timezone via date-fns.
 * Defaults to a friendly `MMM d, yyyy h:mm a`. Empty string for nullish input.
 */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  fmt = 'MMM d, yyyy h:mm a',
): string {
  const d = parseApiDate(value);
  return d ? dfFormat(d, fmt) : '';
}

/**
 * Locale string in the browser's timezone (drop-in for `.toLocaleString()`).
 * Empty string for nullish input.
 */
export function formatLocale(
  value: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleString(undefined, options) : '';
}
