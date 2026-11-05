/**
 * #691 S5 (#733): adapter for the local-vs-cloud AI audit API (S4b, #734).
 *
 * Built against jonny's draft S4b shapes; S4b has not merged yet, so every
 * backend field and query-parameter name lives here and nowhere else.
 * Anything missing or malformed is dropped or read as null. Plate text is
 * never part of these shapes and nothing here renders image paths.
 */
import { apiClient, ApiError } from '@/lib/api-client';

export type AuditVerdict = 'agree' | 'disagree' | 'unsure';
export type AuditVerdictFilter = 'unreviewed' | AuditVerdict;
export type AuditEventType = 'person' | 'vehicle' | 'package' | 'doorbell_ring';
export type AuditSource = 'audit' | 'fallback';

export const VERDICTS: readonly AuditVerdict[] = ['agree', 'disagree', 'unsure'];
export const VERDICT_FILTERS: readonly AuditVerdictFilter[] = ['unreviewed', 'agree', 'disagree', 'unsure'];
export const EVENT_TYPES: readonly AuditEventType[] = ['person', 'vehicle', 'package', 'doorbell_ring'];
const SOURCES: readonly AuditSource[] = ['audit', 'fallback'];

export const EVENT_TYPE_LABELS: Record<AuditEventType, string> = {
  person: 'Person',
  vehicle: 'Vehicle',
  package: 'Package',
  doorbell_ring: 'Doorbell ring',
};

export interface AuditPair {
  id: string;
  eventId: string;
  eventType: AuditEventType | null;
  createdAt: string | null;
  source: AuditSource | null;
  similarity: number | null;
  labelMatch: boolean | null;
  localMs: number | null;
  cloudMs: number | null;
  verdict: AuditVerdict | null;
}

export interface AuditPairDetail extends AuditPair {
  localText: string | null;
  cloudText: string | null;
  localProvider: string | null;
  cloudProvider: string | null;
  verdictAt: string | null;
  textExpiresAt: string | null;
}

export interface AuditPairPage {
  items: AuditPair[];
  nextCursor: string | null;
}

export interface AuditDay {
  date: string;
  pairs: number;
  auditPairs: number;
  fallbackPairs: number;
  meanSimilarity: number | null;
  labelAgreement: number | null;
  localP50Ms: number | null;
  localP95Ms: number | null;
  reviewed: number;
  agree: number;
  disagree: number;
  unsure: number;
  skippedCap: number;
  skippedBudget: number;
}

export interface AuditSummary {
  days: AuditDay[];
  readiness: { informational: boolean; pairsTotal: number; agreeRate: number | null } | null;
}

export interface PairFilters {
  date?: string;
  verdict: AuditVerdictFilter;
  eventType?: AuditEventType;
  limit?: number;
  cursor?: string | null;
}

const F = {
  items: 'items',
  nextCursor: 'next_cursor',
  id: 'id',
  eventId: 'event_id',
  eventType: 'event_type',
  createdAt: 'created_at',
  source: 'source',
  similarity: 'similarity',
  labelMatch: 'label_match',
  localMs: 'local_ms',
  cloudMs: 'cloud_ms',
  verdict: 'verdict',
  localText: 'local_text',
  cloudText: 'cloud_text',
  localProvider: 'local_provider',
  cloudProvider: 'cloud_provider',
  verdictAt: 'verdict_at',
  textExpiresAt: 'text_expires_at',
  days: 'days',
  date: 'date',
  pairs: 'pairs',
  auditPairs: 'audit_pairs',
  fallbackPairs: 'fallback_pairs',
  meanSimilarity: 'mean_similarity',
  labelAgreement: 'label_agreement',
  localP50Ms: 'local_p50_ms',
  localP95Ms: 'local_p95_ms',
  reviewed: 'reviewed',
  agree: 'agree',
  disagree: 'disagree',
  unsure: 'unsure',
  skippedCap: 'skipped_cap',
  skippedBudget: 'skipped_budget',
  readiness: 'readiness',
  informational: 'informational',
  pairsTotal: 'pairs_total',
  agreeRate: 'agree_rate',
} as const;

const Q = {
  date: 'date',
  verdict: 'verdict',
  eventType: 'event_type',
  limit: 'limit',
  cursor: 'cursor',
  from: 'from',
  to: 'to',
} as const;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const count = (v: unknown): number => num(v) ?? 0;
function oneOf<T extends string>(v: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(v as T) ? (v as T) : null;
}

export function parsePair(raw: unknown): AuditPair | null {
  if (!isObj(raw)) return null;
  const id = str(raw[F.id]);
  if (!id) return null;
  return {
    id,
    eventId: str(raw[F.eventId]) ?? '',
    eventType: oneOf(raw[F.eventType], EVENT_TYPES),
    createdAt: str(raw[F.createdAt]),
    source: oneOf(raw[F.source], SOURCES),
    similarity: num(raw[F.similarity]),
    labelMatch: typeof raw[F.labelMatch] === 'boolean' ? (raw[F.labelMatch] as boolean) : null,
    localMs: num(raw[F.localMs]),
    cloudMs: num(raw[F.cloudMs]),
    verdict: oneOf(raw[F.verdict], VERDICTS),
  };
}

