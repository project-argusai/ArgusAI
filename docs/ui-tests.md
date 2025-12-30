# ArgusAI UI Test Suite

Automated E2E UI tests using Playwright MCP for comprehensive feature validation.

## Test Environment

- **URL**: `https://agent.argusai.cc` (Cloudflare Tunnel)
- **Browser**: Chromium via Playwright MCP
- **Auth**: Admin user credentials

## Test Execution

Tests can be executed by Claude Code using the Playwright MCP tools:
- `browser_navigate` - Navigate to pages
- `browser_snapshot` - Get accessibility tree for element refs
- `browser_click` - Click elements
- `browser_fill_form` - Fill form fields
- `browser_take_screenshot` - Capture visual evidence
- `browser_wait_for` - Wait for elements/text

---

## Test Suite: 15 Major Feature Tests

### Test 1: Authentication Flow

**Priority**: P0 - Critical
**Estimated Duration**: 2 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/login` | Login page displays with username/password fields |
| 2 | Submit empty form | Validation error appears |
| 3 | Enter invalid credentials, click Sign in | "Invalid username or password" error displays |
| 4 | Enter valid credentials, click Sign in | Redirect to Dashboard, user menu shows username |
| 5 | Click user menu → Logout | Redirect to login page, "Logged out successfully" toast |
| 6 | Try accessing `/` without auth | Redirect to `/login?returnUrl=%2F` |

**Verification Points**:
- [ ] Login form renders correctly
- [ ] Error messages display for invalid input
- [ ] Session token stored after login
- [ ] Protected routes redirect to login
- [ ] Logout clears session

---

### Test 2: Dashboard Overview

**Priority**: P0 - Critical
**Estimated Duration**: 2 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login and navigate to `/` | Dashboard loads with statistics cards |
| 2 | Verify statistics cards | Total Events, Active Cameras, Alert Rules, Today's Activity displayed |
| 3 | Check Live Cameras section | Camera preview cards with status indicators |
| 4 | Check Recent Activity section | Last 5 events with thumbnails and descriptions |
| 5 | Check Activity Summary | Daily summary with event counts, detection types |
| 6 | Click "View all events" link | Navigate to Events page |

**Verification Points**:
- [ ] All stat cards show numeric values
- [ ] Camera previews load (or show "Connecting" status)
- [ ] Recent events display with thumbnails
- [ ] Navigation links work correctly
- [ ] Real-time updates via WebSocket (if events occur)

---

### Test 3: Camera Management - CRUD Operations

**Priority**: P0 - Critical
**Estimated Duration**: 5 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/cameras` | Camera list displays with filter options |
| 2 | Click "Add Camera" button | Camera form modal opens |
| 3 | Select "RTSP Camera" type | RTSP-specific fields appear (URL, username, password) |
| 4 | Fill form with test data, submit | Camera created, appears in list |
| 5 | Click camera card to edit | Edit form opens with pre-filled data |
| 6 | Modify camera name, save | Changes saved, list updates |
| 7 | Click "Test Connection" button | Connection test runs, result displayed |
| 8 | Click delete icon, confirm | Camera removed from list |

**Test Data**:
```
Name: Test Camera
URL: rtsp://test.example.com:554/stream
Username: testuser
Password: testpass
```

**Verification Points**:
- [ ] Form validation prevents invalid submissions
- [ ] Camera appears in list after creation
- [ ] Edit pre-populates existing values
- [ ] Delete requires confirmation
- [ ] Connection test provides feedback

---

### Test 4: UniFi Protect Integration

