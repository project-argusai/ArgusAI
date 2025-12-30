'use client';

/**
 * SummaryCard Component (Story P4-4.4)
 *
 * Displays today's and yesterday's activity summaries on the dashboard.
 * Shows quick stats and a summary text excerpt with link to full summary.
 *
 * AC Coverage:
 * - AC1: Component exists at this path
 * - AC2: Integrated into dashboard
 * - AC3: Displays Today summary with stats
 * - AC4: Displays Yesterday toggle
 * - AC5: Shows summary text excerpt (200 chars)
 * - AC6: View Full Summary link
 * - AC7: Loading skeleton
 * - AC8: Empty state
 * - AC9: Quick stats grid
 * - AC11: 5-minute refresh via useRecentSummaries
 * - AC12: Responsive layout
 * - AC13: Highlight badges
 */

import { useState, useMemo } from 'react';
import Link from 'next/link';
import {
  Activity,
  Camera,
  AlertTriangle,
  Bell,
  ClipboardList,
  ArrowRight,
  Users,
  Car,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useRecentSummaries, RecentSummaryItem } from '@/hooks/useSummaries';

/**
 * StatCard - Individual stat display component
 */
function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
}) {
  return (
    <div className="flex flex-col items-center p-2 rounded-lg bg-muted/50">
      <Icon className="h-4 w-4 text-muted-foreground mb-1" />
      <span className="text-lg font-semibold">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

/**
 * LoadingSkeleton - Skeleton state while loading (AC7)
 */
function LoadingSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-8 w-48" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats grid skeleton */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
        {/* Summary text skeleton */}
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
        {/* Link skeleton */}
        <Skeleton className="h-4 w-32" />
      </CardContent>
    </Card>
  );
}

/**
 * EmptyState - No summaries available (AC8)
 */
function EmptyState() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Sparkles className="h-5 w-5" />
          Activity Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <ClipboardList className="h-12 w-12 text-muted-foreground/50 mb-3" />
          <p className="text-muted-foreground">No activity summaries yet</p>
          <p className="text-sm text-muted-foreground/75 mt-1">
            Summaries are generated daily based on detected activity
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Truncate text to specified length with ellipsis (AC5)
 */
function truncateText(text: string, maxLength: number = 200): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trim() + '...';
}


/**
 * Main SummaryCard Component
 */
export function SummaryCard() {
  const { data, isLoading, error } = useRecentSummaries();
  const [selectedDate, setSelectedDate] = useState<string>('today');

  // Get today and yesterday summaries
  const summaries = useMemo(() => {
    if (!data?.summaries) return { today: null, yesterday: null };

    const today = new Date().toISOString().split('T')[0];
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterday = yesterdayDate.toISOString().split('T')[0];

    return {
      today: data.summaries.find((s: RecentSummaryItem) => s.date === today) || null,
      yesterday: data.summaries.find((s: RecentSummaryItem) => s.date === yesterday) || null,
    };
  }, [data]);

  // Get the currently selected summary
  const currentSummary: RecentSummaryItem | null =
    selectedDate === 'today' ? summaries.today : summaries.yesterday;

  // Show loading skeleton (AC7)
  if (isLoading) {
    return <LoadingSkeleton />;
  }

  // Show empty state if no summaries at all (AC8)
  if (!summaries.today && !summaries.yesterday) {
    return <EmptyState />;
  }

  // Determine which tabs are available
  const availableTabs = [];
  if (summaries.today) availableTabs.push({ value: 'today', label: 'Today' });
  if (summaries.yesterday) availableTabs.push({ value: 'yesterday', label: 'Yesterday' });

  // If selectedDate tab is not available, switch to first available
  if (selectedDate === 'today' && !summaries.today && summaries.yesterday) {
    setSelectedDate('yesterday');
  }

  // Generate highlight badges (AC13)
  const badges = [];
  if (currentSummary) {
    if (currentSummary.event_count > 20) {
      badges.push({ label: 'High Activity', variant: 'secondary' as const });
    }
    if (currentSummary.person_count >= 5) {
      badges.push({ label: `${currentSummary.person_count} People`, variant: 'default' as const });
    }
    if (currentSummary.doorbell_count > 0) {
      badges.push({
        label: `${currentSummary.doorbell_count} Doorbell${currentSummary.doorbell_count > 1 ? 's' : ''}`,
        variant: 'outline' as const,
      });
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Sparkles className="h-5 w-5" />
            Activity Summary
          </CardTitle>

          {/* Date toggle tabs (AC4) */}
          {availableTabs.length > 1 && (
            <Tabs
              value={selectedDate}
              onValueChange={setSelectedDate}
              className="w-auto"
            >
              <TabsList className="h-8">
                {availableTabs.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value} className="text-xs px-3">
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}
        </div>

        {/* Highlight badges (AC13) */}
        {badges.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {badges.map((badge, idx) => (
              <Badge key={idx} variant={badge.variant} className="text-xs">
                {badge.label}
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {currentSummary ? (
          <>
            {/* Quick stats grid (AC3, AC9) */}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard
                icon={Activity}
                label="Events"
                value={currentSummary.event_count}
              />
              <StatCard
                icon={Camera}
                label="Cameras"
                value={currentSummary.camera_count}
              />
              <StatCard
                icon={AlertTriangle}
                label="Alerts"
                value={currentSummary.alert_count}
              />
              <StatCard
                icon={Bell}
                label="Doorbell"
                value={currentSummary.doorbell_count}
              />
            </div>

            {/* Additional stats row */}
            {(currentSummary.person_count > 0 || currentSummary.vehicle_count > 0) && (
              <div className="flex gap-4 text-sm text-muted-foreground">
                {currentSummary.person_count > 0 && (
                  <span className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {currentSummary.person_count} person{currentSummary.person_count !== 1 ? 's' : ''}
                  </span>
                )}
                {currentSummary.vehicle_count > 0 && (
                  <span className="flex items-center gap-1">
                    <Car className="h-3.5 w-3.5" />
                    {currentSummary.vehicle_count} vehicle{currentSummary.vehicle_count !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}

            {/* Summary text excerpt (AC5) */}
            <p className="text-sm text-muted-foreground leading-relaxed">
              {truncateText(currentSummary.summary_text, 200)}
            </p>

            {/* View full summary link (AC6) */}
            <Link
              href={`/summaries?date=${currentSummary.date}`}
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              View Full Summary
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </>
        ) : (
          <div className="text-center py-4 text-muted-foreground">
            No summary available for {selectedDate === 'today' ? 'today' : 'yesterday'}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SummaryCard;
