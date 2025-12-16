'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { IZoneVertex } from '@/types/camera';
import { Maximize, ArrowUpToLine, ArrowDownToLine, Square, CornerDownRight } from 'lucide-react';

interface ZonePresetTemplatesProps {
  /**
   * Callback when user selects a preset template
   * @param vertices - Pre-defined vertices for the selected shape (normalized 0-1)
   * @param name - Preset name for the zone
   */
  onTemplateSelect: (vertices: IZoneVertex[], name: string) => void;
}

/**
 * Preset template shapes with normalized coordinates (0-1 scale)
 * All coordinates are in 0-1 range for responsive display
 */
export const PRESET_TEMPLATES = {
  /**
   * Full Frame - covers entire canvas
   */
  fullFrame: {
    name: 'Full Frame',
    vertices: (): IZoneVertex[] => [
      { x: 0, y: 0 },     // Top-left
      { x: 1, y: 0 },     // Top-right
      { x: 1, y: 1 },     // Bottom-right
      { x: 0, y: 1 },     // Bottom-left
    ],
  },

  /**
   * Top Half - upper 50% of canvas
   */
  topHalf: {
    name: 'Top Half',
    vertices: (): IZoneVertex[] => [
      { x: 0, y: 0 },     // Top-left
      { x: 1, y: 0 },     // Top-right
      { x: 1, y: 0.5 },   // Bottom-right
      { x: 0, y: 0.5 },   // Bottom-left
    ],
  },

  /**
   * Bottom Half - lower 50% of canvas
   */
  bottomHalf: {
    name: 'Bottom Half',
    vertices: (): IZoneVertex[] => [
      { x: 0, y: 0.5 },   // Top-left
      { x: 1, y: 0.5 },   // Top-right
      { x: 1, y: 1 },     // Bottom-right
      { x: 0, y: 1 },     // Bottom-left
    ],
  },

  /**
   * Center - centered rectangle covering ~60% of canvas
   */
  center: {
    name: 'Center',
    vertices: (): IZoneVertex[] => [
      { x: 0.2, y: 0.2 },  // Top-left
      { x: 0.8, y: 0.2 },  // Top-right
      { x: 0.8, y: 0.8 },  // Bottom-right
      { x: 0.2, y: 0.8 },  // Bottom-left
    ],
  },

  /**
   * L-Shape - covers left side and bottom
   * Useful for covering entryways, doorways, or specific corners
   */
  lShape: {
    name: 'L-Shape',
    vertices: (): IZoneVertex[] => [
      { x: 0, y: 0 },     // Top-left of vertical part
      { x: 0.4, y: 0 },   // Top-right of vertical part
      { x: 0.4, y: 0.6 }, // Elbow inner corner
      { x: 1, y: 0.6 },   // Top-right of horizontal part
      { x: 1, y: 1 },     // Bottom-right
      { x: 0, y: 1 },     // Bottom-left
    ],
  },
};

/**
 * ZonePresetTemplates - Preset shape templates for quick zone creation
 *
 * Features:
 * - Pre-defined shapes: Full Frame, Top Half, Bottom Half, Center, L-Shape
 * - Normalized coordinates (0-1 scale) for responsive display
 * - One-click zone creation for common use cases
 * - Visual icons matching each shape
 * - Accessible with aria-labels and keyboard navigation
 */
export function ZonePresetTemplates({ onTemplateSelect }: ZonePresetTemplatesProps) {
  const presets = [
    {
      key: 'fullFrame',
      template: PRESET_TEMPLATES.fullFrame,
      icon: Maximize,
      description: 'Cover entire frame',
    },
    {
      key: 'topHalf',
      template: PRESET_TEMPLATES.topHalf,
      icon: ArrowUpToLine,
      description: 'Cover top half of frame',
    },
    {
      key: 'bottomHalf',
      template: PRESET_TEMPLATES.bottomHalf,
      icon: ArrowDownToLine,
      description: 'Cover bottom half of frame',
    },
    {
      key: 'center',
      template: PRESET_TEMPLATES.center,
      icon: Square,
      description: 'Cover center of frame',
    },
    {
      key: 'lShape',
      template: PRESET_TEMPLATES.lShape,
      icon: CornerDownRight,
      description: 'L-shaped zone covering left side and bottom',
    },
  ];

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-muted-foreground">
        Quick Templates
      </div>
      <div className="flex flex-wrap gap-2">
        {presets.map(({ key, template, icon: Icon, description }) => (
          <Button
            key={key}
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onTemplateSelect(template.vertices(), template.name)}
            className="flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-label={`Apply ${template.name} detection zone preset: ${description}`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {template.name}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Click a template to use a pre-defined shape, or draw your own custom polygon
      </p>
    </div>
  );
}
