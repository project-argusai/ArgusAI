/**
 * Cost Cap Settings Component
 * Story P3-7.3: Implement Daily/Monthly Cost Caps
 * Story P15-3.5: Add UnsavedIndicator and navigation warning
 *
 * Provides UI for:
 * - Configuring daily and monthly AI cost caps
 * - Viewing current usage vs cap with progress bars
 * - Warning/paused status alerts
 */

'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertCircle,
  AlertTriangle,
  DollarSign,
  Loader2,
  Save,
  X,
  Shield,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import { UnsavedIndicator } from './UnsavedIndicator';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';

// Format cost for display
const formatCost = (cost: number): string => {
  if (cost === 0) return '$0.00';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  if (cost < 1) return `$${cost.toFixed(3)}`;
  return `$${cost.toFixed(2)}`;
};

// Get progress bar color based on percentage
const getProgressColor = (percent: number): string => {
  if (percent >= 100) return 'bg-red-500';
  if (percent >= 80) return 'bg-amber-500';
  return 'bg-green-500';
};

export function CostCapSettings() {
  const queryClient = useQueryClient();

  // Local form state
  const [dailyCapEnabled, setDailyCapEnabled] = useState(false);
  const [monthlyCapEnabled, setMonthlyCapEnabled] = useState(false);
  const [dailyCapValue, setDailyCapValue] = useState('');
  const [monthlyCapValue, setMonthlyCapValue] = useState('');
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch current cost cap status
  const {
    data: status,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['cost-cap-status'],
    queryFn: () => apiClient.settings.getCostCapStatus(),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Initialize form from status
  useEffect(() => {
    if (status) {
      setDailyCapEnabled(status.daily_cap !== null);
      setMonthlyCapEnabled(status.monthly_cap !== null);
      setDailyCapValue(status.daily_cap?.toString() || '');
      setMonthlyCapValue(status.monthly_cap?.toString() || '');
      setHasChanges(false);
    }
  }, [status]);

  // Mutation for updating caps
  const updateCapsMutation = useMutation({
    mutationFn: async () => {
      return apiClient.settings.update({
        ai_daily_cost_cap: dailyCapEnabled ? parseFloat(dailyCapValue) || null : null,
        ai_monthly_cost_cap: monthlyCapEnabled ? parseFloat(monthlyCapValue) || null : null,
      });
    },
    onSuccess: () => {
      toast.success('Cost caps updated successfully');
      queryClient.invalidateQueries({ queryKey: ['cost-cap-status'] });
      setHasChanges(false);
    },
    onError: (err) => {
      toast.error(`Failed to update cost caps: ${err instanceof Error ? err.message : 'Unknown error'}`);
    },
  });

  // Handle form changes
  const handleDailyCapToggle = (enabled: boolean) => {
    setDailyCapEnabled(enabled);
    if (!enabled) setDailyCapValue('');
    setHasChanges(true);
  };

  const handleMonthlyCapToggle = (enabled: boolean) => {
    setMonthlyCapEnabled(enabled);
    if (!enabled) setMonthlyCapValue('');
    setHasChanges(true);
  };

  const handleDailyCapChange = (value: string) => {
    setDailyCapValue(value);
    setHasChanges(true);
  };

  const handleMonthlyCapChange = (value: string) => {
    setMonthlyCapValue(value);
    setHasChanges(true);
  };

  const handleSave = () => {
    // Validate values
    if (dailyCapEnabled && (!dailyCapValue || parseFloat(dailyCapValue) <= 0)) {
      toast.error('Please enter a valid daily cap amount');
      return;
    }
    if (monthlyCapEnabled && (!monthlyCapValue || parseFloat(monthlyCapValue) <= 0)) {
      toast.error('Please enter a valid monthly cap amount');
      return;
    }
    updateCapsMutation.mutate();
  };

  const handleCancel = () => {
    if (status) {
      setDailyCapEnabled(status.daily_cap !== null);
      setMonthlyCapEnabled(status.monthly_cap !== null);
      setDailyCapValue(status.daily_cap?.toString() || '');
      setMonthlyCapValue(status.monthly_cap?.toString() || '');
      setHasChanges(false);
    }
  };

  // Navigation warning when there are unsaved changes
  useUnsavedChangesWarning({ isDirty: hasChanges });

  // Loading state
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Failed to load cost cap status</p>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-blue-500" />
          <CardTitle className="text-base">Cost Caps</CardTitle>
          <UnsavedIndicator isDirty={hasChanges} />
        </div>
        <CardDescription>
          Set spending limits to control AI analysis costs
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Paused Alert */}
        {status?.is_paused && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>AI Analysis Paused</AlertTitle>
            <AlertDescription>
              {status.pause_reason === 'cost_cap_daily'
                ? 'Daily cost cap reached. Analysis will automatically resume at midnight UTC.'
                : 'Monthly cost cap reached. Analysis will automatically resume at the start of next month.'}
            </AlertDescription>
          </Alert>
        )}

        {/* Warning Alert (80%+ of cap) */}
        {!status?.is_paused && status && (
          <>
            {status.daily_cap && status.daily_percent >= 80 && (
              <Alert>
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <AlertTitle>Approaching Daily Cap</AlertTitle>
                <AlertDescription>
                  You have used {status.daily_percent.toFixed(0)}% of your daily AI budget.
                </AlertDescription>
              </Alert>
            )}
            {status.monthly_cap && status.monthly_percent >= 80 && !status.daily_cap && (
              <Alert>
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <AlertTitle>Approaching Monthly Cap</AlertTitle>
                <AlertDescription>
                  You have used {status.monthly_percent.toFixed(0)}% of your monthly AI budget.
                </AlertDescription>
              </Alert>
            )}
          </>
        )}

        {/* Daily Cap Section */}
        <div className="space-y-3 p-4 rounded-lg border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="daily-cap-toggle" className="font-medium cursor-pointer">
                Daily Cost Cap
              </Label>
            </div>
            <Switch
              id="daily-cap-toggle"
              checked={dailyCapEnabled}
              onCheckedChange={handleDailyCapToggle}
            />
          </div>

          {dailyCapEnabled && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={dailyCapValue}
                  onChange={(e) => handleDailyCapChange(e.target.value)}
                  placeholder="e.g., 1.00"
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">per day</span>
              </div>

              {/* Daily progress bar */}
              {status?.daily_cap && (
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                      {formatCost(status.daily_cost)} / {formatCost(status.daily_cap)}
                    </span>
                    <span className={`font-medium ${status.daily_percent >= 80 ? 'text-amber-500' : ''}`}>
                      {status.daily_percent.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${getProgressColor(status.daily_percent)}`}
                      style={{ width: `${Math.min(status.daily_percent, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {!dailyCapEnabled && (
            <p className="text-sm text-muted-foreground">No daily limit set</p>
          )}
        </div>

        {/* Monthly Cap Section */}
        <div className="space-y-3 p-4 rounded-lg border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="monthly-cap-toggle" className="font-medium cursor-pointer">
                Monthly Cost Cap
              </Label>
            </div>
            <Switch
              id="monthly-cap-toggle"
              checked={monthlyCapEnabled}
              onCheckedChange={handleMonthlyCapToggle}
            />
          </div>

          {monthlyCapEnabled && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={monthlyCapValue}
                  onChange={(e) => handleMonthlyCapChange(e.target.value)}
                  placeholder="e.g., 10.00"
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">per month</span>
              </div>

              {/* Monthly progress bar */}
              {status?.monthly_cap && (
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                      {formatCost(status.monthly_cost)} / {formatCost(status.monthly_cap)}
                    </span>
                    <span className={`font-medium ${status.monthly_percent >= 80 ? 'text-amber-500' : ''}`}>
                      {status.monthly_percent.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${getProgressColor(status.monthly_percent)}`}
                      style={{ width: `${Math.min(status.monthly_percent, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {!monthlyCapEnabled && (
            <p className="text-sm text-muted-foreground">No monthly limit set</p>
          )}
        </div>

        {/* Action Buttons */}
        {hasChanges && (
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={updateCapsMutation.isPending}
            >
              <X className="h-4 w-4 mr-2" />
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={updateCapsMutation.isPending}
            >
              {updateCapsMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save Caps
            </Button>
          </div>
        )}

        {/* Info text */}
        <p className="text-xs text-muted-foreground">
          When a cap is reached, AI analysis is paused automatically. Events are still detected and stored,
          but without AI descriptions. Analysis resumes automatically when a new period begins (midnight UTC for daily, first of month for monthly).
        </p>
      </CardContent>
    </Card>
  );
}
