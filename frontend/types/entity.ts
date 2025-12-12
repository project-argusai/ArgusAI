/**
 * TypeScript types for Entity Management (Story P4-3.6)
 * Types for recognized entities (recurring visitors) from the Temporal Context Engine
 */

/**
 * Entity type enumeration
 */
export type EntityType = 'person' | 'vehicle' | 'unknown';

/**
 * Base entity response from API
 * Returned by GET /api/v1/context/entities
 * Note: entity_type is string from API but should be one of EntityType values
 */
export interface IEntity {
  id: string;
  entity_type: string; // 'person' | 'vehicle' | 'unknown' from API
  name: string | null;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
}

/**
 * Event summary included in entity detail response
 */
export interface IEventSummaryForEntity {
  id: string;
  timestamp: string;
  description: string;
  thumbnail_url: string | null;
  camera_id: string;
  similarity_score: number;
}

/**
 * Detailed entity response with recent events
 * Returned by GET /api/v1/context/entities/{id}
 */
export interface IEntityDetail extends IEntity {
  created_at: string;
  updated_at: string;
  recent_events: IEventSummaryForEntity[];
}

/**
 * Response for entity list endpoint
 * Returned by GET /api/v1/context/entities
 */
export interface IEntityListResponse {
  entities: IEntity[];
  total: number;
}

/**
 * Request parameters for listing entities
 */
export interface IEntityQueryParams {
  limit?: number;
  offset?: number;
  entity_type?: EntityType;
  named_only?: boolean;
}

/**
 * Request body for updating an entity
 */
export interface IEntityUpdateRequest {
  name: string | null;
}
