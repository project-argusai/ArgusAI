/**
 * EventFilters component - sidebar for filtering events
 */

'use client';

import { useState, useEffect } from 'react';
import { Search, X, Calendar, Camera, Tag, Gauge } from 'lucide-react';
import type { IEventFilters, DetectedObject } from '@/types/event';
import type { ICamera } from '@/types/camera';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Card } from '@/components/ui/card';
import { useDebounce } from '@/lib/hooks/useDebounce';

interface EventFiltersProps {
  filters: IEventFilters;
  onFiltersChange: (filters: IEventFilters) => void;
  cameras: ICamera[];
}

const OBJECT_TYPES: DetectedObject[] = ['person', 'vehicle', 'animal', 'package', 'unknown'];

const DATE_PRESETS = [
  { label: 'Last 24 hours', value: 24 },
  { label: 'Last 7 days', value: 24 * 7 },
  { label: 'Last 30 days', value: 24 * 30 },
] as const;

export function EventFilters({ filters, onFiltersChange, cameras }: EventFiltersProps) {
  const [searchInput, setSearchInput] = useState(filters.search || '');
  const [minConfidence, setMinConfidence] = useState(filters.min_confidence || 0);
  const [selectedCameras, setSelectedCameras] = useState<Set<string>>(
    new Set(filters.camera_id ? [filters.camera_id] : [])
  );
  const [selectedObjects, setSelectedObjects] = useState<Set<string>>(
    new Set(filters.objects || [])
  );
  const [customDateRange, setCustomDateRange] = useState({
    start: filters.start_date || '',
    end: filters.end_date || '',
  });

  // Debounce search input
  const debouncedSearch = useDebounce(searchInput, 500);

  // Update filters when debounced search changes
  useEffect(() => {
    onFiltersChange({
      ...filters,
      search: debouncedSearch || undefined,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  // Handle date preset selection
  const handleDatePreset = (hoursAgo: number) => {
    const now = new Date();
    const startDate = new Date(now.getTime() - hoursAgo * 60 * 60 * 1000);

    onFiltersChange({
      ...filters,
      start_date: startDate.toISOString(),
      end_date: now.toISOString(),
    });

    setCustomDateRange({
      start: startDate.toISOString().slice(0, 16),
      end: now.toISOString().slice(0, 16),
    });
  };

  // Handle custom date range
  const handleCustomDateChange = (field: 'start' | 'end', value: string) => {
    const newDateRange = { ...customDateRange, [field]: value };
    setCustomDateRange(newDateRange);

    if (newDateRange.start && newDateRange.end) {
      onFiltersChange({
        ...filters,
        start_date: new Date(newDateRange.start).toISOString(),
        end_date: new Date(newDateRange.end).toISOString(),
      });
    }
  };

  // Handle camera selection
  const handleCameraToggle = (cameraId: string) => {
    const newSelected = new Set(selectedCameras);
    if (newSelected.has(cameraId)) {
      newSelected.delete(cameraId);
    } else {
      newSelected.add(cameraId);
    }
    setSelectedCameras(newSelected);

    // Only set camera_id if exactly one camera is selected (API limitation)
    onFiltersChange({
      ...filters,
      camera_id: newSelected.size === 1 ? Array.from(newSelected)[0] : undefined,
    });
  };

  // Handle object type selection
  const handleObjectToggle = (objectType: string) => {
    const newSelected = new Set(selectedObjects);
    if (newSelected.has(objectType)) {
      newSelected.delete(objectType);
    } else {
      newSelected.add(objectType);
    }
    setSelectedObjects(newSelected);

    onFiltersChange({
      ...filters,
      objects: newSelected.size > 0 ? Array.from(newSelected) : undefined,
    });
  };

  // Handle confidence slider
  const handleConfidenceChange = (value: number[]) => {
    const newConfidence = value[0];
    setMinConfidence(newConfidence);

    onFiltersChange({
      ...filters,
      min_confidence: newConfidence > 0 ? newConfidence : undefined,
    });
  };

  // Clear all filters
  const handleClearAll = () => {
    setSearchInput('');
    setMinConfidence(0);
    setSelectedCameras(new Set());
    setSelectedObjects(new Set());
    setCustomDateRange({ start: '', end: '' });
    onFiltersChange({});
  };

  // Check if any filters are active
  const hasActiveFilters =
    searchInput ||
    minConfidence > 0 ||
    selectedCameras.size > 0 ||
    selectedObjects.size > 0 ||
    customDateRange.start ||
    customDateRange.end;

  return (
    <Card className="p-4 space-y-6">
      {/* Header with Clear All */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Filters</h2>
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={handleClearAll}>
            <X className="w-4 h-4 mr-1" />
            Clear all
          </Button>
        )}
      </div>

      {/* Search */}
      <div className="space-y-2">
        <label className="flex items-center text-sm font-medium">
          <Search className="w-4 h-4 mr-2" />
          Search
        </label>
        <Input
          type="text"
          placeholder="Search descriptions..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="w-full"
        />
      </div>

      {/* Date Range */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Calendar className="w-4 h-4 mr-2" />
          Date Range
        </label>

        {/* Quick presets */}
        <div className="flex flex-col gap-2">
          {DATE_PRESETS.map((preset) => (
            <Button
              key={preset.value}
              variant="outline"
              size="sm"
              onClick={() => handleDatePreset(preset.value)}
              className="w-full justify-start"
            >
              {preset.label}
            </Button>
          ))}
        </div>

        {/* Custom date range */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Custom Range</label>
          <Input
            type="datetime-local"
            value={customDateRange.start}
            onChange={(e) => handleCustomDateChange('start', e.target.value)}
            className="w-full text-sm"
          />
          <Input
            type="datetime-local"
            value={customDateRange.end}
            onChange={(e) => handleCustomDateChange('end', e.target.value)}
            className="w-full text-sm"
          />
        </div>
      </div>

      {/* Camera Filter */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Camera className="w-4 h-4 mr-2" />
          Cameras {selectedCameras.size > 1 && '(Select only 1)'}
        </label>
        {cameras.length === 0 ? (
          <p className="text-xs text-muted-foreground">No cameras available</p>
        ) : (
          <div className="space-y-2">
            {cameras.map((camera) => (
              <div key={camera.id} className="flex items-center space-x-2">
                <Checkbox
                  id={`camera-${camera.id}`}
                  checked={selectedCameras.has(camera.id)}
                  onCheckedChange={() => handleCameraToggle(camera.id)}
                />
                <label
                  htmlFor={`camera-${camera.id}`}
                  className="text-sm cursor-pointer flex-1"
                >
                  {camera.name}
                </label>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Object Types */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Tag className="w-4 h-4 mr-2" />
          Object Types
        </label>
        <div className="space-y-2">
          {OBJECT_TYPES.map((objType) => (
            <div key={objType} className="flex items-center space-x-2">
              <Checkbox
                id={`object-${objType}`}
                checked={selectedObjects.has(objType)}
                onCheckedChange={() => handleObjectToggle(objType)}
              />
              <label
                htmlFor={`object-${objType}`}
                className="text-sm cursor-pointer flex-1 capitalize"
              >
                {objType}
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Confidence Slider */}
      <div className="space-y-3">
        <label className="flex items-center justify-between text-sm font-medium">
          <span className="flex items-center">
            <Gauge className="w-4 h-4 mr-2" />
            Min Confidence
          </span>
          <span className="text-blue-600">{minConfidence}%</span>
        </label>
        <Slider
          value={[minConfidence]}
          onValueChange={handleConfidenceChange}
          min={0}
          max={100}
          step={5}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
    </Card>
  );
}
