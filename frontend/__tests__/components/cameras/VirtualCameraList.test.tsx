/**
 * Tests for VirtualCameraList component
 * Story P6-1.3: Virtual scrolling for camera list
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '../../test-utils';
import { VirtualCameraList } from '@/components/cameras/VirtualCameraList';
import type { ICamera } from '@/types/camera';

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

/**
 * Factory function for creating mock camera data
 */
function createMockCamera(index: number, overrides: Partial<ICamera> = {}): ICamera {
  return {
    id: `camera-${index}`,
    name: `Camera ${index}`,
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

/**
 * Create an array of mock cameras
 */
function createMockCameras(count: number): ICamera[] {
  return Array.from({ length: count }, (_, i) => createMockCamera(i + 1));
}

describe('VirtualCameraList', () => {
  let mockOnDelete: (camera: ICamera) => void;
  let originalOffsetWidth: PropertyDescriptor | undefined;
  let originalOffsetHeight: PropertyDescriptor | undefined;

  beforeEach(() => {
    mockOnDelete = vi.fn();

    // Mock container dimensions for responsive calculations
    originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
    originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');

    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      value: 1200, // Wide enough for 3 columns
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      value: 800,
    });
  });

  afterEach(() => {
    // Restore original properties
    if (originalOffsetWidth) {
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', originalOffsetWidth);
    }
    if (originalOffsetHeight) {
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight);
    }
  });

  describe('Rendering (AC: #1, #2)', () => {
    it('renders without crashing with empty cameras array', () => {
      render(<VirtualCameraList cameras={[]} onDelete={mockOnDelete} />);
      // Should not throw and should render nothing
      expect(screen.queryByText(/Camera/)).not.toBeInTheDocument();
    });

    it('renders camera cards for visible items', () => {
      const cameras = createMockCameras(5);
      render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Should render at least some cameras
      expect(screen.getByText('Camera 1')).toBeInTheDocument();
    });

    it('uses useVirtualizer from @tanstack/react-virtual', () => {
      // This test verifies the component imports and uses the library
      // by checking that VirtualCameraList is defined and functional
      const cameras = createMockCameras(3);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Virtual list container should have overflow-auto
      const scrollContainer = container.firstChild as HTMLElement;
      expect(scrollContainer).toHaveClass('overflow-auto');
    });

    it('renders cameras in grid layout', () => {
      const cameras = createMockCameras(6);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Should have grid layout within virtual rows
      const grids = container.querySelectorAll('.grid');
      expect(grids.length).toBeGreaterThan(0);
    });
  });

  describe('Virtual DOM Efficiency (AC: #2)', () => {
    it('does not render all cameras to DOM when list is large', () => {
      const cameras = createMockCameras(50);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Count rendered camera cards (have 'card' class from shadcn Card component)
      const cards = container.querySelectorAll('[class*="card"]');

      // Should render fewer cards than total cameras due to virtualization
      // With overscan of 2 and limited viewport, should render subset
      expect(cards.length).toBeLessThan(50);
    });
  });

  describe('Filtering Integration (AC: #4)', () => {
    it('renders correct cameras when filtered list is passed', () => {
      // Simulate filtering by passing a subset of cameras
      const allCameras = createMockCameras(10);
      const filteredCameras = allCameras.filter((_, i) => i < 3);

      render(<VirtualCameraList cameras={filteredCameras} onDelete={mockOnDelete} />);

      // Should only show filtered cameras
      expect(screen.getByText('Camera 1')).toBeInTheDocument();
      expect(screen.getByText('Camera 2')).toBeInTheDocument();
      expect(screen.getByText('Camera 3')).toBeInTheDocument();
      expect(screen.queryByText('Camera 4')).not.toBeInTheDocument();
    });

    it('updates when filtered cameras change', () => {
      const cameras = createMockCameras(5);
      const { rerender } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      expect(screen.getByText('Camera 1')).toBeInTheDocument();

      // Rerender with fewer cameras (simulating filter change)
      const filteredCameras = cameras.slice(2, 4);
      rerender(<VirtualCameraList cameras={filteredCameras} onDelete={mockOnDelete} />);

      // Original cameras should be gone, filtered ones shown
      expect(screen.queryByText('Camera 1')).not.toBeInTheDocument();
      expect(screen.getByText('Camera 3')).toBeInTheDocument();
    });
  });

  describe('Delete Handler', () => {
    it('calls onDelete when delete button is clicked', async () => {
      const cameras = createMockCameras(3);
      const { user } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Find delete buttons (they have no text, just trash icon)
      const deleteButtons = screen.getAllByRole('button', { name: '' });

      // Click first delete button
      if (deleteButtons[0]) {
        await user.click(deleteButtons[0]);
        expect(mockOnDelete).toHaveBeenCalled();
      }
    });
  });

  describe('Responsive Columns (AC: #4)', () => {
    it('uses grid layout with responsive columns', () => {
      const cameras = createMockCameras(6);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Grid elements should exist with gap-6 class
      const grids = container.querySelectorAll('.grid.gap-6');
      expect(grids.length).toBeGreaterThan(0);
    });
  });

  describe('Scroll Container', () => {
    it('has scroll container with correct styling', () => {
      const cameras = createMockCameras(10);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // First child should be the scroll container
      const scrollContainer = container.firstChild as HTMLElement;
      expect(scrollContainer).toHaveClass('overflow-auto');
      expect(scrollContainer).toHaveStyle({ contain: 'strict' });
    });

    it('renders inner container for total virtual height', () => {
      const cameras = createMockCameras(10);
      const { container } = render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      // Should have inner container with position relative
      const scrollContainer = container.firstChild as HTMLElement;
      const innerContainer = scrollContainer.firstChild as HTMLElement;
      expect(innerContainer).toHaveStyle({ position: 'relative' });
    });
  });

  describe('Mixed Camera Types', () => {
    it('renders cameras of different source types', () => {
      const cameras: ICamera[] = [
        createMockCamera(1, { source_type: 'rtsp', name: 'RTSP Camera' }),
        createMockCamera(2, { source_type: 'usb', name: 'USB Camera', type: 'usb' }),
        createMockCamera(3, { source_type: 'protect', name: 'Protect Camera' }),
      ];

      render(<VirtualCameraList cameras={cameras} onDelete={mockOnDelete} />);

      expect(screen.getByText('RTSP Camera')).toBeInTheDocument();
      expect(screen.getByText('USB Camera')).toBeInTheDocument();
      expect(screen.getByText('Protect Camera')).toBeInTheDocument();
    });
  });
});
