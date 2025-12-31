# Story P15-3.1: Audit Settings Save Patterns

**Epic:** P15-3 - Settings UX Consolidation
**Status:** Done
**Priority:** High

## Story

As a developer, I need to audit all settings sections to document their current save behavior so that we can plan the standardization effort.

## Acceptance Criteria

- [x] AC1: All settings components identified and documented
- [x] AC2: Current save pattern for each component documented (auto-save vs explicit)
- [x] AC3: Components requiring migration identified
- [x] AC4: Shared patterns and opportunities documented

## Audit Results

### Settings Components Audited

| Component | Location | Current Pattern | Migration Needed |
|-----------|----------|-----------------|------------------|
| AIProviders | `components/settings/AIProviders.tsx` | Auto-save on action (reorder, configure, remove) | No (action-based is appropriate) |
| MQTTSettings | `components/settings/MQTTSettings.tsx` | Explicit Save with react-hook-form + isDirty | Template pattern |
| NotificationPreferences | `components/settings/NotificationPreferences.tsx` | Auto-save on each toggle/change | Consider explicit |
| HomekitSettings | `components/settings/HomekitSettings.tsx` | Mutation-based toggle/reset | No (service control) |
| TunnelSettings | `components/settings/TunnelSettings.tsx` | Mutation-based start/stop | No (service control) |
| AnomalySettings | `components/settings/AnomalySettings.tsx` | Manual isDirty + explicit Save | Migrate to hook |
| CostCapSettings | `components/settings/CostCapSettings.tsx` | Manual hasChanges + Save/Cancel | Migrate to hook |

### Shared Patterns Identified

1. **react-hook-form pattern** (MQTTSettings)
   - Uses `useForm` with Zod resolver
   - Built-in `isDirty` from formState
   - `reset()` to restore initial values
   - Good template for complex forms

2. **Manual dirty tracking** (AnomalySettings, CostCapSettings)
   - Manual comparison of current vs initial state
   - Custom `isDirty` / `hasChanges` boolean
   - Manual save/reset handlers
   - Candidate for `useSettingsForm` hook

3. **Service control pattern** (HomekitSettings, TunnelSettings)
   - Toggle enables/disables a service
   - No form state, just mutations
   - Should NOT use form pattern (different UX intent)

4. **Action-based save** (AIProviders)
   - Each action (drag, configure, remove) saves immediately
   - Appropriate for list/CRUD patterns
   - Should NOT change

### Migration Plan

Components to migrate to `useSettingsForm`:
- AnomalySettings
- CostCapSettings

Components to add unsaved indicator only:
- MQTTSettings (already has save pattern)

Components to keep as-is:
- AIProviders (action-based)
- HomekitSettings (service control)
- TunnelSettings (service control)
- NotificationPreferences (preference toggles)

## Implementation Notes

The audit is complete. Key finding: Most settings components already use appropriate patterns. The main opportunity is to:
1. Create `useSettingsForm` hook to standardize the manual patterns
2. Add `UnsavedIndicator` component for visual feedback
3. Add navigation warning via `useUnsavedChangesWarning` hook

## Dev Notes

Audit completed as part of P15-3 implementation planning.
