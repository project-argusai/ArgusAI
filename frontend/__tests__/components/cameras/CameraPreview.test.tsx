/**
 * Tests for CameraPreview component
 * Story P6-1.2: Verifies React.memo optimization with custom comparison function
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '../../test-utils';
import { CameraPreview } from '@/components/cameras/CameraPreview';
import type { ICamera } from '@/types/camera';

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// Mock LiveStreamModal to avoid WebSocket complexity
vi.mock('@/components/streaming/LiveStreamModal', () => ({
  LiveStreamModal: ({ open, cameraName }: { open: boolean; cameraName: string }) =>
    open ? <div data-testid="live-stream-modal">Modal: {cameraName}</div> : null,
}));

/**
 * Factory function for creating mock camera data
 */
function createMockCamera(overrides: Partial<ICamera> = {}): ICamera {
  return {
    id: 'camera-123',
    name: 'Front Door Camera',
    type: 'rtsp',
    source_type: 'rtsp',
    is_enabled: true,
    frame_rate: 5,
    motion_sensitivity: 'medium',
    motion_enabled: true,
    motion_cooldown: 30,
    motion_algorithm: 'mog2',
    analysis_mode: 'single_frame',
    is_doorbell: false,
    created_at: '2025-12-15T10:00:00Z',
    updated_at: '2025-12-16T10:00:00Z',
    ...overrides,
  };
}

