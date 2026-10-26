import { describe, it, expect } from 'vitest';
import { readIncident, combinedDescriptionFor } from '@/lib/incident';
import type { IEvent } from '@/types/event';

const ev = (incident: unknown): IEvent =>
  ({ id: 'e1', correlation_group_id: 'g1', description: 'per camera', incident } as unknown as IEvent);

describe('readIncident', () => {
  it('returns null without incident data', () => {
    expect(readIncident(ev(undefined))).toBeNull();
    expect(readIncident(ev(null))).toBeNull();
    expect(readIncident(ev('junk'))).toBeNull();
  });
  it('reads a finished combined pass', () => {
    const v = readIncident(ev({ id: 'g1', status: 'done', combined_description: ' Combined ', matched_entity_ids: ['a', 'b', 'a'] }));
    expect(v).toEqual({ id: 'g1', status: 'done', combinedDescription: 'Combined', matchedEntityIds: ['a', 'b'] });
  });
  it('ignores the description when the pass fell back, failed or is pending', () => {
    for (const status of ['fallback', 'failed', 'pending']) {
      expect(combinedDescriptionFor(ev({ status, combined_description: 'x' }))).toBeNull();
    }
  });
  it('treats blank descriptions as missing', () => {
    expect(combinedDescriptionFor(ev({ status: 'done', combined_description: '  ' }))).toBeNull();
  });
  it('accepts JSON-string entity ids and drops junk', () => {
    expect(readIncident(ev({ matched_entity_ids: '["a",1,""]' }))?.matchedEntityIds).toEqual(['a']);
    expect(readIncident(ev({ matched_entity_ids: 'not json' }))?.matchedEntityIds).toEqual([]);
  });
  it('never derives entity ids from description text', () => {
    const v = readIncident(ev({ status: 'done', combined_description: 'Entity a and b arrived', matched_entity_ids: null }));
    expect(v?.matchedEntityIds).toEqual([]);
  });
});
