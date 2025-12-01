/**
 * Event Type Filter Component
 * Story P2-2.3: Implement Per-Camera Event Type Filtering
 *
 * Allows users to configure which event types each camera should analyze.
 * Features:
 * - Checkbox options for Person, Vehicle, Package, Animal, All Motion
 * - "All Motion" mutual exclusivity (disables other options when checked)
 * - Apply/Cancel buttons for saving or reverting changes
 * - Loading state while saving
 *
 * AC1: Popover opens on "Configure Filters" click
 * AC2: All filter options with correct defaults
 * AC3: "All Motion" disables and unchecks other options
 * AC4: "All Motion" unchecked re-enables other options
 * AC5: Apply saves, Cancel reverts
 * AC10: Loading state while saving
 */

'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Settings2, Loader2 } from 'lucide-react';

import { apiClient, type ProtectDiscoveredCamera } from '@/lib/api-client';

// Default filter types (same as backend defaults)
const DEFAULT_FILTERS = ['person', 'vehicle', 'package'];

// All available filter types (excluding 'motion' which is special)
const SMART_DETECTION_TYPES = [
  { id: 'person', label: 'Person', defaultChecked: true },
  { id: 'vehicle', label: 'Vehicle', defaultChecked: true },
  { id: 'package', label: 'Package', defaultChecked: true },
  { id: 'animal', label: 'Animal', defaultChecked: false },
] as const;

export interface EventTypeFilterProps {
  camera: ProtectDiscoveredCamera;
  controllerId: string;
  /** Current filters from camera record (if enabled) */
  currentFilters?: string[];
  onSave?: () => void;
  onCancel?: () => void;
}

export function EventTypeFilter({
  camera,
  controllerId,
  currentFilters,
  onSave,
  onCancel,
}: EventTypeFilterProps) {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);

  // Initialize local state from current filters or defaults
  const initialFilters = currentFilters ?? DEFAULT_FILTERS;
  const initialAllMotion = initialFilters.includes('motion') || initialFilters.length === 0;

  const [selectedFilters, setSelectedFilters] = useState<Set<string>>(
    new Set(initialAllMotion ? [] : initialFilters.filter(f => f !== 'motion'))
  );
  const [allMotion, setAllMotion] = useState(initialAllMotion);

  // Reset local state when popover opens (AC5 - Cancel reverts to saved state)
  useEffect(() => {
    if (isOpen) {
      const filters = currentFilters ?? DEFAULT_FILTERS;
      const isAllMotion = filters.includes('motion') || filters.length === 0;
      setAllMotion(isAllMotion);
      setSelectedFilters(
        new Set(isAllMotion ? [] : filters.filter(f => f !== 'motion'))
      );
    }
  }, [isOpen, currentFilters]);

  // Mutation for updating filters
  const filterMutation = useMutation({
    mutationFn: (filters: string[]) =>
      apiClient.protect.updateCameraFilters(controllerId, camera.protect_camera_id, {
        smart_detection_types: filters,
      }),
    onSuccess: () => {
      toast.success('Filters updated');
      // Invalidate camera list to refresh with new filters
      queryClient.invalidateQueries({ queryKey: ['protect-cameras', controllerId] });
      setIsOpen(false);
      onSave?.();
    },
    onError: () => {
      toast.error('Failed to update filters');
    },
  });

  // Handle "All Motion" toggle (AC3, AC4)
  const handleAllMotionChange = (checked: boolean | 'indeterminate') => {
    if (checked === 'indeterminate') return;

    setAllMotion(checked);
    if (checked) {
      // AC3: When checked, clear other selections (they'll be disabled)
      setSelectedFilters(new Set());
    }
    // AC4: When unchecked, other options are re-enabled (handled by disabled prop)
  };

  // Handle individual filter toggle
  const handleFilterChange = (filterId: string, checked: boolean | 'indeterminate') => {
    if (checked === 'indeterminate') return;

    setSelectedFilters(prev => {
      const next = new Set(prev);
      if (checked) {
        next.add(filterId);
      } else {
        next.delete(filterId);
      }
      return next;
    });
  };

  // Handle Apply button (AC5)
  const handleApply = () => {
    const filters = allMotion ? ['motion'] : Array.from(selectedFilters);
    filterMutation.mutate(filters);
  };

  // Handle Cancel button (AC5)
  const handleCancel = () => {
    setIsOpen(false);
    onCancel?.();
  };

  // Get filter count for badge display (AC8)
  const getFilterCount = () => {
    if (allMotion) return 'All Motion';
    const count = selectedFilters.size;
    if (count === 0) return 'No filters';
    return `${count} filter${count === 1 ? '' : 's'}`;
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={!camera.is_enabled_for_ai}
          className="gap-1"
        >
          <Settings2 className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Filters</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="end">
        <div className="space-y-4">
          {/* Header */}
          <div className="font-medium">Event Types to Analyze</div>
          <div className="border-t" />

          {/* Smart Detection Checkboxes (AC2) */}
          <div className="space-y-3">
            {SMART_DETECTION_TYPES.map((filter) => (
              <div key={filter.id} className="flex items-center space-x-2">
                <Checkbox
                  id={`filter-${filter.id}`}
                  checked={selectedFilters.has(filter.id)}
                  onCheckedChange={(checked) => handleFilterChange(filter.id, checked)}
                  disabled={allMotion} // AC3: Disabled when All Motion is checked
                />
                <Label
                  htmlFor={`filter-${filter.id}`}
                  className={allMotion ? 'text-muted-foreground' : ''}
                >
                  {filter.label}
                </Label>
              </div>
            ))}
          </div>

          {/* All Motion Checkbox (AC2, AC3, AC4) */}
          <div className="space-y-1.5">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="filter-all-motion"
                checked={allMotion}
                onCheckedChange={handleAllMotionChange}
              />
              <Label htmlFor="filter-all-motion">All Motion</Label>
            </div>
            {/* Helper text (AC3) */}
            <p className="text-xs text-muted-foreground pl-6">
              Analyzes all motion events, ignores smart detection filtering
            </p>
          </div>

          <div className="border-t" />

          {/* Action Buttons (AC5, AC10) */}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={filterMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              disabled={filterMutation.isPending}
            >
              {filterMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  Saving...
                </>
              ) : (
                'Apply'
              )}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Helper to get filter display text for camera card badge (AC8)
 */
export function getFilterDisplayText(filters: string[] | undefined): string {
  if (!filters || filters.length === 0) {
    return 'All Motion';
  }
  if (filters.includes('motion')) {
    return 'All Motion';
  }
  if (filters.length === 1) {
    return capitalize(filters[0]);
  }
  if (filters.length <= 3) {
    return filters.map(capitalize).join(', ');
  }
  return `${filters.length} filters`;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
