/**
 * Colour assignments for the digital thread visualisation.
 *
 * Entity types get a stable hue; relation types get a stable stroke colour.
 * Low-confidence edges are dashed rather than coloured differently so the
 * legend stays readable.
 */

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  System: '#4c9aff',
  Variant: '#58a6ff',
  Subsystem: '#79c0ff',
  Part: '#f0883e',
  Material: '#d29922',
  ProcessPlan: '#e3b341',
  ProcessRun: '#f2cc60',
  TestArticle: '#3fb950',
  TestCampaign: '#56d364',
  TestResult: '#2ea043',
  Requirement: '#a371f7',
  Interface: '#bc8cff',
  Model: '#db61a2',
  ThreatSystem: '#f85149',
  ThreatObservation: '#ff7b72',
  EngagementScenario: '#db6d28',
  Supplier: '#39c5cf',
  PartProvenance: '#39a0a8',
  Skill: '#7ee787',
  Credential: '#56d364',
  Person: '#ffa657',
  Facility: '#26c6da',
  RangeSlot: '#39c5cf',
};

export const FALLBACK_NODE_COLOR = '#8b949e';

export const RELATION_TYPE_COLORS: Record<string, string> = {
  satisfies: '#a371f7',
  verifies: '#3fb950',
  manufacturedBy: '#d29922',
  characterizedBy: '#f0883e',
  derivedFrom: '#58a6ff',
  threatens: '#f85149',
  engages: '#db61a2',
  requiresSkill: '#7ee787',
  supplies: '#39c5cf',
  reconstitutes: '#8b949e',
};

export const FALLBACK_EDGE_COLOR = '#6e7681';

/** Confidence below this threshold is rendered as a dashed edge. */
export const LOW_CONFIDENCE_THRESHOLD = 0.6;

export function entityColor(type: string): string {
  return ENTITY_TYPE_COLORS[type] ?? FALLBACK_NODE_COLOR;
}

export function relationColor(type: string): string {
  return RELATION_TYPE_COLORS[type] ?? FALLBACK_EDGE_COLOR;
}
