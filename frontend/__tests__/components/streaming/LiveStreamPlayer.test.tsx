/**
 * Tests for LiveStreamPlayer component (Story P16-2.3)
 * Verifies component rendering and basic behavior
 * Note: WebSocket tests are simplified due to JSDOM limitations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '../../test-utils';
import { LiveStreamPlayer } from '@/components/streaming/LiveStreamPlayer';
import { apiClient } from '@/lib/api-client';

// Mock the api-client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    cameras: {
      getStreamInfo: vi.fn(),
      getStreamSnapshot: vi.fn(),
      getStreamWebSocketUrl: vi.fn(),
    },
  },
}));

// Store mock WebSocket instance
let mockWsInstance: {
  readyState: number;
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
  onopen: ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: Event) => void) | null;
  onclose: ((e: CloseEvent) => void) | null;
} | null = null;

// Mock WebSocket class
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  binaryType = 'arraybuffer';
  readyState = MockWebSocket.CONNECTING;
  send = vi.fn();
  close = vi.fn();
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;

  constructor(url: string) {
    void url; // Satisfy unused var lint
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const instance = this;
    mockWsInstance = instance;
    // Auto-connect after a brief delay
    setTimeout(() => {
      instance.readyState = MockWebSocket.OPEN;
      instance.onopen?.(new Event('open'));
    }, 5);
  }
}

const originalWebSocket = global.WebSocket;

beforeEach(() => {
  mockWsInstance = null;
  // @ts-expect-error - Mock WebSocket
  global.WebSocket = MockWebSocket;

  // Mock URL APIs
  global.URL.createObjectURL = vi.fn(() => 'blob:test-url');
  global.URL.revokeObjectURL = vi.fn();

  // Mock default API responses
  vi.mocked(apiClient.cameras.getStreamInfo).mockResolvedValue({
    camera_id: 'camera-1',
    type: 'websocket',
    websocket_path: '/api/v1/cameras/camera-1/stream',
    snapshot_path: '/api/v1/cameras/camera-1/stream/snapshot',
    quality_options: [
      { id: 'low', label: 'Low', resolution: '640x360', fps: 5 },
      { id: 'medium', label: 'Medium', resolution: '1280x720', fps: 10 },
      { id: 'high', label: 'High', resolution: '1920x1080', fps: 15 },
    ],
    default_quality: 'medium',
    current_clients: 0,
    max_clients_available: 10,
    is_available: true,
  });

  vi.mocked(apiClient.cameras.getStreamSnapshot).mockResolvedValue({
    success: true,
    timestamp: new Date().toISOString(),
    quality: 'medium',
    image_base64: 'base64EncodedImageData',
  });

  vi.mocked(apiClient.cameras.getStreamWebSocketUrl).mockReturnValue(
    'ws://localhost:8000/api/v1/cameras/camera-1/stream'
  );
});

afterEach(() => {
  global.WebSocket = originalWebSocket;
  vi.clearAllMocks();
});

describe('LiveStreamPlayer', () => {
  describe('Initial Rendering (AC: 1, 5)', () => {
    it('renders with camera name overlay', () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      expect(screen.getByText('Front Door')).toBeInTheDocument();
    });

    it('shows loading state initially', () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      expect(screen.getByText('Connecting...')).toBeInTheDocument();
    });

    it('renders img element for video display', () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      expect(screen.getByRole('img')).toBeInTheDocument();
    });

    it('fetches stream info on mount', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(apiClient.cameras.getStreamInfo).toHaveBeenCalledWith('camera-1');
      });
    });

    it('creates WebSocket with correct URL', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(apiClient.cameras.getStreamWebSocketUrl).toHaveBeenCalledWith('camera-1', 'medium');
      });
    });

    it('shows controls after connection', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      // Controls should now be visible
      expect(screen.getByTitle('Stream quality')).toBeInTheDocument();
      expect(screen.getByTitle('Fullscreen')).toBeInTheDocument();
    });
  });

  describe('Quality Selection (AC: 2)', () => {
    it('displays current quality level', async () => {
      render(
        <LiveStreamPlayer
          cameraId="camera-1"
          cameraName="Front Door"
          initialQuality="high"
        />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      expect(screen.getByText('high')).toBeInTheDocument();
    });

    it('uses initial quality from props', async () => {
      render(
        <LiveStreamPlayer
          cameraId="camera-1"
          cameraName="Front Door"
          initialQuality="low"
        />
      );

      await waitFor(() => {
        expect(apiClient.cameras.getStreamWebSocketUrl).toHaveBeenCalledWith('camera-1', 'low');
      });
    });

    it('opens quality selector popover on click', async () => {
      const { user } = render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      const qualityButton = screen.getByTitle('Stream quality');
      await user.click(qualityButton);

      // Should show quality options
      expect(screen.getByText('Stream Quality')).toBeInTheDocument();
    });
  });

  describe('Fullscreen Support (AC: 3)', () => {
    it('renders fullscreen button', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      expect(screen.getByTitle('Fullscreen')).toBeInTheDocument();
    });
  });

  describe('Audio Controls (AC: 5)', () => {
    it('renders mute toggle button', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      expect(screen.getByTitle('Unmute')).toBeInTheDocument();
    });

    it('starts muted by default', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      // Muted = shows "Unmute" button
      expect(screen.getByTitle('Unmute')).toBeInTheDocument();
    });

    it('toggles mute state on click', async () => {
      const { user } = render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      const muteButton = screen.getByTitle('Unmute');
      await user.click(muteButton);

      // Now unmuted = shows "Mute" button
      expect(screen.getByTitle('Mute')).toBeInTheDocument();
    });
  });

  describe('Controls Visibility', () => {
    it('hides controls when showControls is false', async () => {
      render(
        <LiveStreamPlayer
          cameraId="camera-1"
          cameraName="Front Door"
          showControls={false}
        />
      );

      await waitFor(() => {
        expect(screen.queryByText('Connecting...')).not.toBeInTheDocument();
      }, { timeout: 100 });

      expect(screen.queryByTitle('Stream quality')).not.toBeInTheDocument();
      expect(screen.queryByTitle('Fullscreen')).not.toBeInTheDocument();
    });
  });

  describe('Custom Props', () => {
    it('applies custom className', () => {
      const { container } = render(
        <LiveStreamPlayer
          cameraId="camera-1"
          cameraName="Front Door"
          className="custom-player-class"
        />
      );

      expect(container.firstChild).toHaveClass('custom-player-class');
    });

    it('applies custom aspect ratio', () => {
      const { container } = render(
        <LiveStreamPlayer
          cameraId="camera-1"
          cameraName="Front Door"
          aspectRatio="aspect-square"
        />
      );

      expect(container.firstChild).toHaveClass('aspect-square');
    });
  });

  describe('Cleanup', () => {
    it('closes WebSocket on unmount', async () => {
      const { unmount } = render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull();
      });

      unmount();

      expect(mockWsInstance?.close).toHaveBeenCalled();
    });
  });

  describe('Memoization', () => {
    it('is wrapped with React.memo', () => {
      expect(LiveStreamPlayer).toBeDefined();
      // memo components have a specific structure
      expect(typeof LiveStreamPlayer).toBe('object');
    });
  });

  describe('Concurrent Stream Limiting (Story P16-2.5)', () => {
    it('shows error when stream limit is reached (close code 4429)', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      // Wait for WebSocket to be created AND opened (mock opens after 5ms)
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull();
        expect(mockWsInstance?.readyState).toBe(MockWebSocket.OPEN);
      });

      // Simulate limit reached close event
      const closeEvent = new CloseEvent('close', {
        code: 4429,
        reason: 'Stream limit reached',
      });
      mockWsInstance?.onclose?.(closeEvent);

      // Should show error message
      await waitFor(() => {
        expect(screen.getByText('Stream unavailable')).toBeInTheDocument();
        expect(screen.getByText(/Maximum concurrent streams reached/)).toBeInTheDocument();
      });
    });

    it('shows error when camera not found (close code 4004)', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      // Wait for WebSocket to be created AND opened (mock opens after 5ms)
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull();
        expect(mockWsInstance?.readyState).toBe(MockWebSocket.OPEN);
      });

      // Simulate camera not found close event
      const closeEvent = new CloseEvent('close', {
        code: 4004,
        reason: 'Camera not found',
      });
      mockWsInstance?.onclose?.(closeEvent);

      // Should show error message
      await waitFor(() => {
        expect(screen.getByText('Stream unavailable')).toBeInTheDocument();
        expect(screen.getByText('Camera not found')).toBeInTheDocument();
      });
    });

    it('falls back to snapshots when stream unavailable (close code 4503)', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      // Wait for WebSocket to be created AND opened (mock opens after 5ms)
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull();
        expect(mockWsInstance?.readyState).toBe(MockWebSocket.OPEN);
      });

      // Simulate stream unavailable close event
      const closeEvent = new CloseEvent('close', {
        code: 4503,
        reason: 'Stream unavailable',
      });
      mockWsInstance?.onclose?.(closeEvent);

      // Should fall back to snapshot mode and fetch snapshot
      await waitFor(() => {
        expect(apiClient.cameras.getStreamSnapshot).toHaveBeenCalled();
      });
    });

    it('shows retry button on error', async () => {
      render(
        <LiveStreamPlayer cameraId="camera-1" cameraName="Front Door" />
      );

      // Wait for WebSocket to be created AND opened (mock opens after 5ms)
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull();
        expect(mockWsInstance?.readyState).toBe(MockWebSocket.OPEN);
      });

      // Simulate limit reached close event
      const closeEvent = new CloseEvent('close', {
        code: 4429,
        reason: 'Stream limit reached',
      });
      mockWsInstance?.onclose?.(closeEvent);

      // Should show retry button
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
      });
    });
  });
});
