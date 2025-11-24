/**
 * Settings context for managing system-wide settings and preferences
 */

'use client';

import { createContext, useContext, useState, useCallback, ReactNode, useEffect } from 'react';

export interface SystemSettings {
  // AI Provider Settings
  aiProvider: 'openai' | 'gemini' | 'claude';
  aiApiKey?: string;

  // Data Retention
  dataRetentionDays: number;

  // Motion Detection
  defaultMotionSensitivity: 'low' | 'medium' | 'high';

  // UI Preferences
  theme: 'light' | 'dark' | 'system';
  timezone: string;

  // System
  backendUrl: string;
}

interface SettingsContextType {
  settings: SystemSettings;
  isLoading: boolean;
  updateSetting: <K extends keyof SystemSettings>(key: K, value: SystemSettings[K]) => void;
  updateSettings: (newSettings: Partial<SystemSettings>) => void;
  resetSettings: () => void;
}

const defaultSettings: SystemSettings = {
  aiProvider: 'openai',
  dataRetentionDays: 30,
  defaultMotionSensitivity: 'medium',
  theme: 'system',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  backendUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const isLoading = false; // Will be used when fetching from backend API

  // Load settings from localStorage on mount - only once during initialization
  const [settings, setSettings] = useState<SystemSettings>(() => {
    if (typeof window !== 'undefined') {
      const savedSettings = localStorage.getItem('system-settings');
      if (savedSettings) {
        try {
          const parsed = JSON.parse(savedSettings);
          return { ...defaultSettings, ...parsed };
        } catch (error) {
          console.error('Failed to load settings from localStorage:', error);
        }
      }
    }
    return defaultSettings;
  });

  // Save settings to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('system-settings', JSON.stringify(settings));
  }, [settings]);

  const updateSetting = useCallback(<K extends keyof SystemSettings>(
    key: K,
    value: SystemSettings[K]
  ) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  }, []);

  const updateSettings = useCallback((newSettings: Partial<SystemSettings>) => {
    setSettings(prev => ({ ...prev, ...newSettings }));
  }, []);

  const resetSettings = useCallback(() => {
    setSettings(defaultSettings);
    localStorage.removeItem('system-settings');
  }, []);

  return (
    <SettingsContext.Provider
      value={{
        settings,
        isLoading,
        updateSetting,
        updateSettings,
        resetSettings,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
