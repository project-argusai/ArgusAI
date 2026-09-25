/**
 * User-facing copy for cookie-authenticated writes rejected by the Origin gate.
 * Forms must show this and leave the user's entries in place.
 */

export const CSRF_ORIGIN_DENIED = 'CSRF_ORIGIN_DENIED';

export const CSRF_ORIGIN_DENIED_MESSAGE =
  'This change was blocked because it did not come from this ArgusAI site. Your entries are still here. Try again, or sign in again if it keeps happening.';

function errorCodeOf(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined;
  const record = error as {
    errorCode?: unknown;
    details?: { error_code?: unknown };
  };
  if (typeof record.errorCode === 'string') return record.errorCode;
  if (record.details && typeof record.details.error_code === 'string') {
    return record.details.error_code;
  }
  return undefined;
}

export function isCsrfOriginDenied(error: unknown): boolean {
  return errorCodeOf(error) === CSRF_ORIGIN_DENIED;
}

/**
 * Error for a failed fetch that bypasses the shared API client.
 * CSRF rejections use the retry message and keep errorCode set.
 */
export function errorForFailedResponse(
  status: number,
  statusText: string,
  data: unknown,
  fallback: string,
): Error {
  const described = describeHttpError(status, statusText, data);
  if (described.errorCode === CSRF_ORIGIN_DENIED) {
    const error = new Error(described.message) as Error & { errorCode?: string };
    error.errorCode = described.errorCode;
    return error;
  }
  const record =
    data && typeof data === 'object' ? (data as { detail?: unknown }) : undefined;
  const detail = typeof record?.detail === 'string' ? record.detail : undefined;
  return new Error(detail || fallback);
}

/** Map an HTTP error body to the message and code thrown by the API client. */
export function describeHttpError(
  status: number,
  statusText: string,
  data: unknown,
): { message: string; errorCode?: string } {
  const record =
    data && typeof data === 'object'
      ? (data as { detail?: unknown; error_code?: unknown })
      : undefined;
  const errorCode = typeof record?.error_code === 'string' ? record.error_code : undefined;
  if (errorCode === CSRF_ORIGIN_DENIED) {
    return { message: CSRF_ORIGIN_DENIED_MESSAGE, errorCode };
  }
  const detail = typeof record?.detail === 'string' ? record.detail : undefined;
  return {
    message: detail || `HTTP ${status}: ${statusText}`,
    errorCode,
  };
}
