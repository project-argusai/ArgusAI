/**
 * Human-readable label for a recognized entity.
 *
 * A user-assigned name wins. Unnamed vehicles use color, make, and model
 * (any subset), then the stored signature, and only then `Vehicle #<id8>`.
 * Other types keep the type-plus-id fallback.
 */

export interface EntityDisplayFields {
  id?: string | null;
  entity_type?: string | null;
  name?: string | null;
  vehicle_color?: string | null;
  vehicle_make?: string | null;
  vehicle_model?: string | null;
  vehicle_signature?: string | null;
}

function cleanText(value: unknown): string {
  if (typeof value !== 'string') return '';
  return value.trim();
}

function capitalizeWord(word: string): string {
  if (!word) return '';
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

function capitalizePhrase(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map(capitalizeWord)
    .join(' ');
}

function typeLabel(entityType: string | null | undefined): string {
  const raw = cleanText(entityType).toLowerCase();
  if (!raw) return 'Unknown';
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function vehicleDescriptor(entity: EntityDisplayFields): string | null {
  if (cleanText(entity.entity_type).toLowerCase() !== 'vehicle') return null;

  const parts = [entity.vehicle_color, entity.vehicle_make, entity.vehicle_model]
    .map((value) => capitalizePhrase(cleanText(value)))
    .filter(Boolean);
  if (parts.length > 0) return parts.join(' ');

  const signature = cleanText(entity.vehicle_signature);
  if (!signature) return null;
  return signature
    .split(/[\s-]+/)
    .filter(Boolean)
    .map(capitalizeWord)
    .join(' ');
}

function typeIdFallback(entity: EntityDisplayFields): string {
  const label = typeLabel(entity.entity_type);
  const id = cleanText(entity.id);
  if (!id) return label;
  return `${label} #${id.slice(0, 8)}`;
}

/** True when a person assigned a name, or a vehicle has attributes or a signature. */
export function entityHasResolvedLabel(entity: EntityDisplayFields): boolean {
  if (cleanText(entity.name)) return true;
  return vehicleDescriptor(entity) !== null;
}

export function getEntityDisplayName(entity: EntityDisplayFields): string {
  const name = cleanText(entity.name);
  if (name) return name;
  return vehicleDescriptor(entity) ?? typeIdFallback(entity);
}

/**
 * Token search against the display name and the raw name, vehicle fields,
 * signature, and id. Every whitespace-separated token must match.
 */
export function entityMatchesSearch(entity: EntityDisplayFields, query: string): boolean {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;

  const haystack = [
    getEntityDisplayName(entity),
    entity.name,
    entity.vehicle_color,
    entity.vehicle_make,
    entity.vehicle_model,
    entity.vehicle_signature,
    entity.entity_type,
    entity.id,
  ]
    .map((value) => cleanText(value).toLowerCase())
    .filter(Boolean)
    .join(' ');

  return tokens.every((token) => haystack.includes(token));
}
