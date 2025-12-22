/**
 * Accuracy Dashboard Component
 * Story P4-5.3: Accuracy Dashboard
 *
 * Displays AI description accuracy metrics with:
 * - Overall accuracy stats
 * - Per-camera breakdown table
 * - Daily trend chart
 * - Top corrections list
 * - Filtering and CSV export
 */

'use client';

import { useState, useMemo } from 'react';
import { format, subDays } from 'date-fns';
import {
  ThumbsUp,
  ThumbsDown,
  BarChart3,
  TrendingUp,
  Filter,
  Download,
  Calendar,
  Camera,
  FileText,  // Story P9-3.6
} from 'lucide-react';

import { useFeedbackStats } from '@/hooks/useFeedbackStats';
import { useCameras } from '@/hooks/useCameras';
import type { IFeedbackStats } from '@/types/event';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { CameraAccuracyTable } from './CameraAccuracyTable';
import { AccuracyTrendChart } from './AccuracyTrendChart';
import { TopCorrections } from './TopCorrections';
import { PromptInsights } from './PromptInsights';  // Story P4-5.4

// Period options for date filtering
type PeriodOption = '7d' | '30d' | '90d' | 'all';

interface PeriodConfig {
  label: string;
  getStartDate: () => string | undefined;
}

const PERIOD_OPTIONS: Record<PeriodOption, PeriodConfig> = {
  '7d': {
    label: 'Last 7 Days',
    getStartDate: () => format(subDays(new Date(), 7), 'yyyy-MM-dd'),
  },
  '30d': {
    label: 'Last 30 Days',
    getStartDate: () => format(subDays(new Date(), 30), 'yyyy-MM-dd'),
  },
  '90d': {
    label: 'Last 90 Days',
    getStartDate: () => format(subDays(new Date(), 90), 'yyyy-MM-dd'),
  },
  all: {
    label: 'All Time',
    getStartDate: () => undefined,
  },
};

// Accuracy color thresholds
const getAccuracyColor = (rate: number): string => {
  if (rate >= 80) return 'text-green-600 bg-green-50 border-green-200';
  if (rate >= 60) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
  return 'text-red-600 bg-red-50 border-red-200';
};

const getAccuracyBgColor = (rate: number): string => {
  if (rate >= 80) return 'bg-green-500';
  if (rate >= 60) return 'bg-yellow-500';
  return 'bg-red-500';
};

