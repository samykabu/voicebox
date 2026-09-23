import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import * as z from 'zod';
import { useToast } from '@/components/ui/use-toast';
import { apiClient } from '@/lib/api/client';
import type { EffectConfig, VoiceProfileResponse } from '@/lib/api/types';
import {
  DEFAULT_HABIBI_MODEL_ID,
  getHabibiModel,
  HABIBI_MODEL_IDS,
} from '@/lib/constants/habibiModels';
import { LANGUAGE_CODES, type LanguageCode } from '@/lib/constants/languages';
import {
  buildAdvancedSettingsPayload,
  buildVoiceDescriptionPayload,
  type DownloadConfirmationDetails,
  downloadConfirmationDetails,
  downloadDecision,
  isEngineSelectable,
  PRE_CAPABILITY_ENGINES,
} from '@/lib/hooks/engineCapabilityRules';
import {
  findEngineCapability,
  loadEngineCapabilities,
  useEngineCapabilities,
} from '@/lib/hooks/useEngineCapabilities';
import { useGeneration } from '@/lib/hooks/useGeneration';
import { useModelDownloadToast } from '@/lib/hooks/useModelDownloadToast';
import { useGenerationSettings } from '@/lib/hooks/useSettings';
import { useGenerationStore } from '@/stores/generationStore';
import { useServerStore } from '@/stores/serverStore';
import { useUIStore } from '@/stores/uiStore';

const generationSchema = z.object({
  text: z.string().min(1, '').max(50000),
  language: z.enum(LANGUAGE_CODES as [LanguageCode, ...LanguageCode[]]),
  seed: z.number().int().optional(),
  modelSize: z.enum(['1.7B', '0.6B', '1B', '3B', ...HABIBI_MODEL_IDS]).optional(),
  instruct: z.string().max(500).optional(),
  engine: z
    .enum([
      'qwen',
      'qwen_custom_voice',
      'luxtts',
      'chatterbox',
      'chatterbox_turbo',
      'tada',
      'kokoro',
      'f5_tts',
      'voxcpm',
    ])
    .optional(),
  personality: z.boolean().optional(),
  /** Values for the selected engine's declared advanced settings, keyed by setting name. */
  advancedSettings: z.record(z.number()).optional(),
  /** A written description of the voice to create, for engines with voice design (FR-015). */
  voiceDescription: z.string().max(500).optional(),
});

export type GenerationFormValues = z.infer<typeof generationSchema>;

interface UseGenerationFormOptions {
  onSuccess?: (generationId: string) => void;
  defaultValues?: Partial<GenerationFormValues>;
  getEffectsChain?: () => EffectConfig[] | undefined;
}

