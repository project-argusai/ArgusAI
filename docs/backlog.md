# Project Backlog

Technical debt, improvements, and future work items identified during development.

## Priority Legend
- **P1**: Critical - blocks other work
- **P2**: High - should be addressed soon
- **P3**: Medium - address when convenient
- **P4**: Low - nice to have

---

## Technical Debt

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|
| TD-001 | 2025-12-06 | P2 | Infrastructure | **Set up frontend testing framework** - Frontend has no Jest, Vitest, or React Testing Library configured. All frontend component tests are currently blocked. Should be addressed at end of Epic P3-3 or start of next phase. Recommended: Vitest + React Testing Library for consistency with modern React patterns. | Story P3-3.4 Code Review | Done |

---

## Improvements

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|
| IMP-001 | 2025-12-06 | P4 | Code Quality | Remove console.log debug statements from EventCard.tsx (lines 104, 107) before production deployment | Story P3-3.4 Code Review | Open |

---

## Future Features

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|

---

## Notes

- Items are added during code reviews, retrospectives, and development
- Priority should be reassessed during sprint planning
- Status: Open, In Progress, Done, Won't Fix
