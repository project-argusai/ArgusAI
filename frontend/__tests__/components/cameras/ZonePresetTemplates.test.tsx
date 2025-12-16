/**
 * Tests for ZonePresetTemplates component
 * Story P5-5.3: Create Detection Zone Preset Templates
 *
 * Tests coverage:
 * - AC1: All 5 preset templates available (Full Frame, Top Half, Bottom Half, Center, L-Shape)
 * - AC2: One-click application calls onTemplateSelect with correct vertices and name
 * - AC3: Presets use normalized coordinates (0-1 range)
 * - AC4: Accessibility - aria-labels present on all buttons
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ZonePresetTemplates, PRESET_TEMPLATES } from '@/components/cameras/ZonePresetTemplates';

describe('ZonePresetTemplates', () => {
  describe('AC1: All preset templates rendered', () => {
    it('renders Full Frame preset button', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByRole('button', { name: /full frame/i })).toBeInTheDocument();
    });

    it('renders Top Half preset button', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByRole('button', { name: /top half/i })).toBeInTheDocument();
    });

    it('renders Bottom Half preset button', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByRole('button', { name: /bottom half/i })).toBeInTheDocument();
    });

    it('renders Center preset button', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByRole('button', { name: /center/i })).toBeInTheDocument();
    });

    it('renders L-Shape preset button', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByRole('button', { name: /l-shape/i })).toBeInTheDocument();
    });

    it('renders all 5 preset buttons', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(5);
    });
  });

  describe('AC2: One-click application calls onTemplateSelect', () => {
    it('calls onTemplateSelect with Full Frame vertices and name when clicked', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      await user.click(screen.getByRole('button', { name: /full frame/i }));

      expect(mockOnSelect).toHaveBeenCalledTimes(1);
      expect(mockOnSelect).toHaveBeenCalledWith(
        PRESET_TEMPLATES.fullFrame.vertices(),
        'Full Frame'
      );
    });

    it('calls onTemplateSelect with Top Half vertices and name when clicked', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      await user.click(screen.getByRole('button', { name: /top half/i }));

      expect(mockOnSelect).toHaveBeenCalledWith(
        PRESET_TEMPLATES.topHalf.vertices(),
        'Top Half'
      );
    });

    it('calls onTemplateSelect with Bottom Half vertices and name when clicked', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      await user.click(screen.getByRole('button', { name: /bottom half/i }));

      expect(mockOnSelect).toHaveBeenCalledWith(
        PRESET_TEMPLATES.bottomHalf.vertices(),
        'Bottom Half'
      );
    });

    it('calls onTemplateSelect with Center vertices and name when clicked', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      await user.click(screen.getByRole('button', { name: /center/i }));

      expect(mockOnSelect).toHaveBeenCalledWith(
        PRESET_TEMPLATES.center.vertices(),
        'Center'
      );
    });

    it('calls onTemplateSelect with L-Shape vertices and name when clicked', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      await user.click(screen.getByRole('button', { name: /l-shape/i }));

      expect(mockOnSelect).toHaveBeenCalledWith(
        PRESET_TEMPLATES.lShape.vertices(),
        'L-Shape'
      );
    });
  });

  describe('AC3: Presets use normalized coordinates (0-1 range)', () => {
    it('Full Frame vertices are in 0-1 range', () => {
      const vertices = PRESET_TEMPLATES.fullFrame.vertices();
      vertices.forEach((v) => {
        expect(v.x).toBeGreaterThanOrEqual(0);
        expect(v.x).toBeLessThanOrEqual(1);
        expect(v.y).toBeGreaterThanOrEqual(0);
        expect(v.y).toBeLessThanOrEqual(1);
      });
    });

    it('Top Half vertices are in 0-1 range', () => {
      const vertices = PRESET_TEMPLATES.topHalf.vertices();
      vertices.forEach((v) => {
        expect(v.x).toBeGreaterThanOrEqual(0);
        expect(v.x).toBeLessThanOrEqual(1);
        expect(v.y).toBeGreaterThanOrEqual(0);
        expect(v.y).toBeLessThanOrEqual(1);
      });
    });

    it('Bottom Half vertices are in 0-1 range', () => {
      const vertices = PRESET_TEMPLATES.bottomHalf.vertices();
      vertices.forEach((v) => {
        expect(v.x).toBeGreaterThanOrEqual(0);
        expect(v.x).toBeLessThanOrEqual(1);
        expect(v.y).toBeGreaterThanOrEqual(0);
        expect(v.y).toBeLessThanOrEqual(1);
      });
    });

    it('Center vertices are in 0-1 range', () => {
      const vertices = PRESET_TEMPLATES.center.vertices();
      vertices.forEach((v) => {
        expect(v.x).toBeGreaterThanOrEqual(0);
        expect(v.x).toBeLessThanOrEqual(1);
        expect(v.y).toBeGreaterThanOrEqual(0);
        expect(v.y).toBeLessThanOrEqual(1);
      });
    });

    it('L-Shape vertices are in 0-1 range', () => {
      const vertices = PRESET_TEMPLATES.lShape.vertices();
      vertices.forEach((v) => {
        expect(v.x).toBeGreaterThanOrEqual(0);
        expect(v.x).toBeLessThanOrEqual(1);
        expect(v.y).toBeGreaterThanOrEqual(0);
        expect(v.y).toBeLessThanOrEqual(1);
      });
    });

    it('Full Frame covers entire canvas (0,0 to 1,1)', () => {
      const vertices = PRESET_TEMPLATES.fullFrame.vertices();
      expect(vertices).toContainEqual({ x: 0, y: 0 });
      expect(vertices).toContainEqual({ x: 1, y: 0 });
      expect(vertices).toContainEqual({ x: 1, y: 1 });
      expect(vertices).toContainEqual({ x: 0, y: 1 });
    });

    it('Top Half covers y range 0 to 0.5', () => {
      const vertices = PRESET_TEMPLATES.topHalf.vertices();
      expect(vertices.some((v) => v.y === 0)).toBe(true);
      expect(vertices.some((v) => v.y === 0.5)).toBe(true);
      expect(vertices.every((v) => v.y <= 0.5)).toBe(true);
    });

    it('Bottom Half covers y range 0.5 to 1', () => {
      const vertices = PRESET_TEMPLATES.bottomHalf.vertices();
      expect(vertices.some((v) => v.y === 0.5)).toBe(true);
      expect(vertices.some((v) => v.y === 1)).toBe(true);
      expect(vertices.every((v) => v.y >= 0.5)).toBe(true);
    });
  });

  describe('AC4: Accessibility - aria-labels present', () => {
    it('Full Frame button has descriptive aria-label', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const button = screen.getByRole('button', { name: /full frame/i });
      expect(button).toHaveAttribute('aria-label');
      expect(button.getAttribute('aria-label')).toContain('Full Frame');
    });

    it('Top Half button has descriptive aria-label', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const button = screen.getByRole('button', { name: /top half/i });
      expect(button).toHaveAttribute('aria-label');
      expect(button.getAttribute('aria-label')).toContain('Top Half');
    });

    it('Bottom Half button has descriptive aria-label', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const button = screen.getByRole('button', { name: /bottom half/i });
      expect(button).toHaveAttribute('aria-label');
      expect(button.getAttribute('aria-label')).toContain('Bottom Half');
    });

    it('Center button has descriptive aria-label', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const button = screen.getByRole('button', { name: /center/i });
      expect(button).toHaveAttribute('aria-label');
      expect(button.getAttribute('aria-label')).toContain('Center');
    });

    it('L-Shape button has descriptive aria-label', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const button = screen.getByRole('button', { name: /l-shape/i });
      expect(button).toHaveAttribute('aria-label');
      expect(button.getAttribute('aria-label')).toContain('L-Shape');
    });

    it('all icons have aria-hidden for screen readers', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      const icons = document.querySelectorAll('svg');
      icons.forEach((icon) => {
        expect(icon).toHaveAttribute('aria-hidden', 'true');
      });
    });
  });

  describe('Keyboard navigation', () => {
    it('preset buttons are focusable and respond to Enter key', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      const button = screen.getByRole('button', { name: /full frame/i });
      await user.tab();
      expect(button).toHaveFocus();

      await user.keyboard('{Enter}');
      expect(mockOnSelect).toHaveBeenCalled();
    });

    it('preset buttons respond to Space key', async () => {
      const user = userEvent.setup();
      const mockOnSelect = vi.fn();
      render(<ZonePresetTemplates onTemplateSelect={mockOnSelect} />);

      const button = screen.getByRole('button', { name: /top half/i });
      button.focus();

      await user.keyboard(' ');
      expect(mockOnSelect).toHaveBeenCalled();
    });
  });

  describe('UI text', () => {
    it('displays "Quick Templates" heading', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(screen.getByText('Quick Templates')).toBeInTheDocument();
    });

    it('displays help text about custom polygons', () => {
      render(<ZonePresetTemplates onTemplateSelect={vi.fn()} />);
      expect(
        screen.getByText(/click a template to use a pre-defined shape/i)
      ).toBeInTheDocument();
    });
  });
});
