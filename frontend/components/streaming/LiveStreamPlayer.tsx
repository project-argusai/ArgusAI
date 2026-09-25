/**
 * LiveStreamPlayer Component (Story P16-2.3)
 * Displays live camera streams via WebSocket with MJPEG frames
 * Features:
 * - WebSocket connection with binary JPEG frame rendering
 * - Quality selector (Low/Medium/High)
 * - Fullscreen support
 * - Mute/unmute toggle (muted by default)
 * - Snapshot fallback on connection failure
 * - Loading spinner during initial connection
 * - Camera name overlay
 */

'use client';

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  memo,
} from 'react';
import {
  Maximize2,
  Minimize2,
  Volume2,
  VolumeX,
  RefreshCw,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StreamQualitySelector } from './StreamQualitySelector';
import { ApiError, apiClient } from '@/lib/api-client';
import { isAuthWebSocketClose, WS_AUTH_FAILURE_MESSAGE } from '@/lib/ws-auth';
import { useToast } from '@/hooks/useToast';
import type {
  StreamQuality,
  IStreamInfo,
  IStreamWebSocketResponse,
} from '@/types/camera';
import { cn } from '@/lib/utils';

// WebSocket close codes (Story P16-2.5)
const WS_CLOSE_CAMERA_NOT_FOUND = 4004;
const WS_CLOSE_NO_RTSP_URL = 4400;
const WS_CLOSE_STREAM_LIMIT = 4429; // Like HTTP 429 - too many streams
const WS_CLOSE_STREAM_UNAVAILABLE = 4503;

interface LiveStreamPlayerProps {
  /**
   * Camera ID to stream
   */
  cameraId: string;
  /**
   * Camera name for overlay display
   */
  cameraName: string;
  /**
   * Optional CSS class name
   */
  className?: string;
  /**
   * Initial quality level (default: medium)
   */
  initialQuality?: StreamQuality;
  /**
   * Aspect ratio class (default: aspect-video)
   */
  aspectRatio?: string;
  /**
   * Show controls overlay (default: true)
   */
  showControls?: boolean;
}

type ConnectionState = 'connecting' | 'connected' | 'fallback' | 'error';

const CONNECTION_TIMEOUT_MS = 5000;
const SNAPSHOT_REFRESH_INTERVAL_MS = 2000;

/**
 * LiveStreamPlayer - Renders live camera stream via WebSocket
 */
