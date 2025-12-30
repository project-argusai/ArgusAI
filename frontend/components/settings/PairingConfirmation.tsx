'use client';

/**
 * PairingConfirmation - Confirm mobile device pairing codes (Story P12-3.3)
 *
 * Allows users to enter 6-digit pairing codes from their mobile app
 * to link their device for push notifications and authentication.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Smartphone, Check, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface PendingPairing {
  code: string;
  device_name: string | null;
  device_model: string | null;
  platform: string;
  expires_at: string;
  created_at: string;
}

export function PairingConfirmation() {
  const queryClient = useQueryClient();
  const [manualCode, setManualCode] = useState('');

  // Fetch pending pairings
  const { data: pendingData, isLoading, refetch } = useQuery({
    queryKey: ['pending-pairings'],
    queryFn: async () => {
      const response = await fetch('/api/v1/mobile/auth/pending', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to fetch pending pairings');
      return response.json() as Promise<{ pairings: PendingPairing[]; total: number }>;
    },
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Confirm pairing mutation
  const confirmMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await fetch('/api/v1/mobile/auth/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to confirm pairing');
      }
      return response.json();
    },
    onSuccess: (data) => {
      toast.success(`Device "${data.device_name || data.platform}" paired successfully!`);
      queryClient.invalidateQueries({ queryKey: ['pending-pairings'] });
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      setManualCode('');
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleManualConfirm = () => {
    if (manualCode.length !== 6) {
      toast.error('Please enter a 6-digit code');
      return;
    }
    confirmMutation.mutate(manualCode);
  };

  const handleConfirmPending = (code: string) => {
    confirmMutation.mutate(code);
  };

  const pendingPairings = pendingData?.pairings ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="h-5 w-5" />
              Device Pairing
            </CardTitle>
            <CardDescription>
              Pair mobile devices by entering the code shown on the device
            </CardDescription>
          </div>
          <Button variant="ghost" size="icon" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Manual Code Entry */}
        <div className="flex gap-2">
          <Input
            placeholder="Enter 6-digit code"
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            maxLength={6}
            className="font-mono text-lg tracking-widest"
          />
          <Button
            onClick={handleManualConfirm}
            disabled={manualCode.length !== 6 || confirmMutation.isPending}
          >
            {confirmMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Pending Pairings List */}
        {isLoading ? (
          <div className="text-center py-4 text-muted-foreground">
            Loading pending requests...
          </div>
        ) : pendingPairings.length > 0 ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">Pending Pairing Requests:</p>
            {pendingPairings.map((pairing) => (
              <div
                key={pairing.code}
                className="flex items-center justify-between p-3 rounded-lg border bg-card"
              >
                <div className="flex items-center gap-3">
                  <Badge variant="outline" className="font-mono text-lg">
                    {pairing.code}
                  </Badge>
                  <div>
                    <p className="text-sm font-medium">
                      {pairing.device_name || pairing.device_model || `${pairing.platform} device`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Expires {formatDistanceToNow(new Date(pairing.expires_at), { addSuffix: true })}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="default"
                    onClick={() => handleConfirmPending(pairing.code)}
                    disabled={confirmMutation.isPending}
                  >
                    <Check className="h-4 w-4 mr-1" />
                    Approve
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-4 text-muted-foreground text-sm">
            No pending pairing requests. Open your mobile app and select &quot;Pair Device&quot;
            to generate a code.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
