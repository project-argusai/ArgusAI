'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw, TrendingUp } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { AICostTrendPoint } from '@/types/monitoring';

interface AICostTrendsCardProps {
  title?: string;
  variant?: 'full' | 'mini';
  daysBack?: number;
  bucket?: 'day' | 'hour';
}

export function AICostTrendsCard({
  title = 'AI Cost & Token Trends',
  variant = 'full',
  daysBack = 30,
  bucket = 'day',
}: AICostTrendsCardProps) {
  const [selectedDays, setSelectedDays] = useState(daysBack);
  const [trends, setTrends] = useState<AICostTrendPoint[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [metric, setMetric] = useState<'cost' | 'tokens'>('cost'); // only used in full variant

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const res = await apiClient.getAICostTrends({
        days_back: selectedDays,
        bucket,
      });
      setTrends(res?.trends || []);
    } catch (error) {
      console.error('Failed to load AI cost trends:', error);
      setTrends([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDays, bucket]);

  const formatCost = (cost: number) => `$${cost.toFixed(4)}`;
  const formatTokens = (tokens: number) => tokens.toLocaleString();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            {title}
          </CardTitle>
          {variant === 'mini' && (
            <CardDescription className="text-xs">
              Last {daysBack} days ({bucket}ly)
            </CardDescription>
          )}
        </div>

        <div className="flex items-center gap-2">
          {variant === 'full' && (
            <>
              <div className="flex items-center gap-1 text-xs border rounded-md mr-2">
                {[7, 30, 90].map((d) => (
                  <button
                    key={d}
                    onClick={() => {
                      setSelectedDays(d);
                    }}
                    className={`px-2 py-1 ${selectedDays === d ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                  >
                    {d}d
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1 text-xs border rounded-md">
                <button
                  onClick={() => setMetric('cost')}
                  className={`px-2 py-1 rounded-l-md ${metric === 'cost' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                >
                  Cost
                </button>
                <button
                  onClick={() => setMetric('tokens')}
                  className={`px-2 py-1 rounded-r-md ${metric === 'tokens' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                >
                  Tokens
                </button>
              </div>
            </>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            disabled={isLoading}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading && trends.length === 0 && (
          <div className="text-sm text-muted-foreground py-6 text-center">
            Loading cost trends...
          </div>
        )}

        {!isLoading && trends.length === 0 && (
          <div className="text-sm text-muted-foreground py-6 text-center">
            No cost data available for the selected period.
          </div>
        )}

        {trends.length > 0 && (
          <>
            {/* Line Chart */}
            <div className={variant === 'mini' ? 'h-[110px] mb-4' : 'h-[220px] mb-6'}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trends}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="bucket"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value) => {
                      // For hourly data, show time only
                      if (bucket === 'hour') {
                        try {
                          const date = parseISO(value.replace(' ', 'T'));
                          return format(date, 'HH:mm');
                        } catch {
                          return value.split(' ')[1]?.slice(0, 5) || value;
                        }
                      }
                      // For daily data, show short date
                      try {
                        return format(parseISO(value), 'MMM d');
                      } catch {
                        return value;
                      }
                    }}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value) =>
                      metric === 'cost'
                        ? `$${Number(value).toFixed(2)}`
                        : Number(value).toLocaleString()
                    }
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload || payload.length === 0) return null;

                      const data = payload[0].payload;
                      const value = metric === 'cost' ? data.total_cost : data.total_tokens;
                      const valueLabel = metric === 'cost' ? 'Cost' : 'Tokens';
                      const formattedValue =
                        metric === 'cost'
                          ? `$${Number(value).toFixed(4)}`
                          : Number(value).toLocaleString();

                      return (
                        <div className="rounded-md border bg-popover p-2 text-xs shadow-md">
                          <div className="font-medium mb-1">{label}</div>
                          <div>
                            <span className="text-muted-foreground">{valueLabel}:</span>{' '}
                            <span className="font-medium">{formattedValue}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Calls:</span>{' '}
                            <span className="font-medium">{data.calls}</span>
                          </div>
                          {data.avg_response_time_ms != null && (
                            <div>
                              <span className="text-muted-foreground">Avg latency:</span>{' '}
                              <span className="font-medium">
                                {Math.round(data.avg_response_time_ms)}ms
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey={metric === 'cost' ? 'total_cost' : 'total_tokens'}
                    stroke={metric === 'cost' ? '#3b82f6' : '#10b981'}
                    strokeWidth={2}
                    dot={variant === 'full' ? { r: 2 } : false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Table (only in full variant) */}
            {variant === 'full' && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-normal">Period</th>
                      <th className="py-2 px-3 font-normal text-right">Calls</th>
                      <th className="py-2 px-3 font-normal text-right">Total Cost</th>
                      <th className="py-2 px-3 font-normal text-right">Tokens</th>
                      <th className="py-2 pl-3 font-normal text-right">Avg Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trends.map((row, index) => (
                      <tr key={index} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-4 font-mono text-xs">{row.bucket}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{row.calls}</td>
                        <td className="py-2 px-3 text-right tabular-nums font-medium">
                          {formatCost(row.total_cost)}
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums">
                          {formatTokens(row.total_tokens)}
                        </td>
                        <td className="py-2 pl-3 text-right tabular-nums text-muted-foreground">
                          {row.avg_response_time_ms ? `${Math.round(row.avg_response_time_ms)}ms` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