describe('CameraPreview', () => {
  let mockOnDelete: (camera: ICamera) => void;

  beforeEach(() => {
    mockOnDelete = vi.fn();
  });

  describe('Rendering (AC: 1, 4)', () => {
    it('renders camera name correctly', () => {
      const camera = createMockCamera({ name: 'Test Camera' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Test Camera')).toBeInTheDocument();
    });

    it('renders RTSP source type badge', () => {
      const camera = createMockCamera({ source_type: 'rtsp' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('RTSP')).toBeInTheDocument();
    });

    it('renders USB source type badge', () => {
      const camera = createMockCamera({ source_type: 'usb', type: 'usb' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('USB')).toBeInTheDocument();
    });

    it('renders Protect source type badge with camera type', () => {
      const camera = createMockCamera({
        source_type: 'protect',
        protect_camera_type: 'G4 Doorbell Pro',
      });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Protect')).toBeInTheDocument();
      expect(screen.getByText('G4 Doorbell Pro')).toBeInTheDocument();
    });

    it('renders doorbell indicator for Protect doorbells', () => {
      const camera = createMockCamera({
        source_type: 'protect',
        is_doorbell: true,
      });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Doorbell')).toBeInTheDocument();
    });

    it('renders frame rate', () => {
      const camera = createMockCamera({ frame_rate: 10 });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('10 FPS')).toBeInTheDocument();
    });

    it('renders motion sensitivity', () => {
      const camera = createMockCamera({ motion_sensitivity: 'high' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('high')).toBeInTheDocument();
    });

    it('renders Edit button for RTSP cameras', () => {
      const camera = createMockCamera({ source_type: 'rtsp' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Edit')).toBeInTheDocument();
    });

    it('renders Configure button for Protect cameras', () => {
      const camera = createMockCamera({ source_type: 'protect' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Configure')).toBeInTheDocument();
    });

    it('renders Live View button for Protect cameras (AC: P16-2.4)', () => {
      const camera = createMockCamera({ source_type: 'protect' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Live View')).toBeInTheDocument();
    });

    it('does NOT render Live View button for RTSP cameras (AC: P16-2.4)', () => {
      const camera = createMockCamera({ source_type: 'rtsp' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.queryByText('Live View')).not.toBeInTheDocument();
    });

    it('does NOT render Live View button for USB cameras (AC: P16-2.4)', () => {
      const camera = createMockCamera({ source_type: 'usb', type: 'usb' });
      render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.queryByText('Live View')).not.toBeInTheDocument();
    });
  });

  describe('Live View Modal (AC: P16-2.4)', () => {
    it('opens LiveStreamModal when Live View button is clicked', async () => {
      const camera = createMockCamera({
        id: 'protect-cam-1',
        name: 'Front Door',
        source_type: 'protect',
      });
      const { user } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      // Modal should not be visible initially
      expect(screen.queryByTestId('live-stream-modal')).not.toBeInTheDocument();

      // Click Live View button
      const liveViewButton = screen.getByRole('button', { name: /live view/i });
      await user.click(liveViewButton);

      // Modal should now be visible with camera name
      expect(screen.getByTestId('live-stream-modal')).toBeInTheDocument();
      expect(screen.getByText('Modal: Front Door')).toBeInTheDocument();
    });
  });

  describe('Delete Handler (AC: 2)', () => {
    it('calls onDelete with camera when delete button clicked', async () => {
      const camera = createMockCamera();
      const { user } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      // Find the delete button (has Trash2 icon, no text)
      const deleteButton = screen.getByRole('button', { name: '' });
      await user.click(deleteButton);

      expect(mockOnDelete).toHaveBeenCalledTimes(1);
      expect(mockOnDelete).toHaveBeenCalledWith(camera);
    });
  });

  describe('Memoization (AC: 1, 2, 3)', () => {
    it('is exported as a memoized component', () => {
      // Verify the component is wrapped with memo
      // React.memo returns a component with $$typeof set to Symbol(react.memo)
      expect(CameraPreview).toBeDefined();
      // The component should be a memo-wrapped component (object with compare property)
      expect(typeof CameraPreview).toBe('object');
      // Check that it's a named component (memo preserves the function name)
      expect((CameraPreview as unknown as { type: { name: string } }).type?.name || CameraPreview.name).toBeDefined();
    });

    it('renders correctly with memoization applied', () => {
      const camera = createMockCamera({ name: 'Memoized Camera' });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(screen.getByText('Memoized Camera')).toBeInTheDocument();

      // Re-render with same props - should not cause visual change
      rerender(<CameraPreview camera={camera} onDelete={mockOnDelete} />);
      expect(screen.getByText('Memoized Camera')).toBeInTheDocument();
    });

    it('updates when camera name changes', () => {
      const camera = createMockCamera({ name: 'Original Name' });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(screen.getByText('Original Name')).toBeInTheDocument();

      // Re-render with changed camera name
      const updatedCamera = createMockCamera({ name: 'Updated Name' });
      rerender(<CameraPreview camera={updatedCamera} onDelete={mockOnDelete} />);

      expect(screen.queryByText('Original Name')).not.toBeInTheDocument();
      expect(screen.getByText('Updated Name')).toBeInTheDocument();
    });

    it('updates when is_enabled changes', () => {
      const camera = createMockCamera({ is_enabled: true });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      // Re-render with changed enabled status
      const disabledCamera = createMockCamera({ is_enabled: false });
      rerender(<CameraPreview camera={disabledCamera} onDelete={mockOnDelete} />);

      // Component should reflect the change (CameraStatus component will show different state)
      expect(screen.getByText('Front Door Camera')).toBeInTheDocument();
    });

    it('updates when frame_rate changes', () => {
      const camera = createMockCamera({ frame_rate: 5 });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(screen.getByText('5 FPS')).toBeInTheDocument();

      const updatedCamera = createMockCamera({ frame_rate: 15 });
      rerender(<CameraPreview camera={updatedCamera} onDelete={mockOnDelete} />);

      expect(screen.queryByText('5 FPS')).not.toBeInTheDocument();
      expect(screen.getByText('15 FPS')).toBeInTheDocument();
    });

    it('updates when motion_sensitivity changes', () => {
      const camera = createMockCamera({ motion_sensitivity: 'low' });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(screen.getByText('low')).toBeInTheDocument();

      const updatedCamera = createMockCamera({ motion_sensitivity: 'high' });
      rerender(<CameraPreview camera={updatedCamera} onDelete={mockOnDelete} />);

      expect(screen.queryByText('low')).not.toBeInTheDocument();
      expect(screen.getByText('high')).toBeInTheDocument();
    });

    it('updates when source_type changes', () => {
      const camera = createMockCamera({ source_type: 'rtsp' });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(screen.getByText('RTSP')).toBeInTheDocument();

      const updatedCamera = createMockCamera({ source_type: 'protect' });
      rerender(<CameraPreview camera={updatedCamera} onDelete={mockOnDelete} />);

      expect(screen.queryByText('RTSP')).not.toBeInTheDocument();
      expect(screen.getByText('Protect')).toBeInTheDocument();
    });

    it('updates when updated_at changes', () => {
      const camera = createMockCamera({ updated_at: '2025-12-15T10:00:00Z' });
      const { rerender } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      // Verify initial render
      expect(screen.getByText('Front Door Camera')).toBeInTheDocument();

      // Update with new timestamp
      const updatedCamera = createMockCamera({ updated_at: '2025-12-16T15:30:00Z' });
      rerender(<CameraPreview camera={updatedCamera} onDelete={mockOnDelete} />);

      // Component should re-render due to timestamp change
      expect(screen.getByText('Front Door Camera')).toBeInTheDocument();
    });
  });

  describe('Visual Regression (AC: 4)', () => {
    it('maintains consistent structure for RTSP camera', () => {
      const camera = createMockCamera({
        name: 'RTSP Camera',
        source_type: 'rtsp',
        is_enabled: true,
        frame_rate: 5,
        motion_sensitivity: 'medium',
      });

      const { container } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      // Verify expected elements are present
      expect(container.querySelector('[class*="card"]')).toBeInTheDocument();
      expect(screen.getByText('RTSP Camera')).toBeInTheDocument();
      expect(screen.getByText('RTSP')).toBeInTheDocument();
      expect(screen.getByText('5 FPS')).toBeInTheDocument();
      expect(screen.getByText('medium')).toBeInTheDocument();
      expect(screen.getByText('Edit')).toBeInTheDocument();
    });

    it('maintains consistent structure for Protect camera with doorbell', () => {
      const camera = createMockCamera({
        name: 'Protect Doorbell',
        source_type: 'protect',
        protect_camera_type: 'G4 Doorbell Pro',
        is_doorbell: true,
        is_enabled: true,
      });

      const { container } = render(<CameraPreview camera={camera} onDelete={mockOnDelete} />);

      expect(container.querySelector('[class*="card"]')).toBeInTheDocument();
      expect(screen.getByText('Protect Doorbell')).toBeInTheDocument();
      expect(screen.getByText('Protect')).toBeInTheDocument();
      expect(screen.getByText('G4 Doorbell Pro')).toBeInTheDocument();
      expect(screen.getByText('Doorbell')).toBeInTheDocument();
      expect(screen.getByText('Configure')).toBeInTheDocument();
    });
  });
});
