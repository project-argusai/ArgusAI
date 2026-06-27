# ArgusAI Design-System Foundations Alignment — Design

**Date:** 2026-06-27
**Status:** Approved (approach A)
**Scope:** Foundations + shared components, aligned to the `ArgusAI Design System`
claude.ai/design project (`ac5cdef4-e30e-4a31-9d11-e6067eb94e30`).

## Context

The claude.ai/design "ArgusAI Design System" was reverse-engineered *from* this
repo's `frontend/`, so the foundations already largely match. This work closes the
*real* divergences between the design system's tokens/specs and the live frontend,
and tightens the shared `ui/` primitives + signature components where they drift —
without churning consumers whose output already matches (approach A).

Non-goals: redesigning whole screens, migrating already-correct consumers
(`SmartDetectionBadge` etc.) onto new tokens, or touching backend / auth / data.

## Gap analysis (authoritative)

| Area | Live frontend | Design target | Action |
|---|---|---|---|
| UI font | `--font-sans: var(--font-inter)` (undefined → fallback) | Geist Sans (`--font-geist-sans`, already loaded in `layout.tsx`) | Fix mapping |
| Focus ring (light) | `--ring: oklch(0.708 0 0)` (gray) | `--argus-blue-500` | Change to blue |
| Dark `--primary` | `oklch(0.922 0 0)` (near-white) | blue-500 | Change to blue + flip `--primary-foreground` to light |
| Dark `--ring` | `oklch(0.556 0 0)` (gray) | blue-500 | Change to blue |
| `--sidebar-primary` (light) | blue-500 | blue-600 | Bump to blue-600 |
| `--sidebar-primary` (dark) | chart-blue `oklch(0.488 0.243 264.376)` | blue-600 | Align to blue-600 |
| `--sidebar-ring` (light+dark) | gray | blue-500 | Align to blue |
| Detection accents | hardcoded `bg-blue-100` etc. (colors correct) | `--argus-detect-*` tokens | **Add tokens** (no consumer migration) |
| radius / borders / semantic colors / mono font | match | match | none |

## Design

### 1. Token layer — `frontend/app/globals.css`

**`@theme inline` block**
- `--font-sans: var(--font-inter)` → `--font-sans: var(--font-geist-sans)`.
- Add detection accent color utilities so `text-detect-person`, `bg-detect-package`,
  etc. resolve:
  `--color-detect-person/vehicle/package/animal/motion/ring: var(--detect-*)`.

**`:root` (light)**
- `--ring: oklch(0.619 0.152 254.604)` (blue-500).
- `--sidebar-primary: oklch(0.546 0.215 262.9)` (blue-600).
- `--sidebar-ring: oklch(0.619 0.152 254.604)` (blue-500).
- Add detection tokens (oklch values from `tokens/colors.css`):
  - `--detect-person: oklch(0.546 0.215 262.9)`
  - `--detect-vehicle: oklch(0.558 0.230 302.3)`
  - `--detect-package: oklch(0.646 0.180 47.6)`
  - `--detect-animal: oklch(0.682 0.171 166.8)`
  - `--detect-motion: oklch(0.556 0 0)`
  - `--detect-ring: oklch(0.715 0.120 215.2)`

**`.dark`**
- `--primary: oklch(0.619 0.152 254.604)` (blue-500).
- `--primary-foreground: oklch(0.985 0 0)` (neutral-50; was dark because primary was light).
- `--ring: oklch(0.619 0.152 254.604)` (blue-500).
- `--sidebar-primary: oklch(0.546 0.215 262.9)` (blue-600).
- `--sidebar-ring: oklch(0.619 0.152 254.604)` (blue-500).

Detection tokens inherit from `:root` (taxonomy is theme-independent); no dark override.

### 2. Shared components — audit-and-align only where divergent

For each, compare rendered result to the design spec/mockup; change only on drift.
Most inherit the blue ring automatically once `--ring` flips.

- `ui/button.tsx` — confirm solid hover darkens ~10%, outline carries `shadow-xs`,
  focus ring is the (now blue) `--ring`.
- `ui/card.tsx` — `rounded-xl`, `shadow-sm`, 1px `--border`; clickable variant lifts to
  `shadow-md` + `border-blue-300` on hover.
- `ui/badge.tsx`, `ui/input.tsx`, `ui/select.tsx`, `ui/switch.tsx`, `ui/checkbox.tsx`
  — verify blue focus ring + 8px (`rounded-md`) radius; no other change expected.
- `ui/logo.tsx` — wordmark is Geist **Bold**, `tracking-[-0.02em]`, single word
  "ArgusAI"; shield + wordmark lockup. Align weight/tracking if off.
- `components/events/EventCard.tsx` (signature surface) — confirm: clickable hover
  lift (`shadow-md` + `border-blue-300`); correlated events render a 4px blue
  left-accent; layout = thumbnail + AI description + detection chips +
  provider/confidence. Add any missing piece.
- Feedback parity check (no rename): `StatusDot`-equivalent has the live "ping";
  skeletons shimmer; `ConfidenceIndicator` ≈ design `ConfidenceMeter`;
  `DashboardStats`/stat tiles ≈ design `StatCard`. Adjust only on visible drift.

`SmartDetectionBadge` is intentionally **left as-is** (colors already match; approach A
forgoes the token migration).

### 3. Verification

- Build/type/lint: `npm run build`, `npx tsc --noEmit`, `npm run lint`.
- Visual (Playwright MCP against `https://agent.argusai.cc`): Login, Dashboard, Events
  in **light and dark**. Confirm: UI font renders as Geist; focus rings are blue;
  dark-mode primary buttons are blue (not gray); EventCard hover lift + correlation
  accent present. Screenshot before/after for the PR.

## Security review

No security surface: presentational tokens + component styling only. No auth,
encryption, external integration, data-model, or cost behavior touched.

## Rollback

Changes confined to `frontend/app/globals.css` plus a small set of `ui/` and
`components/events/` files. Single-commit revert restores prior state; no migrations,
no data changes.

## Effort

S–M. One PR: token layer is mechanical; component work is verify-then-touch with
visual confirmation.
