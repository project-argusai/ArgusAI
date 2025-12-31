# Story P15-3.5: Standardize All Settings Sections

**Epic:** P15-3 - Settings UX Consolidation
**Status:** Done
**Priority:** Medium

## Story

As a user, I want all settings sections to have consistent save/cancel behavior so that the settings experience is predictable.

## Acceptance Criteria

- [x] AC1: AnomalySettings uses useSettingsForm hook
- [x] AC2: AnomalySettings shows UnsavedIndicator when dirty
- [x] AC3: AnomalySettings has Cancel button when dirty
- [x] AC4: CostCapSettings shows UnsavedIndicator when dirty
- [x] AC5: CostCapSettings has navigation warning
- [x] AC6: MQTTSettings shows UnsavedIndicator when dirty
- [x] AC7: MQTTSettings has Cancel button when dirty
- [x] AC8: MQTTSettings has navigation warning
- [x] AC9: All modified components retain existing functionality

## Components Updated

| Component | Changes |
|-----------|---------|
| AnomalySettings | Migrated to useSettingsForm, added UnsavedIndicator, Cancel button |
| CostCapSettings | Added UnsavedIndicator and useUnsavedChangesWarning |
| MQTTSettings | Added UnsavedIndicator, Cancel button, useUnsavedChangesWarning |

## Not Changed (Appropriate for Their Pattern)

| Component | Reason |
|-----------|--------|
| AIProviders | Action-based save (drag, configure, remove) |
| HomekitSettings | Service control (enable/disable service) |
| TunnelSettings | Service control (start/stop tunnel) |
| NotificationPreferences | Preference toggles with immediate feedback |

## Dev Notes

The migration focused on settings sections with form-like behavior where:
1. Users modify multiple fields
2. Changes should be explicitly saved
3. Accidental navigation could lose work

Service control patterns (on/off toggles) and action-based patterns (list CRUD) were intentionally left unchanged as they have different UX expectations.
