# Story BUG-CI: Fix APScheduler Logging Error During Test Shutdown

Status: done

## Story

As a developer,
I want the test suite to run without logging errors during scheduler shutdown,
so that CI logs are clean and I can easily identify real issues.

## Acceptance Criteria

1. Running `pytest tests/` completes without "ValueError: I/O operation on closed file" errors in output
2. APScheduler shutdown in ClipService doesn't log errors when logging streams are already closed
3. DigestScheduler shutdown doesn't log errors when logging streams are already closed
4. The scheduler still shuts down properly even when logging fails
5. No behavioral changes to normal (non-test) operation

## Tasks / Subtasks

- [x] Task 1: Investigate root cause (AC: #1, #2)
  - [x] Identify which service causes the logging error
  - [x] Understand why pytest closes logging streams before atexit handlers run

- [x] Task 2: Fix ClipService._stop_scheduler() (AC: #2, #4)
  - [x] Suppress APScheduler's internal logger during shutdown (set level to CRITICAL+1)
  - [x] Suppress ClipService's own logger during shutdown (set level to CRITICAL+1)
  - [x] Wrap entire shutdown in try-except to handle any remaining errors silently

- [x] Task 3: Review DigestScheduler.stop() for similar issues (AC: #3)
  - [x] Reviewed - DigestScheduler uses stop() which doesn't use atexit, so not affected
  - [x] The issue only affects atexit handlers which run after pytest closes streams

- [x] Task 4: Test the fix (AC: #1, #5)
  - [x] Run full test suite - 3151 tests pass, no logging errors
  - [x] Normal operation unaffected - logging only suppressed during shutdown

## Dev Notes

### Root Cause Analysis

The error occurs in `backend/app/services/clip_service.py:240-241` during the `_stop_scheduler()` method:

```
ValueError: I/O operation on closed file.
Call stack:
  File "clip_service.py", line 240, in _stop_scheduler
    self._scheduler.shutdown(wait=False)
  File "apscheduler/schedulers/base.py", line 245, in shutdown
    self._logger.info("Scheduler has been shut down")
```

**Why this happens:**
1. `ClipService.__init__()` registers `_stop_scheduler()` with `atexit.register()`
2. During pytest teardown, logging stream handlers are closed
3. `atexit` handlers run after streams are closed
4. APScheduler's internal `_logger.info("Scheduler has been shut down")` fails
5. ClipService's own logging on line 241 also fails

**Solution:**
Suppress logging during shutdown by temporarily setting the APScheduler logger level to CRITICAL and wrapping all logging calls in try-except.

### Project Structure Notes

- Affected file: `backend/app/services/clip_service.py` (lines 234-255)
- Similar pattern in: `backend/app/services/digest_scheduler.py` (lines 96-104)
- The digest_scheduler uses AsyncIOScheduler instead of BackgroundScheduler, but same logging issue could apply

### References

- [Source: docs/sprint-artifacts/sprint-status.yaml#BUGS section]
- [Source: backend/app/services/clip_service.py#_stop_scheduler]
- [Source: apscheduler/schedulers/base.py:245 - internal shutdown logging]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Test output showing the error: `pytest tests/ -v` shows ValueError during cleanup

### Completion Notes List

1. The fix temporarily suppresses both APScheduler's logger and ClipService's logger during scheduler shutdown
2. Logger levels are set to CRITICAL+1 (above any standard level) to prevent any log output
3. Original logger levels are restored after shutdown completes (in a try-except to handle errors)
4. DigestScheduler was reviewed and found to be unaffected because it doesn't use atexit handlers
5. The issue only manifests during pytest teardown when logging streams are closed before atexit runs

### File List

- **MODIFIED**: `backend/app/services/clip_service.py` - Updated `_stop_scheduler()` method to suppress logging during shutdown
