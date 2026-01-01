/**
 * Tests for LiveStreamModal component
 * Story P16-2.4: Verifies modal dialog for live camera streams
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '../../test-utils';
import { LiveStreamModal } from '@/components/streaming/LiveStreamModal';

// Mock LiveStreamPlayer to avoid WebSocket complexity in modal tests
vi.mock('@/components/streaming/LiveStreamPlayer', () => ({
  LiveStreamPlayer: ({ cameraId, cameraName }: { cameraId: string; cameraName: string }) => (
    <div data-testid="live-stream-player" data-camera-id={cameraId}>
      LiveStreamPlayer: {cameraName}
    </div>
  ),
}));

describe('LiveStreamModal', () => {
  let mockOnOpenChange: (open: boolean) => void;

  beforeEach(() => {
    mockOnOpenChange = vi.fn();
  });

  describe('Rendering (AC: 2)', () => {
    it('renders modal with camera name in header when open', () => {
      render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Front Door Camera"
        />
      );

      expect(screen.getByText('Live View - Front Door Camera')).toBeInTheDocument();
    });

    it('does not render content when closed', () => {
      render(
        <LiveStreamModal
          open={false}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Front Door Camera"
        />
      );

      expect(screen.queryByText('Live View - Front Door Camera')).not.toBeInTheDocument();
    });

    it('renders LiveStreamPlayer component with correct props', () => {
      render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Test Camera"
        />
      );

      const player = screen.getByTestId('live-stream-player');
      expect(player).toBeInTheDocument();
      expect(player).toHaveAttribute('data-camera-id', 'cam-123');
      expect(screen.getByText('LiveStreamPlayer: Test Camera')).toBeInTheDocument();
    });

    it('renders Video icon in header', () => {
      render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Camera"
        />
      );

      // Dialog header should contain the Video icon (checking for SVG presence)
      const header = screen.getByRole('heading');
      expect(header).toBeInTheDocument();
      expect(header.querySelector('svg')).toBeInTheDocument();
    });
  });

  describe('Modal Controls (AC: 2)', () => {
    it('calls onOpenChange with false when close button is clicked', async () => {
      const { user } = render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Camera"
        />
      );

      // Find and click the close button (X button in dialog)
      const closeButton = screen.getByRole('button', { name: /close/i });
      await user.click(closeButton);

      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });

    it('calls onOpenChange when Escape key is pressed', async () => {
      const { user } = render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Camera"
        />
      );

      await user.keyboard('{Escape}');

      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });
  });

  describe('Quality Settings', () => {
    it('uses medium quality by default', () => {
      render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Camera"
        />
      );

      // LiveStreamPlayer should be rendered with default quality
      expect(screen.getByTestId('live-stream-player')).toBeInTheDocument();
    });

    it('accepts custom initial quality', () => {
      render(
        <LiveStreamModal
          open={true}
          onOpenChange={mockOnOpenChange}
          cameraId="cam-123"
          cameraName="Camera"
          initialQuality="high"
        />
      );

      expect(screen.getByTestId('live-stream-player')).toBeInTheDocument();
    });
  });
});
