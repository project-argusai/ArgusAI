/**
 * useWebSocket Hook Tests
 *
 * Tests for the WebSocket connection hook with reconnection logic.
 *
 * Demonstrates:
 * - Mocking WebSocket API
 * - Testing connection lifecycle (connect, disconnect, reconnect)
 * - Testing message handling for different event types
 * - Testing exponential backoff reconnection
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useWebSocket, ConnectionStatus, CameraStatusChangeData } from '@/lib/hooks/useWebSocket'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })

  // Helper methods for testing
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateClose(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED
    const event = new CloseEvent('close', { code, reason })
    this.onclose?.(event)
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }

  simulateMessage(data: string | object) {
    const messageData = typeof data === 'string' ? data : JSON.stringify(data)
    const event = new MessageEvent('message', { data: messageData })
    this.onmessage?.(event)
  }
}

// Store created instances for testing
let mockWebSocketInstances: MockWebSocket[] = []

describe('useWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockWebSocketInstances = []

    // Mock global WebSocket
    vi.stubGlobal('WebSocket', class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        mockWebSocketInstances.push(this)
      }
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  describe('connection', () => {
    it('auto-connects on mount when autoConnect is true (default)', async () => {
      renderHook(() => useWebSocket())

      // Advance timer to trigger deferred connect
      await act(async () => {
        vi.advanceTimersByTime(0)
      })

      expect(mockWebSocketInstances.length).toBe(1)
      expect(mockWebSocketInstances[0].url).toBe('ws://localhost:8000/ws')
    })

    it('does not auto-connect when autoConnect is false', async () => {
      renderHook(() => useWebSocket({ autoConnect: false }))

      await act(async () => {
        vi.advanceTimersByTime(100)
      })

      expect(mockWebSocketInstances.length).toBe(0)
    })

    it('starts with disconnected status', () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      expect(result.current.status).toBe('disconnected')
    })

    it('transitions to connecting status when connect is called', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      expect(result.current.status).toBe('connecting')
    })

    it('transitions to connected status when WebSocket opens', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      expect(result.current.status).toBe('connected')
    })

    it('calls onStatusChange callback on status transitions', async () => {
      const onStatusChange = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onStatusChange })
      )

      act(() => {
        result.current.connect()
      })

      expect(onStatusChange).toHaveBeenCalledWith('connecting')

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      expect(onStatusChange).toHaveBeenCalledWith('connected')
    })
  })

  describe('disconnection', () => {
    it('transitions to disconnected status on manual disconnect', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      expect(result.current.status).toBe('connected')

      act(() => {
        result.current.disconnect()
      })

      expect(result.current.status).toBe('disconnected')
    })

    it('does not attempt reconnect after manual disconnect', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      act(() => {
        result.current.disconnect()
      })

      // Advance time past reconnect delay
      await act(async () => {
        vi.advanceTimersByTime(30000)
      })

      // Should still only have 1 instance (no reconnect attempt)
      expect(mockWebSocketInstances.length).toBe(1)
      expect(result.current.status).toBe('disconnected')
    })

    it('cleans up WebSocket on unmount', async () => {
      const { result, unmount } = renderHook(() =>
        useWebSocket({ autoConnect: false })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      const ws = mockWebSocketInstances[0]
      unmount()

      expect(ws.close).toHaveBeenCalled()
    })
  })

  describe('reconnection', () => {
    it('attempts reconnection with exponential backoff', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, maxRetries: 3 })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      // Simulate unexpected close
      act(() => {
        mockWebSocketInstances[0].simulateClose()
      })

      expect(result.current.status).toBe('reconnecting')

      // First reconnect after 1s
      await act(async () => {
        vi.advanceTimersByTime(1000)
      })

      expect(mockWebSocketInstances.length).toBe(2)

      // Close again
      act(() => {
        mockWebSocketInstances[1].simulateClose()
      })

      // Second reconnect after 2s
      await act(async () => {
        vi.advanceTimersByTime(2000)
      })

      expect(mockWebSocketInstances.length).toBe(3)
    })

    it('stops reconnecting after maxRetries', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, maxRetries: 2 })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      // Exhaust retries
      for (let i = 0; i < 3; i++) {
        act(() => {
          mockWebSocketInstances[mockWebSocketInstances.length - 1].simulateClose()
        })

        await act(async () => {
          vi.advanceTimersByTime(30000) // Max backoff
        })
      }

      // After max retries, status should be disconnected
      expect(result.current.status).toBe('disconnected')
    })

    it('resets retry counter on successful connection', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, maxRetries: 10 })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      // Disconnect and reconnect
      act(() => {
        mockWebSocketInstances[0].simulateClose()
      })

      await act(async () => {
        vi.advanceTimersByTime(1000)
      })

      act(() => {
        mockWebSocketInstances[1].simulateOpen()
      })

      expect(result.current.status).toBe('connected')

      // After successful reconnect, counter should be reset
      // Close again - backoff should start from 1s again
      act(() => {
        mockWebSocketInstances[1].simulateClose()
      })

      await act(async () => {
        vi.advanceTimersByTime(1000)
      })

      expect(mockWebSocketInstances.length).toBe(3)
    })
  })

  describe('message handling', () => {
    it('responds to ping with pong', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      act(() => {
        mockWebSocketInstances[0].simulateMessage('ping')
      })

      expect(mockWebSocketInstances[0].send).toHaveBeenCalledWith('pong')
    })

    it('ignores pong messages', async () => {
      const onNotification = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onNotification })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      act(() => {
        mockWebSocketInstances[0].simulateMessage('pong')
      })

      expect(onNotification).not.toHaveBeenCalled()
    })

    it('calls onNotification for notification messages', async () => {
      const onNotification = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onNotification })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      const notificationData = { id: '1', title: 'Test', message: 'Hello' }
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'notification',
          data: notificationData,
        })
      })

      expect(onNotification).toHaveBeenCalledWith(notificationData)
    })

    it('calls onAlert for ALERT_TRIGGERED messages', async () => {
      const onAlert = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onAlert })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      const alertData = { event: { id: '1' }, rule: { id: '2' } }
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'ALERT_TRIGGERED',
          data: alertData,
        })
      })

      expect(onAlert).toHaveBeenCalledWith(alertData)
    })

    it('calls onNewEvent for NEW_EVENT messages', async () => {
      const onNewEvent = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onNewEvent })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      const eventData = {
        event_id: 'evt-1',
        camera_id: 'cam-1',
        description: 'Motion detected',
      }
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'NEW_EVENT',
          data: eventData,
        })
      })

      expect(onNewEvent).toHaveBeenCalledWith(eventData)
    })

    it('calls onCameraStatusChange for CAMERA_STATUS_CHANGED messages', async () => {
      const onCameraStatusChange = vi.fn()
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false, onCameraStatusChange })
      )

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      const statusData: CameraStatusChangeData = {
        controller_id: 'ctrl-1',
        camera_id: 'cam-1',
        is_online: true,
      }
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'CAMERA_STATUS_CHANGED',
          data: statusData,
        })
      })

      expect(onCameraStatusChange).toHaveBeenCalledWith(statusData)
    })

    it('handles invalid JSON messages gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      // Send invalid JSON
      act(() => {
        mockWebSocketInstances[0].simulateMessage('invalid json {')
      })

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to parse WebSocket message:',
        expect.any(Error)
      )

      consoleSpy.mockRestore()
    })
  })

  describe('send', () => {
    it('sends message when connected', async () => {
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.connect()
      })

      act(() => {
        mockWebSocketInstances[0].simulateOpen()
      })

      act(() => {
        result.current.send('test message')
      })

      expect(mockWebSocketInstances[0].send).toHaveBeenCalledWith('test message')
    })

    it('warns when trying to send while disconnected', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const { result } = renderHook(() => useWebSocket({ autoConnect: false }))

      act(() => {
        result.current.send('test message')
      })

      expect(consoleSpy).toHaveBeenCalledWith(
        'WebSocket not connected, cannot send message'
      )

      consoleSpy.mockRestore()
    })
  })
})
