/**
 * AddCameraDropdown - Dropdown menu for adding cameras
 *
 * Offers options to add cameras manually (RTSP/USB) or via UniFi Protect.
 * UniFi Protect option redirects to Settings page.
 * Follows UX spec Section 10.6.
 */

'use client';

import { useRouter } from 'next/navigation';
import { Plus, Camera, Shield, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface AddCameraDropdownProps {
  className?: string;
}

/**
 * Dropdown menu for adding cameras with multiple options
 */
export function AddCameraDropdown({ className }: AddCameraDropdownProps) {
  const router = useRouter();

  const handleManualClick = () => {
    router.push('/cameras/new');
  };

  const handleProtectClick = () => {
    // Navigate to Settings page with UniFi Protect section
    router.push('/settings?tab=protect');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button className={className} aria-label="Add camera options">
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          Add Camera
          <ChevronDown className="h-4 w-4 ml-2" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem onClick={handleManualClick} className="cursor-pointer">
          <Camera className="h-4 w-4 mr-2" aria-hidden="true" />
          <div className="flex flex-col">
            <span className="font-medium">Manual (RTSP/USB)</span>
            <span className="text-xs text-muted-foreground">
              Add RTSP IP camera or USB webcam
            </span>
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleProtectClick} className="cursor-pointer">
          <Shield className="h-4 w-4 mr-2" aria-hidden="true" />
          <div className="flex flex-col">
            <span className="font-medium">UniFi Protect</span>
            <span className="text-xs text-muted-foreground">
              Auto-discover cameras from controller
            </span>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
