import type { ClassificationLevel } from '../api/types';

const LEVEL_CLASS: Record<ClassificationLevel, string> = {
  UNCLASSIFIED: 'badge-level-unclassified',
  CUI: 'badge-level-cui',
  'CUI//REL': 'badge-level-cui',
  'CUI//FOUO': 'badge-level-cui',
  RESTRICTED: 'badge-level-restricted',
  SECRET: 'badge-level-secret',
  'TOP SECRET': 'badge-level-top-secret',
};

interface ClassificationBadgeProps {
  level: ClassificationLevel | string | undefined;
  caveats?: string[];
  title?: string;
}

/** Classification badge. Caveats are surfaced in the tooltip, never truncated silently. */
export function ClassificationBadge({ level, caveats, title }: ClassificationBadgeProps): JSX.Element {
  if (!level) return <span className="badge badge-neutral">UNCLASSIFIED</span>;
  const normalised = level as ClassificationLevel;
  const className = LEVEL_CLASS[normalised] ?? 'badge-level-cui';
  const suffix = caveats && caveats.length > 0 ? ` · ${caveats.join(', ')}` : '';
  return (
    <span className={`badge ${className}`} title={title ?? `${level}${suffix}`}>
      {level}
    </span>
  );
}
