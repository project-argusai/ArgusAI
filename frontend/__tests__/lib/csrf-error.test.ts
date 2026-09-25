import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';
import {
  CSRF_ORIGIN_DENIED,
  CSRF_ORIGIN_DENIED_MESSAGE,
  describeHttpError,
  isCsrfOriginDenied,
} from '@/lib/csrf-error';

describe('describeHttpError', () => {
  it('maps a CSRF 403 to a retry message and leaves other errors unchanged', () => {
    const denied = describeHttpError(403, 'Forbidden', {
      detail: 'Request origin is not allowed',
      error_code: CSRF_ORIGIN_DENIED,
    });
    expect(denied).toEqual({
      message: CSRF_ORIGIN_DENIED_MESSAGE,
      errorCode: CSRF_ORIGIN_DENIED,
    });

    const other = describeHttpError(400, 'Bad Request', { detail: 'Name is required' });
    expect(other.message).toBe('Name is required');
    expect(other.errorCode).toBeUndefined();
  });
});

describe('isCsrfOriginDenied', () => {
  it('detects the error code on ApiError details', () => {
    const error = new ApiError('blocked', 403, {
      detail: 'Request origin is not allowed',
      error_code: CSRF_ORIGIN_DENIED,
    });
    expect(isCsrfOriginDenied(error)).toBe(true);
    expect(error.message).toBe('blocked');
    expect(isCsrfOriginDenied(new ApiError('nope', 403, { detail: 'nope' }))).toBe(false);
  });
});
