/**
 * API Key Types
 * Story P13-1.6: Create API keys settings UI
 */

/**
 * Valid API key scopes
 */
export type APIKeyScope = 'read:events' | 'read:cameras' | 'read:mcp' | 'write:cameras' | 'admin';

/**
 * API key creation request
 */
export interface IAPIKeyCreateRequest {
  name: string;
  scopes: APIKeyScope[];
  expires_at?: string | null;
  rate_limit_per_minute?: number;
}

/**
 * API key creation response (contains the full key - shown only once)
 */
export interface IAPIKeyCreateResponse {
  id: string;
  name: string;
  key: string; // Full API key - only shown once
  prefix: string;
  scopes: APIKeyScope[];
  expires_at: string | null;
  rate_limit_per_minute: number;
  created_at: string;
}

/**
 * API key list item (no full key exposed)
 */
export interface IAPIKeyListItem {
  id: string;
  name: string;
  prefix: string;
  scopes: APIKeyScope[];
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  usage_count: number;
  rate_limit_per_minute: number;
  created_at: string;
  revoked_at: string | null;
}

/**
 * API key usage statistics
 */
export interface IAPIKeyUsage {
  id: string;
  name: string;
  prefix: string;
  usage_count: number;
  last_used_at: string | null;
  last_used_ip: string | null;
  rate_limit_per_minute: number;
  created_at: string;
}
