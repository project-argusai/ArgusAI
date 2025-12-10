/**
 * useDebounce Hook Tests
 *
 * Tests for the debounce utility hook that delays value updates.
 *
 * Demonstrates:
 * - Testing custom hooks with renderHook
 * - Testing timing-based behavior with fake timers
 * - Testing cleanup on rapid value changes
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from '@/lib/hooks/useDebounce'

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('initial value', () => {
    it('returns the initial value immediately', () => {
      const { result } = renderHook(() => useDebounce('initial', 500))

      expect(result.current).toBe('initial')
    })

    it('works with different types - number', () => {
      const { result } = renderHook(() => useDebounce(42, 500))

      expect(result.current).toBe(42)
    })

    it('works with different types - object', () => {
      const obj = { foo: 'bar' }
      const { result } = renderHook(() => useDebounce(obj, 500))

      expect(result.current).toEqual({ foo: 'bar' })
    })

    it('works with different types - null', () => {
      const { result } = renderHook(() => useDebounce(null, 500))

      expect(result.current).toBeNull()
    })
  })

  describe('debouncing behavior', () => {
    it('does not update value before delay expires', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value, 500),
        { initialProps: { value: 'initial' } }
      )

      // Change the value
      rerender({ value: 'updated' })

      // Value should still be initial before delay
      expect(result.current).toBe('initial')

      // Advance time but not enough
      act(() => {
        vi.advanceTimersByTime(400)
      })

      expect(result.current).toBe('initial')
    })

    it('updates value after delay expires', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value, 500),
        { initialProps: { value: 'initial' } }
      )

      // Change the value
      rerender({ value: 'updated' })

      // Advance time past the delay
      act(() => {
        vi.advanceTimersByTime(500)
      })

      expect(result.current).toBe('updated')
    })

    it('resets timer when value changes rapidly', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value, 500),
        { initialProps: { value: 'initial' } }
      )

      // Rapid value changes
      rerender({ value: 'change1' })
      act(() => {
        vi.advanceTimersByTime(200)
      })

      rerender({ value: 'change2' })
      act(() => {
        vi.advanceTimersByTime(200)
      })

      rerender({ value: 'change3' })

      // Still should be initial
      expect(result.current).toBe('initial')

      // Advance past the delay from last change
      act(() => {
        vi.advanceTimersByTime(500)
      })

      // Should be the final value
      expect(result.current).toBe('change3')
    })
  })

  describe('custom delay', () => {
    it('uses default delay of 500ms when not specified', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value),
        { initialProps: { value: 'initial' } }
      )

      rerender({ value: 'updated' })

      // Should not update before 500ms
      act(() => {
        vi.advanceTimersByTime(499)
      })
      expect(result.current).toBe('initial')

      // Should update after 500ms
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe('updated')
    })

    it('respects custom delay value', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value, 1000),
        { initialProps: { value: 'initial' } }
      )

      rerender({ value: 'updated' })

      // Should not update before 1000ms
      act(() => {
        vi.advanceTimersByTime(999)
      })
      expect(result.current).toBe('initial')

      // Should update after 1000ms
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe('updated')
    })

    it('works with very short delay', () => {
      const { result, rerender } = renderHook(
        ({ value }) => useDebounce(value, 50),
        { initialProps: { value: 'initial' } }
      )

      rerender({ value: 'updated' })

      act(() => {
        vi.advanceTimersByTime(50)
      })

      expect(result.current).toBe('updated')
    })
  })

  describe('cleanup', () => {
    it('clears timeout on unmount', () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout')

      const { unmount, rerender } = renderHook(
        ({ value }) => useDebounce(value, 500),
        { initialProps: { value: 'initial' } }
      )

      // Trigger a timeout to be set
      rerender({ value: 'updated' })

      // Unmount before delay expires
      unmount()

      // clearTimeout should have been called
      expect(clearTimeoutSpy).toHaveBeenCalled()

      clearTimeoutSpy.mockRestore()
    })

    it('clears previous timeout when value changes', () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout')

      const { rerender } = renderHook(
        ({ value }) => useDebounce(value, 500),
        { initialProps: { value: 'initial' } }
      )

      // Multiple value changes should clear previous timeouts
      rerender({ value: 'change1' })
      rerender({ value: 'change2' })
      rerender({ value: 'change3' })

      // clearTimeout should have been called for each change
      expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThanOrEqual(2)

      clearTimeoutSpy.mockRestore()
    })
  })

  describe('delay changes', () => {
    it('respects delay changes', () => {
      const { result, rerender } = renderHook(
        ({ value, delay }) => useDebounce(value, delay),
        { initialProps: { value: 'initial', delay: 500 } }
      )

      // Change both value and delay
      rerender({ value: 'updated', delay: 1000 })

      // Should not update with old delay
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(result.current).toBe('initial')

      // Should update with new delay
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(result.current).toBe('updated')
    })
  })
})
