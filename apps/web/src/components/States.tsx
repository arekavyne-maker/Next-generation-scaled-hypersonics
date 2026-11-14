import type { ReactNode } from 'react';
import { Icon } from './Icon';

interface StateProps {
  title: string;
  detail?: string;
  action?: ReactNode;
  tone?: 'neutral' | 'error';
}

export function LoadingState({ label = 'Loading' }: { label?: string }): JSX.Element {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="state-block-detail">{label}…</span>
    </div>
  );
}

export function ErrorState({ title, detail, action }: StateProps): JSX.Element {
  return (
    <div className="state-block" data-tone="error" role="alert">
      <Icon name="warning" size={18} />
      <span className="state-block-title">{title}</span>
      {detail ? <span className="state-block-detail">{detail}</span> : null}
      {action}
    </div>
  );
}

export function EmptyState({ title, detail, action }: StateProps): JSX.Element {
  return (
    <div className="state-block">
      <Icon name="search" size={18} />
      <span className="state-block-title">{title}</span>
      {detail ? <span className="state-block-detail">{detail}</span> : null}
      {action}
    </div>
  );
}
