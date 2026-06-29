'use client';

/**
 * HomeKitDiagnostics component (Story P7-1.1 AC6, P7-1.2, P7-1.3, P7-1.4)
 *
 * Displays diagnostic information for HomeKit troubleshooting including:
 * - Bridge status and mDNS advertising state
 * - Network binding info
 * - Connected clients count
 * - Connection status panel with per-sensor delivery tracking (P7-1.4)
 * - Recent diagnostic logs with category filtering
 * - Warnings and errors prominently displayed
 * - Connectivity test button (P7-1.2 AC6)
 * - Test event trigger button (P7-1.3 AC5)
 */
import React, { useState } from 'react';
import { parseApiDate, formatRelative } from '@/lib/datetime';
import {
  useHomekitDiagnostics,
  useHomekitTestConnectivity,
  useHomekitTestEvent,
  type HomekitDiagnosticEntry,
  type HomekitConnectivityTestResponse,
  type HomekitTestEventType,
  type HomekitTestEventResult,
  type HomekitLastEventDelivery,
} from '@/hooks/useHomekitStatus';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Loader2,
  AlertCircle,
  Check,
  X,
  Radio,
  Network,
  Users,
  Activity,
  Clock,
  Filter,
  ChevronDown,
  ChevronUp,
  Wifi,
  TestTube,
  Lightbulb,
  AlertTriangle,
  Play,
  Zap,
  Pause,
  RefreshCw,
  Signal,
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// Log level badge colors
const levelColors: Record<string, string> = {
  debug: 'bg-gray-500',
  info: 'bg-blue-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
};

