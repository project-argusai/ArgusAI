/**
 * Virtual camera list component
 * Uses @tanstack/react-virtual for efficient rendering of large camera lists
 * Story P6-1.3: Implement virtual scrolling for 20+ cameras
 */

'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { CameraPreview } from './CameraPreview';
import type { ICamera } from '@/types/camera';

interface VirtualCameraListProps {
  /**
   * Array of cameras to display
   */
  cameras: ICamera[];
  /**
   * Delete button click handler
   */
  onDelete: (camera: ICamera) => void;
}

/**
 * Hook to calculate responsive column count based on container width
 * Matches Tailwind breakpoints: 1 col < 768px, 2 col 768-1024px, 3 col >= 1024px
 * Recalculates on window resize
 */
function useColumnCount(containerRef: React.RefObject<HTMLDivElement | null>) {
  const calculateColumnCount = useCallback(() => {
    if (!containerRef.current) return 1;
    const width = containerRef.current.offsetWidth;
    if (width >= 1024) return 3; // lg breakpoint
    if (width >= 768) return 2;  // md breakpoint
    return 1;
  }, [containerRef]);

  // Initialize with calculated value
  const [columnCount, setColumnCount] = useState(() => {
    // This will return 1 on first render before ref is attached
    // The effect below will update it once mounted
    return calculateColumnCount();
  });

  useEffect(() => {
    // Handle resize events
    const handleResize = () => {
      setColumnCount(calculateColumnCount());
    };

    // Calculate on mount (ref may not be available during useState init)
    handleResize();

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [calculateColumnCount]);

  return columnCount;
}

/**
 * Estimated card height in pixels
 * Includes card content (~180px) + gap (24px)
 */
const ESTIMATED_CARD_HEIGHT = 220;

/**
 * Number of rows to render outside the visible area for smooth scrolling
 */
const OVERSCAN = 2;

/**
 * Virtual camera list with efficient rendering
 * Only renders visible camera cards to DOM
 */
export function VirtualCameraList({ cameras, onDelete }: VirtualCameraListProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const columnCount = useColumnCount(parentRef);

  // Group cameras into rows based on column count
  const rows: ICamera[][] = [];
  for (let i = 0; i < cameras.length; i += columnCount) {
    rows.push(cameras.slice(i, i + columnCount));
  }

  // Virtual row count for the virtualizer
  const rowCount = rows.length;

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ESTIMATED_CARD_HEIGHT,
    overscan: OVERSCAN,
  });

  const virtualRows = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  // If no cameras, don't render anything (parent handles empty state)
  if (cameras.length === 0) {
    return null;
  }

  return (
    <div
      ref={parentRef}
      className="h-[calc(100vh-280px)] overflow-auto"
      style={{ contain: 'strict' }}
    >
      <div
        style={{
          height: `${totalSize}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualRows.map((virtualRow) => {
          const rowCameras = rows[virtualRow.index];

          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <div
                className="grid gap-6"
                style={{
                  gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
                }}
              >
                {rowCameras.map((camera) => (
                  <CameraPreview
                    key={camera.id}
                    camera={camera}
                    onDelete={onDelete}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
