import { useMemo, useState } from 'react';
import type { TraceEdge, TraceNode, TraceResponse } from '../api/types';
import { entityColor, relationColor, LOW_CONFIDENCE_THRESHOLD } from '../lib/palette';

interface TraceGraphProps {
  trace: TraceResponse;
  selectedNodeId: string | null;
  selectedEdgeKey: string | null;
  onSelectNode: (node: TraceNode) => void;
  onSelectEdge: (edge: TraceEdge) => void;
}

interface Positioned {
  node: TraceNode;
  x: number;
  y: number;
  depth: number;
  angle: number;
  span: number;
  isRoot: boolean;
}

interface EdgeShape {
  key: string;
  edge: TraceEdge;
  path: string;
  arrow: string;
  lowConfidence: boolean;
  selected: boolean;
}

const RING_RADIUS = 112;
const CENTER = { x: 380, y: 330 };

function edgeKey(edge: TraceEdge): string {
  return `${edge.from}->${edge.to}:${edge.type}`;
}

function truncateLabel(label: string, max = 18): string {
  if (label.length <= max) return label;
  return `${label.slice(0, max - 1)}…`;
}

/**
 * Radial layout.
 *
 * The root sits at the centre. Each ring holds one BFS depth level. Children
 * inherit a slice of their parent's angular span, which keeps sibling
 * subtrees visually grouped instead of scattering them around the circle.
 */
function layout(trace: TraceResponse): { positioned: Positioned[]; width: number; height: number } {
  const rootId = trace.root.includes(':') ? trace.root.slice(trace.root.indexOf(':') + 1) : trace.root;
  const nodeById = new Map(trace.nodes.map((node) => [node.id, node]));

  const adjacency = new Map<string, string[]>();
  for (const node of trace.nodes) adjacency.set(node.id, []);
  for (const edge of trace.edges) {
    if (!adjacency.has(edge.from) || !adjacency.has(edge.to)) continue;
    adjacency.get(edge.from)!.push(edge.to);
    adjacency.get(edge.to)!.push(edge.from);
  }

  const root = nodeById.get(rootId) ?? trace.nodes[0];
  if (!root) return { positioned: [], width: CENTER.x * 2, height: CENTER.y * 2 };

  const depthOf = new Map<string, number>([[root.id, 0]]);
  const childrenOf = new Map<string, string[]>([[root.id, []]]);
  const order: string[] = [root.id];
  const queue: string[] = [root.id];

  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentDepth = depthOf.get(current)!;
    for (const neighbour of adjacency.get(current) ?? []) {
      if (depthOf.has(neighbour)) continue;
      depthOf.set(neighbour, currentDepth + 1);
      childrenOf.set(current, [...(childrenOf.get(current) ?? []), neighbour]);
      childrenOf.set(neighbour, []);
      order.push(neighbour);
      queue.push(neighbour);
    }
  }

  // Nodes that are only reachable through an already-visited node still get a
  // position so that lateral edges do not disappear from the drawing.
  for (const node of trace.nodes) {
    if (!depthOf.has(node.id)) {
      depthOf.set(node.id, 1);
      childrenOf.set(node.id, []);
      order.push(node.id);
    }
  }

  const angleOf = new Map<string, number>();
  const spanOf = new Map<string, number>();
  angleOf.set(root.id, -Math.PI / 2);
  spanOf.set(root.id, Math.PI * 2);

  const byDepth = new Map<number, string[]>();
  for (const id of order) {
    const depth = depthOf.get(id)!;
    byDepth.set(depth, [...(byDepth.get(depth) ?? []), id]);
  }

  for (const depth of Array.from(byDepth.keys()).sort((a, b) => a - b)) {
    if (depth === 0) continue;
    const level = byDepth.get(depth)!;
    const parents = new Map<string, string>();
    for (const id of level) {
      const parent = order.find(
        (candidate) => (childrenOf.get(candidate) ?? []).includes(id) && depthOf.get(candidate) === depth - 1,
      );
      if (parent) parents.set(id, parent);
    }

    for (const id of level) {
      const parent = parents.get(id);
      if (!parent) {
        const siblings = level.filter((candidate) => !parents.has(candidate));
        const index = Math.max(siblings.indexOf(id), 0);
        const span = (Math.PI * 2) / Math.max(siblings.length, 1);
        angleOf.set(id, -Math.PI / 2 + span * (index + 0.5));
        spanOf.set(id, span);
        continue;
      }
      const parentAngle = angleOf.get(parent) ?? 0;
      const parentSpan = spanOf.get(parent) ?? (Math.PI * 2) / Math.max(level.length, 1);
      const siblings = childrenOf.get(parent) ?? [id];
      const index = siblings.indexOf(id);
      const span = parentSpan / Math.max(siblings.length, 1);
      angleOf.set(id, parentAngle - parentSpan / 2 + span * (index + 0.5));
      spanOf.set(id, span);
    }
  }

  const positioned: Positioned[] = order.map((id) => {
    const node = nodeById.get(id);
    if (!node) return null;
    const depth = depthOf.get(id)!;
    const angle = angleOf.get(id) ?? 0;
    const radius = depth * RING_RADIUS;
    return {
      node,
      depth,
      angle,
      span: spanOf.get(id) ?? 0,
      isRoot: id === root.id,
      x: CENTER.x + Math.cos(angle) * radius,
      y: CENTER.y + Math.sin(angle) * radius,
    };
  }).filter((value): value is Positioned => value !== null);

  const maxRadius = positioned.reduce((max, item) => Math.max(max, item.depth * RING_RADIUS), 0);
  const width = Math.max(CENTER.x + maxRadius + 120, 760);
  const height = Math.max(CENTER.y + maxRadius + 120, 660);

  return { positioned, width, height };
}