export function useGenerationForm(options: UseGenerationFormOptions = {}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const serverUrl = useServerStore((state) => state.serverUrl);
  const generation = useGeneration();
  const addPendingGeneration = useGenerationStore((state) => state.addPendingGeneration);
  const { settings: genSettings } = useGenerationSettings();
  const maxChunkChars = genSettings?.max_chunk_chars ?? 800;
  const crossfadeMs = genSettings?.crossfade_ms ?? 50;
  const normalizeAudio = genSettings?.normalize_audio ?? true;
  const selectedEngine = useUIStore((state) => state.selectedEngine);
  const [downloadingModelName, setDownloadingModelName] = useState<string | null>(null);
  const [downloadingDisplayName, setDownloadingDisplayName] = useState<string | null>(null);
  const { data: engineCapabilities } = useEngineCapabilities();
  const [downloadConfirmation, setDownloadConfirmation] = useState<
    (DownloadConfirmationDetails & { resolve: (confirmed: boolean) => void }) | null
  >(null);

  function requestDownloadConfirmation(details: DownloadConfirmationDetails): Promise<boolean> {
    return new Promise((resolve) => setDownloadConfirmation({ ...details, resolve }));
  }

  function resolveDownloadConfirmation(confirmed: boolean) {
    downloadConfirmation?.resolve(confirmed);
    setDownloadConfirmation(null);
  }

  useModelDownloadToast({
    modelName: downloadingModelName || '',
    displayName: downloadingDisplayName || '',
    enabled: !!downloadingModelName,
  });

  const form = useForm<GenerationFormValues>({
    resolver: zodResolver(generationSchema),
    defaultValues: {
      text: '',
      language: selectedEngine === 'f5_tts' ? 'ar' : 'en',
      seed: undefined,
      modelSize: selectedEngine === 'f5_tts' ? DEFAULT_HABIBI_MODEL_ID : '1.7B',
      instruct: '',
      engine: (selectedEngine as GenerationFormValues['engine']) || 'qwen',
      personality: false,
      ...options.defaultValues,
    },
  });

  async function handleSubmit(
    data: GenerationFormValues,
    selectedProfileId: string | null,
    selectedProfile?: Pick<VoiceProfileResponse, 'voice_type'>,
  ): Promise<void> {
    if (!selectedProfileId) {
      toast({
        title: 'No profile selected',
        description: 'Please select a voice profile from the cards above.',
        variant: 'destructive',
      });
      return;
    }

    const engine = data.engine || 'qwen';
    // Decide from the capability, not from its absence: on a cold start the list may not have
    // loaded yet, so load it through the same query before deciding (FR-003, FR-018).
    const capability =
      findEngineCapability(engineCapabilities, engine) ??
      findEngineCapability(await loadEngineCapabilities(queryClient, serverUrl), engine);
    // FR-003: an engine this machine cannot run must not lead to a failed generation.
    if (!isEngineSelectable(capability)) {
      toast({
        title: t('engines.unavailableTitle', { name: capability?.display_name ?? engine }),
        description: capability?.reason ?? undefined,
        variant: 'destructive',
      });
      return;
    }

    try {
      const selectedModelSize =
        engine === 'f5_tts' ? getHabibiModel(data.modelSize).id : data.modelSize;
      const modelName =
        engine === 'luxtts'
          ? 'luxtts'
          : engine === 'chatterbox'
            ? 'chatterbox-tts'
            : engine === 'chatterbox_turbo'
              ? 'chatterbox-turbo'
              : engine === 'tada'
                ? data.modelSize === '3B'
                  ? 'tada-3b-ml'
                  : 'tada-1b'
                : engine === 'kokoro'
                  ? 'kokoro'
                  : engine === 'f5_tts'
                    ? getHabibiModel(selectedModelSize).id
                    : engine === 'qwen_custom_voice'
                      ? `qwen-custom-voice-${data.modelSize}`
                      : engine === 'voxcpm'
                        ? 'voxcpm2'
                        : `qwen-tts-${data.modelSize}`;
      const displayName =
        engine === 'luxtts'
          ? 'LuxTTS'
          : engine === 'chatterbox'
            ? 'Chatterbox TTS'
            : engine === 'chatterbox_turbo'
              ? 'Chatterbox Turbo'
              : engine === 'tada'
                ? data.modelSize === '3B'
                  ? 'TADA 3B Multilingual'
                  : 'TADA 1B'
                : engine === 'kokoro'
                  ? 'Kokoro 82M'
                  : engine === 'f5_tts'
                    ? getHabibiModel(selectedModelSize).label
                    : engine === 'qwen_custom_voice'
                      ? data.modelSize === '1.7B'
                        ? 'Qwen CustomVoice 1.7B'
                        : 'Qwen CustomVoice 0.6B'
                      : engine === 'voxcpm'
                        ? 'VoxCPM2'
                        : data.modelSize === '1.7B'
                          ? 'Qwen TTS 1.7B'
                          : 'Qwen TTS 0.6B';

      // Check if model needs downloading
      let model: { downloaded: boolean; downloading?: boolean } | undefined;
      try {
        const modelStatus = await apiClient.getModelStatus();
        model = modelStatus.models.find((m) => m.model_name === modelName);
      } catch (error) {
        console.error('Failed to check model status:', error);
      }

      // FR-018 / C1Q7: /generate starts the download itself, so ask first when the engine's
      // capability requires it; declining cancels this generation. It fails closed: without
      // a capability for an engine that depends on one, the download is not started.
      const decision = downloadDecision(engine, capability, model, PRE_CAPABILITY_ENGINES);
      if (decision === 'refuse') {
        toast({
          title: t('engines.detailsUnavailable.title'),
          description: t('engines.detailsUnavailable.description', { name: displayName }),
          variant: 'destructive',
        });
        return;
      }
      if (decision === 'confirm' && capability) {
        const confirmed = await requestDownloadConfirmation(
          downloadConfirmationDetails(capability, displayName),
        );
        if (!confirmed) return;
      }

      if (model && !model.downloaded) {
        setDownloadingModelName(modelName);
        setDownloadingDisplayName(displayName);
      }

      const hasModelSizes =
        engine === 'qwen' ||
        engine === 'qwen_custom_voice' ||
        engine === 'tada' ||
        engine === 'f5_tts';
      // Only Qwen CustomVoice actually honors the instruct kwarg at model level.
      // Base Qwen3-TTS accepts the kwarg but ignores it.
      const supportsInstruct = engine === 'qwen_custom_voice';
      const effectsChain = options.getEffectsChain?.();
      // This now returns immediately with status="generating"
      const result = await generation.mutateAsync({
        profile_id: selectedProfileId,
        text: data.text,
        language: data.language,
        seed: data.seed,
        model_size: hasModelSizes ? selectedModelSize : undefined,
        engine,
        instruct: supportsInstruct ? data.instruct || undefined : undefined,
        personality: data.personality || undefined,
        max_chunk_chars: maxChunkChars,
        crossfade_ms: crossfadeMs,
        normalize: normalizeAudio,
        effects_chain: effectsChain?.length ? effectsChain : undefined,
        // FR-010: only engines that declare advanced settings receive them.
        advanced_settings: buildAdvancedSettingsPayload(capability, data.advancedSettings),
        // FR-015 / C1Q5: its own field, never `instruct`; omitted unless the engine declares
        // voice design and the profile has no recording that would win over it (C1Q6).
        voice_description: buildVoiceDescriptionPayload(
          capability,
          selectedProfile,
          data.voiceDescription,
        ),
      });

      // Track this generation for SSE status updates
      addPendingGeneration(result.id);

      // Reset form immediately — user can start typing again
      form.reset({
        text: '',
        language: data.language,
        seed: undefined,
        modelSize: selectedModelSize,
        instruct: '',
        engine: data.engine,
        personality: data.personality,
        advancedSettings: data.advancedSettings,
        // Kept so the next text can be generated with the same designed voice.
        voiceDescription: data.voiceDescription,
      });
      options.onSuccess?.(result.id);
    } catch (error) {
      toast({
        title: 'Generation failed',
        description: error instanceof Error ? error.message : 'Failed to generate audio',
        variant: 'destructive',
      });
    } finally {
      setDownloadingModelName(null);
      setDownloadingDisplayName(null);
    }
  }

  return {
    form,
    handleSubmit,
    isPending: generation.isPending,
    downloadConfirmation,
    resolveDownloadConfirmation,
  };
}
