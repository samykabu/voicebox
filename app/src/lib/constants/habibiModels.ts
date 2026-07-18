export const HABIBI_MODELS = [
  {
    id: 'habibi-msa',
    label: 'Habibi MSA',
    dialect: 'Modern Standard Arabic',
    license: 'Apache-2.0',
    commercialUse: true,
    description:
      'Specialized Modern Standard Arabic checkpoint for high-quality Arabic voice cloning.',
  },
  {
    id: 'habibi-unified',
    label: 'Habibi Unified (automatic dialect)',
    dialect: 'Automatic dialect detection',
    license: 'CC-BY-NC-SA-4.0',
    commercialUse: false,
    description:
      'Unified Arabic checkpoint with automatic dialect handling. Licensed for noncommercial use only.',
  },
  {
    id: 'habibi-sau',
    label: 'Habibi Saudi Arabic',
    dialect: 'Saudi Arabic',
    license: 'CC-BY-NC-SA-4.0',
    commercialUse: false,
    description:
      'Saudi Arabic checkpoint for dialect-specific voice cloning. Licensed for noncommercial use only.',
  },
  {
    id: 'habibi-uae',
    label: 'Habibi UAE Arabic',
    dialect: 'UAE Arabic',
    license: 'CC-BY-NC-SA-4.0',
    commercialUse: false,
    description:
      'UAE Arabic checkpoint for dialect-specific voice cloning. Licensed for noncommercial use only.',
  },
  {
    id: 'habibi-alg',
    label: 'Habibi Algerian Arabic',
    dialect: 'Algerian Arabic',
    license: 'Apache-2.0',
    commercialUse: true,
    description: 'Specialized Algerian Arabic checkpoint for dialect-specific voice cloning.',
  },
  {
    id: 'habibi-irq',
    label: 'Habibi Iraqi Arabic',
    dialect: 'Iraqi Arabic',
    license: 'Apache-2.0',
    commercialUse: true,
    description: 'Specialized Iraqi Arabic checkpoint for dialect-specific voice cloning.',
  },
  {
    id: 'habibi-egy',
    label: 'Habibi Egyptian Arabic',
    dialect: 'Egyptian Arabic',
    license: 'Apache-2.0',
    commercialUse: true,
    description: 'Specialized Egyptian Arabic checkpoint for dialect-specific voice cloning.',
  },
  {
    id: 'habibi-mar',
    label: 'Habibi Moroccan Arabic',
    dialect: 'Moroccan Arabic',
    license: 'Apache-2.0',
    commercialUse: true,
    description: 'Specialized Moroccan Arabic checkpoint for dialect-specific voice cloning.',
  },
] as const;

export type HabibiModelId = (typeof HABIBI_MODELS)[number]['id'];

export const HABIBI_MODEL_IDS = HABIBI_MODELS.map((model) => model.id) as [
  HabibiModelId,
  ...HabibiModelId[],
];

export const DEFAULT_HABIBI_MODEL_ID: HabibiModelId = 'habibi-msa';

const HABIBI_MODEL_MAP = new Map(HABIBI_MODELS.map((model) => [model.id, model]));

export function isHabibiModelId(value?: string): value is HabibiModelId {
  return value !== undefined && HABIBI_MODEL_MAP.has(value as HabibiModelId);
}

export function getHabibiModel(value?: string) {
  return HABIBI_MODEL_MAP.get(
    isHabibiModelId(value) ? value : DEFAULT_HABIBI_MODEL_ID,
  ) as (typeof HABIBI_MODELS)[number];
}
