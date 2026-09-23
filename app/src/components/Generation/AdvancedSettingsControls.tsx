import type { UseFormReturn } from 'react-hook-form';
import { Slider } from '@/components/ui/slider';
import type { EngineAdvancedSettingResponse } from '@/lib/api/models/EngineAdvancedSettingResponse';
import { advancedSettingStep } from '@/lib/hooks/engineCapabilityRules';
import type { GenerationFormValues } from '@/lib/hooks/useGenerationForm';

interface AdvancedSettingsControlsProps {
  form: UseFormReturn<GenerationFormValues>;
  /** The selected engine's declared `advanced_settings` (FR-010, C1Q8). */
  settings: readonly EngineAdvancedSettingResponse[];
}

/**
 * One slider per declared advanced setting, preselected at its declared default and bounded
 * by its declared min and max. Values land in the form's `advancedSettings`, which
 * useGenerationForm sends as the request's `advanced_settings`.
 */
export function AdvancedSettingsControls({ form, settings }: AdvancedSettingsControlsProps) {
  const values = form.watch('advancedSettings');

  return (
    <div className="mt-2 grid gap-3 rounded-2xl border border-accent/20 px-3 py-2">
      {settings.map((setting) => {
        const value = values?.[setting.name] ?? setting.default;
        const inputId = `advanced-setting-${setting.name}`;
        return (
          <div key={setting.name} className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <label htmlFor={inputId}>{setting.label}</label>
              <span className="tabular-nums">{value}</span>
            </div>
            <Slider
              id={inputId}
              min={setting.min}
              max={setting.max}
              step={advancedSettingStep(setting)}
              value={[value]}
              onValueChange={([next]) =>
                form.setValue('advancedSettings', {
                  ...form.getValues('advancedSettings'),
                  [setting.name]: Math.round(next * 100) / 100,
                })
              }
              aria-label={setting.label}
            />
          </div>
        );
      })}
    </div>
  );
}
