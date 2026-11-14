import { useCallback, useEffect, useRef, useState } from 'react';

interface CopyableTextProps {
  value: string;
  /** Characters kept before truncation; the full value is exposed on hover. */
  display?: string;
  label: string;
  className?: string;
}

/**
 * Monospace identifier that copies its full value on click and on hover.
 * The truncated form is always backed by the complete value in the title
 * attribute so nothing is hidden from the operator.
 */
export function CopyableText({ value, display, label, className }: CopyableTextProps): JSX.Element {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = useCallback(() => {
    const write = navigator.clipboard?.writeText(value);
    if (!write) return;
    void write
      .then(() => {
        setCopied(true);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => {
        setCopied(false);
      });
  }, [value]);

  return (
    <span className="hash-wrap">
      <button
        type="button"
        className={className ?? 'hash'}
        title={`${value}\n\nClick to copy`}
        aria-label={`${label}: ${value}. Activate to copy the full value.`}
        onClick={copy}
        style={{ background: 'none', border: 'none', padding: 0, textAlign: 'left', cursor: 'copy' }}
      >
        {display ?? value}
      </button>
      {copied ? <span className="copied-flag">copied</span> : <span className="copy-hint">click to copy</span>}
    </span>
  );
}
