# Epic Technical Specification: Documentation & UX Polish

Date: 2025-12-22
Author: Brent
Epic ID: P9-6
Status: Draft

---

## Overview

Epic P9-6 focuses on updating documentation to reflect the current state of ArgusAI and polishing UI rough edges. This epic improves the onboarding experience for new users, establishes a public documentation site via GitHub Pages, and addresses accumulated UX issues identified in the backlog.

The work spans README updates, GitHub Pages setup with a static site generator, CSS/layout fixes, accessibility improvements, and performance optimizations for the camera list.

## Objectives and Scope

**In Scope:**
- Comprehensive README.md refactor to reflect Phases 1-8
- GitHub Pages infrastructure with static site generator
- Landing page with project overview
- Documentation section with searchable content
- Fix events page button positioning
- Hide MQTT form fields when integration is disabled
- Add skip-to-content accessibility link
- Camera list performance optimizations with React.memo
- Test connection endpoint for camera validation

**Out of Scope:**
- Video tutorials or screencasts
- Interactive demos
- Internationalization (i18n)
- Dark mode theme (separate backlog item)
- New feature documentation (covered in respective epics)

## System Architecture Alignment

This epic primarily affects frontend and documentation components:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| README | `README.md` | Full content refactor |
| GitHub Pages | `docs-site/` | New directory |
| GH Actions | `.github/workflows/deploy-docs.yml` | New workflow |
| Events Page | `frontend/components/events/` | CSS fixes |
| Settings Page | `frontend/components/settings/` | Conditional MQTT form |
| Layout | `frontend/components/layout/` | Skip link, a11y |
| Camera List | `frontend/components/cameras/` | Performance |
| Backend API | `backend/app/api/v1/cameras.py` | Test endpoint |

### Documentation Site Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                     GitHub Pages Infrastructure                     │
└────────────────────────────────────────────────────────────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
    ┌──────▼──────┐          ┌─────▼──────┐          ┌──────▼──────┐
    │   Source    │          │   Build    │          │   Deploy    │
    │  docs-site/ │─────────►│  Docusaurus│─────────►│  gh-pages   │
    │             │          │            │          │   branch    │
    └─────────────┘          └────────────┘          └─────────────┘
           │                        │                        │
           │                        │                        │
    ┌──────▼──────┐          ┌─────▼──────┐          ┌──────▼──────┐
    │  /docs/     │          │  Static    │          │   CDN       │
    │  Markdown   │          │  HTML/JS   │          │   (GitHub)  │
    └─────────────┘          └────────────┘          └─────────────┘
```

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| README.md | Project documentation | Markdown content | Rendered docs |
| Docusaurus | Static site generation | Markdown, config | HTML/JS site |
| GH Actions | Auto deployment | Push to main | Deployed site |
| SkipLink Component | Accessibility | Focus event | Jump to content |
| CameraCard | Camera display | Camera data | Memoized render |
| Test Connection API | Camera validation | Camera config | Success/failure |

### Data Models and Contracts

**Test Connection Request:**
```typescript
interface TestConnectionRequest {
  rtsp_url: string;
  username?: string;
  password?: string;
}
```

**Test Connection Response:**
```typescript
interface TestConnectionResponse {
  success: boolean;
  message: string;
  thumbnail?: string;  // Base64 encoded preview image
  resolution?: {
    width: number;
    height: number;
  };
  codec?: string;
  fps?: number;
}
```

**Docusaurus Configuration:**
```javascript
// docusaurus.config.js
module.exports = {
  title: 'ArgusAI',
  tagline: 'AI-Powered Home Security',
  url: 'https://bbengt1.github.io',
  baseUrl: '/argusai/',
  organizationName: 'bbengt1',
  projectName: 'argusai',
  themeConfig: {
    navbar: {
      title: 'ArgusAI',
      items: [
        { to: 'docs/getting-started', label: 'Docs' },
        { to: 'docs/api', label: 'API' },
        { href: 'https://github.com/bbengt1/argusai', label: 'GitHub' }
      ]
    }
  }
};
```

### APIs and Interfaces

**New API Endpoint:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/cameras/test` | Test camera connection without saving |

