/**
 * Auth close handling for live WebSockets.
 *
 * The server closes an already-accepted socket with 1008 when the session is
 * revoked, the user is disabled, or the origin is rejected on a later check.
 * A rejection before accept is an HTTP 403. Browsers report that as close
 * code 1006, so a failed handshake is checked against /auth/me.
 */

export const WS_AUTH_CLOSE_CODES = [1008, 4401, 4403] as const;

export const WS_AUTH_FAILURE_MESSAGE =
  'Session expired. Sign in again to resume live updates.';

export function isAuthWebSocketClose(code: number): boolean {
  return (WS_AUTH_CLOSE_CODES as readonly number[]).includes(code);
}

/**
 * True when the HTTP session is rejected. Network failures return false so
 * a backend outage can still use bounded reconnects.
 */
export async function sessionProbeIsUnauthorized(): Promise<boolean> {
  try {
    const base = process.env.NEXT_PUBLIC_API_URL ?? '';
    const response = await fetch(`${base}/api/v1/auth/me`, {
      method: 'GET',
      credentials: 'include',
    });
    return response.status === 401 || response.status === 403;
  } catch {
    return false;
  }
}
