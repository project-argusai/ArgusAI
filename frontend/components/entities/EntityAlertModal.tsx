/**
 * EntityAlertModal component - Stub UI for configuring entity-based alerts (Story P7-4.3)
 *
 * This is a non-functional UI that displays alert configuration options.
 * Actual entity alerting will be implemented in a future phase.
 *
 * AC1: Modal opens from entity card "Add Alert" button
 * AC2: Shows "Notify when seen" option
 * AC3: Shows "Notify when NOT seen for X hours" option with hour input
 * AC4: Time range configuration displayed
 * AC5: "Coming Soon" message shown when save attempted
 * AC6: Link to alert rules page provided
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Bell, Clock, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import type { IEntity } from '@/types/entity';

export interface EntityAlertModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when the modal should close */
  onClose: () => void;
  /** The entity to configure alerts for */
  entity: IEntity;
}

/**
 * EntityAlertModal - Non-functional stub for entity alert configuration
 */
export function EntityAlertModal({ isOpen, onClose, entity }: EntityAlertModalProps) {
  // Form state (non-functional, just for UI)
  const [notifyWhenSeen, setNotifyWhenSeen] = useState(true);
  const [notifyWhenNotSeen, setNotifyWhenNotSeen] = useState(false);
  const [notSeenHours, setNotSeenHours] = useState('24');
  const [timeRange, setTimeRange] = useState<'all-day' | 'custom'>('all-day');

  // Display name with fallback
  const displayName = entity.name || `Unknown ${entity.entity_type}`;

  // AC5: Handle save - show "Coming Soon" message
  const handleSave = () => {
    toast.info('Coming Soon', {
      description: 'Entity-based alerts will be available in a future update. For now, use the Alert Rules page to create general alerts.',
    });
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Create Alert for {displayName}
          </DialogTitle>
          <DialogDescription>
            Configure when you want to be notified about this {entity.entity_type}.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* AC2: Notify when seen option */}
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="notify-when-seen" className="text-sm font-medium">
                Notify when seen
              </Label>
              <p className="text-xs text-muted-foreground">
                Receive a notification whenever this {entity.entity_type} is detected
              </p>
            </div>
            <Switch
              id="notify-when-seen"
              checked={notifyWhenSeen}
              onCheckedChange={setNotifyWhenSeen}
              aria-label="Notify when seen"
            />
          </div>

          {/* AC3: Notify when NOT seen option with hour input */}
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-0.5">
                <Label htmlFor="notify-when-not-seen" className="text-sm font-medium">
                  Notify when NOT seen
                </Label>
                <p className="text-xs text-muted-foreground">
                  Alert if this {entity.entity_type} is not detected for a period
                </p>
              </div>
              <Switch
                id="notify-when-not-seen"
                checked={notifyWhenNotSeen}
                onCheckedChange={setNotifyWhenNotSeen}
                aria-label="Notify when not seen"
              />
            </div>

            {notifyWhenNotSeen && (
              <div className="ml-4 flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <Label htmlFor="not-seen-hours" className="text-sm">
                  Alert after
                </Label>
                <Input
                  id="not-seen-hours"
                  type="number"
                  min="1"
                  max="168"
                  value={notSeenHours}
                  onChange={(e) => setNotSeenHours(e.target.value)}
                  className="w-20"
                  aria-label="Hours until not seen alert"
                />
                <span className="text-sm text-muted-foreground">hours without detection</span>
              </div>
            )}
          </div>

          {/* AC4: Time range configuration */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Alert Schedule</Label>
            <RadioGroup
              value={timeRange}
              onValueChange={(value) => setTimeRange(value as 'all-day' | 'custom')}
              className="space-y-2"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="all-day" id="all-day" />
                <Label htmlFor="all-day" className="text-sm font-normal cursor-pointer">
                  All day (24/7)
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="custom" id="custom" />
                <Label htmlFor="custom" className="text-sm font-normal cursor-pointer">
                  Custom schedule
                </Label>
              </div>
            </RadioGroup>

            {timeRange === 'custom' && (
              <div className="ml-6 p-3 bg-muted/50 rounded-md">
                <p className="text-xs text-muted-foreground">
                  Custom scheduling options will be available when this feature is released.
                </p>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          {/* AC6: Link to alert rules page */}
          <Link
            href="/rules"
            className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 underline-offset-4 hover:underline"
            onClick={onClose}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View Alert Rules
          </Link>
          <div className="flex-1" />
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          {/* AC5: Save button shows Coming Soon */}
          <Button onClick={handleSave}>
            Save Alert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
