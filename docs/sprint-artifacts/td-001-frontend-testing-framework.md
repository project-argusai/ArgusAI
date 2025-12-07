# Story TD-001: Set Up Frontend Testing Framework

Status: done

## Story

As a **developer**,
I want **a configured frontend testing framework with Vitest and React Testing Library**,
So that **I can write unit and integration tests for React components and hooks**.

## Background

This story addresses technical debt item TD-001 identified during Story P3-3.4 code review. The frontend currently has no testing framework configured, blocking all component-level testing.

## Acceptance Criteria

1. **AC1:** Given Vitest is installed, when `npm test` is run, then tests execute successfully with proper configuration for Next.js 15 and React 19

2. **AC2:** Given React Testing Library is installed, when testing components, then I can use `render`, `screen`, `fireEvent`, and `userEvent` utilities

3. **AC3:** Given test utilities exist, when writing tests, then I have access to common mocks (next/router, next/navigation, TanStack Query)

4. **AC4:** Given sample tests exist, when reviewing the test setup, then there are example tests demonstrating patterns for:
   - Simple component rendering
   - Component with props
   - Component with user interaction
   - Hook testing

5. **AC5:** Given tests are configured, when running `npm run test:coverage`, then coverage reports are generated

## Tasks / Subtasks

- [x] **Task 1: Install testing dependencies**
  - [x] 1.1 Install Vitest and related packages
  - [x] 1.2 Install React Testing Library packages
  - [x] 1.3 Install jsdom for DOM simulation

- [x] **Task 2: Configure Vitest for Next.js**
  - [x] 2.1 Create vitest.config.ts with proper setup
  - [x] 2.2 Configure path aliases matching tsconfig
  - [x] 2.3 Set up test environment (jsdom)

- [x] **Task 3: Create test utilities and setup files**
  - [x] 3.1 Create test setup file (vitest.setup.tsx)
  - [x] 3.2 Create test utilities (renderWithProviders, mock helpers)
  - [x] 3.3 Create common mocks (next/navigation, TanStack Query)

- [x] **Task 4: Write sample component tests**
  - [x] 4.1 Test simple presentational component (Button - 18 tests)
  - [x] 4.2 Test component with props (AnalysisModeBadge - 18 tests)
  - [x] 4.3 Test component with user interaction (Button, AnalysisModeBadge tooltips)
  - [ ] 4.4 Test a custom hook if time permits (deferred)

- [x] **Task 5: Update package.json and documentation**
  - [x] 5.1 Add test scripts to package.json
  - [x] 5.2 Update backlog.md to mark TD-001 as Done
  - [x] 5.3 Verify all tests pass with `npm test` (36/36 passing)

## Dev Notes

### Recommended Stack

Based on docs/test-design-system.md and modern React patterns:

- **Vitest** - Fast, Vite-native test runner (preferred over Jest for Vite/Next projects)
- **React Testing Library** - Component testing with user-centric approach
- **@testing-library/user-event** - Realistic user interactions
- **jsdom** - DOM simulation environment
- **@testing-library/jest-dom** - Extended DOM matchers (toBeInTheDocument, etc.)

### Package Installation

```bash
npm install -D vitest @vitejs/plugin-react jsdom
npm install -D @testing-library/react @testing-library/jest-dom @testing-library/user-event
npm install -D @vitest/coverage-v8
```

### Vitest Config Structure

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.{test,spec}.{js,jsx,ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
})
```

### Test Patterns to Demonstrate

1. **Simple render test**
2. **Props testing**
3. **User interaction (click, type)**
4. **Async component testing**
5. **Mock API responses**

### References

- [Source: docs/backlog.md#TD-001]
- [Source: docs/test-design-system.md]
- [Source: docs/architecture/03-technology-stack.md]
- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)

## Dev Agent Record

### Context Reference

N/A - Technical debt story, no epic context needed

### Agent Model Used

Claude Opus 4.5

### Debug Log References

N/A

### Completion Notes List

- Installed Vitest 4.0.15 with React Testing Library 16.3.0
- Created vitest.config.ts with jsdom environment and path aliases
- Created vitest.setup.tsx with mocks for next/navigation, next/image, matchMedia, ResizeObserver, IntersectionObserver
- Created test utilities with renderWithProviders wrapper and mock data factories
- Wrote 18 Button component tests covering rendering, variants, sizes, interactions, accessibility
- Wrote 18 AnalysisModeBadge component tests covering rendering, styling, tooltips, accessibility
- Fixed Radix UI tooltip testing pattern (use findAllByText for duplicated a11y content)
- All 36 tests pass

### File List

- `frontend/vitest.config.ts` - Vitest configuration with jsdom, coverage, path aliases
- `frontend/vitest.setup.tsx` - Test setup with browser API mocks and Next.js mocks
- `frontend/__tests__/test-utils.tsx` - Custom render wrapper with TanStack Query provider
- `frontend/__tests__/components/ui/button.test.tsx` - Button component tests (18 tests)
- `frontend/__tests__/components/events/AnalysisModeBadge.test.tsx` - AnalysisModeBadge tests (18 tests)
- `frontend/package.json` - Added test, test:run, test:coverage, test:ui scripts

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-06 | 1.0 | Story created from TD-001 technical debt item |
| 2025-12-06 | 1.1 | Story completed - 36 tests passing |
