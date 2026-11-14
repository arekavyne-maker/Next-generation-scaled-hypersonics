import type { ReactNode } from 'react';

interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  /** Removes body padding — used when the body is a full-bleed table. */
  flush?: boolean;
  className?: string;
}

export function Panel({
  title,
  subtitle,
  actions,
  footer,
  children,
  flush = false,
  className,
}: PanelProps): JSX.Element {
  return (
    <section className={className ? `panel ${className}` : 'panel'}>
      <header className="panel-header">
        <h2 className="panel-title">{title}</h2>
        {subtitle ? <span className="panel-subtitle">{subtitle}</span> : null}
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </header>
      <div className={flush ? 'panel-body flush' : 'panel-body'}>{children}</div>
      {footer ? <footer className="panel-footer">{footer}</footer> : null}
    </section>
  );
}
