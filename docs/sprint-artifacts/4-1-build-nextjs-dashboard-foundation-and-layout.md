# Story 4.1: Build Next.js Dashboard Foundation and Layout

Status: ready-for-dev

## Story

As a **frontend developer**,
I want **a responsive dashboard layout with navigation and routing**,
so that **users can access all features through a clean interface**.

## Acceptance Criteria

1. **Application Structure** - Next.js App Router foundation
   - App Router architecture: `/frontend/app` directory
   - Layout component: `/frontend/app/layout.tsx` with persistent header/sidebar
   - Pages: `/` (home/dashboard), `/events`, `/cameras`, `/rules`, `/settings`
   - Components: `/frontend/components` for reusable UI elements
   - TypeScript strict mode enabled throughout

2. **Header Component** - Top navigation bar
   - Logo/branding (top left)
   - Navigation links: Dashboard, Events, Cameras, Rules, Settings
   - Notification bell icon with unread count badge
   - System status indicator (green=healthy, red=degraded)
   - User menu dropdown (logout, profile - Phase 1.5)

3. **Sidebar Navigation (Desktop >1024px)** - Fixed left sidebar
   - Fixed left sidebar, 240px width
   - Icons + labels for each section
   - Active state highlighting (blue background)
   - Collapse/expand button (hamburger icon)
   - Collapsed state shows icons only (64px width)

4. **Mobile Navigation (<1024px)** - Mobile-optimized navigation
   - Bottom tab bar with icons
   - Hamburger menu for header
   - Swipe gestures for sidebar (optional)
   - Full-screen pages (no persistent sidebar)

5. **Responsive Breakpoints** - Tailwind-based responsive design
   - Mobile: <640px (single column, bottom tabs)
   - Tablet: 640-1024px (two columns, top nav)
   - Desktop: >1024px (sidebar + multi-column content)

