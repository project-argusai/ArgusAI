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
| IMP-001 | 2025-12-06 | P4 | Code Quality | Remove console.log debug statements from EventCard.tsx (lines 104, 107) before production deployment | Story P3-3.4 Code Review | Done |

---

## Future Features

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|
| FF-001 | 2025-12-08 | P3 | Troubleshooting | **Log Viewer UI** - Simple dashboard page to view and download logs for troubleshooting. Features: (1) View last 24 hours of backend logs, (2) Filter by log level (ERROR, WARNING, INFO, DEBUG), (3) Search/filter by text, (4) Download logs as file, (5) Auto-refresh option. Implementation: Store logs in SQLite or file rotation, add /api/v1/system/logs endpoint, build React component in Settings page. | User Request | Done |
| FF-002 | 2025-12-08 | P2 | UX | **Events Page Real-time Updates** - Add refresh capability to events page so new events appear without manual page reload. Options: (1) Manual refresh button with loading indicator, (2) WebSocket subscription to EVENT_CREATED messages (backend already broadcasts these), (3) Auto-refresh toggle with configurable interval. Recommended: Use existing WebSocket infrastructure - subscribe to EVENT_CREATED and prepend new events to list. | User Request | Done |
| FF-003 | 2025-12-08 | P2 | UX | **Show Camera Name on Event Cards** - Event cards currently display camera_id (UUID) instead of the human-readable camera name. Update EventCard component to show camera.name for better identification. Backend API already includes camera_name in EVENT_CREATED WebSocket messages and event responses - just need to use it in the frontend display. | User Request | Done |
| FF-004 | 2025-12-08 | P2 | Performance | **Move Camera Preview to Cameras Page** - Dashboard currently shows live camera previews which generates significant network traffic (frame polling). Move the live preview grid to the Cameras page instead. Dashboard should show only camera status info (name, online/offline, last event) without live video streams. This reduces API chatter when users are just viewing the main dashboard. | User Request | Won't Fix |
| FF-005 | 2025-12-08 | P3 | UX | **Mobile Navigation - Top Bar Only** - On mobile devices, show navigation only at the top of the page instead of sidebar. Hide the sidebar on small screens and use a hamburger menu or horizontal nav bar to clean up the interface and maximize content area. Use Tailwind responsive breakpoints (md:hidden, lg:block) to toggle between mobile top nav and desktop sidebar. | User Request | Done |
| FF-006 | 2025-12-08 | P2 | UX | **Dashboard Real-time Stats Update** - When a new event is created, update the "Total Events" and "Current Activity" cards on the dashboard in real-time. Subscribe to EVENT_CREATED WebSocket messages and increment counters without requiring page refresh. Can be implemented alongside FF-002 (Events Page Real-time Updates) using same WebSocket subscription pattern. | User Request | Done |
| BUG-001 | 2025-12-08 | P2 | Bug | **Export JSON/CSV Buttons Failing** - The export buttons on the events page are not working. Investigate and fix the /api/v1/events/export endpoint or frontend export functionality. Check: (1) API endpoint returning correct data format, (2) Frontend correctly calling export endpoint, (3) File download handling in browser. | User Report | Done |
| BUG-002 | 2025-12-08 | P3 | Bug | **Motion Events Not Captured from Protect** - Pure motion events (without smart detection) are not being captured. Investigation shows that `is_motion_currently_detected` flag is separate from `is_smart_detected` in Protect WebSocket. When smart detection occurs (person/vehicle), motion flag is False. Options: (1) Treat smart detections AS motion events (they all involve motion), (2) Add separate motion event polling, (3) Accept that smart detections are the primary event type and update camera config UI to clarify this. Note: This may be expected behavior - Protect prioritizes smart detection over raw motion. | Investigation | Done |
| FF-007 | 2025-12-08 | P3 | Feature | **Selective Backup/Restore Options** - Add granular selection for both backup and restore operations. Backup: Allow users to choose which components to include via checkboxes: (1) Database (events, cameras, alert rules), (2) Thumbnails/media files, (3) System settings, (4) AI provider configuration (API keys), (5) Protect controller config. Restore: Parse backup file to show available components, let user select which parts to restore (e.g., restore only settings without overwriting events). | User Request | Done |
| FF-008 | 2025-12-08 | P2 | DevOps | **Installation Script & Setup Wizard** - Create executable install script to automate application setup. Script should: (1) Check/install Python 3.11+, Node.js 18+, (2) Create virtual environment and install backend dependencies, (3) Install frontend dependencies and build, (4) Initialize database with migrations, (5) Generate encryption key, (6) Create systemd/launchd service files, (7) Configure reverse proxy (nginx) template. Manual setup items to document: (a) AI provider API keys (OpenAI, Gemini, Claude, Grok), (b) UniFi Protect controller credentials, (c) RTSP camera URLs and credentials, (d) SSL certificates for HTTPS, (e) Firewall/port forwarding for remote access. Include first-run setup wizard in UI for manual config items. | User Request | Done |
| IMP-002 | 2025-12-10 | P3 | UX | **Clean Up Event Card Duplicative Stats** - Event cards display redundant information that clutters the UI. Remove or consolidate duplicative stats including: (1) Confidence scoring shown in multiple places, (2) Identification/objects detected items that repeat, (3) Other redundant metadata. Streamline the event card layout to show essential info once in a clean, scannable format. | User Request | Done |
| FF-009 | 2025-12-10 | P2 | Feature | **Save & Display Multi-Frame Event Frames** - For events analyzed with multi-frame mode, persist the extracted frames so users can review them. Implementation: (1) Save key frames to filesystem alongside thumbnails during analysis, (2) Store frame paths/metadata in event record, (3) Add frame gallery UI when event card is expanded/selected, (4) Show frames in sequence with timestamps. This provides transparency into what the AI analyzed and helps users understand multi-frame descriptions. Note: Story P3-7.5 "Display Key Frames Gallery on Event Detail" in sprint-status covers similar scope. | User Request | Done |
| IMP-003 | 2025-12-10 | P3 | UX | **Remove Top Navigation on Desktop** - On desktop mode, the top navigation bar is redundant since the sidebar provides full navigation. Hide the top nav bar on larger screens (lg: breakpoint and above) to maximize content area and reduce visual clutter. Keep top nav visible only on mobile/tablet where sidebar is hidden. Use Tailwind responsive classes (lg:hidden) on the top nav component. | User Request | Done |
| FF-010 | 2025-12-10 | P2 | Feature | **Multi-Select Delete on Events Page** - Add ability to select multiple events and delete them in bulk. Implementation: (1) Add checkbox to each event card for selection, (2) Add "Select All" checkbox in header, (3) Show floating action bar when items selected with delete button and count, (4) Add confirmation dialog before bulk delete, (5) Create backend endpoint `DELETE /api/v1/events/bulk` accepting array of event IDs, (6) Handle associated thumbnails cleanup on delete. | User Request | Done |
| BUG-003 | 2025-12-10 | P3 | Bug | **System Name Not Applied Everywhere** - When changing the system name in settings, not all references update. Fix locations: (1) Top-left corner logo/title in sidebar, (2) Browser tab title (document.title), (3) Any other hardcoded "ArgusAI" references. Implementation: Store system_name in React context or fetch from settings API, use dynamic value in Sidebar component and layout.tsx metadata. Ensure name updates immediately after settings save without page refresh. | User Request | Done |
| TD-002 | 2025-12-12 | P3 | Testing | **FeedbackButtons Component Tests** - Frontend tests for Story P4-5.1 FeedbackButtons component were deferred. Tests to write: (1) Test thumbs up click submits correct rating, (2) Test thumbs down click shows correction input, (3) Test correction input character limit (500), (4) Test selected state visual indicator, (5) Test loading state during submission, (6) Test success toast appears, (7) Test accessibility attributes (aria-label, keyboard navigation). Create `frontend/__tests__/components/events/FeedbackButtons.test.tsx`. | Story P4-5.1 | Done |
| TD-003 | 2025-12-14 | P3 | Testing | **Real Camera Integration Testing** - Test motion detection with diverse real-world footage. Acquire test footage: (1) Indoor/outdoor scenarios, (2) Different lighting conditions (day/night), (3) Various camera angles, (4) Edge cases: trees swaying, rain, shadows. Target: validate >90% person detection, <20% false positive rate. | Epic F2 Retrospective | Done |
| TD-004 | 2025-12-14 | P3 | Testing | **Performance Baseline Documentation** - Document actual CPU/memory usage with: (1) 1 camera @ 5 FPS + motion detection, (2) Different sensitivity levels, (3) MOG2 vs KNN vs frame-diff algorithms. Test on macOS (M1/Intel) and Linux (Ubuntu 22.04, 2-core VM). | Epic F2 Tech-Spec | Done |
| TD-005 | 2025-12-14 | P4 | Documentation | **Update README with Frontend Setup** - Add comprehensive frontend setup instructions: installation steps, environment configuration, development server commands. | F1.2 Code Review | Done |

