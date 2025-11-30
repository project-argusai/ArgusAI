# Live Object AI Classifier - UX Design Specification

_Created on 2025-11-17 by Brent_
_Generated using BMad Method - Create UX Design Workflow v1.0_

---

## Executive Summary

Live Object AI Classifier is an intelligent multi-camera AI vision system that transforms surveillance into understanding by storing rich natural language descriptions of events instead of raw video footage. This UX specification defines the visual design, interaction patterns, and user experience decisions for the web-based dashboard.

**Target Users:** Security-conscious homeowners, smart home enthusiasts, and accessibility users (visually impaired)

**Platform:** Web dashboard (Next.js/React) - Desktop and mobile responsive

**Design Philosophy:** Sophisticated guardian - professional, protective, privacy-focused with modern AI intelligence

---

## 1. Design System Foundation

### 1.1 Design System Choice

**Selected: shadcn/ui**

**Rationale:**
- Built specifically for Next.js + Tailwind CSS (matches our tech stack from epics)
- Copy-paste component ownership (no external dependencies to manage)
- Excellent accessibility (WCAG AA compliant) - critical for Linda's use case
- Modern aesthetic with full customization flexibility
- 50+ pre-built components (forms, modals, cards, dropdowns, buttons, tables)
- Active development and community support

**Components Provided:**
- Forms with validation styling (camera setup, alert rules)
- Dialog/Modal components (confirmations, camera config)
- Card components (event timeline cards)
- Dropdown/Select menus (settings, filters)
- Button variants (primary, secondary, ghost, destructive)
- Input fields with focus states
- Toast notifications (alerts, success messages)
- Table components (event lists, webhook logs)
- Tabs and navigation elements

**Installation:**
```bash
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card dialog input select table toast
```

---

## 2. Core User Experience

### 2.1 Defining Experience

**Primary User Actions (in priority order):**

1. **Reviewing Event Timeline** (Most frequent - 60% of interactions)
   - Users open dashboard to see "what happened while I was away"
   - Scroll through AI-generated event descriptions
   - Filter by camera, date range, object type
   - Search for specific events ("package delivery")

2. **Monitoring Live Cameras** (Second most frequent - 25%)
   - Quick glance at live camera previews
   - Check connection status (green/red indicators)
   - Manual "Analyze Now" trigger when needed

3. **Managing Alert Rules** (Setup/configuration - 10%)
   - Create rules for notifications
   - Test webhook integrations
   - Adjust sensitivity and conditions

4. **System Configuration** (Infrequent - 5%)
   - Add/edit cameras
   - Adjust settings (AI model, retention, motion sensitivity)

**Must Be Effortless:**
- Finding a specific event (search/filter must be fast and obvious)
- Understanding event descriptions (natural language, scannable)
- Seeing camera status at a glance (clear visual indicators)
- Creating basic alert rules (guided, not technical)

**Emotional Goals:**
- **Feel secure** - System is watching, intelligent, reliable
- **Feel informed** - Rich context, not just "motion detected"
- **Feel in control** - Customizable, transparent, privacy-respecting
- **Reduce anxiety** - Trust the alerts, not alert fatigue

---

## 3. Visual Foundation

### 3.1 Color System

**Theme: Guardian Slate** - Sophisticated, protective, privacy-focused

**Primary Colors:**
- Primary: `#475569` (Slate 600) - Main actions, navigation, headers
- Primary Light: `#64748b` (Slate 500) - Hover states, secondary elements
- Primary Dark: `#334155` (Slate 700) - Active states, dark text

**Accent Colors:**
- Accent: `#0ea5e9` (Sky 500) - Key interactive elements, links, "Analyze Now" button
- Used for: Call-to-action buttons, important notifications, live indicators

**Semantic Colors:**
- Success: `#22c55e` (Green 500) - Connected cameras, successful actions
- Warning: `#f97316` (Orange 500) - Warnings, high sensitivity alerts
- Error: `#ef4444` (Red 500) - Connection errors, critical alerts
- Info: `#0ea5e9` (Sky 500) - Informational messages

**Neutral Palette:**
- Background: `#f8fafc` (Slate 50) - Page background
- Surface: `#ffffff` (White) - Cards, modals, elevated surfaces
- Border: `#e2e8f0` (Slate 200) - Dividers, card borders, input borders
- Text Primary: `#0f172a` (Slate 900) - Body text, headings
- Text Secondary: `#64748b` (Slate 500) - Helper text, timestamps, metadata
- Text Muted: `#94a3b8` (Slate 400) - Disabled states, placeholders