function formatTimestamp(timestamp: string): string {
  const date = parseApiDate(timestamp)!;
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

interface DiagnosticLogEntryProps {
  entry: HomekitDiagnosticEntry;
}

function DiagnosticLogEntry({ entry }: DiagnosticLogEntryProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-border py-2 last:border-0">
      <div
        className="flex items-start justify-between gap-2 cursor-pointer"
        onClick={() => entry.details && setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground font-mono">
            {formatTimestamp(entry.timestamp)}
          </span>
          <Badge className={`${levelColors[entry.level]} text-white text-xs`}>
            {entry.level}
          </Badge>
          <Badge variant="outline" className={`text-xs`}>
            {entry.category}
          </Badge>
        </div>
        {entry.details && (
          <Button variant="ghost" size="sm" className="h-5 w-5 p-0">
            {expanded ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </Button>
        )}
      </div>
      <p className="text-sm mt-1">{entry.message}</p>
      {expanded && entry.details && (
        <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-x-auto">
          {JSON.stringify(entry.details, null, 2)}
        </pre>
      )}
    </div>
  );
}

/**
 * ConnectivityTestPanel component (Story P7-1.2 AC6)
 *
 * Displays the "Test Discovery" button and shows connectivity test results
 * including mDNS visibility, port accessibility, and troubleshooting hints.
 */
function ConnectivityTestPanel() {
  const [testResult, setTestResult] = useState<HomekitConnectivityTestResponse | null>(null);
  const connectivityMutation = useHomekitTestConnectivity();

  const runConnectivityTest = async () => {
    try {
      const result = await connectivityMutation.mutateAsync();
      setTestResult(result);
    } catch (err) {
      console.error('Connectivity test failed:', err);
    }
  };

  return (
    <div className="border rounded-lg p-4 bg-muted/30">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Discovery Test</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={runConnectivityTest}
          disabled={connectivityMutation.isPending}
        >
          {connectivityMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Testing...
            </>
          ) : (
            <>
              <TestTube className="h-4 w-4 mr-2" />
              Test Discovery
            </>
          )}
        </Button>
      </div>

      {connectivityMutation.isError && (
        <Alert variant="destructive" className="mt-3">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Test Failed</AlertTitle>
          <AlertDescription>
            {connectivityMutation.error instanceof Error
              ? connectivityMutation.error.message
              : 'Connectivity test failed'}
          </AlertDescription>
        </Alert>
      )}

      {testResult && (
        <div className="mt-3 space-y-3">
          {/* Test Results Grid */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {/* mDNS Visibility */}
            <div className="flex items-center gap-2">
              {testResult.mdns_visible ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <X className="h-4 w-4 text-red-500" />
              )}
              <span>mDNS Visible</span>
            </div>

            {/* Port Accessible */}
            <div className="flex items-center gap-2">
              {testResult.port_accessible ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <X className="h-4 w-4 text-red-500" />
              )}
              <span>Port {testResult.network_binding?.port ?? 51826} Accessible</span>
            </div>

            {/* Discovered As */}
            {testResult.discovered_as && (
              <div className="col-span-2 flex items-center gap-2">
                <Radio className="h-4 w-4 text-muted-foreground" />
                <span className="font-mono text-xs">{testResult.discovered_as}</span>
              </div>
            )}

            {/* Network Binding */}
            {testResult.network_binding && (
              <div className="col-span-2 flex items-center gap-2">
                <Network className="h-4 w-4 text-muted-foreground" />
                <span className="font-mono text-xs">
                  {testResult.network_binding.ip}:{testResult.network_binding.port}
                </span>
              </div>
            )}

            {/* Test Duration */}
            <div className="col-span-2 text-xs text-muted-foreground">
              Test completed in {testResult.test_duration_ms}ms
            </div>
          </div>

          {/* Firewall Issues */}
          {testResult.firewall_issues.length > 0 && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Firewall Issues Detected</AlertTitle>
              <AlertDescription>
                <ul className="list-disc list-inside mt-2">
                  {testResult.firewall_issues.map((issue, i) => (
                    <li key={i} className="text-sm">{issue}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Recommendations */}
          {testResult.recommendations.length > 0 && (
            <div className="border rounded-lg p-3 bg-blue-500/10 border-blue-500/30">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb className="h-4 w-4 text-blue-500" />
                <span className="text-sm font-medium text-blue-500">Recommendations</span>
              </div>
              <ul className="list-disc list-inside space-y-1">
                {testResult.recommendations.map((rec, i) => (
                  <li key={i} className="text-sm text-muted-foreground">{rec}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Success Message */}
          {testResult.mdns_visible && testResult.port_accessible && testResult.firewall_issues.length === 0 && (
            <Alert className="border-green-500 bg-green-500/10">
              <Check className="h-4 w-4 text-green-500" />
              <AlertTitle className="text-green-500">All Checks Passed</AlertTitle>
              <AlertDescription>
                HomeKit bridge is discoverable and accessible.
                It should appear in the Apple Home app.
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Format relative time from timestamp (Story P7-1.4)
 */
function formatRelativeTime(timestamp: string): string {
  try {
    return formatRelative(timestamp);
  } catch {
    return 'Unknown';
  }
}

/**
 * ConnectionStatusPanel component (Story P7-1.4 AC1-5)
 *
 * Displays real-time connection health status including:
 * - mDNS advertisement status with green/red indicator
 * - Connected clients count with numeric badge
 * - Per-sensor delivery status table with relative timestamps
 * - Errors and warnings display
 * - Auto-refresh toggle for debugging
 */
interface ConnectionStatusPanelProps {
  mdnsAdvertising: boolean;
  connectedClients: number;
  sensorDeliveries: HomekitLastEventDelivery[];
  warnings: string[];
  errors: string[];
  isPolling: boolean;
  onTogglePolling: () => void;
}

function ConnectionStatusPanel({
  mdnsAdvertising,
  connectedClients,
  sensorDeliveries,
  warnings,
  errors,
  isPolling,
  onTogglePolling,
}: ConnectionStatusPanelProps) {
  const [isDeliveryExpanded, setIsDeliveryExpanded] = useState(true);

  return (
    <div className="border rounded-lg p-4 bg-muted/30 space-y-4">
      {/* Header with refresh toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Signal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Connection Status</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onTogglePolling}
          className="h-7 text-xs"
        >
          {isPolling ? (
            <>
              <Pause className="h-3 w-3 mr-1" />
              Pause Refresh
            </>
          ) : (
            <>
              <RefreshCw className="h-3 w-3 mr-1" />
              Resume Refresh
            </>
          )}
        </Button>
      </div>

      {/* Status Grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* mDNS Status (AC1) */}
        <div className="flex items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              mdnsAdvertising ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-sm">
            mDNS {mdnsAdvertising ? 'Advertising' : 'Not Advertising'}
          </span>
        </div>

        {/* Connected Clients (AC2) */}
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">{connectedClients} Connected</span>
          {connectedClients > 0 && (
            <Badge variant="secondary" className="text-xs h-5">
              {connectedClients}
            </Badge>
          )}
        </div>
      </div>

      {/* Errors Display (AC4) */}
      {errors.length > 0 && (
        <Alert variant="destructive" className="py-2">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle className="text-sm">Errors ({errors.length})</AlertTitle>
          <AlertDescription className="text-xs">
            <ul className="list-disc list-inside mt-1">
              {errors.slice(0, 3).map((err, i) => (
                <li key={i}>{err}</li>
              ))}
              {errors.length > 3 && (
                <li className="text-muted-foreground">+{errors.length - 3} more...</li>
              )}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Warnings Display (AC4) */}
      {warnings.length > 0 && (
        <Alert className="py-2 border-yellow-500 bg-yellow-500/10">
          <AlertTriangle className="h-4 w-4 text-yellow-500" />
          <AlertTitle className="text-sm text-yellow-600">Warnings ({warnings.length})</AlertTitle>
          <AlertDescription className="text-xs">
            <ul className="list-disc list-inside mt-1">
              {warnings.slice(0, 3).map((warn, i) => (
                <li key={i}>{warn}</li>
              ))}
              {warnings.length > 3 && (
                <li className="text-muted-foreground">+{warnings.length - 3} more...</li>
              )}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Per-Sensor Delivery Status (AC3) */}
      <div className="border rounded-lg overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-3 py-2 bg-muted/50 hover:bg-muted text-sm font-medium"
          onClick={() => setIsDeliveryExpanded(!isDeliveryExpanded)}
        >
          <span className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Last Event Delivery per Sensor
            <Badge variant="outline" className="text-xs">
              {sensorDeliveries.length}
            </Badge>
          </span>
          {isDeliveryExpanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>

        {isDeliveryExpanded && (
          <div className="max-h-48 overflow-y-auto">
            {sensorDeliveries.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                No event deliveries recorded yet
              </div>
            ) : (
              <div className="divide-y divide-border">
                {sensorDeliveries.map((delivery, i) => (
                  <div key={`${delivery.camera_id}-${delivery.sensor_type}-${i}`} className="px-3 py-2 flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      {delivery.delivered ? (
                        <Check className="h-3.5 w-3.5 text-green-500" />
                      ) : (
                        <X className="h-3.5 w-3.5 text-red-500" />
                      )}
                      <span className="font-medium">
                        {delivery.camera_name || delivery.camera_id.slice(0, 8)}
                      </span>
                      <Badge variant="outline" className="text-xs h-5">
                        {delivery.sensor_type}
                      </Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatRelativeTime(delivery.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * TestEventPanel component (Story P7-1.3 AC5)
 *
 * Displays the "Test Event" panel with camera and event type selection
 * to manually trigger HomeKit events and verify delivery to paired devices.
 */
function TestEventPanel() {
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  const [selectedEventType, setSelectedEventType] = useState<HomekitTestEventType>('motion');
  const [testResult, setTestResult] = useState<HomekitTestEventResult | null>(null);
  const testEventMutation = useHomekitTestEvent();

  // Fetch cameras for the dropdown
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiClient.cameras.list(),
    staleTime: 60000,
  });

  const runTestEvent = async () => {
    if (!selectedCamera) return;

    try {
      const result = await testEventMutation.mutateAsync({
        camera_id: selectedCamera,
        event_type: selectedEventType,
      });
      setTestResult(result);
    } catch (err) {
      console.error('Test event failed:', err);
    }
  };

  const eventTypeLabels: Record<HomekitTestEventType, string> = {
    motion: 'Motion',
    occupancy: 'Occupancy (Person)',
    vehicle: 'Vehicle',
    animal: 'Animal',
    package: 'Package',
    doorbell: 'Doorbell Ring',
  };

  return (
    <div className="border rounded-lg p-4 bg-muted/30">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Test Event Trigger</span>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        {/* Camera Selector */}
        <Select value={selectedCamera} onValueChange={setSelectedCamera}>
          <SelectTrigger className="text-sm">
            <SelectValue placeholder="Select camera" />
          </SelectTrigger>
          <SelectContent>
            {cameras.map((camera) => (
              <SelectItem key={camera.id} value={camera.id}>
                {camera.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Event Type Selector */}
        <Select value={selectedEventType} onValueChange={(v) => setSelectedEventType(v as HomekitTestEventType)}>
          <SelectTrigger className="text-sm">
            <SelectValue placeholder="Event type" />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(eventTypeLabels) as HomekitTestEventType[]).map((type) => (
              <SelectItem key={type} value={type}>
                {eventTypeLabels[type]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={runTestEvent}
        disabled={!selectedCamera || testEventMutation.isPending}
        className="w-full"
      >
        {testEventMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Triggering...
          </>
        ) : (
          <>
            <Play className="h-4 w-4 mr-2" />
            Trigger Test Event
          </>
        )}
      </Button>

      {/* Error Display */}
      {testEventMutation.isError && (
        <Alert variant="destructive" className="mt-3">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Test Failed</AlertTitle>
          <AlertDescription>
            {testEventMutation.error instanceof Error
              ? testEventMutation.error.message
              : 'Failed to trigger test event'}
          </AlertDescription>
        </Alert>
      )}

      {/* Success Result */}
      {testResult && testResult.success && (
        <Alert className="mt-3 border-green-500 bg-green-500/10">
          <Check className="h-4 w-4 text-green-500" />
          <AlertTitle className="text-green-500">Event Triggered</AlertTitle>
          <AlertDescription>
            <div className="grid grid-cols-2 gap-1 text-sm mt-2">
              <span>Sensor: {testResult.sensor_name}</span>
              <span>Type: {testResult.event_type}</span>
              <span className="col-span-2">
                Delivered to: {testResult.delivered_to_clients} client{testResult.delivered_to_clients !== 1 ? 's' : ''}
              </span>
            </div>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

interface HomeKitDiagnosticsProps {
  enabled?: boolean;
}

export function HomeKitDiagnostics({ enabled = true }: HomeKitDiagnosticsProps) {
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    new Set(['lifecycle', 'pairing', 'event', 'delivery', 'network', 'mdns'])
  );
  const [selectedLevels, setSelectedLevels] = useState<Set<string>>(
    new Set(['debug', 'info', 'warning', 'error'])
  );
  // Story P7-1.4 AC5: Polling state control for "Pause Auto-Refresh" toggle
  const [isPolling, setIsPolling] = useState(true);

  const { data: diagnostics, isLoading, error } = useHomekitDiagnostics({
    enabled,
    refetchInterval: isPolling ? 5000 : false, // Story P7-1.4 AC5: 5-second polling when enabled
  });

  const toggleCategory = (category: string) => {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const toggleLevel = (level: string) => {
    setSelectedLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) {
        next.delete(level);
      } else {
        next.add(level);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>
          Failed to load diagnostics. {(error as Error).message}
        </AlertDescription>
      </Alert>
    );
  }

  if (!diagnostics) {
    return null;
  }

  // Filter logs by selected categories and levels
  const filteredLogs = diagnostics.recent_logs.filter(
    (log) =>
      selectedCategories.has(log.category) && selectedLevels.has(log.level)
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          <CardTitle>Diagnostics</CardTitle>
        </div>
        <CardDescription>
          HomeKit bridge diagnostic information for troubleshooting
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Connection Status Panel (Story P7-1.4 AC1-5) */}
        <ConnectionStatusPanel
          mdnsAdvertising={diagnostics.mdns_advertising}
          connectedClients={diagnostics.connected_clients}
          sensorDeliveries={diagnostics.sensor_deliveries || []}
          warnings={diagnostics.warnings}
          errors={diagnostics.errors}
          isPolling={isPolling}
          onTogglePolling={() => setIsPolling(!isPolling)}
        />

        {/* Status Grid */}
        <div className="grid grid-cols-2 gap-4">
          {/* Bridge Status */}
          <div className="flex items-center gap-2">
            <div
              className={`w-3 h-3 rounded-full ${
                diagnostics.bridge_running ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm">
              Bridge {diagnostics.bridge_running ? 'Running' : 'Stopped'}
            </span>
          </div>

          {/* mDNS Status */}
          <div className="flex items-center gap-2">
            <Radio
              className={`h-4 w-4 ${
                diagnostics.mdns_advertising
                  ? 'text-green-500'
                  : 'text-muted-foreground'
              }`}
            />
            <span className="text-sm">
              mDNS{' '}
              {diagnostics.mdns_advertising ? 'Advertising' : 'Not Advertising'}
            </span>
          </div>

          {/* Network Binding */}
          {diagnostics.network_binding && (
            <div className="flex items-center gap-2">
              <Network className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-mono">
                {diagnostics.network_binding.ip}:{diagnostics.network_binding.port}
              </span>
            </div>
          )}

          {/* Connected Clients */}
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              {diagnostics.connected_clients} Connected
            </span>
          </div>
        </div>

        {/* Last Event Delivery */}
        {diagnostics.last_event_delivery && (
          <div className="border rounded-lg p-3 bg-muted/30">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Last Event Delivery</span>
              {diagnostics.last_event_delivery.delivered ? (
                <Badge className="bg-green-500 text-white">
                  <Check className="h-3 w-3 mr-1" />
                  Delivered
                </Badge>
              ) : (
                <Badge variant="destructive">
                  <X className="h-3 w-3 mr-1" />
                  Failed
                </Badge>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm text-muted-foreground">
              <span>Camera: {diagnostics.last_event_delivery.camera_id.slice(0, 8)}...</span>
              <span>Sensor: {diagnostics.last_event_delivery.sensor_type}</span>
              <span className="col-span-2">
                Time: {formatTimestamp(diagnostics.last_event_delivery.timestamp)}
              </span>
            </div>
          </div>
        )}

        {/* Connectivity Test Panel (Story P7-1.2 AC6) */}
        <ConnectivityTestPanel />

        {/* Test Event Panel (Story P7-1.3 AC5) */}
        <TestEventPanel />

        {/* Log Filters */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Filters:</span>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                Categories ({selectedCategories.size})
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>Categories</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {['lifecycle', 'pairing', 'event', 'delivery', 'network', 'mdns'].map((cat) => (
                <DropdownMenuCheckboxItem
                  key={cat}
                  checked={selectedCategories.has(cat)}
                  onCheckedChange={() => toggleCategory(cat)}
                >
                  {cat}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                Levels ({selectedLevels.size})
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>Log Levels</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {['debug', 'info', 'warning', 'error'].map((level) => (
                <DropdownMenuCheckboxItem
                  key={level}
                  checked={selectedLevels.has(level)}
                  onCheckedChange={() => toggleLevel(level)}
                >
                  {level}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Diagnostic Logs */}
        <div className="border rounded-lg">
          <div className="px-3 py-2 border-b bg-muted/50">
            <span className="text-sm font-medium">
              Recent Logs ({filteredLogs.length})
            </span>
          </div>
          <ScrollArea className="h-64">
            <div className="px-3">
              {filteredLogs.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground text-sm">
                  No logs matching filters
                </div>
              ) : (
                filteredLogs.map((log, i) => (
                  <DiagnosticLogEntry key={i} entry={log} />
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
