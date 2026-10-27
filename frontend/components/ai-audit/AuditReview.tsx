'use client';

/**
 * #691 S5 (#733): admin review queue for local-vs-cloud AI audit pairs.
 * Summary strip, filterable cursor-paged pair list (default: unreviewed),
 * and a side-by-side pair detail with keyboard-friendly verdict buttons.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  aiAuditApi,
  EVENT_TYPE_LABELS,
  EVENT_TYPES,
  formatMs,
  formatPercent,
  VERDICT_FILTERS,
  verdictErrorMessage,
  type AuditEventType,
  type AuditPair,
  type AuditVerdict,
  type AuditVerdictFilter,
} from '@/lib/ai-audit';

const SUMMARY_DAYS = 7;
const PAGE_SIZE = 50;

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const VERDICT_LABEL: Record<AuditVerdict, string> = { agree: 'Agree', disagree: 'Disagree', unsure: 'Unsure' };
const VERDICT_KEY: Record<AuditVerdict, string> = { agree: 'a', disagree: 'd', unsure: 'u' };

export function SummaryStrip({ now = new Date() }: { now?: Date }) {
  const to = isoDate(now);
  const fromD = new Date(now);
  fromD.setDate(fromD.getDate() - (SUMMARY_DAYS - 1));
  const from = isoDate(fromD);
  const q = useQuery({ queryKey: ['ai-audit', 'summary', from, to], queryFn: () => aiAuditApi.getSummary(from, to) });

  if (q.isLoading) return <Skeleton className="h-20 w-full" data-testid="summary-loading" />;
  if (q.isError) return <p role="alert" className="text-sm text-destructive">Couldn’t load the daily summary.</p>;
  const s = q.data!;
  const totals = s.days.reduce(
    (a, d) => ({ pairs: a.pairs + d.pairs, reviewed: a.reviewed + d.reviewed, skipped: a.skipped + d.skippedCap + d.skippedBudget }),
    { pairs: 0, reviewed: 0, skipped: 0 },
  );
  const latest = s.days[s.days.length - 1];
  return (
    <section aria-label="Daily audit summary" className="space-y-2">
      {s.days.length === 0 ? (
        <p className="text-sm text-muted-foreground">No audit pairs in the last {SUMMARY_DAYS} days.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5 text-sm">
          <Stat label={`Pairs (${SUMMARY_DAYS} days)`} value={String(totals.pairs)} />
          <Stat label="Reviewed" value={String(totals.reviewed)} />
          <Stat label="Mean similarity (latest day)" value={formatPercent(latest.meanSimilarity)} />
          <Stat label="Label agreement (latest day)" value={formatPercent(latest.labelAgreement)} />
          <Stat label="Local p50 / p95 (latest day)" value={`${formatMs(latest.localP50Ms)} / ${formatMs(latest.localP95Ms)}`} />
        </dl>
      )}
      {totals.skipped > 0 && (
        <p className="text-xs text-muted-foreground">{totals.skipped} events skipped by the daily or cost cap.</p>
      )}
      {s.readiness && (
        <p className="text-xs text-muted-foreground" data-testid="readiness">
          <Badge variant="outline" className="mr-2">Informational</Badge>
          Readiness: {s.readiness.pairsTotal} pairs total, {formatPercent(s.readiness.agreeRate)} agree. This does not
          gate anything.
        </p>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function PairDetail({
  id,
  onVerdict,
}: {
  id: string;
  onVerdict: (pair: AuditPair) => void;
}) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['ai-audit', 'pair', id], queryFn: () => aiAuditApi.getPair(id) });
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (v: AuditVerdict) => aiAuditApi.setVerdict(id, v),
    onSuccess: (pair) => {
      setError(null);
      qc.setQueryData(['ai-audit', 'pair', id], pair);
      qc.invalidateQueries({ queryKey: ['ai-audit', 'pairs'] });
      qc.invalidateQueries({ queryKey: ['ai-audit', 'summary'] });
      onVerdict(pair);
    },
    onError: (e) => setError(verdictErrorMessage(e)),
  });
  const { mutate, isPending } = m;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isPending) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const v = (Object.keys(VERDICT_KEY) as AuditVerdict[]).find((k) => VERDICT_KEY[k] === e.key.toLowerCase());
      if (v) {
        e.preventDefault();
        mutate(v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mutate, isPending]);

  if (q.isLoading) return <Skeleton className="h-40 w-full" data-testid="pair-loading" />;
  if (q.isError || !q.data) {
    return <p role="alert" className="text-sm text-destructive">Couldn’t load this pair. It may have expired.</p>;
  }
  const p = q.data;
  return (
    <section aria-label="Pair detail" className="space-y-3">
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {p.eventType && <Badge variant="secondary">{EVENT_TYPE_LABELS[p.eventType]}</Badge>}
        {p.source && <Badge variant="outline">{p.source === 'fallback' ? 'Fallback pair' : 'Audit sample'}</Badge>}
        <span>Similarity {formatPercent(p.similarity)}</span>
        <span>Labels {p.labelMatch === null ? '—' : p.labelMatch ? 'match' : 'differ'}</span>
        {p.verdict && <span>Current verdict: {VERDICT_LABEL[p.verdict]}</span>}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <TextPane title="Local" provider={p.localProvider} ms={p.localMs} text={p.localText} />
        <TextPane title="Cloud" provider={p.cloudProvider} ms={p.cloudMs} text={p.cloudText} />
      </div>
      <div role="group" aria-label="Verdict" className="flex flex-wrap items-center gap-2">
        {(['agree', 'disagree', 'unsure'] as AuditVerdict[]).map((v) => (
          <Button
            key={v}
            type="button"
            variant={p.verdict === v ? 'default' : 'outline'}
            aria-pressed={p.verdict === v}
            aria-keyshortcuts={VERDICT_KEY[v].toUpperCase()}
            disabled={isPending}
            onClick={() => mutate(v)}
          >
            {VERDICT_LABEL[v]} <kbd className="ml-1 text-xs opacity-70">{VERDICT_KEY[v].toUpperCase()}</kbd>
          </Button>
        ))}
        <span className="text-xs text-muted-foreground">Keys A / D / U. Moves to the next unreviewed pair.</span>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {p.textExpiresAt && (
        <p className="text-xs text-muted-foreground">Text kept until {new Date(p.textExpiresAt).toLocaleDateString()}.</p>
      )}
    </section>
  );
}

function TextPane({ title, provider, ms, text }: { title: string; provider: string | null; ms: number | null; text: string | null }) {
  return (
    <div className="rounded-md border p-3">
      <h4 className="text-sm font-semibold">
        {title}
        {provider ? ` · ${provider}` : ''} <span className="font-normal text-muted-foreground">({formatMs(ms)})</span>
      </h4>
      <p className="mt-1 whitespace-pre-wrap text-sm" data-testid={`${title.toLowerCase()}-text`}>
        {text ?? <span className="italic text-muted-foreground">No text available.</span>}
      </p>
    </div>
  );
}

export function AuditReview({ now }: { now?: Date } = {}) {
  const [verdict, setVerdict] = useState<AuditVerdictFilter>('unreviewed');
  const [eventType, setEventType] = useState<AuditEventType | ''>('');
  const [date, setDate] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const [selected, setSelected] = useState<string | null>(null);

  const resetPaging = () => {
    setCursors([null]);
    setSelected(null);
  };

  const filters = useMemo(
    () => ({ verdict, eventType: eventType || undefined, date: date || undefined, limit: PAGE_SIZE, cursor }),
    [verdict, eventType, date, cursor],
  );
  const list = useQuery({ queryKey: ['ai-audit', 'pairs', filters], queryFn: () => aiAuditApi.listPairs(filters) });
  const items = useMemo(() => list.data?.items ?? [], [list.data]);

  const onVerdict = useCallback(
    (pair: AuditPair) => {
      const idx = items.findIndex((i) => i.id === pair.id);
      const after = [...items.slice(idx + 1), ...items.slice(0, Math.max(idx, 0))];
      const next = after.find((i) => i.verdict === null && i.id !== pair.id);
      setSelected(next ? next.id : null);
    },
    [items],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Local vs cloud AI audit</CardTitle>
        <CardDescription>
          Spot-check local descriptions against a cloud sample. About 50 pairs a week is plenty.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <SummaryStrip now={now} />

        <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filters">
          <label className="text-sm">
            <span className="block text-xs text-muted-foreground">Verdict</span>
            <select
              className="rounded-md border bg-background px-2 py-1"
              value={verdict}
              onChange={(e) => {
                setVerdict(e.target.value as AuditVerdictFilter);
                resetPaging();
              }}
            >
              {VERDICT_FILTERS.map((v) => (
                <option key={v} value={v}>
                  {v === 'unreviewed' ? 'Unreviewed' : VERDICT_LABEL[v]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-muted-foreground">Event type</span>
            <select
              className="rounded-md border bg-background px-2 py-1"
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value as AuditEventType | '');
                resetPaging();
              }}
            >
              <option value="">All key events</option>
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {EVENT_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-muted-foreground">Date</span>
            <input
              type="date"
              className="rounded-md border bg-background px-2 py-1"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                resetPaging();
              }}
            />
          </label>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div>
            {list.isLoading ? (
              <Skeleton className="h-40 w-full" data-testid="pairs-loading" />
            ) : list.isError ? (
              <div role="alert" className="space-y-2 text-sm text-destructive">
                <p>Couldn’t load audit pairs.</p>
                <Button type="button" size="sm" variant="outline" onClick={() => list.refetch()}>
                  Retry
                </Button>
              </div>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {verdict === 'unreviewed' ? 'Nothing left to review. ' : ''}No pairs match these filters.
              </p>
            ) : (
              <ul aria-label="Audit pairs" className="divide-y rounded-md border">
                {items.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      aria-current={selected === p.id ? 'true' : undefined}
                      className={`w-full px-3 py-2 text-left text-sm hover:bg-muted focus:bg-muted focus:outline-none ${selected === p.id ? 'bg-muted' : ''}`}
                      onClick={() => setSelected(p.id)}
                    >
                      <span className="font-medium">{p.eventType ? EVENT_TYPE_LABELS[p.eventType] : 'Event'}</span>
                      <span className="ml-2 text-muted-foreground">
                        {p.createdAt ? new Date(p.createdAt).toLocaleString() : ''} · {formatPercent(p.similarity)}
                        {p.verdict ? ` · ${VERDICT_LABEL[p.verdict]}` : ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={cursors.length <= 1}
                onClick={() => {
                  setCursors((c) => c.slice(0, -1));
                  setSelected(null);
                }}
              >
                Previous
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!list.data?.nextCursor}
                onClick={() => {
                  const next = list.data?.nextCursor;
                  if (next) {
                    setCursors((c) => [...c, next]);
                    setSelected(null);
                  }
                }}
              >
                Next page
              </Button>
            </div>
          </div>
          <div>
            {selected ? (
              <PairDetail key={selected} id={selected} onVerdict={onVerdict} />
            ) : (
              <p className="text-sm text-muted-foreground">Select a pair to compare the local and cloud descriptions.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
