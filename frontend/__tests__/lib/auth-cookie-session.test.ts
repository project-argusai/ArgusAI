/**
 * Web auth is cookie-only (CR-011 / #601): no browser-readable tokens.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearLegacyBrowserTokens,
  hasAuthToken,
  setAuthToken,
  clearAuthToken,
} from '@/lib/api-client';

describe('cookie-only web auth (#601)', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('clears legacy localStorage and sessionStorage auth keys', () => {
    localStorage.setItem('auth_token', 'legacy-access');
    sessionStorage.setItem('auth_token', 'legacy-session');
    localStorage.setItem('refresh_token', 'legacy-refresh');

    clearLegacyBrowserTokens();

    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(sessionStorage.getItem('auth_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
  });

  it('setAuthToken does not persist a readable token', () => {
    setAuthToken('should-not-stick');
    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(hasAuthToken()).toBe(false);
  });

  it('clearAuthToken removes any leftover keys', () => {
    localStorage.setItem('auth_token', 'x');
    clearAuthToken();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });
});
