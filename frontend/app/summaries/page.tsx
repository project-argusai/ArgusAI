'use client';

/**
 * Summaries Page (Story P4-4.5, P9-3.4)
 *
 * Main page for viewing activity summaries and generating on-demand summaries.
 *
 * AC Coverage:
 * - AC6: Summaries page with "Generate Summary" button
 * - AC12: View saved summaries in history
 * - AC-3.4.1-6: Summary feedback buttons (Story P9-3.4)
 */

import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import {
  Sparkles,
  Activity,
  Camera,
  AlertTriangle,
  Bell,
  Users,
  Car,
  History,
  Clock,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { GenerateSummaryDialog } from '@/components/summaries/GenerateSummaryDialog';
import { SummaryFeedbackButtons } from '@/components/summaries/SummaryFeedbackButtons';
import { useRecentSummaries, useSummaryList, RecentSummaryItem } from '@/hooks/useSummaries';
import type { SummaryGenerateResponse } from '@/hooks/useSummaries';

/**
 * StatBadge - Small stat badge for summary cards
 */
function StatBadge({
  icon: Icon,
  value,
  label,
}: {
  icon: React.ElementType;
  value: number;
  label: string;
}) {
  if (value === 0) return null;

  return (
    <Badge variant="secondary" className="gap-1 font-normal">
      <Icon className="h-3 w-3" />
      {value} {label}
    </Badge>
  );
}

/**
 * SummaryListItem - Display a single summary in the history list
 */
function SummaryListItem({ summary }: { summary: RecentSummaryItem | SummaryGenerateResponse }) {
  // Handle both types (RecentSummaryItem has date, SummaryGenerateResponse has period_start)
  const dateDisplay = 'date' in summary
    ? format(parseISO(summary.date), 'EEEE, MMMM d, yyyy')
    : format(parseISO(summary.period_start), 'MMM d, yyyy h:mm a');

  const timeDisplay = 'period_start' in summary && 'period_end' in summary
    ? `${format(parseISO(summary.period_start), 'h:mm a')} - ${format(parseISO(summary.period_end), 'h:mm a')}`
    : null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{dateDisplay}</CardTitle>
            {timeDisplay && (
              <CardDescription className="flex items-center gap-1 mt-0.5">
                <Clock className="h-3 w-3" />
                {timeDisplay}
              </CardDescription>
            )}
          </div>
          <Badge variant="outline" className="text-xs">
            {summary.event_count} events
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary text */}
        <p className="text-sm text-muted-foreground leading-relaxed">
          {summary.summary_text}
        </p>

        {/* Stats badges */}
        <div className="flex flex-wrap gap-2">
          <StatBadge icon={Camera} value={summary.camera_count} label="cameras" />
          <StatBadge icon={AlertTriangle} value={summary.alert_count} label="alerts" />
          <StatBadge icon={Bell} value={summary.doorbell_count} label="doorbells" />
          <StatBadge icon={Users} value={summary.person_count} label="people" />
          <StatBadge icon={Car} value={summary.vehicle_count} label="vehicles" />
        </div>

        {/* Story P9-3.4: Feedback Buttons (AC-3.4.1) */}
        <div className="flex justify-end pt-2 border-t mt-3">
          <SummaryFeedbackButtons summaryId={summary.id} />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * LoadingSkeleton - Skeleton for loading state
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader className="pb-2">
            <Skeleton className="h-5 w-48" />
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-5 w-20" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * EmptyState - No summaries available
 */
function EmptyState({ type }: { type: 'recent' | 'history' }) {
  return (
    <Card>
      <CardContent className="py-12">
        <div className="flex flex-col items-center justify-center text-center">
          <History className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium mb-1">
            {type === 'recent' ? 'No Recent Summaries' : 'No Summaries Yet'}
          </h3>
          <p className="text-sm text-muted-foreground max-w-sm">
            {type === 'recent'
              ? 'Summaries for today and yesterday will appear here once generated.'
              : 'Generate your first on-demand summary using the button above.'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Main Summaries Page Component
 */
export default function SummariesPage() {
  const [activeTab, setActiveTab] = useState('recent');
  const { data: recentData, isLoading: recentLoading } = useRecentSummaries();
  const { data: historyData, isLoading: historyLoading } = useSummaryList(50, 0);

  const recentSummaries = recentData?.summaries || [];
  const historySummaries = historyData?.summaries || [];

  return (
    <div className="container mx-auto px-4 py-6 max-w-4xl">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="h-6 w-6" />
            Activity Summaries
          </h1>
          <p className="text-muted-foreground mt-1">
            AI-generated summaries of your camera activity
          </p>
        </div>

        {/* Generate Summary Button (AC6) */}
        <GenerateSummaryDialog />
      </div>

      {/* Tabs for Recent vs History */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="recent" className="gap-2">
            <Activity className="h-4 w-4" />
            Recent
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-2">
            <History className="h-4 w-4" />
            History
          </TabsTrigger>
        </TabsList>

        {/* Recent Summaries Tab */}
        <TabsContent value="recent" className="space-y-4">
          {recentLoading ? (
            <LoadingSkeleton />
          ) : recentSummaries.length === 0 ? (
            <EmptyState type="recent" />
          ) : (
            <div className="space-y-4">
              {recentSummaries.map((summary: RecentSummaryItem | SummaryGenerateResponse) => (
                <SummaryListItem key={summary.id} summary={summary} />
              ))}
            </div>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-4">
          {historyLoading ? (
            <LoadingSkeleton />
          ) : historySummaries.length === 0 ? (
            <EmptyState type="history" />
          ) : (
            <div className="space-y-4">
              {historySummaries.map((summary: RecentSummaryItem | SummaryGenerateResponse) => (
                <SummaryListItem key={summary.id} summary={summary} />
              ))}
              {historyData && historyData.total > historySummaries.length && (
                <p className="text-center text-sm text-muted-foreground">
                  Showing {historySummaries.length} of {historyData.total} summaries
                </p>
              )}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