// CSV export utility
function exportToCSV(stats: IFeedbackStats, period: string) {
  const rows: string[][] = [
    ['AI Feedback Statistics Export'],
    [`Generated: ${new Date().toISOString()}`],
    [`Period: ${period}`],
    [],
    ['Overall Statistics'],
    ['Metric', 'Value'],
    ['Total Feedback', stats.total_count.toString()],
    ['Helpful', stats.helpful_count.toString()],
    ['Not Helpful', stats.not_helpful_count.toString()],
    ['Accuracy Rate', `${stats.accuracy_rate.toFixed(1)}%`],
    [],
    ['Per-Camera Breakdown'],
    ['Camera', 'Helpful', 'Not Helpful', 'Accuracy Rate'],
  ];

  Object.values(stats.feedback_by_camera).forEach((camera) => {
    rows.push([
      camera.camera_name,
      camera.helpful_count.toString(),
      camera.not_helpful_count.toString(),
      `${camera.accuracy_rate.toFixed(1)}%`,
    ]);
  });

  rows.push([]);
  rows.push(['Daily Trend']);
  rows.push(['Date', 'Helpful', 'Not Helpful']);
  stats.daily_trend.forEach((day) => {
    rows.push([day.date, day.helpful_count.toString(), day.not_helpful_count.toString()]);
  });

  rows.push([]);
  rows.push(['Top Corrections']);
  rows.push(['Correction', 'Count']);
  stats.top_corrections.forEach((correction) => {
    rows.push([`"${correction.correction_text.replace(/"/g, '""')}"`, correction.count.toString()]);
  });

  const csvContent = rows.map((r) => r.join(',')).join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `ai-accuracy-stats-${format(new Date(), 'yyyy-MM-dd')}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function AccuracyDashboard() {
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption>('30d');
  const [selectedCamera, setSelectedCamera] = useState<string>('all');

  // Get cameras list for filter dropdown
  const { cameras } = useCameras();

  // Build query params
  const queryParams = useMemo(() => {
    const params: { camera_id?: string; start_date?: string; end_date?: string } = {};

    const startDate = PERIOD_OPTIONS[selectedPeriod].getStartDate();
    if (startDate) {
      params.start_date = startDate;
    }

    if (selectedCamera !== 'all') {
      params.camera_id = selectedCamera;
    }

    return params;
  }, [selectedPeriod, selectedCamera]);

  const { data: stats, isLoading, error } = useFeedbackStats(queryParams);

  // Handle reset filters
  const handleResetFilters = () => {
    setSelectedPeriod('30d');
    setSelectedCamera('all');
  };

  // Handle export
  const handleExport = () => {
    if (stats) {
      exportToCSV(stats, PERIOD_OPTIONS[selectedPeriod].label);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row justify-between gap-4">
          <Skeleton className="h-10 w-48" />
          <div className="flex gap-2">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-24" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center text-destructive">
            <p className="font-medium">Failed to load feedback statistics</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error instanceof Error ? error.message : 'Unknown error occurred'}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Empty state
  if (!stats || stats.total_count === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <BarChart3 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No Feedback Data Yet</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              Feedback statistics will appear here once users start rating AI descriptions.
              Use the thumbs up/down buttons on event cards to provide feedback.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with filters */}
      <div className="flex flex-col sm:flex-row justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            AI Accuracy Dashboard
          </h2>
          <p className="text-sm text-muted-foreground">
            Monitor AI description quality based on user feedback
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Period filter */}
          <Select value={selectedPeriod} onValueChange={(v) => setSelectedPeriod(v as PeriodOption)}>
            <SelectTrigger className="w-36">
              <Calendar className="h-4 w-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(PERIOD_OPTIONS).map(([key, config]) => (
                <SelectItem key={key} value={key}>
                  {config.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Camera filter */}
          <Select value={selectedCamera} onValueChange={setSelectedCamera}>
            <SelectTrigger className="w-40">
              <Camera className="h-4 w-4 mr-2" />
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

          {/* Reset filters */}
          {(selectedPeriod !== '30d' || selectedCamera !== 'all') && (
            <Button variant="outline" size="sm" onClick={handleResetFilters}>
              <Filter className="h-4 w-4 mr-1" />
              Reset
            </Button>
          )}

          {/* Export button */}
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Accuracy Rate */}
        <Card className={`border-2 ${getAccuracyColor(stats.accuracy_rate)}`}>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Accuracy Rate
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold">{stats.accuracy_rate.toFixed(1)}%</span>
              <div className={`h-2 w-2 rounded-full ${getAccuracyBgColor(stats.accuracy_rate)}`} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {stats.accuracy_rate >= 80 ? 'Excellent' : stats.accuracy_rate >= 60 ? 'Good' : 'Needs improvement'}
            </p>
          </CardContent>
        </Card>

        {/* Total Feedback */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Total Feedback
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span className="text-3xl font-bold">{stats.total_count.toLocaleString()}</span>
            <p className="text-xs text-muted-foreground mt-1">
              feedback submissions
            </p>
          </CardContent>
        </Card>

        {/* Helpful */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2">
              <ThumbsUp className="h-4 w-4 text-green-600" />
              Helpful
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span className="text-3xl font-bold text-green-600">{stats.helpful_count.toLocaleString()}</span>
            <p className="text-xs text-muted-foreground mt-1">
              positive ratings
            </p>
          </CardContent>
        </Card>

        {/* Not Helpful */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2">
              <ThumbsDown className="h-4 w-4 text-red-600" />
              Not Helpful
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span className="text-3xl font-bold text-red-600">{stats.not_helpful_count.toLocaleString()}</span>
            <p className="text-xs text-muted-foreground mt-1">
              negative ratings
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Story P9-3.6: Summary Feedback Accuracy Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileText className="h-5 w-5" />
            Summary Accuracy
          </CardTitle>
          <CardDescription>
            User feedback on AI-generated activity summaries
          </CardDescription>
        </CardHeader>
        <CardContent>
          {stats.summary_feedback ? (
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              {/* Summary Accuracy Rate */}
              <div className={`p-4 rounded-lg border-2 ${getAccuracyColor(stats.summary_feedback.accuracy_rate)}`}>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <TrendingUp className="h-4 w-4" />
                  Accuracy Rate
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold">{stats.summary_feedback.accuracy_rate.toFixed(1)}%</span>
                  <div className={`h-2 w-2 rounded-full ${getAccuracyBgColor(stats.summary_feedback.accuracy_rate)}`} />
                </div>
              </div>

              {/* Total Summary Feedback */}
              <div className="p-4 rounded-lg bg-muted/50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <BarChart3 className="h-4 w-4" />
                  Total Feedback
                </div>
                <span className="text-2xl font-bold">{stats.summary_feedback.total_count.toLocaleString()}</span>
              </div>

              {/* Positive Summary Feedback */}
              <div className="p-4 rounded-lg bg-green-50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <ThumbsUp className="h-4 w-4 text-green-600" />
                  Positive
                </div>
                <span className="text-2xl font-bold text-green-600">{stats.summary_feedback.positive_count.toLocaleString()}</span>
              </div>

              {/* Negative Summary Feedback */}
              <div className="p-4 rounded-lg bg-red-50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <ThumbsDown className="h-4 w-4 text-red-600" />
                  Negative
                </div>
                <span className="text-2xl font-bold text-red-600">{stats.summary_feedback.negative_count.toLocaleString()}</span>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-muted-foreground">
              <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No feedback collected</p>
              <p className="text-sm mt-1">
                Use the thumbs up/down buttons on daily summaries to provide feedback
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trend chart */}
        <AccuracyTrendChart dailyTrend={stats.daily_trend} />

        {/* Top corrections */}
        <TopCorrections corrections={stats.top_corrections} />
      </div>

      {/* Story P4-5.4: Prompt improvement suggestions */}
      <PromptInsights cameraId={selectedCamera === 'all' ? undefined : selectedCamera} />

      {/* Camera breakdown table */}
      <CameraAccuracyTable feedbackByCamera={stats.feedback_by_camera} />
    </div>
  );
}
