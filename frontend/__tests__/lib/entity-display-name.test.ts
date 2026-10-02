import { describe, expect, it } from 'vitest';

import {
  entityHasResolvedLabel,
  entityMatchesSearch,
  getEntityDisplayName,
} from '@/lib/entity-display-name';

const TESLA_ID = '1c915ee6-aaaa-bbbb-cccc-ddddeeeeffff';

describe('getEntityDisplayName', () => {
  it('returns the user-assigned name when one is set', () => {
    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: 'Groceries car',
        vehicle_color: 'red',
        vehicle_make: 'tesla',
        vehicle_model: 'model y',
      })
    ).toBe('Groceries car');
  });

  it('ignores a blank name and builds a vehicle descriptor', () => {
    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: '   ',
        vehicle_color: 'red',
        vehicle_make: 'tesla',
        vehicle_model: 'model y',
      })
    ).toBe('Red Tesla Model Y');
  });

  it('capitalizes a full vehicle color, make, and model', () => {
    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
        vehicle_color: 'red',
        vehicle_make: 'tesla',
        vehicle_model: 'model y',
        vehicle_signature: 'red-tesla-modely',
      })
    ).toBe('Red Tesla Model Y');
  });

  it('uses whichever vehicle fields are present', () => {
    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
        vehicle_make: 'kia',
        vehicle_model: 'seltos',
      })
    ).toBe('Kia Seltos');

    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
        vehicle_color: 'black',
      })
    ).toBe('Black');
  });

  it('falls back to a title-cased signature, then the id', () => {
    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
        vehicle_signature: 'red-tesla-modely',
      })
    ).toBe('Red Tesla Modely');

    expect(
      getEntityDisplayName({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
      })
    ).toBe('Vehicle #1c915ee6');
  });

  it('keeps the type and id fallback for non-vehicles', () => {
    expect(
      getEntityDisplayName({
        id: 'abcd1234-0000-0000-0000-000000000000',
        entity_type: 'person',
        name: null,
        vehicle_make: 'tesla',
      })
    ).toBe('Person #abcd1234');

    expect(
      getEntityDisplayName({
        entity_type: 'unknown',
        name: null,
      })
    ).toBe('Unknown');
  });
});

describe('entityMatchesSearch', () => {
  const tesla = {
    id: TESLA_ID,
    entity_type: 'vehicle' as const,
    name: null,
    vehicle_color: 'red',
    vehicle_make: 'tesla',
    vehicle_model: 'model y',
    vehicle_signature: 'red-tesla-modely',
  };

  it('matches a make that is not the display name prefix', () => {
    expect(entityMatchesSearch(tesla, 'tesla')).toBe(true);
    expect(entityMatchesSearch(tesla, 'Red Tesla')).toBe(true);
    expect(entityMatchesSearch(tesla, 'kia')).toBe(false);
  });

  it('still matches a named vehicle by its stored make', () => {
    expect(entityMatchesSearch({ ...tesla, name: 'Daily driver' }, 'tesla')).toBe(true);
    expect(getEntityDisplayName({ ...tesla, name: 'Daily driver' })).toBe('Daily driver');
  });

  it('treats an empty query as a match', () => {
    expect(entityMatchesSearch(tesla, '   ')).toBe(true);
  });
});

describe('entityHasResolvedLabel', () => {
  it('is true for a name or a vehicle descriptor, false for an id fallback', () => {
    expect(
      entityHasResolvedLabel({
        id: TESLA_ID,
        entity_type: 'vehicle',
        name: null,
        vehicle_make: 'tesla',
      })
    ).toBe(true);
    expect(
      entityHasResolvedLabel({
        id: 'abcd1234-0000-0000-0000-000000000000',
        entity_type: 'person',
        name: null,
      })
    ).toBe(false);
  });
});