function buildEdges(trace: TraceResponse, positions: Map<string, Positioned>): EdgeShape[] {
  return trace.edges.map((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) {
      return { key: edgeKey(edge), edge, path: '', arrow: '', lowConfidence: false, selected: false };
    }

    const sameRing = from.depth === to.depth;
    const midX = (from.x + to.x) / 2;
    const midY = (from.y + to.y) / 2;

    let path: string;
    let arrow: string;

    if (sameRing) {
      // Lateral edge: bow outwards so it does not cut through the ring.
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const length = Math.hypot(dx, dy) || 1;
      const outwardX = (midX - CENTER.x) / (Math.hypot(midX - CENTER.x, midY - CENTER.y) || 1);
      const outwardY = (midY - CENTER.y) / (Math.hypot(midX - CENTER.x, midY - CENTER.y) || 1);
      const bow = 26;
      const controlX = midX + outwardX * bow + (-dy / length) * 0;
      const controlY = midY + outwardY * bow + (dx / length) * 0;
      path = `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;

      const t = 0.88;
      const bx = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * controlX + t * t * to.x;
      const by = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * controlY + t * t * to.y;
      const tx = 2 * (1 - t) * (controlX - from.x) + 2 * t * (to.x - controlX);
      const ty = 2 * (1 - t) * (controlY - from.y) + 2 * t * (to.y - controlY);
      arrow = arrowHead(bx, by, tx, ty, 5.5);
    } else {
      // Radial edge: gentle perpendicular bow keeps sibling edges distinguishable.
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const length = Math.hypot(dx, dy) || 1;
      const sign = from.depth < to.depth ? 1 : -1;
      const bow = 10 * sign;
      const controlX = midX + (-dy / length) * bow;
      const controlY = midY + (dx / length) * bow;
      path = `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;

      const t = 0.92;
      const bx = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * controlX + t * t * to.x;
      const by = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * controlY + t * t * to.y;
      const tx = 2 * (1 - t) * (controlX - from.x) + 2 * t * (to.x - controlX);
      const ty = 2 * (1 - t) * (controlY - from.y) + 2 * t * (to.y - controlY);
      arrow = arrowHead(bx, by, tx, ty, 5.5);
    }

    const confidence = edge.confidence ?? 1;
    return {
      key: edgeKey(edge),
      edge,
      path,
      arrow,
      lowConfidence: confidence < LOW_CONFIDENCE_THRESHOLD,
      selected: false,
    };
  });
}

function arrowHead(x: number, y: number, dx: number, dy: number, size: number): string {
  const length = Math.hypot(dx, dy) || 1;
  const ux = dx / length;
  const uy = dy / length;
  const baseX = x - ux * size;
  const baseY = y - uy * size;
  const leftX = baseX - uy * size * 0.55;
  const leftY = baseY + ux * size * 0.55;
  const rightX = baseX + uy * size * 0.55;
  const rightY = baseY - ux * size * 0.55;
  return `${x},${y} ${leftX},${leftY} ${rightX},${rightY}`;
}

/**
 * Hand-rolled layered radial graph. No graph library is used: layout, edge
 * routing and hit testing are all computed here.
 */
