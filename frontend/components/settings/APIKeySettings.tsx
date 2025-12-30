'use client';

/**
 * APIKeySettings - Manage API keys for external integrations (Story P13-1.6)
 *
 * Provides UI for:
 * - Creating API keys with customizable scopes
 * - Listing existing API keys
 * - Revoking API keys
 * - Viewing usage statistics
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow, format } from 'date-fns';
import {
  Key,
  Plus,
  Trash2,
  Copy,
  AlertTriangle,
  Loader2,
  Check,
  Eye,
  EyeOff,
} from 'lucide-react';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api-client';
import type { IAPIKeyListItem, IAPIKeyCreateResponse, APIKeyScope } from '@/types/api-key';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const SCOPES: { value: APIKeyScope; label: string; description: string }[] = [
  { value: 'read:events', label: 'Read Events', description: 'Read access to events' },
  { value: 'read:cameras', label: 'Read Cameras', description: 'Read access to cameras' },
  { value: 'write:cameras', label: 'Write Cameras', description: 'Write access to cameras' },
  { value: 'admin', label: 'Admin', description: 'Full access (includes all other scopes)' },
];

function ScopesBadges({ scopes }: { scopes: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {scopes.map((scope) => (
        <Badge key={scope} variant="secondary" className="text-xs">
          {scope}
        </Badge>
      ))}
    </div>
  );
}

export function APIKeySettings() {
  const queryClient = useQueryClient();
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newKeyResult, setNewKeyResult] = useState<IAPIKeyCreateResponse | null>(null);
  const [showNewKey, setShowNewKey] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showRevoked, setShowRevoked] = useState(false);

  // Create form state
  const [keyName, setKeyName] = useState('');
  const [selectedScopes, setSelectedScopes] = useState<APIKeyScope[]>(['read:events']);
  const [expiresIn, setExpiresIn] = useState<string>('never');
  const [rateLimit, setRateLimit] = useState(100);

  // Fetch API keys
  const { data: keys, isLoading, error } = useQuery({
    queryKey: ['api-keys', showRevoked],
    queryFn: () => apiClient.apiKeys.list(showRevoked),
  });

  // Create API key mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      let expires_at: string | null = null;
      if (expiresIn !== 'never') {
        const now = new Date();
        const days = parseInt(expiresIn, 10);
        now.setDate(now.getDate() + days);
        expires_at = now.toISOString();
      }

      return apiClient.apiKeys.create({
        name: keyName,
        scopes: selectedScopes,
        expires_at,
        rate_limit_per_minute: rateLimit,
      });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      setNewKeyResult(result);
      setShowCreateDialog(false);
      // Reset form
      setKeyName('');
      setSelectedScopes(['read:events']);
      setExpiresIn('never');
      setRateLimit(100);
      toast.success('API key created');
    },
    onError: (error: Error) => {
      toast.error(`Failed to create API key: ${error.message}`);
    },
  });

  // Revoke API key mutation
  const revokeMutation = useMutation({
    mutationFn: (keyId: string) => apiClient.apiKeys.revoke(keyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      toast.success('API key revoked');
    },
    onError: () => {
      toast.error('Failed to revoke API key');
    },
  });

  const handleCopyKey = async () => {
    if (newKeyResult?.key) {
      await navigator.clipboard.writeText(newKeyResult.key);
      setCopied(true);
      toast.success('API key copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleScopeChange = (scope: APIKeyScope, checked: boolean) => {
    if (checked) {
      // If admin is selected, clear others (admin includes all)
      if (scope === 'admin') {
        setSelectedScopes(['admin']);
      } else {
        // Remove admin if selecting specific scopes
        setSelectedScopes((prev) => [...prev.filter((s) => s !== 'admin'), scope]);
      }
    } else {
      setSelectedScopes((prev) => prev.filter((s) => s !== scope));
    }
  };

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            API Keys
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            Failed to load API keys
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                API Keys
              </CardTitle>
              <CardDescription>
                Create and manage API keys for external integrations
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={showRevoked}
                  onCheckedChange={(checked) => setShowRevoked(!!checked)}
                />
                Show revoked
              </label>
              <Button onClick={() => setShowCreateDialog(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Key
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : !keys || keys.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Key className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>No API keys yet</p>
              <p className="text-sm mt-1">
                Create an API key to integrate with external services
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {keys.map((apiKey: IAPIKeyListItem) => (
                <div
                  key={apiKey.id}
                  className={`flex items-center justify-between p-4 rounded-lg border ${
                    !apiKey.is_active ? 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950 opacity-60' : ''
                  }`}
                >
                  <div className="flex flex-col gap-2 min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{apiKey.name}</span>
                      {!apiKey.is_active && (
                        <Badge variant="destructive" className="text-xs">
                          Revoked
                        </Badge>
                      )}
                      {apiKey.expires_at && new Date(apiKey.expires_at) < new Date() && (
                        <Badge variant="destructive" className="text-xs">
                          Expired
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <code className="bg-muted px-2 py-0.5 rounded">{apiKey.prefix}</code>
                      <ScopesBadges scopes={apiKey.scopes} />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      <span>Created {formatDistanceToNow(new Date(apiKey.created_at), { addSuffix: true })}</span>
                      {apiKey.last_used_at && (
                        <span> • Last used {formatDistanceToNow(new Date(apiKey.last_used_at), { addSuffix: true })}</span>
                      )}
                      <span> • {apiKey.usage_count} requests</span>
                      {apiKey.expires_at && (
                        <span> • Expires {format(new Date(apiKey.expires_at), 'MMM d, yyyy')}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {apiKey.is_active && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Revoke API Key?</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will immediately revoke &quot;{apiKey.name}&quot;.
                              Any applications using this key will stop working.
                              This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => revokeMutation.mutate(apiKey.id)}
                              disabled={revokeMutation.isPending}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              {revokeMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                              Revoke
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create API Key Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Create a new API key for external integrations. The key will only be shown once.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="key-name">Name</Label>
              <Input
                id="key-name"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder="Home Assistant Integration"
                maxLength={255}
              />
            </div>

            <div className="space-y-2">
              <Label>Scopes</Label>
              <div className="space-y-2">
                {SCOPES.map((scope) => (
                  <label key={scope.value} className="flex items-start gap-3 p-2 rounded border hover:bg-muted cursor-pointer">
                    <Checkbox
                      checked={selectedScopes.includes(scope.value)}
                      onCheckedChange={(checked) => handleScopeChange(scope.value, !!checked)}
                      className="mt-0.5"
                    />
                    <div>
                      <div className="font-medium text-sm">{scope.label}</div>
                      <div className="text-xs text-muted-foreground">{scope.description}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="expires-in">Expires</Label>
              <Select value={expiresIn} onValueChange={setExpiresIn}>
                <SelectTrigger id="expires-in">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never</SelectItem>
                  <SelectItem value="7">7 days</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                  <SelectItem value="365">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-limit">Rate Limit (requests/minute)</Label>
              <Input
                id="rate-limit"
                type="number"
                min={1}
                max={10000}
                value={rateLimit}
                onChange={(e) => setRateLimit(parseInt(e.target.value, 10) || 100)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !keyName.trim() || selectedScopes.length === 0}
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create Key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Key Result Dialog */}
      <Dialog open={!!newKeyResult} onOpenChange={(open) => !open && setNewKeyResult(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-green-600">
              <Check className="h-5 w-5" />
              API Key Created
            </DialogTitle>
            <DialogDescription>
              <span className="text-amber-600 font-medium">
                Copy your API key now. It will only be shown once!
              </span>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Your API Key</Label>
              <div className="flex items-center gap-2">
                <code className="flex-1 p-3 bg-muted rounded text-sm font-mono break-all">
                  {showNewKey ? newKeyResult?.key : '••••••••••••••••••••••••••••••••••••••••'}
                </code>
                <Button variant="ghost" size="icon" onClick={() => setShowNewKey(!showNewKey)}>
                  {showNewKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button variant="outline" size="icon" onClick={handleCopyKey}>
                  {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="p-3 rounded bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-800 dark:text-amber-200">
                  <p className="font-medium">Important</p>
                  <p>Store this key securely. You won&apos;t be able to see it again. If you lose it, you&apos;ll need to create a new one.</p>
                </div>
              </div>
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <p><strong>Name:</strong> {newKeyResult?.name}</p>
              <p><strong>Prefix:</strong> {newKeyResult?.prefix}</p>
              <p><strong>Scopes:</strong> {newKeyResult?.scopes.join(', ')}</p>
              <p><strong>Rate Limit:</strong> {newKeyResult?.rate_limit_per_minute} requests/minute</p>
              {newKeyResult?.expires_at && (
                <p><strong>Expires:</strong> {format(new Date(newKeyResult.expires_at), 'MMM d, yyyy')}</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setNewKeyResult(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
