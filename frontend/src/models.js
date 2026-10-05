// Model catalogue: the single place that knows what each difficulty model is,
// how it routes, and whether its cuts are adjustable. Keeping it here stops the
// picker, the diagram, and the input controls from drifting apart.
//
// Names are ours, not the vendors'. Short people names, because the honest
// difference between the two support models is "who handles the middle" — not
// "which is smarter overall".

import { LISA_CUTS, KATE_CUTS, DATASETS } from './productMetrics'

// The cuts below come from productMetrics, which mirrors the shipped joblib
// artifacts read at runtime by feature_builder.load_policy(). The dashboard
// renders live values from /policy-analytics, so if these ever disagree with
// the artifact the picker and the metrics table will visibly contradict each
// other -- which is the bug this indirection exists to prevent.

export const MODELS = {
  emma: {
    id: 'emma',
    supportMode: 'generic',
    name: 'Emma',
    tagline: 'General purpose',
    description:
      `A regression model trained on ${DATASETS.emma.trainRows.toLocaleString()} Claude-gold labels predicts how hard each request actually is, then routes it to the cheapest tier that can handle it.`,
    tiers: ['cheap', 'mid', 'frontier'],
    // Only Emma has economy/balanced/quality, so only Emma gets the slider.
    adjustable: true,
    accent: 'cool',
    examples: [
      'What is 2+2?',
      'Explain quantum entanglement',
      "Who is OpenAI's CEO?",
    ],
  },
  lisa: {
    id: 'lisa',
    supportMode: '3tier',
    name: 'Lisa',
    tagline: 'Support · balanced',
    description:
      `Trained on ${DATASETS.support.trainRows.toLocaleString()} labeled support tickets: routine ones stay cheap, moderate ones get a mid model, and only the hardest reach the best one.`,
    tiers: ['cheap', 'mid', 'frontier'],
    adjustable: false,
    accent: 'signal',
    cuts: { ...LISA_CUTS },
    examples: [
      "My order hasn't arrived — where is it?",
      'Can I return a damaged item?',
      'Please update my shipping address.',
    ],
  },
  kate: {
    id: 'kate',
    supportMode: '2tier',
    name: 'Kate',
    tagline: 'Support · maximum care',
    description:
      `Trained on ${DATASETS.support.trainRows.toLocaleString()} labeled support tickets with no middle tier: anything that is not obviously routine goes straight to the strongest model.`,
    tiers: ['cheap', 'frontier'],
    adjustable: false,
    accent: 'danger',
    // Single cut: one rule, so the frontier floor equals the cheap ceiling.
    // The artifact also stores a frontier_floor of 4.5, which tier_for() never
    // reads for a 2-tier policy -- cheap_ceil is the only number that routes.
    cuts: { cheap: KATE_CUTS.cheap, frontier: KATE_CUTS.cheap },
    examples: [
      'Why was I charged twice?',
      'Can you refund a failed payment?',
      'My account was locked — help.',
    ],
  },
}

export const DEFAULT_MODEL_ID = 'emma'

export const MODEL_LIST = Object.values(MODELS)

export function getModel(id) {
  return MODELS[id] || MODELS[DEFAULT_MODEL_ID]
}

export function modelForSupportMode(supportMode) {
  return MODEL_LIST.find((m) => m.supportMode === supportMode) || MODELS[DEFAULT_MODEL_ID]
}

// Fixed-cut models report their own bands. Emma has none, because her threshold
// slider moves them, so the caller falls back to the slider-derived values.
export function policyBandsFor(id) {
  return getModel(id).cuts || null
}