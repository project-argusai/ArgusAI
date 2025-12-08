/**
 * AIProviderBadge - displays which AI provider analyzed an event
 *
 * Story P3-4.5: Shows compact badge with provider name and icon,
 * color-coded per provider, with tooltip showing full provider name.
 *
 * Colors:
 * - OpenAI: Green
 * - xAI Grok: Orange
 * - Anthropic Claude: Amber
 * - Google Gemini: Blue
 */

'use client';

import { Sparkles, Zap, MessageCircle, Sparkle } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

/**
 * Valid AI provider types
 */
type AIProvider = 'openai' | 'grok' | 'claude' | 'gemini';

interface AIProviderBadgeProps {
  provider?: string | null;
}

/**
 * Configuration for each AI provider
 */
const PROVIDER_CONFIG: Record<
  AIProvider,
  {
    icon: typeof Sparkles;
    label: string;
    fullName: string;
    bgClass: string;
    textClass: string;
  }
> = {
  openai: {
    icon: Sparkles,
    label: 'OpenAI',
    fullName: 'OpenAI GPT-4o mini',
    bgClass: 'bg-green-100 dark:bg-green-900/30',
    textClass: 'text-green-700 dark:text-green-300',
  },
  grok: {
    icon: Zap,
    label: 'Grok',
    fullName: 'xAI Grok 2 Vision',
    bgClass: 'bg-orange-100 dark:bg-orange-900/30',
    textClass: 'text-orange-700 dark:text-orange-300',
  },
  claude: {
    icon: MessageCircle,
    label: 'Claude',
    fullName: 'Anthropic Claude 3 Haiku',
    bgClass: 'bg-amber-100 dark:bg-amber-900/30',
    textClass: 'text-amber-700 dark:text-amber-300',
  },
  gemini: {
    icon: Sparkle,
    label: 'Gemini',
    fullName: 'Google Gemini 2.0 Flash',
    bgClass: 'bg-blue-100 dark:bg-blue-900/30',
    textClass: 'text-blue-700 dark:text-blue-300',
  },
};

/**
 * Type guard to check if a string is a valid AI provider
 */
function isValidProvider(provider: string): provider is AIProvider {
  return provider in PROVIDER_CONFIG;
}

export function AIProviderBadge({ provider }: AIProviderBadgeProps) {
  // AC2: Handle null/undefined provider - show nothing
  if (!provider) {
    return null;
  }

  // Validate provider is a known type
  if (!isValidProvider(provider)) {
    return null;
  }

  const config = PROVIDER_CONFIG[provider];
  const Icon = config.icon;

  // Build tooltip content
  const tooltipContent = (
    <div className="text-xs">
      <p className="font-medium">{config.fullName}</p>
    </div>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${config.bgClass} ${config.textClass} cursor-help`}
        >
          <Icon className="h-3 w-3" aria-hidden="true" />
          <span>{config.label}</span>
          {/* AC5: Accessibility - sr-only text for screen readers */}
          <span className="sr-only">
            AI Provider: {config.fullName}
          </span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {tooltipContent}
      </TooltipContent>
    </Tooltip>
  );
}
