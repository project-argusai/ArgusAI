/**
 * ArgusAI Logo component
 * Displays the ArgusAI logo image with optional text
 * Story P13-4.2: Update frontend branding
 */

import Image from 'next/image';
import { cn } from '@/lib/utils';

interface LogoProps {
  /** Size of the logo in pixels */
  size?: number;
  /** Whether to show the text label */
  showText?: boolean;
  /** Text to display (defaults to settings.systemName via parent) */
  text?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ArgusAI logo component with optional text
 */
export function Logo({ size = 24, showText = true, text = 'ArgusAI', className }: LogoProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
        <Image
          src="/icons/icon-96.png"
          alt="ArgusAI"
          width={size}
          height={size}
          className="object-contain"
          priority
        />
      </div>
      {showText && (
        <span className="font-bold text-lg truncate">{text}</span>
      )}
    </div>
  );
}
