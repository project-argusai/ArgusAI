/**
 * Tests for AudioSettingsSection component (Story P6-3.3)
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { useForm, FormProvider } from 'react-hook-form';
import { describe, it, expect } from 'vitest';
import { AudioSettingsSection } from '@/components/cameras/AudioSettingsSection';
import type { CameraFormValues } from '@/lib/validations/camera';

// Wrapper component that provides form context
function AudioSettingsSectionWrapper({
  defaultValues = {},
}: {
  defaultValues?: Partial<CameraFormValues>;
}) {
  const form = useForm<CameraFormValues>({
    defaultValues: {
      name: 'Test Camera',
      type: 'rtsp',
      frame_rate: 5,
      is_enabled: true,
      motion_enabled: true,
      motion_sensitivity: 'medium',
      motion_cooldown: 30,
      motion_algorithm: 'mog2',
      analysis_mode: 'single_frame',
      audio_enabled: false,
      audio_event_types: [],
      audio_threshold: null,
      ...defaultValues,
    },
  });

  return (
    <FormProvider {...form}>
      <form>
        <AudioSettingsSection form={form} />
      </form>
    </FormProvider>
  );
}

describe('AudioSettingsSection', () => {
  describe('Audio Enabled Toggle (AC#1)', () => {
    it('renders audio enabled toggle switch', () => {
      render(<AudioSettingsSectionWrapper />);

      expect(screen.getByRole('switch')).toBeInTheDocument();
      expect(screen.getByText('Enable Audio Capture')).toBeInTheDocument();
    });

    it('toggle is off by default', () => {
      render(<AudioSettingsSectionWrapper />);

      const toggle = screen.getByRole('switch');
      expect(toggle).toHaveAttribute('aria-checked', 'false');
    });

    it('toggle can be turned on', () => {
      render(<AudioSettingsSectionWrapper />);

      const toggle = screen.getByRole('switch');
      fireEvent.click(toggle);

      expect(toggle).toHaveAttribute('aria-checked', 'true');
    });

    it('shows audio event options when enabled', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: true }} />);

      expect(screen.getByText('Glass Break')).toBeInTheDocument();
      expect(screen.getByText('Gunshot')).toBeInTheDocument();
      expect(screen.getByText('Scream')).toBeInTheDocument();
      expect(screen.getByText('Doorbell')).toBeInTheDocument();
    });

    it('hides audio event options when disabled', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: false }} />);

      expect(screen.queryByText('Glass Break')).not.toBeInTheDocument();
      expect(screen.queryByText('Gunshot')).not.toBeInTheDocument();
    });
  });

  describe('Audio Event Types Selection (AC#2)', () => {
    it('renders all four audio event type checkboxes when enabled', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: true }} />);

      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes).toHaveLength(4);
    });

    it('checkboxes can be selected', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: true }} />);

      const glassBreakCheckbox = screen.getAllByRole('checkbox')[0];
      fireEvent.click(glassBreakCheckbox);

      expect(glassBreakCheckbox).toBeChecked();
    });

    it('displays event type descriptions', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: true }} />);

      expect(screen.getByText('Sound of glass shattering or breaking')).toBeInTheDocument();
      expect(screen.getByText('Sound of gunfire or explosions')).toBeInTheDocument();
      expect(screen.getByText('Human screaming, shouting, or distress calls')).toBeInTheDocument();
      expect(screen.getByText('Doorbell ring or chime sounds')).toBeInTheDocument();
    });

    it('pre-selected event types are checked', () => {
      render(
        <AudioSettingsSectionWrapper
          defaultValues={{
            audio_enabled: true,
            audio_event_types: ['glass_break', 'doorbell'],
          }}
        />
      );

      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes[0]).toBeChecked(); // glass_break
      expect(checkboxes[1]).not.toBeChecked(); // gunshot
      expect(checkboxes[2]).not.toBeChecked(); // scream
      expect(checkboxes[3]).toBeChecked(); // doorbell
    });
  });

  describe('Confidence Threshold Slider (AC#3)', () => {
    it('renders threshold slider when audio is enabled', () => {
      render(<AudioSettingsSectionWrapper defaultValues={{ audio_enabled: true }} />);

      expect(screen.getByText('Confidence Threshold')).toBeInTheDocument();
      expect(screen.getByRole('slider')).toBeInTheDocument();
    });

    it('shows "Use Global Default" when threshold is null', () => {
      render(
        <AudioSettingsSectionWrapper
          defaultValues={{ audio_enabled: true, audio_threshold: null }}
        />
      );

      expect(screen.getByText('Use Global Default (70%)')).toBeInTheDocument();
    });

    it('shows percentage when threshold is set', () => {
      render(
        <AudioSettingsSectionWrapper
          defaultValues={{ audio_enabled: true, audio_threshold: 0.85 }}
        />
      );

      expect(screen.getByText('85%')).toBeInTheDocument();
    });

    it('shows reset to default button when threshold is set', () => {
      render(
        <AudioSettingsSectionWrapper
          defaultValues={{ audio_enabled: true, audio_threshold: 0.8 }}
        />
      );

      expect(screen.getByText('Reset to Default')).toBeInTheDocument();
    });
  });

  describe('Section Header', () => {
    it('displays section title', () => {
      render(<AudioSettingsSectionWrapper />);

      expect(screen.getByText('Audio Detection Settings')).toBeInTheDocument();
    });

    it('displays section description', () => {
      render(<AudioSettingsSectionWrapper />);

      expect(
        screen.getByText('Configure audio capture and event detection for this camera')
      ).toBeInTheDocument();
    });
  });
});