**Test Connection API:**
```python
@router.post("/test", response_model=TestConnectionResponse)
async def test_camera_connection(
    request: TestConnectionRequest,
    db: Session = Depends(get_db)
) -> TestConnectionResponse:
    """
    Test camera connection without persisting.
    Returns success status and preview thumbnail.
    """
    try:
        # Attempt to connect and grab single frame
        frame = await camera_service.test_connection(
            rtsp_url=request.rtsp_url,
            username=request.username,
            password=request.password
        )

        # Encode frame as base64 thumbnail
        thumbnail = encode_thumbnail(frame)

        return TestConnectionResponse(
            success=True,
            message="Connection successful",
            thumbnail=thumbnail,
            resolution={"width": frame.width, "height": frame.height}
        )
    except ConnectionError as e:
        return TestConnectionResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )
```

### Workflows and Sequencing

**GitHub Pages Deployment Flow:**
```
1. Developer pushes to main branch
2. GitHub Actions workflow triggers
3. Checkout code
4. Install Docusaurus dependencies
5. Build static site
6. Deploy to gh-pages branch
7. GitHub Pages serves site
```

**Test Connection UI Flow:**
```
1. User enters camera details
2. User clicks "Test Connection"
3. Loading spinner shows
4. API validates connection
5. On success: Show thumbnail preview
6. On failure: Show error message
7. User can then Save (if successful) or retry
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| GitHub Pages load time | <2 seconds | Lighthouse |
| Camera list render | <100ms for 20 cameras | React profiler |
| Test connection timeout | 10 seconds max | API timeout |
| Documentation search | <200ms | Client-side |

### Security

- No sensitive data in documentation (API keys, credentials)
- Test connection endpoint requires authentication
- Camera passwords not logged during test
- GitHub Pages served over HTTPS

### Reliability/Availability

- GitHub Pages 99.9% uptime (GitHub SLA)
- Test connection handles network timeouts gracefully
- Documentation builds must pass before deployment
- Fallback messaging for missing thumbnails

### Observability

- GitHub Actions build logs
- Failed deployment notifications
- Test connection attempt logging
- Page view analytics (optional, privacy-respecting)

---

## Dependencies and Integrations

### Frontend Dependencies (package.json)

```json
{
  "devDependencies": {
    "@docusaurus/core": "^3.0.0",
    "@docusaurus/preset-classic": "^3.0.0",
    "react-window": "^1.8.10"
  }
}
```

### Documentation Site Dependencies

```json
{
  "name": "argusai-docs",
  "dependencies": {
    "@docusaurus/core": "^3.0.0",
    "@docusaurus/preset-classic": "^3.0.0",
    "@docusaurus/theme-search-algolia": "^3.0.0"
  }
}
```

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy-docs.yml
name: Deploy Documentation

on:
  push:
    branches: [main]
    paths:
      - 'docs-site/**'
      - 'docs/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - name: Install and Build
        working-directory: docs-site
        run: |
          npm install
          npm run build
      - name: Deploy
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs-site/build
```

---

## Acceptance Criteria (Authoritative)

### P9-6.1: Refactor README.md

**AC-6.1.1:** Given I view the README, when I read the feature list, then it includes all features through Phase 8
**AC-6.1.2:** Given I view the README, when I read the feature list, then it includes: UniFi Protect, multi-frame analysis, entities, summaries, push notifications, MQTT, HomeKit
**AC-6.1.3:** Given I want to install ArgusAI, when I follow the installation section, then instructions match the current install script
**AC-6.1.4:** Given I want to install ArgusAI, when I check prerequisites, then Python 3.11+ and Node 18+ are listed
**AC-6.1.5:** Given I view the README, when I look for troubleshooting, then common issues are documented

### P9-6.2: Set Up GitHub Pages Infrastructure

**AC-6.2.1:** Given GitHub Pages is enabled, when content is pushed to main, then the site builds automatically
**AC-6.2.2:** Given the build completes, when I check gh-pages branch, then static files are deployed
**AC-6.2.3:** Given Docusaurus is configured, when I run npm run build, then site builds without errors
**AC-6.2.4:** Given the site is deployed, when I access the URL, then the site loads correctly