**Priority**: P1 - High
**Estimated Duration**: 4 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/settings` → Protect tab | Protect settings panel displays |
| 2 | Click "Add Controller" | Controller form appears |
| 3 | Enter Protect controller details | Form accepts host, port, username, password |
| 4 | Click "Test Connection" | Connection test runs, shows success/failure |
| 5 | Save controller | Controller appears in list |
| 6 | Click "Discover Cameras" | Camera discovery dialog shows available cameras |
| 7 | Enable a camera for AI analysis | Camera added to monitored list |
| 8 | Set event filters (person, vehicle) | Filters saved for camera |

**Verification Points**:
- [ ] Controller connection test works
- [ ] Camera discovery returns Protect cameras
- [ ] Enable/disable toggles work
- [ ] Event type filters persist
- [ ] Controller status updates in real-time

---

### Test 5: Event Timeline and Filtering

**Priority**: P0 - Critical
**Estimated Duration**: 4 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/events` | Event timeline loads with recent events |
| 2 | Scroll down to trigger infinite scroll | More events load automatically |
| 3 | Click camera filter dropdown | Camera list appears |
| 4 | Select specific camera | Events filtered to selected camera |
| 5 | Click detection type filter | Type options appear (person, vehicle, etc.) |
| 6 | Select "Person" | Only person detection events shown |
| 7 | Set date range filter | Events filtered to date range |
| 8 | Click "Clear filters" | All events shown again |
| 9 | Use search box to search descriptions | Events matching search term displayed |

**Verification Points**:
- [ ] Infinite scroll loads more events
- [ ] Filters combine correctly (AND logic)
- [ ] Filter badges show active filters
- [ ] Clear filters resets all
- [ ] Search works on event descriptions
- [ ] Empty state shown when no matches

---

### Test 6: Event Detail and Actions

**Priority**: P1 - High
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/events` | Event list displays |
| 2 | Click on an event card | Event detail modal opens |
| 3 | View event information | Thumbnail, description, timestamp, camera, confidence shown |
| 4 | Click thumbnail to view frames | Frame gallery opens with all analyzed frames |
| 5 | Navigate through frames | Arrow keys or buttons navigate frames |
| 6 | Click thumbs up feedback | Feedback submitted, button highlighted |
| 7 | Click "Re-analyze" button | Re-analysis dialog opens |
| 8 | Close modal | Modal closes, return to event list |

**Verification Points**:
- [ ] Event detail shows all metadata
- [ ] Frame gallery displays extracted frames
- [ ] Feedback buttons toggle correctly
- [ ] AI provider badge shows which AI analyzed
- [ ] Confidence score displays as percentage

---

### Test 7: Bulk Event Operations

**Priority**: P1 - High
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/events` | Event list displays |
| 2 | Click checkbox on first event | Event selected, action bar appears |
| 3 | Click "Select All" | All visible events selected |
| 4 | Verify selection count | Count shown in action bar matches |
| 5 | Click "Delete Selected" | Confirmation dialog appears |
| 6 | Cancel deletion | Dialog closes, events remain |
| 7 | Click "Export CSV" | CSV file downloads with selected events |
| 8 | Deselect all | Action bar hides |

**Verification Points**:
- [ ] Checkbox selection works
- [ ] Select all selects current page
- [ ] Action bar shows correct count
- [ ] Delete confirmation prevents accidental deletion
- [ ] CSV export includes correct fields

---

### Test 8: Entity Management

**Priority**: P1 - High
**Estimated Duration**: 4 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/entities` | Entity list displays (people, vehicles) |
| 2 | Filter by entity type "Person" | Only person entities shown |
| 3 | Click on an entity card | Entity detail modal opens |
| 4 | View related events | Events associated with entity displayed |
| 5 | Click "Edit" button | Edit form opens |
| 6 | Change entity name, save | Name updated in list |
| 7 | Toggle "VIP" status | VIP badge appears on entity |
| 8 | Click "Add to Blocklist" | Entity marked as blocked |
| 9 | Delete entity, confirm | Entity removed from list |

**Verification Points**:
- [ ] Entity list shows thumbnails
- [ ] Type filter works correctly
- [ ] Related events load in detail view
- [ ] VIP/Blocked status persists
- [ ] Delete removes entity and relationships

---

### Test 9: Alert Rules Configuration

**Priority**: P0 - Critical
**Estimated Duration**: 5 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/rules` | Alert rules list displays |
| 2 | Click "Create Rule" | Rule creation form opens |
| 3 | Enter rule name | Name field accepts input |
| 4 | Select detection type "Person" | Type selector updates |
| 5 | Select specific camera | Camera dropdown works |
| 6 | Set time schedule (weekdays, 9am-5pm) | Schedule picker configured |
| 7 | Set confidence threshold (80%) | Slider/input updates |
| 8 | Add webhook action | Webhook URL field appears |
| 9 | Enter webhook URL | URL validated |
| 10 | Save rule | Rule appears in list as enabled |
| 11 | Toggle rule off | Rule disabled, visual indicator changes |
| 12 | Delete rule, confirm | Rule removed from list |