export function TraceGraph({
  trace,
  selectedNodeId,
  selectedEdgeKey,
  onSelectNode,
  onSelectEdge,
}: TraceGraphProps): JSX.Element {
  const [zoom, setZoom] = useState(1);

  const { positioned, width, height } = useMemo(() => layout(trace), [trace]);
  const positions = useMemo(() => new Map(positioned.map((item) => [item.node.id, item])), [positioned]);
  const edges = useMemo(() => buildEdges(trace, positions), [trace, positions]);

  const showLabels = positioned.length <= 42;
  const selectedEdge = edges.find((shape) => shape.key === selectedEdgeKey);

  return (
    <div className="graph-surface">
      <div className="row" style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="text-xs text-faint">
          {positioned.length} nodes · {edges.length} edges · depth {Math.max(0, ...positioned.map((item) => item.depth))}
        </span>
        <div className="topbar-spacer" />
        <button
          type="button"
          className="btn btn-sm"
          aria-label="Zoom out"
          onClick={() => setZoom((value) => Math.max(0.6, Number((value - 0.15).toFixed(2))))}
        >
          −
        </button>
        <button
          type="button"
          className="btn btn-sm"
          aria-label="Zoom in"
          onClick={() => setZoom((value) => Math.min(1.8, Number((value + 0.15).toFixed(2))))}
        >
          +
        </button>
        <button type="button" className="btn btn-sm" aria-label="Reset zoom" onClick={() => setZoom(1)}>
          reset
        </button>
      </div>

      <svg
        className="graph-svg"
        width={width * zoom}
        height={height * zoom}
        viewBox={`0 0 ${width} ${height}`}
        role="application"
        aria-label="Digital thread graph"
      >
        <g>
          {edges.map((shape) => {
            if (!shape.path) return null;
            const color = relationColor(shape.edge.type);
            const isSelected = selectedEdgeKey === shape.key;
            return (
              <g key={shape.key}>
                <path
                  className={[
                    'graph-edge',
                    shape.lowConfidence ? 'is-low-confidence' : '',
                    isSelected ? 'is-selected' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  d={shape.path}
                  stroke={color}
                  strokeOpacity={isSelected ? 1 : 0.62}
                />
                <polygon points={shape.arrow} fill={color} fillOpacity={isSelected ? 1 : 0.62} />
                <path
                  d={shape.path}
                  stroke="transparent"
                  strokeWidth={10}
                  fill="none"
                  style={{ cursor: 'pointer' }}
                  onClick={() => onSelectEdge(shape.edge)}
                >
                  <title>{`${shape.edge.type}: ${shape.edge.from} → ${shape.edge.to}${
                    shape.edge.confidence !== undefined ? ` (confidence ${shape.edge.confidence.toFixed(2)})` : ''
                  }`}</title>
                </path>
              </g>
            );
          })}

          {positioned.map((item) => {
            const isSelected = item.node.id === selectedNodeId;
            const color = entityColor(item.node.type);
            const radius = item.isRoot ? 9 : 6.5;
            return (
              <g
                key={item.node.id}
                className={['graph-node', item.isRoot ? 'is-root' : '', isSelected ? 'is-selected' : ''].filter(Boolean).join(' ')}
                transform={`translate(${item.x} ${item.y})`}
                tabIndex={0}
                role="button"
                aria-label={`${item.node.type} ${item.node.label}`}
                onClick={() => onSelectNode(item.node)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onSelectNode(item.node);
                  }
                }}
              >
                <circle r={radius} fill={color} fillOpacity={isSelected ? 1 : 0.85} />
                <title>{`${item.node.type} · ${item.node.label}\n${item.node.id}`}</title>
                {showLabels || item.isRoot || isSelected ? (
                  <text x={radius + 4} y={3} textAnchor="start">
                    {truncateLabel(item.node.label)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="graph-legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#4c9aff' }} /> System
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#f0883e' }} /> Part
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#2ea043' }} /> TestResult
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#a371f7' }} /> Requirement
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#db61a2' }} /> Model
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: '#f85149' }} /> Threat
        </span>
        <span className="legend-item">
          <span className="legend-line" style={{ borderTopStyle: 'solid', borderTopColor: '#a371f7' }} /> satisfies
        </span>
        <span className="legend-item">
          <span className="legend-line" style={{ borderTopStyle: 'solid', borderTopColor: '#3fb950' }} /> verifies
        </span>
        <span className="legend-item">
          <span className="legend-line" style={{ borderTopStyle: 'dashed', borderTopColor: '#58a6ff' }} /> confidence &lt; 0.60
        </span>
        {selectedEdge ? (
          <span className="legend-item text-accent">
            selected: {selectedEdge.edge.type} → {selectedEdge.edge.to}
          </span>
        ) : null}
      </div>
    </div>
  );
}
