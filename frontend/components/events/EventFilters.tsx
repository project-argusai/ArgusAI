/**
 * EventFilters component - sidebar for filtering events
 */

'use client';

import { useState, useEffect } from 'react';
import { Search, X, Calendar, Camera, Tag, Gauge, Shield, Bell, Layers, AlertTriangle } from 'lucide-react';
import type { IEventFilters, DetectedObject, SourceType, SmartDetectionType, AnalysisMode } from '@/types/event';
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

const SOURCE_TYPES: { value: SourceType; label: string }[] = [
  { value: 'protect', label: 'UniFi Protect' },
  { value: 'rtsp', label: 'RTSP' },
  { value: 'usb', label: 'USB' },
];

const SMART_DETECTION_TYPES: { value: SmartDetectionType; label: string; icon?: string }[] = [
  { value: 'ring', label: 'Doorbell Ring' },
  { value: 'person', label: 'Person' },
  { value: 'vehicle', label: 'Vehicle' },
  { value: 'package', label: 'Package' },
  { value: 'animal', label: 'Animal' },
  { value: 'motion', label: 'Motion' },
];

// Story P3-7.6: Analysis mode filter options
const ANALYSIS_MODE_TYPES: { value: AnalysisMode; label: string; description: string }[] = [
  { value: 'single_frame', label: 'Single Frame', description: 'Snapshot analysis' },
  { value: 'multi_frame', label: 'Multi-Frame', description: 'Sequence analysis' },
  { value: 'video_native', label: 'Video Native', description: 'Full video analysis' },
];