**Verification Points**:
- [ ] All rule condition types available
- [ ] Schedule picker works correctly
- [ ] Webhook URL validated
- [ ] Enable/disable toggle persists
- [ ] Rule triggers when conditions met (manual verify)

---

### Test 10: Activity Summaries

**Priority**: P1 - High
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/summaries` or Dashboard | Summary section visible |
| 2 | View today's summary | AI-generated summary text displayed |
| 3 | Click "Generate Summary" button | Summary generation dialog opens |
| 4 | Select custom date range | Date picker allows selection |
| 5 | Choose summary style | Style options available |
| 6 | Click "Generate" | Summary generation starts, progress shown |
| 7 | View generated summary | New summary appears with event stats |
| 8 | Click thumbs up/down feedback | Feedback recorded |
| 9 | Click "View Full Summary" link | Expanded summary view opens |

**Verification Points**:
- [ ] Daily summaries auto-generate
- [ ] Custom date range works
- [ ] Summary includes event counts
- [ ] Entity mentions highlighted
- [ ] Feedback buttons work

---

### Test 11: Settings - AI Configuration

**Priority**: P0 - Critical
**Estimated Duration**: 4 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/settings` → AI Models tab | AI settings panel displays |
| 2 | View configured providers | List of AI providers with status |
| 3 | Click "Add Provider" | Provider selection appears |
| 4 | Select OpenAI, enter API key | Key field accepts input (masked) |
| 5 | Click "Test Connection" | Provider connection tested |
| 6 | Save provider | Provider appears in list |
| 7 | Drag to reorder providers | Fallback order updated |
| 8 | Edit description prompt | Prompt textarea editable |
| 9 | Click "AI Assist" on prompt | AI suggests improvements |
| 10 | Save settings | Settings persisted |

**Verification Points**:
- [ ] API keys masked in UI
- [ ] Connection test provides feedback
- [ ] Provider order determines fallback
- [ ] Custom prompts saved correctly
- [ ] AI assist provides suggestions

---

### Test 12: Settings - Data Management

**Priority**: P1 - High
**Estimated Duration**: 4 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/settings` → Data tab | Data settings panel displays |
| 2 | View storage statistics | Disk usage, event count displayed |
| 3 | Set retention policy (30 days) | Retention slider/input works |
| 4 | Click "Backup Data" | Backup creation starts |
| 5 | Download backup file | Backup file downloads |
| 6 | Click "Reprocess Entities" | Reprocessing dialog opens |
| 7 | Select options, start reprocessing | Progress indicator shows |
| 8 | Click "Delete All Data" | Confirmation dialog (requires typing) |
| 9 | Cancel deletion | Dialog closes safely |

**Verification Points**:
- [ ] Storage stats update after operations
- [ ] Backup file is valid JSON/ZIP
- [ ] Reprocessing shows progress
- [ ] Delete requires explicit confirmation
- [ ] Retention policy affects cleanup

---

### Test 13: MQTT/Home Assistant Integration

**Priority**: P2 - Standard
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/settings` → Integrations tab | Integrations panel displays |
| 2 | Enable MQTT toggle | MQTT configuration form appears |
| 3 | Enter broker details | Host, port, username, password fields |
| 4 | Click "Test Connection" | MQTT connection tested |
| 5 | Enable auto-discovery | Toggle activates |
| 6 | Click "Publish Discovery" | MQTT discovery messages sent |
| 7 | View connection status | Connected/Disconnected indicator |
| 8 | Disable MQTT toggle | Form fields hidden |