---

## Improvements

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|
| IMP-001 | 2025-12-06 | P4 | Code Quality | Remove console.log debug statements from EventCard.tsx (lines 104, 107) before production deployment | Story P3-3.4 Code Review | Done |
| IMP-004 | 2025-12-14 | P4 | Code Quality | **Accessibility Enhancements** - Improve frontend accessibility: (1) ~~Add ARIA labels for screen readers~~ (Done in Story P5-5.1, PR #52), (2) ~~Keyboard navigation testing~~ (Done in Story P5-5.2), (3) ~~Focus management in dialogs~~ (Verified - Radix handles this), (4) Skip to content links. | F1.2 Code Review | Partial |
| IMP-005 | 2025-12-14 | P4 | Performance | **Camera List Optimizations** - If camera list grows large: (1) Add React.memo for CameraPreview component, (2) Virtual scrolling for large lists, (3) Consider SWR or React Query for caching. | F1.2 Code Review | Open |

---

## Future Features

| ID | Date | Priority | Type | Description | Source | Status |
|----|------|----------|------|-------------|--------|--------|
| FF-001 | 2025-12-08 | P3 | Troubleshooting | **Log Viewer UI** - Simple dashboard page to view and download logs for troubleshooting. Features: (1) View last 24 hours of backend logs, (2) Filter by log level (ERROR, WARNING, INFO, DEBUG), (3) Search/filter by text, (4) Download logs as file, (5) Auto-refresh option. Implementation: Store logs in SQLite or file rotation, add /api/v1/system/logs endpoint, build React component in Settings page. | User Request | Done |
| FF-002 | 2025-12-08 | P2 | UX | **Events Page Real-time Updates** - Add refresh capability to events page so new events appear without manual page reload. Options: (1) Manual refresh button with loading indicator, (2) WebSocket subscription to EVENT_CREATED messages (backend already broadcasts these), (3) Auto-refresh toggle with configurable interval. Recommended: Use existing WebSocket infrastructure - subscribe to EVENT_CREATED and prepend new events to list. | User Request | Done |
| FF-003 | 2025-12-08 | P2 | UX | **Show Camera Name on Event Cards** - Event cards currently display camera_id (UUID) instead of the human-readable camera name. Update EventCard component to show camera.name for better identification. Backend API already includes camera_name in EVENT_CREATED WebSocket messages and event responses - just need to use it in the frontend display. | User Request | Done |
| FF-004 | 2025-12-08 | P2 | Performance | **Move Camera Preview to Cameras Page** - Dashboard currently shows live camera previews which generates significant network traffic (frame polling). Move the live preview grid to the Cameras page instead. Dashboard should show only camera status info (name, online/offline, last event) without live video streams. This reduces API chatter when users are just viewing the main dashboard. | User Request | Won't Fix |
| FF-005 | 2025-12-08 | P3 | UX | **Mobile Navigation - Top Bar Only** - On mobile devices, show navigation only at the top of the page instead of sidebar. Hide the sidebar on small screens and use a hamburger menu or horizontal nav bar to clean up the interface and maximize content area. Use Tailwind responsive breakpoints (md:hidden, lg:block) to toggle between mobile top nav and desktop sidebar. | User Request | Done |
| FF-006 | 2025-12-08 | P2 | UX | **Dashboard Real-time Stats Update** - When a new event is created, update the "Total Events" and "Current Activity" cards on the dashboard in real-time. Subscribe to EVENT_CREATED WebSocket messages and increment counters without requiring page refresh. Can be implemented alongside FF-002 (Events Page Real-time Updates) using same WebSocket subscription pattern. | User Request | Done |
| BUG-001 | 2025-12-08 | P2 | Bug | **Export JSON/CSV Buttons Failing** - The export buttons on the events page are not working. Investigate and fix the /api/v1/events/export endpoint or frontend export functionality. Check: (1) API endpoint returning correct data format, (2) Frontend correctly calling export endpoint, (3) File download handling in browser. | User Report | Done |
| BUG-002 | 2025-12-08 | P3 | Bug | **Motion Events Not Captured from Protect** - Pure motion events (without smart detection) are not being captured. Investigation shows that `is_motion_currently_detected` flag is separate from `is_smart_detected` in Protect WebSocket. When smart detection occurs (person/vehicle), motion flag is False. Options: (1) Treat smart detections AS motion events (they all involve motion), (2) Add separate motion event polling, (3) Accept that smart detections are the primary event type and update camera config UI to clarify this. Note: This may be expected behavior - Protect prioritizes smart detection over raw motion. | Investigation | Done |
| FF-007 | 2025-12-08 | P3 | Feature | **Selective Backup/Restore Options** - Add granular selection for both backup and restore operations. Backup: Allow users to choose which components to include via checkboxes: (1) Database (events, cameras, alert rules), (2) Thumbnails/media files, (3) System settings, (4) AI provider configuration (API keys), (5) Protect controller config. Restore: Parse backup file to show available components, let user select which parts to restore (e.g., restore only settings without overwriting events). | User Request | Done |
| FF-008 | 2025-12-08 | P2 | DevOps | **Installation Script & Setup Wizard** - Create executable install script to automate application setup. Script should: (1) Check/install Python 3.11+, Node.js 18+, (2) Create virtual environment and install backend dependencies, (3) Install frontend dependencies and build, (4) Initialize database with migrations, (5) Generate encryption key, (6) Create systemd/launchd service files, (7) Configure reverse proxy (nginx) template. Manual setup items to document: (a) AI provider API keys (OpenAI, Gemini, Claude, Grok), (b) UniFi Protect controller credentials, (c) RTSP camera URLs and credentials, (d) SSL certificates for HTTPS, (e) Firewall/port forwarding for remote access. Include first-run setup wizard in UI for manual config items. | User Request | Done |
| IMP-002 | 2025-12-10 | P3 | UX | **Clean Up Event Card Duplicative Stats** - Event cards display redundant information that clutters the UI. Remove or consolidate duplicative stats including: (1) Confidence scoring shown in multiple places, (2) Identification/objects detected items that repeat, (3) Other redundant metadata. Streamline the event card layout to show essential info once in a clean, scannable format. | User Request | Done |
| FF-009 | 2025-12-10 | P2 | Feature | **Save & Display Multi-Frame Event Frames** - For events analyzed with multi-frame mode, persist the extracted frames so users can review them. Implementation: (1) Save key frames to filesystem alongside thumbnails during analysis, (2) Store frame paths/metadata in event record, (3) Add frame gallery UI when event card is expanded/selected, (4) Show frames in sequence with timestamps. This provides transparency into what the AI analyzed and helps users understand multi-frame descriptions. Note: Story P3-7.5 "Display Key Frames Gallery on Event Detail" in sprint-status covers similar scope. | User Request | Done |
| IMP-003 | 2025-12-10 | P3 | UX | **Remove Top Navigation on Desktop** - On desktop mode, the top navigation bar is redundant since the sidebar provides full navigation. Hide the top nav bar on larger screens (lg: breakpoint and above) to maximize content area and reduce visual clutter. Keep top nav visible only on mobile/tablet where sidebar is hidden. Use Tailwind responsive classes (lg:hidden) on the top nav component. | User Request | Done |
| FF-010 | 2025-12-10 | P2 | Feature | **Multi-Select Delete on Events Page** - Add ability to select multiple events and delete them in bulk. Implementation: (1) Add checkbox to each event card for selection, (2) Add "Select All" checkbox in header, (3) Show floating action bar when items selected with delete button and count, (4) Add confirmation dialog before bulk delete, (5) Create backend endpoint `DELETE /api/v1/events/bulk` accepting array of event IDs, (6) Handle associated thumbnails cleanup on delete. | User Request | Done |
| BUG-003 | 2025-12-10 | P3 | Bug | **System Name Not Applied Everywhere** - When changing the system name in settings, not all references update. Fix locations: (1) Top-left corner logo/title in sidebar, (2) Browser tab title (document.title), (3) Any other hardcoded "ArgusAI" references. Implementation: Store system_name in React context or fetch from settings API, use dynamic value in Sidebar component and layout.tsx metadata. Ensure name updates immediately after settings save without page refresh. | User Request | Done |
| FF-011 | 2025-12-14 | P3 | Feature | **Test Connection Before Save** - Backend enhancement to support temporary test endpoint (POST /cameras/test with body). This allows users to test RTSP connection before saving the camera, improving UX in the add camera flow. | F1.2 Code Review | Open |
| FF-012 | 2025-12-14 | P2 | Feature | **MQTT 5.0 Features** - Consider support for MQTT 5.0 features: message expiry, shared subscriptions. Evaluate if these improve reliability or reduce broker load for high-volume event publishing. | P4-2 Tech-Spec | Done |
| FF-013 | 2025-12-14 | P3 | Feature | **MQTT Birth/Will Messages** - Implement MQTT birth (online) and will (offline) messages for connection monitoring. Allows Home Assistant to track ArgusAI connection state and create automations based on availability. | P4-2 Tech-Spec | Done |
| FF-014 | 2025-12-14 | P2 | Feature | **ONVIF Camera Discovery** - Auto-detect cameras on local network using ONVIF protocol. Reduces manual configuration for users with compatible cameras. Deferred from Phase 1 MVP. | Epic F1 Tech-Spec | In Progress |
| FF-015 | 2025-12-14 | P4 | Feature | **Audio Capture from Cameras** - Support audio streams from RTSP cameras for future audio-based event detection (glass break, doorbell ring, etc.). Out of scope for video AI analysis but enables future audio AI features. | Epic F1 Tech-Spec | Open |
| FF-016 | 2025-12-14 | P3 | Feature | **Multiple Schedule Time Ranges** - Extend detection schedule to support multiple time ranges per day (e.g., 6-9am AND 6-11pm). Current implementation only supports single time range. User workaround: use two cameras or disable/enable manually. | Epic F2 Tech-Spec | Done |
| FF-017 | 2025-12-14 | P4 | Feature | **Export Motion Events to CSV** - Add CSV export functionality for motion events for external analysis. Include timestamp, camera, confidence, algorithm, bounding box coordinates. | Epic F2 Tech-Spec | Open |
| FF-018 | 2025-12-14 | P3 | Feature | **Detection Zone Presets** - Provide preset zone templates for common use cases: "Full Frame", "Top Half", "Bottom Half", "Center", "L-shape". Reduces need for manual polygon drawing. | Epic F2 Tech-Spec | Done |
| BUG-004 | 2025-12-14 | P2 | Bug | **Feedback Status Not Persisting on Page Refresh** - User feedback (thumbs up/down) on event cards does not persist after page refresh. The feedback is submitted to the backend but the UI state is not restored when the page reloads. Fix: (1) Check if backend stores feedback correctly, (2) Ensure event API returns feedback status, (3) Initialize FeedbackButtons component with saved feedback state from event data. Related: Story P4-5.1 FeedbackButtons component. | User Report | Open |

---

## GitHub Issues

All open backlog items have been created as GitHub issues for tracking:

| Backlog ID | GitHub Issue | Title |
|------------|--------------|-------|
| TD-002 | [#30](https://github.com/bbengt1/ArgusAI/issues/30) | FeedbackButtons Component Tests |
| TD-003 | [#31](https://github.com/bbengt1/ArgusAI/issues/31) | Real Camera Integration Testing |
| TD-004 | [#32](https://github.com/bbengt1/ArgusAI/issues/32) | Performance Baseline Documentation |
| TD-005 | [#33](https://github.com/bbengt1/ArgusAI/issues/33) | Update README with Frontend Setup |
| IMP-004 | [#34](https://github.com/bbengt1/ArgusAI/issues/34) | Accessibility Enhancements |
| IMP-005 | [#35](https://github.com/bbengt1/ArgusAI/issues/35) | Camera List Optimizations |
| FF-011 | [#36](https://github.com/bbengt1/ArgusAI/issues/36) | Test Connection Before Save |
| FF-012 | [#37](https://github.com/bbengt1/ArgusAI/issues/37) | MQTT 5.0 Features |
| FF-013 | [#38](https://github.com/bbengt1/ArgusAI/issues/38) | MQTT Birth/Will Messages |
| FF-014 | [#39](https://github.com/bbengt1/ArgusAI/issues/39) | ONVIF Camera Discovery |
| FF-015 | [#40](https://github.com/bbengt1/ArgusAI/issues/40) | Audio Capture from Cameras |
| FF-016 | [#41](https://github.com/bbengt1/ArgusAI/issues/41) | Multiple Schedule Time Ranges |
| FF-017 | [#42](https://github.com/bbengt1/ArgusAI/issues/42) | Export Motion Events to CSV |
| FF-018 | [#43](https://github.com/bbengt1/ArgusAI/issues/43) | Detection Zone Presets |
| BUG-004 | [#47](https://github.com/bbengt1/ArgusAI/issues/47) | Feedback Status Not Persisting on Page Refresh |

**GitHub Labels Created:**
- `technical-debt`, `testing`, `frontend`, `backend`, `performance`, `feature`, `integration`
- `P2-high`, `P3-medium`, `P4-low`

---

## Notes

- Items are added during code reviews, retrospectives, and development
- Priority should be reassessed during sprint planning
- Status: Open, In Progress, Done, Won't Fix
- When adding new open items, create corresponding GitHub issue and add to mapping table above
