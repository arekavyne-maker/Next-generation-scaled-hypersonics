interface MeterProps {
  /** Value in the 0..1 range. */
  value: number;
  label: string;
  detail?: string;
  /** Threshold that switches the bar from accent to warning. */
  warnBelow?: number;
  dangerBelow?: number;
}

/** Horizontal coverage meter with a numeric readout. */
export function Meter({ value, label, detail, warnBelow = 0.5, dangerBelow = 0.25 }: MeterProps): JSX.Element {
  const clamped = Math.max(0, Math.min(1, value));
  const percent = clamped * 100;
  const tone = clamped <= dangerBelow ? 'danger' : clamped <= warnBelow ? 'warn' : 'ok';

  return (
    <div className="meter">
      <div className="meter-head">
        <span className="status-tile-label">{label}</span>
        <span className="meter-value">{percent.toFixed(1)}%</span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className="meter-fill" data-tone={tone} style={{ width: `${percent}%` }} />
      </div>
      {detail ? (
        <div className="meter-scale">
          <span>{detail}</span>
          <span>0 — 100%</span>
        </div>
      ) : null}
    </div>
  );
}