**Verification Points**:
- [ ] MQTT form validates inputs
- [ ] Connection test provides clear feedback
- [ ] Auto-discovery sends proper payloads
- [ ] Status indicator reflects actual state
- [ ] Disable clears connection

---

### Test 14: Push Notifications Setup

**Priority**: P1 - High
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/settings` → Notifications tab | Notifications panel displays |
| 2 | Click "Enable Push Notifications" | Browser permission prompt appears |
| 3 | Grant notification permission | Subscription created |
| 4 | View subscription status | "Subscribed" status shown |
| 5 | Click "Test Notification" | Test push notification received |
| 6 | View Device Manager | List of paired devices |
| 7 | Click "Pair New Device" | QR code/pairing code displayed |
| 8 | Remove a device | Device removed from list |

**Verification Points**:
- [ ] Permission request handled correctly
- [ ] Subscription persists across sessions
- [ ] Test notification actually delivers
- [ ] Device pairing flow works
- [ ] Device removal revokes access

---

### Test 15: Responsive Design & Mobile Navigation

**Priority**: P2 - Standard
**Estimated Duration**: 3 min

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Resize browser to mobile (375px width) | Mobile layout activates |
| 2 | Verify sidebar hidden | Sidebar not visible on mobile |
| 3 | Click hamburger menu | Mobile navigation drawer opens |
| 4 | Navigate to Events via menu | Page loads, menu closes |
| 5 | Verify touch targets | Buttons/links at least 44px |
| 6 | Test event card interaction | Cards expand/navigate correctly |
| 7 | Resize to tablet (768px) | Tablet layout shows |
| 8 | Resize to desktop (1280px) | Full desktop layout with sidebar |

**Verification Points**:
- [ ] Breakpoints trigger correctly
- [ ] Mobile nav accessible via hamburger
- [ ] All features usable on mobile
- [ ] Touch targets appropriately sized
- [ ] No horizontal scroll on mobile

---

## Test Execution Checklist

Before running tests:
- [ ] Verify `https://agent.argusai.cc` is accessible
- [ ] Ensure test admin account exists
- [ ] Clear previous test data if needed
- [ ] Verify at least one camera is configured
- [ ] Check that AI provider is configured

After running tests:
- [ ] Review screenshots for visual regressions
- [ ] Check console for JavaScript errors
- [ ] Verify no data corruption occurred
- [ ] Reset test password if changed
- [ ] Document any failures with details

---

## Test Data Requirements

| Test | Required Data |
|------|---------------|
| Test 1 | Admin credentials |
| Test 2 | At least 1 camera, 5+ events |
| Test 3 | No prerequisites |
| Test 4 | UniFi Protect controller access |
| Test 5 | 20+ events across multiple cameras |
| Test 6 | Events with multi-frame analysis |
| Test 7 | 10+ events for bulk operations |
| Test 8 | 5+ recognized entities |
| Test 9 | Working webhook endpoint |
| Test 10 | 24+ hours of event data |
| Test 11 | AI provider API keys |
| Test 12 | Events/entities to manage |
| Test 13 | MQTT broker access |
| Test 14 | HTTPS enabled |
| Test 15 | No prerequisites |

---

## Running a Test

To execute a test, instruct Claude Code:

```
Run UI Test #[number] from docs/ui-tests.md
```

Example:
```
Run UI Test #1 (Authentication Flow) from docs/ui-tests.md
```

Claude will:
1. Navigate to the required page
2. Execute each step using Playwright MCP tools
3. Capture screenshots at key points
4. Verify expected results
5. Report pass/fail status