// Story P4-7.3: Anomaly severity filter options
type AnomalySeverity = 'low' | 'medium' | 'high';
const ANOMALY_SEVERITY_TYPES: { value: AnomalySeverity; label: string; description: string }[] = [
  { value: 'low', label: 'Normal', description: 'Score < 30%' },
  { value: 'medium', label: 'Unusual', description: 'Score 30-60%' },
  { value: 'high', label: 'Anomaly', description: 'Score > 60%' },
];

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
  const [selectedSources, setSelectedSources] = useState<Set<SourceType>>(
    new Set(filters.source_type ? [filters.source_type] : [])
  );
  const [selectedSmartDetection, setSelectedSmartDetection] = useState<SmartDetectionType | null>(
    filters.smart_detection_type || null
  );
  // Story P3-7.6: Analysis mode filter state
  const [selectedAnalysisMode, setSelectedAnalysisMode] = useState<AnalysisMode | null>(
    filters.analysis_mode || null
  );
  const [hasFallback, setHasFallback] = useState<boolean>(filters.has_fallback || false);
  const [lowConfidenceOnly, setLowConfidenceOnly] = useState<boolean>(filters.low_confidence || false);
  // Story P4-7.3: Anomaly severity filter state
  const [selectedAnomalySeverity, setSelectedAnomalySeverity] = useState<AnomalySeverity | null>(
    filters.anomaly_severity || null
  );

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

  // Handle source type selection
  const handleSourceToggle = (sourceType: SourceType) => {
    const newSelected = new Set(selectedSources);
    if (newSelected.has(sourceType)) {
      newSelected.delete(sourceType);
    } else {
      newSelected.add(sourceType);
    }
    setSelectedSources(newSelected);

    // Pass first selected source as filter (API supports single source)
    onFiltersChange({
      ...filters,
      source_type: newSelected.size > 0 ? Array.from(newSelected)[0] : undefined,
    });
  };

  // Handle smart detection type selection (single select - radio behavior)
  const handleSmartDetectionSelect = (detectionType: SmartDetectionType) => {
    // Toggle off if already selected, otherwise select
    const newValue = selectedSmartDetection === detectionType ? null : detectionType;
    setSelectedSmartDetection(newValue);

    onFiltersChange({
      ...filters,
      smart_detection_type: newValue || undefined,
    });
  };

  // Story P3-7.6: Handle analysis mode selection (single select - radio behavior)
  const handleAnalysisModeSelect = (mode: AnalysisMode) => {
    // Toggle off if already selected, otherwise select
    const newValue = selectedAnalysisMode === mode ? null : mode;
    setSelectedAnalysisMode(newValue);

    onFiltersChange({
      ...filters,
      analysis_mode: newValue || undefined,
    });
  };

  // Story P3-7.6: Handle fallback filter toggle
  const handleFallbackToggle = (checked: boolean) => {
    setHasFallback(checked);
    onFiltersChange({
      ...filters,
      has_fallback: checked || undefined,
    });
  };

  // Story P3-7.6: Handle low confidence filter toggle
  const handleLowConfidenceToggle = (checked: boolean) => {
    setLowConfidenceOnly(checked);
    onFiltersChange({
      ...filters,
      low_confidence: checked || undefined,
    });
  };

  // Story P4-7.3: Handle anomaly severity selection (single select - radio behavior)
  const handleAnomalySeveritySelect = (severity: AnomalySeverity) => {
    // Toggle off if already selected, otherwise select
    const newValue = selectedAnomalySeverity === severity ? null : severity;
    setSelectedAnomalySeverity(newValue);

    onFiltersChange({
      ...filters,
      anomaly_severity: newValue || undefined,
    });
  };

  // Clear all filters
  const handleClearAll = () => {
    setSearchInput('');
    setMinConfidence(0);
    setSelectedCameras(new Set());
    setSelectedObjects(new Set());
    setSelectedSources(new Set());
    setSelectedSmartDetection(null);
    setSelectedAnalysisMode(null);
    setHasFallback(false);
    setLowConfidenceOnly(false);
    setSelectedAnomalySeverity(null);
    setCustomDateRange({ start: '', end: '' });
    onFiltersChange({});
  };

  // Check if any filters are active
  const hasActiveFilters =
    searchInput ||
    minConfidence > 0 ||
    selectedCameras.size > 0 ||
    selectedObjects.size > 0 ||
    selectedSources.size > 0 ||
    selectedSmartDetection !== null ||
    selectedAnalysisMode !== null ||
    hasFallback ||
    lowConfidenceOnly ||
    selectedAnomalySeverity !== null ||
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

      {/* Source Types */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Shield className="w-4 h-4 mr-2" />
          Event Source
        </label>
        <div className="space-y-2">
          {SOURCE_TYPES.map((source) => (
            <div key={source.value} className="flex items-center space-x-2">
              <Checkbox
                id={`source-${source.value}`}
                checked={selectedSources.has(source.value)}
                onCheckedChange={() => handleSourceToggle(source.value)}
              />
              <label
                htmlFor={`source-${source.value}`}
                className="text-sm cursor-pointer flex-1"
              >
                {source.label}
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Smart Detection Types (Protect events) */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Bell className="w-4 h-4 mr-2" />
          Smart Detection
        </label>
        <div className="space-y-2">
          {SMART_DETECTION_TYPES.map((detection) => (
            <div key={detection.value} className="flex items-center space-x-2">
              <Checkbox
                id={`detection-${detection.value}`}
                checked={selectedSmartDetection === detection.value}
                onCheckedChange={() => handleSmartDetectionSelect(detection.value)}
              />
              <label
                htmlFor={`detection-${detection.value}`}
                className={`text-sm cursor-pointer flex-1 ${
                  detection.value === 'ring' ? 'text-cyan-700 font-medium' : ''
                }`}
              >
                {detection.label}
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Story P3-7.6: Analysis Mode Filter */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <Layers className="w-4 h-4 mr-2" />
          Analysis Mode
        </label>
        <div className="space-y-2">
          {ANALYSIS_MODE_TYPES.map((mode) => (
            <div key={mode.value} className="flex items-center space-x-2">
              <Checkbox
                id={`analysis-${mode.value}`}
                checked={selectedAnalysisMode === mode.value}
                onCheckedChange={() => handleAnalysisModeSelect(mode.value)}
              />
              <label
                htmlFor={`analysis-${mode.value}`}
                className="text-sm cursor-pointer flex-1"
              >
                <span>{mode.label}</span>
                <span className="text-xs text-muted-foreground ml-1">({mode.description})</span>
              </label>
            </div>
          ))}
        </div>

        {/* Fallback and Low Confidence filters */}
        <div className="pt-2 border-t border-border space-y-2">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="filter-fallback"
              checked={hasFallback}
              onCheckedChange={(checked) => handleFallbackToggle(checked === true)}
            />
            <label
              htmlFor="filter-fallback"
              className="text-sm cursor-pointer flex-1"
            >
              <span className="text-amber-600">With fallback</span>
              <span className="text-xs text-muted-foreground ml-1">(downgraded mode)</span>
            </label>
          </div>
          <div className="flex items-center space-x-2">
            <Checkbox
              id="filter-low-confidence"
              checked={lowConfidenceOnly}
              onCheckedChange={(checked) => handleLowConfidenceToggle(checked === true)}
            />
            <label
              htmlFor="filter-low-confidence"
              className="text-sm cursor-pointer flex-1 flex items-center"
            >
              <AlertTriangle className="w-3 h-3 mr-1 text-orange-500" />
              <span className="text-orange-600">Low confidence</span>
              <span className="text-xs text-muted-foreground ml-1">(uncertain)</span>
            </label>
          </div>
        </div>
      </div>

      {/* Story P4-7.3: Anomaly Severity Filter */}
      <div className="space-y-3">
        <label className="flex items-center text-sm font-medium">
          <AlertTriangle className="w-4 h-4 mr-2" />
          Anomaly Level
        </label>
        <div className="space-y-2">
          {ANOMALY_SEVERITY_TYPES.map((severity) => (
            <div key={severity.value} className="flex items-center space-x-2">
              <Checkbox
                id={`anomaly-${severity.value}`}
                checked={selectedAnomalySeverity === severity.value}
                onCheckedChange={() => handleAnomalySeveritySelect(severity.value)}
              />
              <label
                htmlFor={`anomaly-${severity.value}`}
                className={`text-sm cursor-pointer flex-1 ${
                  severity.value === 'high' ? 'text-red-600 font-medium' :
                  severity.value === 'medium' ? 'text-amber-600 font-medium' : ''
                }`}
              >
                <span>{severity.label}</span>
                <span className="text-xs text-muted-foreground ml-1">({severity.description})</span>
              </label>
            </div>
          ))}
        </div>
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
