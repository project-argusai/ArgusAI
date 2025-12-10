/**
 * Cost Dashboard Component
 * Story P3-7.2: Build Cost Dashboard UI
 *
 * Displays AI usage costs with:
 * - Key metrics (today's cost, monthly cost, total requests)
 * - Cost by provider (pie chart)
 * - Cost by camera (bar chart with drilldown)
 * - Daily trend (line chart)
 */

'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays, startOfMonth } from 'date-fns';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Area,
  AreaChart,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  DollarSign,
  TrendingUp,
  Activity,
  Calendar,
  Info,
  AlertTriangle,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import type {
  IAIUsageByCamera,
  IAIUsageByMode,
} from '@/types/settings';

// Chart-compatible data types (recharts 3.x requires index signature)
interface ChartDataPoint {
  [key: string]: string | number;
}

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip as UITooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { CostCapSettings } from './CostCapSettings';

// Provider colors matching existing UI patterns
const PROVIDER_COLORS: Record<string, string> = {
  openai: '#22c55e',   // green-500
  grok: '#f97316',     // orange-500
  claude: '#f59e0b',   // amber-500
  gemini: '#3b82f6',   // blue-500
};

// Analysis mode colors
const MODE_COLORS: Record<string, string> = {
  single_frame: '#8b5cf6',   // violet-500
  multi_frame: '#06b6d4',    // cyan-500
  video_native: '#ec4899',   // pink-500
};

// Format cost to display with appropriate precision
const formatCost = (cost: number): string => {
  if (cost === 0) return '$0.00';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  if (cost < 1) return `$${cost.toFixed(3)}`;
  return `$${cost.toFixed(2)}`;
};

// Format provider name for display
const formatProviderName = (provider: string): string => {
  const names: Record<string, string> = {
    openai: 'OpenAI',
    grok: 'Grok',
    claude: 'Claude',
    gemini: 'Gemini',
  };
  return names[provider] || provider;
};

// Format mode name for display
const formatModeName = (mode: string): string => {
  const names: Record<string, string> = {
    single_frame: 'Single Frame',
    multi_frame: 'Multi-Frame',
    video_native: 'Video Native',
    single_image: 'Single Image',
  };
  return names[mode] || mode;
};

// Period options
type PeriodOption = '7d' | '30d' | '90d' | 'mtd';

interface PeriodConfig {
  label: string;
  getStartDate: () => string;
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
  mtd: {
    label: 'Month to Date',
    getStartDate: () => format(startOfMonth(new Date()), 'yyyy-MM-dd'),
  },
};

// Custom tooltip for recharts
interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string; payload: Record<string, unknown> }>;
  label?: string;
}

const ChartTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3 text-sm">
      {label && <p className="font-medium mb-1">{label}</p>}
      {payload.map((entry, index) => {
        const requests = entry.payload?.requests as number | undefined;
        return (
          <p key={index} className="text-muted-foreground">
            {entry.name}: {formatCost(entry.value)}
            {requests !== undefined && (
              <span className="ml-2">({requests} requests)</span>
            )}
          </p>
        );
      })}
    </div>
  );
};