### P9-6.3: Build GitHub Pages Landing Page

**AC-6.3.1:** Given I visit the GitHub Pages URL, when the landing page loads, then I see project name and tagline
**AC-6.3.2:** Given I visit the GitHub Pages URL, when the landing page loads, then I see a hero image or screenshot
**AC-6.3.3:** Given I visit the GitHub Pages URL, when I view features, then I see 3-5 key feature bullet points
**AC-6.3.4:** Given I visit the GitHub Pages URL, when I want to start, then I see a "Get Started" button
**AC-6.3.5:** Given I'm on mobile, when I view the landing page, then it's responsive and readable

### P9-6.4: Create GitHub Pages Documentation Section

**AC-6.4.1:** Given I navigate to documentation, when I view the sidebar, then I see organized categories
**AC-6.4.2:** Given I view documentation categories, when I check structure, then I see: Getting Started, Installation, Configuration, Features, API Reference, Troubleshooting
**AC-6.4.3:** Given I want to find something, when I use search, then relevant docs are shown
**AC-6.4.4:** Given I view documentation, when I see code examples, then syntax highlighting is applied

### P9-6.5: Fix Events Page Button Positioning

**AC-6.5.1:** Given I view the Events page on desktop, when I look at action buttons, then they don't overlap with header
**AC-6.5.2:** Given I view the Events page, when I look at action buttons, then there's clear visual separation from navigation
**AC-6.5.3:** Given I view the Events page on mobile, when I look at action buttons, then they're positioned appropriately
**AC-6.5.4:** Given I view the Events page on mobile, when I tap action buttons, then touch targets are at least 44x44px

### P9-6.6: Hide MQTT Form When Disabled

**AC-6.6.1:** Given MQTT integration is disabled, when I view Settings > Integrations, then only the enable toggle is visible
**AC-6.6.2:** Given MQTT is disabled, when I view Settings > Integrations, then configuration fields are hidden
**AC-6.6.3:** Given I enable MQTT integration, when the toggle turns on, then the configuration form appears with animation
**AC-6.6.4:** Given I toggle MQTT off, when form hides, then form values are preserved (not reset)

### P9-6.7: Add Skip to Content Link

**AC-6.7.1:** Given I navigate to any page using keyboard, when I press Tab first, then "Skip to content" link is focused
**AC-6.7.2:** Given skip link is focused, when I view the page, then the link is visible and styled
**AC-6.7.3:** Given I activate the skip link, when focus moves, then it jumps to main content area
**AC-6.7.4:** Given I've skipped to content, when I interact, then I can immediately use page content

### P9-6.8: Add Camera List Optimizations and Test Connection

