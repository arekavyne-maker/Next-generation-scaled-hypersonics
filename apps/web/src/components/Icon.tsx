import type { ReactNode } from 'react';

export type IconName =
  | 'overview'
  | 'stream'
  | 'thread'
  | 'requirements'
  | 'audit'
  | 'access'
  | 'chevron'
  | 'copy'
  | 'check'
  | 'cross'
  | 'warning'
  | 'refresh'
  | 'search'
  | 'link'
  | 'database'
  | 'shield';

const PATHS: Record<IconName, ReactNode> = {
  overview: (
    <>
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </>
  ),
  stream: (
    <>
      <path d="M1 4h14M1 8h14M1 12h9" />
      <circle cx="13" cy="12" r="2" />
    </>
  ),
  thread: (
    <>
      <circle cx="8" cy="8" r="2.4" />
      <circle cx="2.5" cy="3.5" r="1.6" />
      <circle cx="13.5" cy="3.5" r="1.6" />
      <circle cx="8" cy="14" r="1.6" />
      <path d="M3.6 4.7 6.6 7M12.4 4.7 9.4 7M8 10.4v2" />
    </>
  ),
  requirements: (
    <>
      <path d="M3 2h7l3 3v9H3z" />
      <path d="M10 2v3h3" />
      <path d="M5.5 9.5 7 11l3.5-4" />
    </>
  ),
  audit: (
    <>
      <path d="M8 1.6 13.4 4v4.2c0 3.3-2.2 5.6-5.4 6.2-3.2-.6-5.4-2.9-5.4-6.2V4z" />
      <path d="M5.8 8.2 7.4 9.8l3-3.2" />
    </>
  ),
  access: (
    <>
      <rect x="3" y="7" width="10" height="7" rx="1.5" />
      <path d="M5.5 7V5.2a2.5 2.5 0 0 1 5 0V7" />
    </>
  ),
  chevron: <path d="M6 3.5 10.5 8 6 12.5" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.2" />
      <path d="M10.5 5.5v-1a1.5 1.5 0 0 0-1.5-1.5H4A1.5 1.5 0 0 0 2.5 4.5V9A1.5 1.5 0 0 0 4 10.5h1" />
    </>
  ),
  check: <path d="M3 8.5 6.5 12 13 4.5" />,
  cross: <path d="M4 4l8 8M12 4l-8 8" />,
  warning: (
    <>
      <path d="M8 2 14.5 13.5h-13z" />
      <path d="M8 6.5v3.2M8 11.6v.4" />
    </>
  ),
  refresh: (
    <>
      <path d="M13.5 8a5.5 5.5 0 1 1-1.9-4.2" />
      <path d="M13.8 1.8v3h-3" />
    </>
  ),
  search: (
    <>
      <circle cx="7" cy="7" r="4.2" />
      <path d="M10.2 10.2 14 14" />
    </>
  ),
  link: (
    <>
      <path d="M6.8 9.2a2.6 2.6 0 0 0 3.9.3l2-2a2.6 2.6 0 0 0-3.7-3.7l-1 1" />
      <path d="M9.2 6.8a2.6 2.6 0 0 0-3.9-.3l-2 2a2.6 2.6 0 0 0 3.7 3.7l1-1" />
    </>
  ),
  database: (
    <>
      <ellipse cx="8" cy="3.8" rx="5.4" ry="2" />
      <path d="M2.6 3.8v8.4c0 1.1 2.4 2 5.4 2s5.4-.9 5.4-2V3.8" />
      <path d="M2.6 8c0 1.1 2.4 2 5.4 2s5.4-.9 5.4-2" />
    </>
  ),
  shield: (
    <>
      <path d="M8 1.6 13.4 4v4.2c0 3.3-2.2 5.6-5.4 6.2-3.2-.6-5.4-2.9-5.4-6.2V4z" />
    </>
  ),
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

/** Inline SVG icon set — no icon font, no emoji, no raster assets. */
export function Icon({ name, size = 14, className }: IconProps): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