// Camera drilldown dialog
interface CameraDrilldownProps {
  camera: IAIUsageByCamera | null;
  modeData: IAIUsageByMode[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CameraDrilldown = ({ camera, modeData, open, onOpenChange }: CameraDrilldownProps) => {
  if (!camera) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            {camera.camera_name}
          </DialogTitle>
          <DialogDescription>
            Usage breakdown by analysis mode
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 p-4 bg-muted rounded-lg">
            <div>
              <p className="text-sm text-muted-foreground">Total Cost</p>
              <p className="text-2xl font-bold">{formatCost(camera.cost)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Requests</p>
              <p className="text-2xl font-bold">{camera.requests.toLocaleString()}</p>
            </div>
          </div>

          <div>
            <h4 className="font-medium mb-3">By Analysis Mode</h4>
            {modeData.length > 0 ? (
              <div className="space-y-2">
                {modeData.map((mode) => (
                  <div
                    key={mode.mode}
                    className="flex items-center justify-between p-3 rounded-lg border"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: MODE_COLORS[mode.mode] || '#6b7280' }}
                      />
                      <span>{formatModeName(mode.mode)}</span>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">{formatCost(mode.cost)}</p>
                      <p className="text-xs text-muted-foreground">
                        {mode.requests} requests
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                No mode breakdown available
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export function CostDashboard() {
  const [period, setPeriod] = useState<PeriodOption>('30d');
  const [selectedCamera, setSelectedCamera] = useState<IAIUsageByCamera | null>(null);
  const [drilldownOpen, setDrilldownOpen] = useState(false);

  // Calculate date range based on period
  const dateRange = useMemo(() => {
    const endDate = format(new Date(), 'yyyy-MM-dd');
    const startDate = PERIOD_OPTIONS[period].getStartDate();
    return { start_date: startDate, end_date: endDate };
  }, [period]);

  // Fetch AI usage data
  const {
    data: usageData,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['ai-usage', dateRange],
    queryFn: () => apiClient.settings.getAIUsage(dateRange),
    staleTime: 60000, // 1 minute
    refetchOnWindowFocus: false,
  });

  // Calculate today's cost from by_date
  const todayCost = useMemo(() => {
    if (!usageData?.by_date) return 0;
    const today = format(new Date(), 'yyyy-MM-dd');
    const todayData = usageData.by_date.find((d) => d.date === today);
    return todayData?.cost || 0;
  }, [usageData]);

  // Transform data for recharts (requires index signature compatibility)
  const providerChartData = useMemo(() => {
    if (!usageData?.by_provider) return [];
    return usageData.by_provider.map((p) => ({
      provider: p.provider,
      cost: p.cost,
      requests: p.requests,
    } as ChartDataPoint));
  }, [usageData]);

  const cameraChartData = useMemo(() => {
    if (!usageData?.by_camera) return [];
    return usageData.by_camera.map((c) => ({
      camera_id: c.camera_id,
      camera_name: c.camera_name,
      cost: c.cost,
      requests: c.requests,
    } as ChartDataPoint));
  }, [usageData]);

  const dateChartData = useMemo(() => {
    if (!usageData?.by_date) return [];
    return usageData.by_date.map((d) => ({
      date: d.date,
      cost: d.cost,
      requests: d.requests,
    } as ChartDataPoint));
  }, [usageData]);

  // Handle camera bar click for drilldown
  const handleCameraClick = (data: ChartDataPoint) => {
    // Find the original camera data to pass to drilldown
    const camera = usageData?.by_camera.find((c) => c.camera_id === data.camera_id);
    if (camera) {
      setSelectedCamera(camera);
      setDrilldownOpen(true);
    }
  };

  // Check if there's any data
  const hasData = usageData && usageData.total_requests > 0;

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
        <Skeleton className="h-80" />
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            <div>
              <p className="font-medium">Failed to load AI usage data</p>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : 'Unknown error occurred'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Empty state
  if (!hasData) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center py-12">
            <DollarSign className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No AI usage recorded yet</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              AI usage and costs will appear here once you start analyzing camera events.
              Costs are tracked per API request to each AI provider.
            </p>
            <div className="mt-6 p-4 bg-muted rounded-lg text-left max-w-md mx-auto">
              <h4 className="font-medium text-sm mb-2">How usage tracking works:</h4>
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>• Each AI analysis request is recorded</li>
                <li>• Costs are calculated based on provider rates</li>
                <li>• Usage is tracked by camera, provider, and analysis mode</li>
                <li>• Daily trends show spending patterns over time</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Period Selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            AI Usage & Costs
          </h2>
          <p className="text-sm text-muted-foreground">
            {usageData?.period && (
              <>
                {format(new Date(usageData.period.start), 'MMM d, yyyy')} -{' '}
                {format(new Date(usageData.period.end), 'MMM d, yyyy')}
              </>
            )}
          </p>
        </div>
        <Select value={period} onValueChange={(v) => setPeriod(v as PeriodOption)}>
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
      </div>

      {/* Cost Cap Settings - Story P3-7.3 */}
      <CostCapSettings />

      {/* Key Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Today's Cost */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              Today&apos;s Cost
              <UITooltip>
                <TooltipTrigger asChild>
                  <Info className="h-3 w-3 cursor-help" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Total AI cost for today</p>
                </TooltipContent>
              </UITooltip>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-green-600">{formatCost(todayCost)}</p>
          </CardContent>
        </Card>

        {/* Period Total Cost */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              Period Total
              <UITooltip>
                <TooltipTrigger asChild>
                  <Info className="h-3 w-3 cursor-help" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Total cost for selected period</p>
                  <p className="text-xs">Costs are estimated based on provider rates</p>
                </TooltipContent>
              </UITooltip>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{formatCost(usageData?.total_cost || 0)}</p>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Estimated ±20%
            </p>
          </CardContent>
        </Card>

        {/* Total Requests */}
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              Total Requests
              <UITooltip>
                <TooltipTrigger asChild>
                  <Info className="h-3 w-3 cursor-help" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Number of AI analysis requests</p>
                </TooltipContent>
              </UITooltip>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {usageData?.total_requests.toLocaleString() || 0}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost by Provider (Pie Chart) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cost by Provider</CardTitle>
            <CardDescription>Distribution across AI providers</CardDescription>
          </CardHeader>
          <CardContent>
            {providerChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={providerChartData}
                    dataKey="cost"
                    nameKey="provider"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ payload, percent }) =>
                      `${formatProviderName((payload as ChartDataPoint)?.provider as string || '')} ${((percent || 0) * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {providerChartData.map((entry) => (
                      <Cell
                        key={entry.provider as string}
                        fill={PROVIDER_COLORS[entry.provider as string] || '#6b7280'}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                  <Legend
                    formatter={(value) => formatProviderName(value as string)}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                No provider data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* Cost by Camera (Bar Chart) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cost by Camera</CardTitle>
            <CardDescription>Click a bar to see mode breakdown</CardDescription>
          </CardHeader>
          <CardContent>
            {cameraChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={cameraChartData}
                  layout="vertical"
                  margin={{ left: 100 }}
                >
                  <XAxis type="number" tickFormatter={(v) => formatCost(v)} />
                  <YAxis
                    type="category"
                    dataKey="camera_name"
                    width={90}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar
                    dataKey="cost"
                    fill="#3b82f6"
                    cursor="pointer"
                    onClick={(data) => handleCameraClick(data as unknown as ChartDataPoint)}
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                No camera data available
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Daily Trend (Area Chart) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Daily Cost Trend
          </CardTitle>
          <CardDescription>Cost over time for the selected period</CardDescription>
        </CardHeader>
        <CardContent>
          {dateChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={dateChartData}>
                <defs>
                  <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tickFormatter={(date) => format(new Date(date as string), 'MMM d')}
                  tick={{ fontSize: 12 }}
                />
                <YAxis tickFormatter={(v) => formatCost(v)} tick={{ fontSize: 12 }} />
                <Tooltip
                  content={<ChartTooltip />}
                  labelFormatter={(date) => format(new Date(date as string), 'MMMM d, yyyy')}
                />
                <Area
                  type="monotone"
                  dataKey="cost"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#costGradient)"
                  name="Cost"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              No daily trend data available
            </div>
          )}
        </CardContent>
      </Card>

      {/* Camera Drilldown Dialog */}
      <CameraDrilldown
        camera={selectedCamera}
        modeData={usageData?.by_mode || []}
        open={drilldownOpen}
        onOpenChange={setDrilldownOpen}
      />
    </div>
  );
}