export const LiveStreamPlayer = memo(function LiveStreamPlayer({
  cameraId,
  cameraName,
  className,
  initialQuality = 'medium',
  aspectRatio = 'aspect-video',
  showControls = true,
}: LiveStreamPlayerProps) {
  // Hooks
  const { showWarning, showError } = useToast();

  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [streamInfo, setStreamInfo] = useState<IStreamInfo | null>(null);
  const [quality, setQuality] = useState<StreamQuality>(initialQuality);
  const [isMuted, setIsMuted] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const connectionTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const snapshotIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const blobUrlRef = useRef<string | null>(null);

  /**
   * Clean up blob URL to prevent memory leaks
   */
  const cleanupBlobUrl = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
  }, []);

  /**
   * Cleanup WebSocket connection
   */
  const cleanupWebSocket = useCallback(() => {
    if (connectionTimeoutRef.current) {
      clearTimeout(connectionTimeoutRef.current);
      connectionTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  /**
   * Cleanup snapshot interval
   */
  const cleanupSnapshotInterval = useCallback(() => {
    if (snapshotIntervalRef.current) {
      clearInterval(snapshotIntervalRef.current);
      snapshotIntervalRef.current = null;
    }
  }, []);

  /**
   * Fetch stream info from API
   */
  const fetchStreamInfo = useCallback(async () => {
    try {
      const info = await apiClient.cameras.getStreamInfo(cameraId);
      setStreamInfo(info);
      return info;
    } catch (err) {
      console.error('Failed to fetch stream info:', err);
      return null;
    }
  }, [cameraId]);

  /**
   * Start snapshot fallback mode
   */
  const startSnapshotFallback = useCallback(async () => {
    setConnectionState('fallback');
    cleanupWebSocket();

    let stoppedForAuth = false;
    const fetchSnapshot = async () => {
      if (stoppedForAuth) {
        return;
      }
      try {
        const snapshot = await apiClient.cameras.getStreamSnapshot(cameraId, quality);
        if (snapshot.success && snapshot.image_base64 && imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${snapshot.image_base64}`;
        }
      } catch (err) {
        if (err instanceof ApiError && (err.statusCode === 401 || err.statusCode === 403)) {
          stoppedForAuth = true;
          cleanupSnapshotInterval();
          setConnectionState('error');
          setErrorMessage(WS_AUTH_FAILURE_MESSAGE);
          return;
        }
        console.error('Failed to fetch snapshot:', err);
      }
    };

    // Fetch initial snapshot
    await fetchSnapshot();
    if (stoppedForAuth) {
      return;
    }

    // Start interval for periodic refresh
    snapshotIntervalRef.current = setInterval(fetchSnapshot, SNAPSHOT_REFRESH_INTERVAL_MS);
  }, [cameraId, quality, cleanupWebSocket, cleanupSnapshotInterval]);

  /**
   * Connect to WebSocket stream
   */
  const connectWebSocket = useCallback(() => {
    cleanupWebSocket();
    cleanupSnapshotInterval();
    cleanupBlobUrl();
    setConnectionState('connecting');
    setErrorMessage(null);

    const wsUrl = apiClient.cameras.getStreamWebSocketUrl(cameraId, quality);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // Set connection timeout
    connectionTimeoutRef.current = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket connection timeout, falling back to snapshots');
        ws.close();
        startSnapshotFallback();
      }
    }, CONNECTION_TIMEOUT_MS);

    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
      setConnectionState('connected');
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary JPEG frame
        cleanupBlobUrl();
        const blob = new Blob([event.data], { type: 'image/jpeg' });
        blobUrlRef.current = URL.createObjectURL(blob);
        if (imgRef.current) {
          imgRef.current.src = blobUrlRef.current;
        }
      } else {
        // JSON control message
        try {
          const message: IStreamWebSocketResponse = JSON.parse(event.data);
          if (message.type === 'error') {
            console.error('Stream error:', message.message);
            setErrorMessage(message.message || 'Stream error');
          } else if (message.type === 'quality_changed') {
            console.log('Quality changed to:', message.quality);
          } else if (message.type === 'info') {
            console.log('Stream info:', message.message);
          }
        } catch {
          console.warn('Failed to parse WebSocket message:', event.data);
        }
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
    };

    ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);

      // Auth closes must not fall through into snapshot polling.
      if (isAuthWebSocketClose(event.code)) {
        cleanupSnapshotInterval();
        setConnectionState('error');
        setErrorMessage(WS_AUTH_FAILURE_MESSAGE);
        return;
      }

      // Handle specific close codes (Story P16-2.5)
      switch (event.code) {
        case WS_CLOSE_STREAM_LIMIT:
          // Concurrent stream limit reached
          setConnectionState('error');
          setErrorMessage('Maximum concurrent streams reached. Please close another stream first.');
          showWarning('Maximum concurrent streams reached. Please close another stream first.');
          return;
        case WS_CLOSE_CAMERA_NOT_FOUND:
          setConnectionState('error');
          setErrorMessage('Camera not found');
          showError('Camera not found');
          return;
        case WS_CLOSE_NO_RTSP_URL:
          setConnectionState('error');
          setErrorMessage('Camera does not have a stream URL configured');
          return;
        case WS_CLOSE_STREAM_UNAVAILABLE:
          // Fall through to snapshot fallback
          break;
      }

      if (connectionState === 'connecting') {
        // Connection failed, switch to fallback
        startSnapshotFallback();
      } else if (connectionState === 'connected') {
        // Unexpected disconnect, try to reconnect once
        setConnectionState('error');
        setErrorMessage('Connection lost');
      }
    };
  }, [
    cameraId,
    quality,
    connectionState,
    cleanupWebSocket,
    cleanupSnapshotInterval,
    cleanupBlobUrl,
    startSnapshotFallback,
    showWarning,
    showError,
  ]);

  /**
   * Handle quality change
   */
  const handleQualityChange = useCallback((newQuality: StreamQuality) => {
    setQuality(newQuality);

    // If connected via WebSocket, send quality change message
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'quality_change', quality: newQuality }));
    } else if (connectionState === 'fallback') {
      // In fallback mode, just update state - snapshot will use new quality
    } else {
      // Reconnect with new quality
      connectWebSocket();
    }
  }, [connectionState, connectWebSocket]);

  /**
   * Handle retry button click
   */
  const handleRetry = useCallback(() => {
    cleanupSnapshotInterval();
    connectWebSocket();
  }, [cleanupSnapshotInterval, connectWebSocket]);

  /**
   * Toggle fullscreen
   */
  const toggleFullscreen = useCallback(async () => {
    if (!containerRef.current) return;

    try {
      if (!document.fullscreenElement) {
        await containerRef.current.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch (err) {
      console.error('Fullscreen error:', err);
    }
  }, []);

  /**
   * Handle fullscreen change events
   */
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  /**
   * Handle Escape key for fullscreen exit
   */
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isFullscreen) {
        document.exitFullscreen().catch(console.error);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFullscreen]);

  /**
   * Initialize stream on mount
   */
  useEffect(() => {
    fetchStreamInfo();
    connectWebSocket();

    return () => {
      cleanupWebSocket();
      cleanupSnapshotInterval();
      cleanupBlobUrl();
    };
  }, [cameraId]); // Only reconnect when cameraId changes

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative bg-black rounded-lg overflow-hidden',
        aspectRatio,
        isFullscreen && 'rounded-none',
        className
      )}
    >
      {/* Video/Image Display */}
      <img
        ref={imgRef}
        alt={`Live stream from ${cameraName}`}
        className="w-full h-full object-contain"
        draggable={false}
      />

      {/* Loading Overlay */}
      {connectionState === 'connecting' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
          <div className="flex flex-col items-center gap-2 text-white">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="text-sm">Connecting...</span>
          </div>
        </div>
      )}

      {/* Error Overlay */}
      {connectionState === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70">
          <div className="flex flex-col items-center gap-3 text-white text-center p-4">
            <AlertCircle className="h-10 w-10 text-red-400" />
            <span className="text-sm font-medium">Stream unavailable</span>
            {errorMessage && (
              <span className="text-xs text-gray-400">{errorMessage}</span>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRetry}
              className="mt-2"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </div>
      )}

      {/* Fallback Mode Indicator */}
      {connectionState === 'fallback' && (
        <div className="absolute top-2 right-2 bg-amber-500/80 text-white text-xs px-2 py-1 rounded">
          Snapshot mode
        </div>
      )}

      {/* Camera Name Overlay */}
      <div className="absolute top-2 left-2 bg-black/60 text-white text-sm px-2 py-1 rounded">
        {cameraName}
      </div>

      {/* Controls Overlay */}
      {showControls && (connectionState === 'connected' || connectionState === 'fallback') && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
          <div className="flex items-center justify-between">
            {/* Left controls */}
            <div className="flex items-center gap-2">
              {/* Mute/Unmute */}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-white hover:bg-white/20"
                onClick={() => setIsMuted(!isMuted)}
                title={isMuted ? 'Unmute' : 'Mute'}
              >
                {isMuted ? (
                  <VolumeX className="h-4 w-4" />
                ) : (
                  <Volume2 className="h-4 w-4" />
                )}
              </Button>

              {/* Quality Selector */}
              <StreamQualitySelector
                currentQuality={quality}
                qualityOptions={streamInfo?.quality_options}
                onQualityChange={handleQualityChange}
              />
            </div>

            {/* Right controls */}
            <div className="flex items-center gap-2">
              {/* Retry button in fallback mode */}
              {connectionState === 'fallback' && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-white hover:bg-white/20"
                  onClick={handleRetry}
                  title="Reconnect live stream"
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              )}

              {/* Fullscreen */}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-white hover:bg-white/20"
                onClick={toggleFullscreen}
                title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