**AC-6.8.1:** Given I have 10+ cameras configured, when I view Cameras page, then the list renders without lag
**AC-6.8.2:** Given I scroll through cameras, when viewing list, then scrolling is smooth (60fps target)
**AC-6.8.3:** Given I'm adding a new camera, when I enter URL, then I see a "Test Connection" button
**AC-6.8.4:** Given I test a valid camera, when test succeeds, then I see "Connection successful" with thumbnail
**AC-6.8.5:** Given I test an invalid camera, when test fails, then I see clear error message
**AC-6.8.6:** Given test connection succeeds, when I proceed, then I can save the camera

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-6.1.1-5 | README | README.md | Content review |
| AC-6.2.1-4 | GH Pages Setup | deploy-docs.yml, docusaurus.config.js | Build and deploy |
| AC-6.3.1-5 | Landing Page | docs-site/src/pages/index.js | Visual review, responsive |
| AC-6.4.1-4 | Documentation | docs-site/docs/*.md | Navigate, search |
| AC-6.5.1-4 | Events Page | EventsPage.tsx | Visual inspection, touch |
| AC-6.6.1-4 | MQTT Form | MQTTSettings.tsx | Toggle interaction |
| AC-6.7.1-4 | Skip Link | Layout.tsx, SkipLink.tsx | Keyboard navigation |
| AC-6.8.1-6 | Camera List | CameraList.tsx, cameras.py | Performance test, API test |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Documentation becomes outdated | Medium | Medium | Link to source files, automate where possible |
| GitHub Pages quota exceeded | Low | Low | Monitor usage, optimize assets |
| Camera test timeout issues | Medium | Low | Configurable timeout, clear error messages |
| Accessibility regressions | Low | Medium | Automated a11y testing in CI |

### Assumptions

- GitHub Pages is available for the repository
- Docusaurus is suitable for documentation needs
- Camera test connection can complete in <10 seconds
- Users have modern browsers (Chrome, Firefox, Safari, Edge)

### Open Questions

- **Q1:** Should we use Docusaurus or a simpler solution like Jekyll?
  - **A:** Docusaurus recommended for React familiarity and search features

- **Q2:** Should camera test connection require authentication?
  - **A:** Yes, to prevent unauthorized testing of arbitrary URLs

- **Q3:** Should we add analytics to GitHub Pages?
  - **A:** Optional, use privacy-respecting solution if added

- **Q4:** Should skip link be visible at all times or only on focus?
  - **A:** Only on focus (standard accessibility pattern)

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | React components | Vitest, RTL | SkipLink, CameraCard memo |
| Integration | API endpoints | pytest | Test connection |
| E2E | Full workflows | Manual | Camera add flow |
| Visual | Layout/styling | Browser inspection | Button positioning |
| A11y | Accessibility | axe-core, keyboard | Skip link, ARIA |

### Test Cases by Story

**P9-6.1 (README):**
- Manual: Verify feature list completeness
- Manual: Follow installation steps
- Manual: Check all links work

**P9-6.2 (GH Pages Setup):**
- Test: GH Actions workflow runs on push
- Test: Build succeeds without errors
- Test: Site is accessible at URL

**P9-6.3 (Landing Page):**
- Visual: Hero section renders correctly
- Visual: Mobile responsive design
- Manual: "Get Started" links correctly

**P9-6.4 (Documentation):**
- Test: Search returns relevant results
- Test: All pages render without errors
- Visual: Code blocks have syntax highlighting

**P9-6.5 (Events Page Buttons):**
- Visual: Buttons don't overlap on desktop (1920px, 1366px, 1024px)
- Visual: Buttons render correctly on mobile (375px, 414px)
- Test: Touch targets are 44px minimum

**P9-6.6 (MQTT Form):**
- Test: Form hidden when toggle is off
- Test: Form shows with animation when toggled on
- Test: Form values persist through toggle cycle

**P9-6.7 (Skip Link):**
- A11y: Tab focuses skip link first
- A11y: Enter key activates skip link
- A11y: Focus moves to main content

**P9-6.8 (Camera List/Test):**
- Performance: Render 20 cameras in <100ms
- Test: React.memo prevents unnecessary renders
- Integration: Test connection API returns thumbnail
- Integration: Test connection handles timeout

### Edge Cases

- README with unusual markdown formatting
- Very long camera list (50+ cameras)
- Camera test connection during network timeout
- Skip link with very short main content
- MQTT form toggle during form validation
- GitHub Pages build failure

---

## Implementation Details

### Skip Link Component

```tsx
// frontend/components/layout/SkipLink.tsx
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4
                 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground
                 focus:rounded-md focus:ring-2 focus:ring-offset-2"
    >
      Skip to content
    </a>
  );
}
```

```tsx
// frontend/components/layout/Layout.tsx
import { SkipLink } from './SkipLink';

export function Layout({ children }) {
  return (
    <>
      <SkipLink />
      <Header />
      <main id="main-content" tabIndex={-1}>
        {children}
      </main>
      <Footer />
    </>
  );
}
```

### Camera Card Memoization

```tsx
// frontend/components/cameras/CameraCard.tsx
import { memo } from 'react';

interface CameraCardProps {
  camera: Camera;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

export const CameraCard = memo(function CameraCard({
  camera,
  onEdit,
  onDelete
}: CameraCardProps) {
  // Component implementation
  return (
    <Card>
      <CardHeader>
        <CardTitle>{camera.name}</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Camera preview and details */}
      </CardContent>
      <CardFooter>
        <Button onClick={() => onEdit(camera.id)}>Edit</Button>
        <Button onClick={() => onDelete(camera.id)}>Delete</Button>
      </CardFooter>
    </Card>
  );
});
```

### MQTT Form Conditional Rendering

```tsx
// frontend/components/settings/MQTTSettings.tsx
export function MQTTSettings() {
  const [enabled, setEnabled] = useState(false);
  const [formValues, setFormValues] = useState<MQTTConfig | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>MQTT Integration</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center space-x-2">
          <Switch
            id="mqtt-enabled"
            checked={enabled}
            onCheckedChange={setEnabled}
          />
          <Label htmlFor="mqtt-enabled">Enable MQTT</Label>
        </div>

        {/* Animated form section */}
        <div
          className={cn(
            "overflow-hidden transition-all duration-300",
            enabled ? "max-h-96 opacity-100 mt-4" : "max-h-0 opacity-0"
          )}
        >
          <div className="space-y-4">
            <Input
              label="MQTT Host"
              value={formValues?.host ?? ''}
              onChange={(e) => setFormValues(prev => ({ ...prev, host: e.target.value }))}
            />
            <Input
              label="MQTT Port"
              type="number"
              value={formValues?.port ?? 1883}
              onChange={(e) => setFormValues(prev => ({ ...prev, port: parseInt(e.target.value) }))}
            />
            {/* Additional fields */}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

### Test Connection Button

```tsx
// frontend/components/cameras/CameraForm.tsx
export function CameraForm() {
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      const response = await api.post('/cameras/test', {
        rtsp_url: formValues.rtsp_url,
        username: formValues.username,
        password: formValues.password
      });
      setTestResult(response.data);
    } catch (error) {
      setTestResult({
        success: false,
        message: error.message || 'Connection test failed'
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <form>
      {/* Form fields */}

      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={handleTestConnection}
          disabled={isTesting}
        >
          {isTesting ? <Spinner /> : 'Test Connection'}
        </Button>
        <Button type="submit" disabled={!testResult?.success}>
          Save Camera
        </Button>
      </div>

      {testResult && (
        <Alert variant={testResult.success ? 'success' : 'error'}>
          {testResult.message}
          {testResult.thumbnail && (
            <img
              src={`data:image/jpeg;base64,${testResult.thumbnail}`}
              alt="Camera preview"
              className="mt-2 rounded"
            />
          )}
        </Alert>
      )}
    </form>
  );
}
```

### Events Page Button Fix

```css
/* Fix button positioning in events page header */
.events-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;  /* Add margin to prevent overlap */
  flex-wrap: wrap;
  gap: 0.5rem;
}

.events-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;  /* Add top margin on mobile */
}

@media (min-width: 768px) {
  .events-actions {
    margin-top: 0;
  }
}
```

### README Structure

```markdown
# ArgusAI

AI-Powered Home Security System

[Features](#features) | [Installation](#installation) | [Documentation](https://bbengt1.github.io/argusai/)

## Features

- **UniFi Protect Integration** - Native support for UniFi cameras
- **Multi-Frame AI Analysis** - Intelligent frame selection and analysis
- **Entity Recognition** - Track people, vehicles, and packages
- **Daily Summaries** - AI-generated activity digests
- **Push Notifications** - Real-time alerts with thumbnails
- **Home Assistant** - MQTT integration with auto-discovery
- **HomeKit** - Apple Home app integration

## Quick Start

```bash
# Clone and install
git clone https://github.com/bbengt1/argusai.git
cd argusai
./scripts/install.sh
```

## Requirements

- Python 3.11+
- Node.js 18+
- SQLite or PostgreSQL
- UniFi Protect controller (optional)

## Documentation

Full documentation available at [bbengt1.github.io/argusai](https://bbengt1.github.io/argusai/)

- [Installation Guide](docs/installation.md)
- [Configuration](docs/configuration.md)
- [API Reference](docs/api.md)
- [Troubleshooting](docs/troubleshooting.md)

## Development

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload

# Frontend
cd frontend && npm run dev
```

## License

MIT License - see [LICENSE](LICENSE)
```

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
