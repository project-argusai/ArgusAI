# Story P14-3.7: Increase Test Parametrization

Status: done

## Story

As a **developer**,
I want data-driven tests to use pytest parametrization instead of loop-based patterns,
So that test isolation is improved, failure messages show which parameter set failed, and tests are easier to maintain.

## Acceptance Criteria

1. **AC1**: At least 50 parametrized tests exist across the test suite (up from current 17)
2. **AC2**: `test_ai_service.py` object extraction tests are converted to parametrization
3. **AC3**: Each parameter set runs as an isolated test
4. **AC4**: Failure messages clearly show which parameter set failed
5. **AC5**: All existing tests continue to pass after conversion

## Tasks / Subtasks

- [ ] Task 1: Audit current parametrization usage (AC: #1)
  - [ ] 1.1 Count current `@pytest.mark.parametrize` instances
  - [ ] 1.2 Identify loop-based tests candidates for conversion
  - [ ] 1.3 Prioritize conversions by test file importance

- [ ] Task 2: Convert test_ai_service.py object extraction tests (AC: #2)
  - [ ] 2.1 Convert `TestOpenAIProvider.test_object_extraction` (line 165) from loop to parametrize
  - [ ] 2.2 Convert `TestGrokProvider.test_object_extraction` (line 314) from loop to parametrize
  - [ ] 2.3 Verify test isolation and clear failure messages

- [ ] Task 3: Convert additional high-value loop-based tests (AC: #1, #3, #4)
  - [ ] 3.1 Review test_event_processor.py for conversion candidates
  - [ ] 3.2 Review test_carrier_extractor.py (already has 7 parametrize instances, add more if needed)
  - [ ] 3.3 Review test_description_quality.py for additional conversion opportunities
  - [ ] 3.4 Review test_protect_event_handler.py for additional conversion opportunities

- [ ] Task 4: Convert integration test loop patterns (AC: #1)
  - [ ] 4.1 Review test_coexistence.py for conversion candidates
  - [ ] 4.2 Review test_protect_events.py for conversion candidates
  - [ ] 4.3 Convert suitable loop-based patterns to parametrization

- [ ] Task 5: Add new parametrized tests where beneficial (AC: #1)
  - [ ] 5.1 Add parametrized edge case tests to existing test classes
  - [ ] 5.2 Add parametrized error scenario tests

- [ ] Task 6: Validate changes (AC: #3, #4, #5)
  - [ ] 6.1 Run full test suite: `pytest tests/ -v`
  - [ ] 6.2 Verify test count increased appropriately
  - [ ] 6.3 Verify failure messages show parameter values
  - [ ] 6.4 Count final `@pytest.mark.parametrize` instances (target: 50+)

## Dev Notes

### Current State Analysis

Current parametrize count: **17 instances**
- `test_protect_service.py`: 2 instances (exception handling, backoff delays)
- `test_api_key_service.py`: 1 instance (scopes)
- `test_carrier_extractor.py`: 7 instances (description/expected pairs)
- `test_snapshot_service.py`: 1 instance
- `test_description_quality.py`: 3 instances (phrase detection)
- `test_protect_event_handler.py`: 2 instances (detection flags, filter types)
- `test_events.py`: 1 instance (carrier display names)

### High-Priority Conversion Candidates

1. **test_ai_service.py**:
   - `TestOpenAIProvider.test_object_extraction` (line 165-181): Loop with 6 test cases
   - `TestGrokProvider.test_object_extraction` (line 314-329): Loop with 5 test cases

2. **test_event_processor.py**:
   - `test_worker_count_clamping` (line 181-191): Could be parametrized for boundary tests

3. **Integration tests**:
   - Many `for i in range(N):` patterns that create test data
   - Some can be converted to parametrized tests for specific scenarios

### Parametrization Pattern

Convert from:
```python
def test_object_extraction(self):
    test_cases = [
        ("A person wearing a red shirt", ['person']),
        ("A delivery truck is parked", ['vehicle']),
    ]
    for description, expected in test_cases:
        objects = provider._extract_objects(description)
        assert expected[0] in objects
```

To:
```python
@pytest.mark.parametrize("description,expected_objects", [
    ("A person wearing a red shirt", ['person']),
    ("A delivery truck is parked", ['vehicle']),
])
def test_object_extraction(self, description, expected_objects):
    objects = provider._extract_objects(description)
    for expected in expected_objects:
        assert expected in objects
```

### Benefits of Parametrization
- **Isolation**: Each parameter set runs as separate test
- **Failure clarity**: Test name shows `test_object_extraction[A person wearing a red shirt-person]`
- **Maintainability**: Easy to add new test cases
- **Parallelization**: Pytest can run parametrized tests in parallel

### Testing Standards (from epics-phase14.md)

- Pattern: Convert `for case in cases: assert...` to `@pytest.mark.parametrize`
- Focus files: `test_ai_service.py`, `test_event_processor.py`
- Example: `@pytest.mark.parametrize("input,expected", [("person", True), ("tree", False)])`

### Project Structure Notes

- Tests location: `backend/tests/`
- Service tests: `backend/tests/test_services/`
- Integration tests: `backend/tests/test_integration/`
- API tests: `backend/tests/test_api/`

### References

- [Source: docs/epics-phase14.md#Story-P14-3.7]
- [Source: backend/tests/test_services/test_ai_service.py:165-181]
- [Source: backend/tests/test_services/test_ai_service.py:314-329]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