6. **Theme and Styling** - Tailwind CSS configuration
   - Tailwind CSS utility classes
   - Custom theme in `tailwind.config.ts`:
     - Primary color: Blue (#3B82F6)
     - Success: Green (#10B981)
     - Warning: Yellow (#F59E0B)
     - Error: Red (#EF4444)
     - Neutral: Gray scale
   - Dark mode support (optional, Phase 2)
   - Font: Inter from Google Fonts

7. **Routing Configuration** - Next.js routing patterns
   - Client-side navigation with Next.js Link components
   - Loading states for page transitions
   - Error boundaries for graceful error handling
   - 404 page for invalid routes
   - Metadata and SEO tags in layout

8. **Global State Management** - React state architecture
   - React Context for: auth state, notifications, system settings
   - TanStack Query for: API data fetching, caching, mutations
   - Local state: useState/useReducer for component-specific state

## Tasks / Subtasks

**Task 1: Set up Next.js App Router structure** (AC: #1)
- [ ] Create `/frontend/app/layout.tsx` with root layout
- [ ] Create page routes: `/app/page.tsx` (dashboard), `/app/events/page.tsx`, `/app/cameras/page.tsx`, `/app/rules/page.tsx`, `/app/settings/page.tsx`
- [ ] Create `/app/loading.tsx` for loading states
- [ ] Create `/app/error.tsx` for error boundaries
- [ ] Create `/app/not-found.tsx` for 404 handling
- [ ] Configure TypeScript strict mode in `tsconfig.json`
- [ ] Add metadata and SEO tags in layout.tsx

**Task 2: Implement Header component** (AC: #2)
- [ ] Create `/frontend/components/layout/Header.tsx`
- [ ] Add logo/branding (top left) - use placeholder or project logo
- [ ] Implement navigation links (Dashboard, Events, Cameras, Rules, Settings)
- [ ] Add notification bell icon with badge (using Heroicons)
- [ ] Add system status indicator (green/red dot with tooltip)
- [ ] Create user menu dropdown with Headless UI (placeholder for Phase 1.5)
- [ ] Make header sticky (position: sticky top-0)
- [ ] Add mobile hamburger menu toggle button

**Task 3: Implement Sidebar navigation** (AC: #3)
- [ ] Create `/frontend/components/layout/Sidebar.tsx`
- [ ] Implement fixed left sidebar (240px width for desktop)
- [ ] Add navigation items with icons (Heroicons) + labels
- [ ] Implement active state highlighting (blue background using Next.js usePathname)
- [ ] Add collapse/expand button (toggle between 240px and 64px)
- [ ] Store sidebar state in localStorage (persist across sessions)
- [ ] Hide sidebar on tablet/mobile (<1024px)

**Task 4: Implement Mobile navigation** (AC: #4)
- [ ] Create `/frontend/components/layout/MobileNav.tsx`
- [ ] Implement bottom tab bar with icons (visible on mobile only)
- [ ] Add navigation items matching desktop sidebar
- [ ] Highlight active tab
- [ ] Position: fixed bottom with z-index
- [ ] Show only on screens <1024px (Tailwind `lg:hidden`)

**Task 5: Configure Tailwind theme** (AC: #6)
- [ ] Update `tailwind.config.ts` with custom colors (Primary: Blue, Success: Green, Warning: Yellow, Error: Red)
- [ ] Add Inter font from Google Fonts in layout.tsx
- [ ] Configure responsive breakpoints (sm: 640px, md: 768px, lg: 1024px, xl: 1280px, 2xl: 1536px - default)
- [ ] Test theme colors across all components
- [ ] Add dark mode configuration (optional, defer to Phase 2 if not needed now)

**Task 6: Set up global state management** (AC: #8)
- [ ] Create React Context for auth state: `/frontend/contexts/AuthContext.tsx`
- [ ] Create React Context for notifications: `/frontend/contexts/NotificationContext.tsx`
- [ ] Create React Context for system settings: `/frontend/contexts/SettingsContext.tsx`
- [ ] Configure TanStack Query provider in layout.tsx
- [ ] Add QueryClient with default options (staleTime, cacheTime, refetchOnWindowFocus)
- [ ] Wrap app with all context providers in correct order

**Task 7: Implement routing patterns** (AC: #7)
- [ ] Test client-side navigation with Next.js Link (no full page reloads)
- [ ] Verify loading.tsx shows during page transitions
- [ ] Verify error.tsx catches errors gracefully
- [ ] Test 404 page for invalid routes
- [ ] Add page metadata (title, description) using Next.js Metadata API

**Task 8: Create placeholder page content** (AC: #1, #5)
- [ ] Dashboard page (`/app/page.tsx`): "Dashboard - Coming Soon" with stats placeholders
- [ ] Events page (`/app/events/page.tsx`): "Events Timeline - Coming Soon"
- [ ] Cameras page (`/app/cameras/page.tsx`): "Camera Management - Coming Soon"
- [ ] Rules page (`/app/rules/page.tsx`): "Alert Rules - Coming Soon"
- [ ] Settings page (`/app/settings/page.tsx`): "System Settings - Coming Soon"
- [ ] Test responsive behavior on mobile/tablet/desktop

**Task 9: Testing and validation** (AC: All)
- [ ] Manual testing: Navigate between all pages
- [ ] Manual testing: Resize browser to test responsive breakpoints
- [ ] Manual testing: Test sidebar collapse/expand
- [ ] Manual testing: Test mobile bottom navigation
- [ ] Manual testing: Test header navigation and dropdowns
- [ ] Verify TypeScript strict mode has no errors
- [ ] Verify all routes load without errors
- [ ] Test loading and error states (simulate slow network)

## Dev Notes

### Architecture Context

From `docs/architecture.md`:
- **Frontend Framework**: Next.js 14+ with App Router architecture
- **Styling**: Tailwind CSS 3.4+ with custom theme
- **State Management**: React Context + TanStack Query
- **Component Library**: Headless UI + Heroicons
- **TypeScript**: Strict mode enabled

### Learnings from Previous Story

**From Story 3.4 (Implement Data Retention and Cleanup) - Status: done**

**Epic 3 (Backend) Completed:**
- All 4 backend stories complete (AI integration, event storage, processing pipeline, data retention)
- Backend APIs ready for frontend consumption:
  - GET /api/v1/events - Event listing with filtering
  - GET /api/v1/events/{id} - Single event retrieval
  - GET /api/v1/events/export - Event export (JSON/CSV)
  - GET /api/v1/cameras - Camera listing
  - GET /api/v1/system/storage - Storage monitoring
  - GET /api/v1/system/retention - Retention policy

**Key Services Available:**
- **Event Storage** (`backend/app/api/v1/events.py`) - Full CRUD with FTS5 search, export, cleanup
- **System API** (`backend/app/api/v1/system.py`) - Retention policy, storage monitoring
- **Cleanup Service** (`backend/app/services/cleanup_service.py`) - Batch deletion, audit logging

**Frontend Integration Notes:**
- Backend running on http://localhost:8000 (default FastAPI port)
- All API endpoints ready for axios/fetch calls
- Event data structure: id (UUID), camera_id, timestamp, description, confidence, objects_detected, thumbnail_path
- Camera data structure: id (UUID), name, stream_url, type (rtsp/usb), enabled status

**Technical Patterns to Apply:**
- Use TanStack Query for API calls (caching, refetching, optimistic updates)
- Follow backend API contracts (refer to Pydantic schemas in `backend/app/schemas/`)
- Implement loading/error states for all API calls
- Use TypeScript interfaces matching backend Pydantic models

[Source: docs/sprint-artifacts/3-4-implement-data-retention-and-cleanup.md#Completion-Notes-List]

### Project Structure Notes

**Expected File Structure:**
```
frontend/
├── app/
│   ├── layout.tsx           # NEW - Root layout with providers
│   ├── page.tsx              # NEW - Dashboard home
│   ├── loading.tsx           # NEW - Loading UI
│   ├── error.tsx             # NEW - Error boundary
│   ├── not-found.tsx         # NEW - 404 page
│   ├── events/
│   │   └── page.tsx          # NEW - Events page (Story 4.2)
│   ├── cameras/
│   │   └── page.tsx          # NEW - Cameras page
│   ├── rules/
│   │   └── page.tsx          # NEW - Rules page (Story 5.2)
│   └── settings/
│       └── page.tsx          # NEW - Settings page (Story 4.4)
├── components/
│   └── layout/
│       ├── Header.tsx        # NEW - Header component
│       ├── Sidebar.tsx       # NEW - Desktop sidebar
│       └── MobileNav.tsx     # NEW - Mobile navigation
├── contexts/
│   ├── AuthContext.tsx       # NEW - Auth state
│   ├── NotificationContext.tsx # NEW - Notifications
│   └── SettingsContext.tsx   # NEW - Settings
├── lib/
│   └── api.ts                # NEW - API client configuration
└── tailwind.config.ts        # MODIFIED - Custom theme
```

### References

- [Next.js App Router Documentation](https://nextjs.org/docs/app)
- [Tailwind CSS Configuration](https://tailwindcss.com/docs/configuration)
- [Headless UI Components](https://headlessui.com/)
- [Heroicons](https://heroicons.com/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Architecture: Frontend Stack](../architecture.md#Frontend-Stack)
- [PRD: F6 - Dashboard Requirements](../prd.md#F6-Dashboard-User-Interface)
- [Epic 3 Backend APIs](./3-2-implement-event-storage-and-retrieval-system.md)

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/4-1-build-nextjs-dashboard-foundation-and-layout.context.xml`

### Agent Model Used

<!-- Will be filled by dev agent -->

### Debug Log References

<!-- Dev agent will log implementation notes here -->

### Completion Notes List

<!-- Dev agent will document implementation details here -->

### File List

<!-- Dev agent will list all files created/modified here -->
