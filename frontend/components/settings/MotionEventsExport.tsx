/**
 * Motion Events Export Component (Story P6-4.2)
 *
 * Features:
 * - Date range picker for filtering export data
 * - Camera selector dropdown with "All Cameras" default
 * - Export CSV button with loading state
 * - Success/error toast notifications
 */

'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  Download,
  Loader2,
  Calendar as CalendarIcon,
  ChevronDown,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

interface DateRange {
  from: Date | undefined;
  to: Date | undefined;
}

export function MotionEventsExport() {
  const [dateRange, setDateRange] = useState<DateRange>({
    from: undefined,
    to: undefined,
  });
  const [selectedCameraId, setSelectedCameraId] = useState<string>('all');
  const [isExporting, setIsExporting] = useState(false);

  // Fetch cameras for the dropdown
  const camerasQuery = useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiClient.cameras.list(),
  });

  const cameras = camerasQuery.data || [];

  const handleExport = async () => {
    try {
      setIsExporting(true);

      // Build query params
      const params = new URLSearchParams();
      params.set('format', 'csv');

      if (dateRange.from) {
        params.set('start_date', format(dateRange.from, 'yyyy-MM-dd'));
      }
      if (dateRange.to) {
        params.set('end_date', format(dateRange.to, 'yyyy-MM-dd'));
      }
      if (selectedCameraId && selectedCameraId !== 'all') {
        params.set('camera_id', selectedCameraId);
      }

      // Make the API request
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/motion-events/export?${params.toString()}`,
        {
          method: 'GET',
          headers: {
            'Accept': 'text/csv',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'motion_events.csv';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=([^;]+)/);
        if (match) {
          filename = match[1].trim();
        }
      }

      // Convert response to blob and trigger download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success(`Motion events exported successfully: ${filename}`);
    } catch (error) {
      console.error('Export failed:', error);
      toast.error(
        error instanceof Error
          ? `Export failed: ${error.message}`
          : 'Failed to export motion events. Please try again.'
      );
    } finally {
      setIsExporting(false);
    }
  };

  const formatDateRangeLabel = () => {
    if (dateRange.from && dateRange.to) {
      return `${format(dateRange.from, 'MMM d, yyyy')} - ${format(dateRange.to, 'MMM d, yyyy')}`;
    }
    if (dateRange.from) {
      return `${format(dateRange.from, 'MMM d, yyyy')} - ...`;
    }
    return 'Select date range';
  };

  const clearDateRange = () => {
    setDateRange({ from: undefined, to: undefined });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Download className="h-5 w-5" aria-hidden="true" />
          Motion Events Export
        </CardTitle>
        <CardDescription>
          Export raw motion detection data to CSV for external analysis
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Date Range Picker */}
        <div className="space-y-2">
          <Label>Date Range (Optional)</Label>
          <div className="flex items-center gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    'w-full justify-start text-left font-normal',
                    !dateRange.from && !dateRange.to && 'text-muted-foreground'
                  )}
                  aria-label="Select date range"
                >
                  <CalendarIcon className="mr-2 h-4 w-4" aria-hidden="true" />
                  {formatDateRangeLabel()}
                  <ChevronDown className="ml-auto h-4 w-4 opacity-50" aria-hidden="true" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="range"
                  defaultMonth={dateRange.from}
                  selected={{ from: dateRange.from, to: dateRange.to }}
                  onSelect={(range) => {
                    setDateRange({
                      from: range?.from,
                      to: range?.to,
                    });
                  }}
                  numberOfMonths={2}
                  disabled={{ after: new Date() }}
                />
                <div className="p-3 border-t">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearDateRange}
                    className="w-full"
                  >
                    Clear dates
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
          </div>
          <p className="text-xs text-muted-foreground">
            Leave empty to export all motion events
          </p>
        </div>

        {/* Camera Selector */}
        <div className="space-y-2">
          <Label htmlFor="camera-select">Camera (Optional)</Label>
          <Select
            value={selectedCameraId}
            onValueChange={setSelectedCameraId}
          >
            <SelectTrigger id="camera-select" aria-label="Select camera">
              <SelectValue placeholder="All Cameras" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Cameras</SelectItem>
              {cameras.map((camera) => (
                <SelectItem key={camera.id} value={camera.id}>
                  {camera.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Filter by a specific camera or export from all cameras
          </p>
        </div>

        {/* Export Button */}
        <Button
          onClick={handleExport}
          disabled={isExporting}
          className="w-full"
          aria-label="Export motion events to CSV"
        >
          {isExporting ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
              Exporting...
            </>
          ) : (
            <>
              <Download className="h-4 w-4 mr-2" aria-hidden="true" />
              Export CSV
            </>
          )}
        </Button>

        <p className="text-xs text-muted-foreground text-center">
          CSV columns: timestamp, camera_id, camera_name, confidence, algorithm, x, y, width, height, zone_id
        </p>
      </CardContent>
    </Card>
  );
}