export function parsePairDetail(raw: unknown): AuditPairDetail | null {
  const base = parsePair(raw);
  if (!base || !isObj(raw)) return null;
  return {
    ...base,
    localText: str(raw[F.localText]),
    cloudText: str(raw[F.cloudText]),
    localProvider: str(raw[F.localProvider]),
    cloudProvider: str(raw[F.cloudProvider]),
    verdictAt: str(raw[F.verdictAt]),
    textExpiresAt: str(raw[F.textExpiresAt]),
  };
}

export function parsePairPage(raw: unknown): AuditPairPage {
  if (!isObj(raw)) return { items: [], nextCursor: null };
  const list = Array.isArray(raw[F.items]) ? (raw[F.items] as unknown[]) : [];
  return {
    items: list.map(parsePair).filter((p): p is AuditPair => p !== null),
    nextCursor: str(raw[F.nextCursor]),
  };
}

function parseDay(raw: unknown): AuditDay | null {
  if (!isObj(raw)) return null;
  const date = str(raw[F.date]);
  if (!date) return null;
  return {
    date,
    pairs: count(raw[F.pairs]),
    auditPairs: count(raw[F.auditPairs]),
    fallbackPairs: count(raw[F.fallbackPairs]),
    meanSimilarity: num(raw[F.meanSimilarity]),
    labelAgreement: num(raw[F.labelAgreement]),
    localP50Ms: num(raw[F.localP50Ms]),
    localP95Ms: num(raw[F.localP95Ms]),
    reviewed: count(raw[F.reviewed]),
    agree: count(raw[F.agree]),
    disagree: count(raw[F.disagree]),
    unsure: count(raw[F.unsure]),
    skippedCap: count(raw[F.skippedCap]),
    skippedBudget: count(raw[F.skippedBudget]),
  };
}

export function parseSummary(raw: unknown): AuditSummary {
  if (!isObj(raw)) return { days: [], readiness: null };
  const list = Array.isArray(raw[F.days]) ? (raw[F.days] as unknown[]) : [];
  const r = raw[F.readiness];
  return {
    days: list.map(parseDay).filter((d): d is AuditDay => d !== null),
    readiness: isObj(r)
      ? {
          // Readiness is informational only (Brent waived the gate); default to true.
          informational: r[F.informational] !== false,
          pairsTotal: count(r[F.pairsTotal]),
          agreeRate: num(r[F.agreeRate]),
        }
      : null,
  };
}

export function pairsQuery(f: PairFilters): string {
  const p = new URLSearchParams();
  if (f.date) p.set(Q.date, f.date);
  p.set(Q.verdict, f.verdict);
  if (f.eventType) p.set(Q.eventType, f.eventType);
  p.set(Q.limit, String(f.limit ?? 50));
  if (f.cursor) p.set(Q.cursor, f.cursor);
  return `?${p.toString()}`;
}

export const aiAuditApi = {
  listPairs: async (f: PairFilters): Promise<AuditPairPage> =>
    parsePairPage(await apiClient.aiAudit.get(`/pairs${pairsQuery(f)}`)),
  getPair: async (id: string): Promise<AuditPairDetail> => {
    const d = parsePairDetail(await apiClient.aiAudit.get(`/pairs/${encodeURIComponent(id)}`));
    if (!d) throw new Error('Unreadable pair');
    return d;
  },
  setVerdict: async (id: string, verdict: AuditVerdict): Promise<AuditPairDetail> => {
    const d = parsePairDetail(
      await apiClient.aiAudit.put(`/pairs/${encodeURIComponent(id)}/verdict`, { [F.verdict]: verdict }),
    );
    if (!d) throw new Error('Unreadable pair');
    return d;
  },
  getSummary: async (from: string, to: string): Promise<AuditSummary> => {
    const p = new URLSearchParams({ [Q.from]: from, [Q.to]: to });
    return parseSummary(await apiClient.aiAudit.get(`/summary?${p.toString()}`));
  },
};

/** Clear user-facing copy for a failed verdict save. */
export function verdictErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.statusCode === 404) {
    return 'This pair’s text has expired (kept 30 days), so it can no longer be reviewed.';
  }
  if (err instanceof ApiError && err.statusCode === 422) return 'That verdict was not accepted. Please try again.';
  if (err instanceof ApiError && err.statusCode === 403) return 'Only admins can review audit pairs.';
  return 'Could not save the verdict. Please try again.';
}

export function formatPercent(v: number | null): string {
  return v === null ? '—' : `${Math.round(v * 100)}%`;
}

export function formatMs(v: number | null): string {
  if (v === null) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;
}
