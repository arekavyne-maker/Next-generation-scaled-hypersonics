import { useState, type ReactNode } from 'react';

interface JsonViewerProps {
  value: unknown;
  /** Initial expansion depth; 1 shows the top level only. */
  defaultDepth?: number;
  label?: string;
}

type JsonKind = 'object' | 'array' | 'string' | 'number' | 'boolean' | 'null';

function kindOf(value: unknown): JsonKind {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  const type = typeof value;
  if (type === 'object') return 'object';
  if (type === 'number') return 'number';
  if (type === 'boolean') return 'boolean';
  if (type === 'string') return 'string';
  return 'null';
}

function isExpandable(kind: JsonKind): boolean {
  return kind === 'object' || kind === 'array';
}

function preview(value: unknown, kind: JsonKind): string {
  if (kind === 'array') {
    const length = (value as unknown[]).length;
    return length === 0 ? '[]' : `Array(${length})`;
  }
  if (kind === 'object') {
    const keys = Object.keys(value as Record<string, unknown>);
    return keys.length === 0 ? '{}' : `{ ${keys.length} keys }`;
  }
  return '';
}

function scalarText(value: unknown, kind: JsonKind): string {
  if (kind === 'string') return JSON.stringify(value);
  if (kind === 'null') return 'null';
  return String(value);
}

function JsonNode({
  name,
  value,
  depth,
  defaultDepth,
}: {
  name: string | null;
  value: unknown;
  depth: number;
  defaultDepth: number;
}): ReactNode {
  const kind = kindOf(value);
  const [open, setOpen] = useState(depth < defaultDepth);

  if (!isExpandable(kind)) {
    return (
      <div className="json-row">
        {name !== null ? (
          <>
            <span className="json-key">{name}</span>
            <span className="json-colon">:</span>
          </>
        ) : null}
        <span className={`json-value ${kind}`}>{scalarText(value, kind)}</span>
      </div>
    );
  }

  const entries: Array<[string, unknown]> = Array.isArray(value)
    ? (value as unknown[]).map((item, index) => [String(index), item])
    : Object.entries(value as Record<string, unknown>);

  return (
    <div className="json-row">
      <button
        type="button"
        className="json-toggle"
        aria-expanded={open}
        aria-label={`${open ? 'Collapse' : 'Expand'} ${name ?? (kind === 'array' ? 'array' : 'object')}`}
        onClick={() => setOpen((previous) => !previous)}
      >
        {open ? '▾' : '▸'}
      </button>
      {name !== null ? (
        <>
          <span className="json-key">{name}</span>
          <span className="json-colon">:</span>
        </>
      ) : null}
      <span className="json-brace">{kind === 'array' ? '[' : '{'}</span>
      {!open ? (
        <>
          <span className="json-brace"> {preview(value, kind)} </span>
          <span className="json-brace">{kind === 'array' ? ']' : '}'}</span>
        </>
      ) : null}
      {open && entries.length === 0 ? (
        <span className="json-brace">{kind === 'array' ? ']' : '}'}</span>
      ) : null}
      {open && entries.length > 0 ? (
        <div className="json-children">
          {entries.map(([key, child]) => (
            <JsonNode key={key} name={key} value={child} depth={depth + 1} defaultDepth={defaultDepth} />
          ))}
          <div className="json-row">
            <span className="json-toggle" aria-hidden="true" />
            <span className="json-brace">{kind === 'array' ? ']' : '}'}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Collapsible JSON tree for event payloads and entity bodies.
 * Scalars are typed by colour; keys are stable-width so the tree scans cleanly.
 */
export function JsonViewer({ value, defaultDepth = 1, label = 'JSON document' }: JsonViewerProps): JSX.Element {
  return (
    <div className="json-viewer" role="tree" aria-label={label}>
      <JsonNode name={null} value={value} depth={0} defaultDepth={defaultDepth} />
    </div>
  );
}
