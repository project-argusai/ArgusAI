import type { IEvent } from '@/types/event';

/**
 * Pick the card that represents an incident on the timeline.
 * A doorbell ring stays the visible card. Otherwise the earliest detection does.
 */
export function incidentPrimaryId(members: IEvent[]): string {
  const ranked = [...members].sort((a, b) => {
    const aRing = a.is_doorbell_ring ? 0 : 1;
    const bRing = b.is_doorbell_ring ? 0 : 1;
    if (aRing !== bRing) return aRing - bRing;
    if (a.timestamp !== b.timestamp) return a.timestamp < b.timestamp ? -1 : 1;
    return a.id < b.id ? -1 : 1;
  });
  return ranked[0].id;
}

/**
 * Hide non-primary members when their primary is also in this list.
 * A member whose primary is on another page stays visible.
 */
export function collapseIncidentTimeline(events: IEvent[]): IEvent[] {
  const groups = new Map<string, IEvent[]>();
  for (const event of events) {
    const groupId = event.correlation_group_id;
    if (!groupId) continue;
    const members = groups.get(groupId);
    if (members) {
      members.push(event);
    } else {
      groups.set(groupId, [event]);
    }
  }

  const hidden = new Set<string>();
  for (const members of groups.values()) {
    if (members.length < 2) continue;
    const primaryId = incidentPrimaryId(members);
    for (const member of members) {
      if (member.id !== primaryId) hidden.add(member.id);
    }
  }

  return events.filter((event) => !hidden.has(event.id));
}