**Usage Guidelines:**
- Primary slate for navigation, buttons, professional actions
- Accent cyan for "smart" actions (AI analysis, live monitoring)
- Semantic colors strictly for their purpose (don't use green for non-success)
- Maintain 4.5:1 contrast ratio minimum (WCAG AA)

### 3.2 Typography System

**Font Families:**
- **Sans Serif (Primary):** `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
  - Modern, highly readable, excellent at small sizes
  - Used for: All UI text, body copy, navigation

- **Monospace (Code/Technical):** `'Fira Code', 'Courier New', monospace`
  - Used for: RTSP URLs, API keys, webhook URLs, timestamps

**Type Scale (rem units, base 16px):**
- Display: `3rem` (48px) - Hero text, empty states
- H1: `2.25rem` (36px) - Page titles
- H2: `1.875rem` (30px) - Section headers
- H3: `1.5rem` (24px) - Card titles, modal headers
- H4: `1.25rem` (20px) - Subsection headers
- Body Large: `1.125rem` (18px) - Emphasis text
- Body: `1rem` (16px) - Default body text
- Body Small: `0.875rem` (14px) - Helper text, metadata
- Caption: `0.75rem` (12px) - Timestamps, labels

**Font Weights:**
- Regular: 400 (body text, descriptions)
- Medium: 500 (buttons, labels, slight emphasis)
- Semibold: 600 (headings, card titles, navigation)
- Bold: 700 (data emphasis, critical alerts)

**Line Heights:**
- Tight: 1.25 - Headings, navigation
- Normal: 1.5 - Body text, descriptions
- Relaxed: 1.75 - Long-form content (documentation)

### 3.3 Spacing System

**Base Unit:** 4px (0.25rem)

**Spacing Scale:**
- xs: `0.25rem` (4px) - Tight spacing, icon gaps
- sm: `0.5rem` (8px) - Button padding, form field gaps
- md: `1rem` (16px) - Card padding, section gaps
- lg: `1.5rem` (24px) - Section spacing
- xl: `2rem` (32px) - Page margins, major sections
- 2xl: `3rem` (48px) - Large vertical spacing
- 3xl: `4rem` (64px) - Hero sections, empty states

**Component Spacing Guidelines:**
- Button padding: `sm` vertical, `md` horizontal (8px × 16px)
- Card padding: `lg` (24px all sides)
- Form field gaps: `md` (16px between fields)
- Section spacing: `xl` to `2xl` (32-48px)
- Page margins: `lg` on mobile, `xl` on desktop

### 3.4 Layout & Grid

**Responsive Breakpoints:**
- Mobile: `< 640px` (sm)
- Tablet: `640px - 1024px` (md to lg)
- Desktop: `> 1024px` (xl)
- Wide: `> 1280px` (2xl)

**Container Widths:**
- Mobile: Full width with 16px padding
- Tablet: Full width with 24px padding
- Desktop: Max 1280px centered
- Wide: Max 1536px centered

**Grid System:**
- 12-column grid (Tailwind default)
- Gutter: 16px (mobile), 24px (desktop)

---

## 4. Design Direction

### 4.1 Chosen Design Approach

**Design Direction: Split View Dashboard** (Direction 5 from mockup exploration)

**Layout Structure:**
- **Left Sidebar:** Persistent navigation (240px width on desktop)
- **Main Content Area:** Event timeline with 2-column card grid
- **Right Sidebar:** Stats and context panel (400px width on desktop)
  - Today's activity stats (events, alerts, confidence)
  - Camera status indicators (online/offline)
  - Quick camera thumbnail grid (2×2)

**Key Layout Decisions:**
- **Navigation:** Persistent left sidebar (desktop) / Bottom tabs (mobile)
- **Content:** 2-column card-based event timeline in main area
- **Context Panel:** Right sidebar with stats and camera status
- **Density:** Balanced - information-rich but well-organized
- **Visual Style:** Clean, modern, minimal shadows with clear hierarchy

**Design Rationale:**
- **Split view balances event focus with contextual awareness**
  - Main area prioritizes event review (60% of screen width)
  - Right sidebar provides at-a-glance status without navigation
  - Users can monitor events AND system health simultaneously

- **Addresses all three persona needs:**
  - **Sarah (Homeowner):** Easy event scanning in main area, quick stats
  - **Marcus (Smart Home):** Data-rich sidebar, camera status, statistics
  - **Linda (Accessibility):** Organized layout, clear hierarchy for screen readers

- **Efficient use of wide screens (>1280px)**
  - Maximizes information density on desktop
  - No wasted space, but not cluttered
  - Quick camera tiles eliminate need to navigate to Cameras page

- **Responsive adaptation:**
  - Desktop (>1024px): Full split view with both sidebars
  - Tablet (640-1024px): Hide right sidebar, show stats as collapsible panel
  - Mobile (<640px): Single column, stats as swipe-up drawer

**Component Hierarchy:**
1. **Primary Focus:** Event timeline (main content)
2. **Secondary Context:** Stats sidebar (persistent but not primary)
3. **Quick Actions:** Camera thumbnails (monitoring without navigation)
4. **Navigation:** Left sidebar (always accessible)

**Interaction Patterns:**
- Click event card → Modal with full details
- Click camera tile → Navigate to camera detail page
- Stats update in real-time (WebSocket)
- Sidebar collapsible on desktop for more event space

---

## 5. User Journey Flows

### 5.1 Critical User Paths

**Journey 1: Review Event History (Primary)**

**User Goal:** See what happened while away, find specific events

**Flow:**
1. **Entry:** User opens dashboard → Lands on Events page
2. **Scan:** User scans event timeline (most recent first)
3. **Filter (optional):** User applies filters (date range, camera, object type)
4. **Search (optional):** User searches descriptions ("package")
5. **Review:** User clicks event card → Modal with full details + thumbnail
6. **Action (optional):** User provides feedback or shares event

**Key Design Decisions:**
- Events page is default landing page (most frequent action)
- Filters visible but not intrusive (collapsible sidebar or top bar)
- Search prominent (top right, always visible)
- Infinite scroll for timeline (load 20 events at a time)
- Click anywhere on card to expand (large touch target)

**Journey 2: Add New Camera (Configuration)**

**User Goal:** Set up camera to start monitoring

**Flow:**
1. **Entry:** User clicks "Add Camera" button on Cameras page
2. **Form:** Modal appears with camera configuration form
   - Camera Name (text input)
   - Camera Type (RTSP / USB radio buttons)
   - RTSP URL (text input, conditional on type)
   - Username/Password (text inputs, optional)
3. **Test:** User clicks "Test Connection" button
   - Shows loading spinner
   - Success: Green checkmark + preview thumbnail
   - Error: Red X + specific error message
4. **Save:** User clicks "Save Camera"
   - Camera added to list
   - Toast notification: "Camera added successfully"
5. **Monitor:** Camera appears in live preview grid

**Key Design Decisions:**
- Modal form (don't leave Cameras page)
- Test connection before saving (validate immediately)
- Clear error messages with troubleshooting hints
- Preview thumbnail confirms connection working
- Form validation prevents common mistakes

**Journey 3: Create Alert Rule (Automation)**

**User Goal:** Get notified when specific events occur

**Flow:**
1. **Entry:** User clicks "Create Rule" on Rules page
2. **Name:** User enters rule name ("Package Delivery Alert")
3. **Conditions:** User selects conditions
   - Object types: Checkboxes (Person, Vehicle, Package, Animal)
   - Cameras: Multi-select dropdown
   - Time of day: Optional time range picker
   - Days of week: Optional checkboxes
4. **Actions:** User configures actions
   - Dashboard notification: Checkbox (default ON)
   - Webhook: Checkbox + URL input (conditional)
5. **Test (optional):** User clicks "Test Rule" → Shows matching past events
6. **Save:** User clicks "Save Rule"
   - Rule added to list
   - Toast: "Alert rule created"

**Key Design Decisions:**
- Guided form layout (step-by-step feel without wizard)
- Smart defaults (most common conditions pre-selected)
- Test feature prevents "set and forget and it doesn't work"
- Webhook configuration optional (don't overwhelm beginners)
- Visual preview of what rule will match

---

## 6. Component Library

### 6.1 Component Strategy

**From shadcn/ui (Use as-is or lightly customized):**
- Button (Primary, Secondary, Ghost, Destructive variants)
- Input (Text, Password, Number)
- Select / Dropdown
- Dialog / Modal
- Card
- Table
- Toast / Notification
- Tabs
- Toggle / Switch
- Slider
- Badge

**Custom Components Needed:**

**1. EventCard**
- **Purpose:** Display event summary in timeline
- **Content:**
  - Thumbnail image (320×180px)
  - Timestamp (relative + absolute on hover)
  - Camera name with icon
  - AI description (truncated to 3 lines)
  - Confidence score (visual indicator)
  - Object badges (Person, Vehicle, etc.)
- **States:**
  - Default: White background, subtle border
  - Hover: Slight elevation, border color change
  - Clicked: Modal opens with full details
  - Alert triggered: Orange left border accent
- **Variants:**
  - Compact (for mobile)
  - Expanded (modal view)
- **Accessibility:**
  - ARIA role: article
  - Keyboard: Enter to expand
  - Screen reader: Full description announced

**2. CameraPreview**
- **Purpose:** Show live camera feed with status
- **Content:**
  - Camera name header
  - Live image preview (auto-refreshing every 2s)
  - Connection status indicator (dot + text)
  - Last update timestamp
  - "Analyze Now" button (hover overlay)
- **States:**
  - Connected: Green dot, image updates
  - Connecting: Yellow dot, loading skeleton
  - Disconnected: Red dot, error message
  - Disabled: Gray dot, "Camera disabled"
- **Behavior:**
  - Click preview → Navigate to camera detail page
  - Hover → Show "Analyze Now" button
  - Auto-refresh pauses when browser tab inactive
- **Accessibility:**
  - Alt text for preview image
  - Status announced on change
  - Button keyboard accessible

**3. AlertRuleBuilder**
- **Purpose:** Visual interface for creating alert conditions
- **Content:**
  - Rule name input
  - Condition builder (object types, cameras, time/day)
  - Action configuration (notifications, webhooks)
  - Cooldown slider
  - Test and Save buttons
- **States:**
  - Editing: Live validation, save enabled/disabled
  - Testing: Loading spinner, results displayed
  - Error: Field-level validation errors
- **Behavior:**
  - Real-time validation (required fields)
  - Test shows "This would match X events" with examples
  - Save triggers confirmation toast
- **Accessibility:**
  - Form labels properly associated
  - Error messages announced
  - Keyboard navigation through all fields

**4. NotificationBell**
- **Purpose:** Header notification center
- **Content:**
  - Bell icon with unread count badge
  - Dropdown panel with notification list
  - "Mark all read" action
- **States:**
  - No notifications: Gray bell
  - Unread: Red badge with count
  - Open: Dropdown visible
- **Behavior:**
  - Real-time updates via WebSocket
  - Click notification → Navigate to event
  - Click "Mark all read" → Clears badge
- **Accessibility:**
  - ARIA live region for new notifications
  - Keyboard: Tab to open, arrows to navigate
  - Screen reader announces new notifications

---

## 7. UX Pattern Decisions

### 7.1 Consistency Rules

**Button Hierarchy:**
- **Primary:** Slate background (`#475569`), white text - Main actions (Save, Create, Add Camera)
- **Secondary:** White background, slate border/text - Cancel, alternative actions
- **Accent:** Cyan background (`#0ea5e9`), white text - Smart actions (Analyze Now, Test Connection)
- **Destructive:** Red background (`#ef4444`), white text - Delete, Remove (requires confirmation)
- **Ghost:** Transparent background, slate text on hover - Tertiary actions, icon buttons

**Feedback Patterns:**
- **Success:** Green toast notification (top-right, auto-dismiss 3s) - "Camera added successfully"
- **Error:** Red inline message + red toast - Field errors inline, system errors as toast
- **Warning:** Orange banner (top of page, dismissible) - "High motion sensitivity may cause false positives"
- **Info:** Blue toast (auto-dismiss 5s) - "Processing event..."
- **Loading:** Inline spinner + disabled state - Never block entire UI, show loading in context

**Form Patterns:**
- **Label position:** Above input field (not floating labels)
- **Required indicator:** Asterisk (*) next to label
- **Validation timing:** onBlur for fields, onSubmit for form
- **Error display:** Inline below field (red text + red border on input)
- **Help text:** Gray text below input when not in error state

**Modal Patterns:**
- **Size variants:**
  - Small (400px): Confirmations, simple actions
  - Medium (600px): Camera config, alert rules
  - Large (800px): Event details with image
  - Full-screen on mobile (<640px)
- **Dismiss behavior:** Click backdrop, Escape key, explicit Close button
- **Focus management:** Auto-focus first input field on open
- **Stacking:** Max 1 modal at a time (close current before opening new)

**Navigation Patterns:**
- **Active state:** Slate background, white text, left border accent (cyan)
- **Breadcrumbs:** Not needed (flat structure)
- **Back button:** Browser back works (proper routing), app back button not needed
- **Deep linking:** All pages support direct URL access with filters

**Empty State Patterns:**
- **First use:** Large icon + heading + description + CTA button
  - Example: "No cameras yet. Add your first camera to start monitoring."
- **No results:** Helpful message with suggestions
  - Example: "No events found. Try adjusting your filters or date range."
- **Cleared content:** Option to undo if applicable
  - Example: "All notifications cleared" with "Undo" link

**Confirmation Patterns:**
- **Delete:** Always confirm with modal ("Delete [Item]? This cannot be undone")
- **Leave unsaved:** Warn before navigation if form has changes
- **Irreversible actions:** Explicit confirmation (delete all data, reset settings)
- **Destructive action color:** Red button in confirmation modal

**Notification Patterns:**
- **Placement:** Top-right corner (standard position)
- **Duration:**
  - Success: 3 seconds auto-dismiss
  - Error: 5 seconds (or manual dismiss)
  - Info: 4 seconds
  - Warning: Manual dismiss only
- **Stacking:** Max 3 visible, older ones auto-dismiss
- **Priority:** Errors appear above other types

**Search Patterns:**
- **Trigger:** Auto-search with 500ms debounce (type → wait → search)
- **Results display:** Inline in timeline (filters existing list)
- **Filters:** Sidebar on desktop, collapsible drawer on mobile
- **No results:** "No events matching '[query]'" + clear filters option

**Date/Time Patterns:**
- **Format:** Relative time primary ("2 hours ago"), absolute on hover tooltip
- **Timezone:** User's local timezone (auto-detected)
- **Picker:** Calendar dropdown for date range (not native input)
- **Display:** 12-hour format with AM/PM (US default), 24-hour as user setting

---

## 8. Responsive Design & Accessibility

### 8.1 Responsive Strategy

**Breakpoint Adaptations:**

**Mobile (<640px):**
- **Navigation:** Bottom tab bar (4 tabs: Events, Cameras, Rules, Settings)
- **Sidebar:** Hidden, hamburger menu if needed
- **Event cards:** Single column, full width
- **Camera grid:** 1 column
- **Forms:** Stacked fields, full-width inputs
- **Modals:** Full-screen overlay
- **Tables:** Convert to card view (no horizontal scroll)

**Tablet (640-1024px):**
- **Navigation:** Top bar with hamburger, or persistent sidebar (collapsible)
- **Event cards:** 1-2 columns depending on space
- **Camera grid:** 2 columns
- **Forms:** Some fields side-by-side (Name + Type on one row)
- **Modals:** Centered with max-width

**Desktop (>1024px):**
- **Navigation:** Persistent left sidebar (240px width)
- **Event cards:** 2-3 columns in grid view option
- **Camera grid:** 3 columns (up to 4 on wide screens)
- **Forms:** Multi-column layout where logical
- **Modals:** Centered with defined widths

**Touch Targets:**
- Minimum size: 44×44px (WCAG AAA)
- Button padding: 12px vertical minimum
- Clickable areas extend to full card height (not just text)

### 8.2 Accessibility Strategy

**Compliance Target:** WCAG 2.1 Level AA

**Key Requirements:**

**Color Contrast:**
- Text contrast: 4.5:1 minimum (body text)
- Large text: 3:1 minimum (18px+, or 14px bold)
- UI components: 3:1 minimum (borders, icons)
- All theme colors tested and compliant

**Keyboard Navigation:**
- All interactive elements keyboard accessible
- Logical tab order (left-to-right, top-to-bottom)
- Focus indicators: 2px cyan outline on all focusable elements
- Skip navigation link (jump to main content)
- Keyboard shortcuts documented (optional for power users)

**Screen Reader Support:**
- Semantic HTML (nav, main, article, button elements)
- ARIA labels for icon buttons ("Add Camera", not just plus icon)
- ARIA live regions for notifications and dynamic updates
- Alt text for all event thumbnail images (includes description)
- Form labels properly associated with inputs
- Error messages announced when validation fails

**Visual Accessibility:**
- Text resizable up to 200% without breaking layout
- No information conveyed by color alone (use icons + text)
- Animations respect prefers-reduced-motion
- Clear focus indicators (never hide outline)

**Testing Strategy:**
- Automated: Lighthouse accessibility audit (score >90)
- Keyboard: Full keyboard-only navigation test
- Screen reader: VoiceOver (Safari) and NVDA (Chrome) testing
- Color blindness: Test with Stark or ColorOracle simulator

**Specific Considerations for Linda (Visually Impaired User):**
- Event descriptions read naturally by screen readers
- All camera status changes announced
- Notifications include full event description (not just "New event")
- Dashboard fully navigable with VoiceOver
- High contrast mode support (respect system preferences)

---

## 9. Implementation Guidance

### 9.1 Design Tokens (Tailwind Config)

```javascript
// tailwind.config.js extensions
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#475569', // slate-600
          light: '#64748b',   // slate-500
          dark: '#334155',    // slate-700
        },
        accent: {
          DEFAULT: '#0ea5e9', // sky-500
        },
        // Semantic colors use Tailwind defaults (green, orange, red)
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Fira Code', 'Courier New', 'monospace'],
      },
    },
  },
}
```

### 9.2 Component Implementation Priority

**Phase 1 (MVP Foundation):**
1. Layout structure (Sidebar, Header, Main content area)
2. EventCard component
3. CameraPreview component
4. Basic forms (Camera config, Alert rules)
5. Toast notifications

**Phase 2 (Polish):**
6. NotificationBell component
7. Advanced filtering UI
8. Empty states
9. Loading skeletons
10. Responsive refinements

### 9.3 Next Steps

**Immediate Actions:**
1. Install shadcn/ui and configure theme colors
2. Create base layout components (Sidebar, Header)
3. Implement EventCard with all states
4. Build camera configuration form
5. Set up toast notification system

**Design Artifacts Needed:**
- High-fidelity mockups for key screens (optional, can build directly from this spec)
- Icon set selection (recommend Heroicons 2.0 - already in stack)
- Example event descriptions for realistic data

---

## 10. Phase 2 UX Additions (UniFi Protect + xAI Grok)

_Added 2025-11-30 for Phase 2 feature enhancements_

### 10.1 Overview

Phase 2 introduces native UniFi Protect integration and xAI Grok as an additional AI provider. These additions extend the existing UX without replacing it - all MVP patterns, colors, and components remain unchanged.

**New UI Elements:**
- UniFi Protect configuration section in Settings
- Camera discovery and selection interface
- Event type filtering per camera
- Connection status indicators
- xAI Grok provider configuration
- Event source type indicator
- Multi-camera event correlation display

### 10.2 Settings Page: UniFi Protect Section

**Location:** Settings page → New "UniFi Protect" tab/section

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ UniFi Protect Integration                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Controller Connection                    [Status Indicator] │
│ ─────────────────────────────────────────────────────────── │
│                                                             │
│ Host/IP:     [________________________]                     │
│ Username:    [________________________]                     │
│ Password:    [________________________]                     │
│                                                             │
│ [Test Connection]              [Save]  [Remove Controller]  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Discovered Cameras (6 found)                    [Refresh]   │
│ ─────────────────────────────────────────────────────────── │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ☑ Front Door Camera              [Configure Filters ▼]  │ │
│ │   Type: G4 Doorbell  •  Status: Online                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ☑ Driveway Camera                [Configure Filters ▼]  │ │
│ │   Type: G4 Pro  •  Status: Online                       │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ☐ Backyard Camera                [Configure Filters ▼]  │ │
│ │   Type: G3 Flex  •  Status: Online  (Disabled)          │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Components:**

**UniFiControllerForm**
- **Purpose:** Configure connection to UniFi Protect controller
- **Fields:**
  - Host/IP (text input, required) - placeholder: "192.168.1.1 or unifi.local"
  - Username (text input, required)
  - Password (password input, required)
- **Actions:**
  - Test Connection: Validates credentials, shows success/error
  - Save: Stores encrypted credentials, initiates WebSocket connection
  - Remove Controller: Confirms, then disconnects and clears settings
- **States:**
  - No controller: Empty form with "Connect your UniFi Protect controller"
  - Connecting: Form disabled, spinner on Test/Save buttons
  - Connected: Green status badge, form populated (password hidden)
  - Connection error: Red status badge, error message displayed
  - Disconnected: Yellow status badge, "Reconnecting..." message

**ConnectionStatusIndicator**
- **Purpose:** Show real-time connection state
- **Variants:**
  - Connected: Green dot + "Connected" text
  - Connecting: Yellow dot + "Connecting..." text + spinner
  - Disconnected: Red dot + "Disconnected" text
  - Error: Red dot + "Connection Error" text + error details tooltip
- **Behavior:** Updates in real-time via WebSocket status
- **Accessibility:** Status changes announced via ARIA live region

**DiscoveredCameraList**
- **Purpose:** Display cameras found from controller with enable/disable toggles
- **Content per camera:**
  - Checkbox: Enable/disable for AI analysis
  - Camera name (from Protect)
  - Camera type badge (G4 Doorbell, G4 Pro, G3 Flex, etc.)
  - Status indicator (Online/Offline)
  - "Configure Filters" dropdown button
- **States:**
  - No cameras: "No cameras discovered. Check controller connection."
  - Loading: Skeleton list with 3 placeholder items
  - Populated: List of DiscoveredCameraCard components
- **Actions:**
  - Refresh: Re-fetch camera list from controller
  - Enable/Disable: Toggle persists immediately
- **Sorting:** Enabled cameras first, then alphabetical by name

**DiscoveredCameraCard**
- **Purpose:** Single camera row in discovered list
- **Content:**
  - Enable checkbox (left)
  - Camera icon (based on type: doorbell icon, camera icon)
  - Camera name (bold)
  - Type badge (muted text)
  - Status dot (green/red)
  - Configure Filters button (right)
- **States:**
  - Enabled: Full opacity, checkbox checked
  - Disabled: 50% opacity, checkbox unchecked, "(Disabled)" label
  - Offline: Red status dot, "Offline" badge
- **Accessibility:**
  - Checkbox labeled with camera name
  - Status announced when changed

### 10.3 Event Type Filter Configuration

**Location:** Dropdown/popover from "Configure Filters" button on each camera

**Layout:**
```
┌─────────────────────────────────────┐
│ Event Types to Analyze              │
│ ─────────────────────────────────── │
│ ☑ Person                            │
│ ☑ Vehicle                           │
│ ☑ Package                           │
│ ☐ Animal                            │
│ ☐ All Motion (ignores above)        │
│ ─────────────────────────────────── │
│ [Apply]                    [Cancel] │
└─────────────────────────────────────┘
```

**EventTypeFilterPopover**
- **Purpose:** Configure which Protect smart detection types trigger AI analysis
- **Options:**
  - Person (default: checked)
  - Vehicle (default: checked)
  - Package (default: checked)
  - Animal (default: unchecked)
  - All Motion (default: unchecked) - mutually exclusive, overrides others
- **Behavior:**
  - Checking "All Motion" disables and unchecks other options
  - Unchecking "All Motion" re-enables other options
  - Changes require Apply to save (not immediate)
  - Cancel reverts to saved state
- **Visual:**
  - Checkbox list with labels
  - "All Motion" has helper text: "Analyzes all motion, ignores smart detection types"
- **Accessibility:**
  - Fieldset with legend "Event Types to Analyze"
  - Checkboxes properly labeled

### 10.4 Settings Page: xAI Grok Provider

**Location:** Settings page → AI Providers section (existing)

**Addition to existing AI provider list:**

```
┌─────────────────────────────────────────────────────────────┐
│ AI Providers                                                │
├─────────────────────────────────────────────────────────────┤
│ Fallback Order (drag to reorder):                           │
│                                                             │
│ 1. ⋮⋮ OpenAI GPT-4o mini        [Configured ✓]  [Edit]     │
│ 2. ⋮⋮ Anthropic Claude 3 Haiku  [Configured ✓]  [Edit]     │
│ 3. ⋮⋮ Google Gemini Flash       [Configured ✓]  [Edit]     │
│ 4. ⋮⋮ xAI Grok                  [Not configured] [Setup]    │
│                                                             │
│ [+ Add Provider]                                            │
└─────────────────────────────────────────────────────────────┘
```

**GrokProviderConfig**
- **Purpose:** Configure xAI Grok API access
- **Fields:**
  - API Key (password input, required)
  - Model selection (dropdown): grok-4, grok-3
- **Actions:**
  - Test: Validates API key with test request
  - Save: Stores encrypted, adds to fallback chain
  - Remove: Removes from chain (with confirmation)
- **States:**
  - Not configured: "Setup" button, muted appearance
  - Configured: "Configured ✓" badge, "Edit" button
  - Testing: Spinner on test button
  - Error: Red border, error message below field
- **Drag handle:** Allows reordering position in fallback chain
- **Follows same pattern as existing OpenAI/Claude/Gemini providers**

### 10.5 Enhanced Event Display

**EventCard Additions:**

**Source Type Indicator**
- **Location:** Top-right corner of event card, next to timestamp
- **Variants:**
  - UniFi Protect: Shield icon + "Protect" text (muted)
  - RTSP: Camera icon + "RTSP" text (muted)
  - USB: USB icon + "USB" text (muted)
- **Purpose:** Users can identify which camera system captured the event
- **Visual:** Small badge, subtle (doesn't compete with description)

**Smart Detection Badge**
- **Location:** Below AI description, alongside existing object badges
- **Content:** Shows Protect's smart detection type that triggered event
- **Variants:**
  - Person: Blue badge with person icon
  - Vehicle: Purple badge with car icon
  - Package: Orange badge with box icon
  - Animal: Green badge with paw icon
  - Motion: Gray badge with motion icon
- **Purpose:** Shows what Protect detected vs what AI described

**Correlation Indicator**
- **Location:** Bottom of event card (when correlated)
- **Content:** "Also captured by: [Camera Name], [Camera Name]"
- **Visual:** Link/button styling - clickable to navigate to related events
- **Behavior:**
  - Click camera name → Scrolls to/highlights that camera's event
  - Correlated events share a visual connector (subtle background tint or left border)
- **Icon:** Link chain icon to indicate correlation

**Enhanced EventCard Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ [Thumbnail]                                                 │
│                                                             │
│ Front Door Camera          2 min ago  •  🛡️ Protect        │
│ ─────────────────────────────────────────────────────────── │
│ "A delivery driver in a brown uniform is placing a         │
│ package on the front porch. The package appears to be      │
│ from Amazon based on the visible logo."                    │
│                                                             │
│ [👤 Person] [📦 Package]        Confidence: 94%            │
│                                                             │
│ 🔗 Also captured by: Driveway Camera                       │
└─────────────────────────────────────────────────────────────┘
```

### 10.6 Cameras Page Enhancement

**Location:** Existing Cameras page

**Changes:**
- **Camera source grouping:** Optional toggle to group by source (UniFi Protect / RTSP / USB)
- **UniFi Protect cameras:** Show Protect-specific info (camera model, firmware)
- **Status indicator:** Enhanced to show WebSocket connection status for Protect cameras
- **"Add Camera" flow:** Now offers choice between "Manual (RTSP/USB)" and "UniFi Protect" (redirects to Settings)

**Camera Grid Enhancement:**
```
┌─────────────────────────────────────────────────────────────┐
│ Cameras                                    [+ Add Camera ▼] │
│                                                             │
│ [All] [UniFi Protect (4)] [RTSP (1)] [USB (0)]             │
│ ─────────────────────────────────────────────────────────── │
│                                                             │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│ │ [Preview]   │ │ [Preview]   │ │ [Preview]   │            │
│ │             │ │             │ │             │            │
│ │ Front Door  │ │ Driveway    │ │ Backyard    │            │
│ │ 🛡️ Protect  │ │ 🛡️ Protect  │ │ 📹 RTSP     │            │
│ │ ● Online    │ │ ● Online    │ │ ● Online    │            │
│ └─────────────┘ └─────────────┘ └─────────────┘            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 10.7 Doorbell-Specific UX

**Doorbell Ring Event:**
- **Distinct event type:** Doorbell icon instead of motion icon
- **Notification priority:** Higher priority than motion events
- **Event card styling:** Subtle accent border (cyan) to stand out
- **Description prompt:** AI specifically asked "Who is at the door?"

**Doorbell EventCard:**
```
┌─────────────────────────────────────────────────────────────┐
│ 🔔 DOORBELL RING                           Just now         │
├─────────────────────────────────────────────────────────────┤
│ [Thumbnail]                                                 │
│                                                             │
│ Front Door Camera                          🛡️ Protect       │
│ ─────────────────────────────────────────────────────────── │
│ "A woman in her 30s wearing a blue jacket is standing at   │
│ the front door. She appears to be holding a clipboard and  │
│ may be a delivery person or solicitor."                    │
│                                                             │
│ [👤 Person]                             Confidence: 91%     │
└─────────────────────────────────────────────────────────────┘
```

### 10.8 User Journeys (Phase 2)

**Journey: Set Up UniFi Protect Integration**

**User Goal:** Connect UniFi Protect system to start using native integration

**Flow:**
1. **Entry:** User navigates to Settings → UniFi Protect section
2. **Configure:** User enters controller IP, username, password
3. **Test:** User clicks "Test Connection"
   - Success: Green checkmark, camera count shown
   - Error: Red X, specific error message (auth failed, host unreachable, etc.)
4. **Save:** User clicks "Save" → Credentials stored encrypted
5. **Discovery:** Camera list populates automatically
6. **Select:** User enables desired cameras via checkboxes
7. **Filter:** User optionally configures event type filters per camera
8. **Complete:** Events begin flowing from enabled cameras

**Key Design Decisions:**
- Test before save (validate immediately)
- Auto-discovery (no manual camera entry)
- Sensible defaults (Person/Vehicle/Package checked by default)
- Clear status indicators throughout

**Journey: Configure xAI Grok**

**User Goal:** Add Grok as an AI provider option

**Flow:**
1. **Entry:** User navigates to Settings → AI Providers
2. **Add:** User clicks "Setup" next to xAI Grok (or "+ Add Provider")
3. **Configure:** User enters API key, selects model
4. **Test:** User clicks "Test" → Shows success/failure
5. **Save:** User clicks "Save" → Added to fallback chain
6. **Order:** User optionally drags to reorder position in chain

**Key Design Decisions:**
- Same pattern as existing AI providers (consistency)
- Drag-to-reorder for fallback position (intuitive)
- Test validates before committing

### 10.9 Error States (Phase 2)

**Controller Connection Errors:**
- "Unable to connect to controller" → Check IP/hostname, ensure controller is online
- "Authentication failed" → Check username/password, ensure user has API access
- "Connection lost" → Yellow banner, auto-reconnect in progress
- "Controller unreachable" → Red banner, manual retry option

**Camera Discovery Errors:**
- "No cameras found" → Check controller has cameras, user has camera permissions
- "Camera offline" → Gray out camera, show "Offline" status

**WebSocket Errors:**
- "Real-time connection lost" → Yellow toast, auto-reconnect with backoff
- "Reconnected" → Green toast (brief), resume normal operation

**API Errors:**
- "Grok API error" → Falls back to next provider, logs error
- "Rate limit exceeded" → Queues request, retries after delay

### 10.10 Phase 2 Component Summary

| Component | Type | Purpose |
|-----------|------|---------|
| UniFiControllerForm | New | Controller connection config |
| ConnectionStatusIndicator | New | Real-time connection state |
| DiscoveredCameraList | New | Camera discovery display |
| DiscoveredCameraCard | New | Single camera row |
| EventTypeFilterPopover | New | Per-camera filter config |
| GrokProviderConfig | New | xAI Grok API setup |
| SourceTypeBadge | Enhancement | Event source indicator |
| SmartDetectionBadge | Enhancement | Protect detection type |
| CorrelationIndicator | Enhancement | Multi-camera event links |
| DoorbellEventCard | Variant | Doorbell-specific styling |

---

## Appendix

### Related Documents

- Product Requirements: `docs/prd/`
- Product Brief: `docs/product-brief.md`
- Epic Breakdown: `docs/epics.md`
- Architecture: `docs/architecture.md`

### Interactive Deliverables

- **Color Theme Visualizer**: `docs/ux-color-themes.html`
  - Interactive HTML showing Theme 2 (Guardian Slate) selected
  - Live UI component examples in chosen theme
  - Color palette with hex codes and usage guidelines

### Version History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-17 | 1.0 | Initial UX Design Specification | Brent |
| 2025-11-30 | 1.1 | Phase 2 additions: UniFi Protect integration UX, xAI Grok provider, event enhancements | Brent |

---

_This UX Design Specification provides the visual design foundation and interaction patterns for the Live Object AI Classifier dashboard. Implementation should reference this document for all design decisions, ensuring consistency and meeting accessibility requirements._
