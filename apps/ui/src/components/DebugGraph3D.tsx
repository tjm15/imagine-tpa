import { useEffect, useMemo, useRef, useState } from 'react';

export type DebugGraphNode = {
  node_id: string;
  node_type?: string | null;
  label?: string | null;
  layout?: { x?: number; y?: number; z?: number } | null;
  ref?: Record<string, unknown> | null;
  props_jsonb?: Record<string, unknown> | null;
  canonical_fk?: string | null;
};

export type DebugGraphEdge = {
  edge_id: string;
  src_id: string;
  dst_id: string;
  edge_type?: string | null;
  label?: string | null;
  props_jsonb?: Record<string, unknown> | null;
  evidence_ref_id?: string | null;
  tool_run_id?: string | null;
};

export type DebugGraphData = {
  nodes: DebugGraphNode[];
  edges: DebugGraphEdge[];
};

type PositionedNode = DebugGraphNode & {
  x: number;
  y: number;
  z: number;
};

type ScreenNode = PositionedNode & {
  sx: number;
  sy: number;
  radius: number;
};

type DebugGraph3DProps = {
  graph: DebugGraphData | null;
  onNodeSelect?: (node: DebugGraphNode | null) => void;
  selectedNodeId?: string | null;
  height?: number;
};

const PALETTE = [
  '#0EA5E9',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#14B8A6',
  '#EC4899',
  '#22C55E',
  '#F97316',
  '#6366F1',
];

function colorForType(type: string | null | undefined): string {
  if (!type) return PALETTE[0];
  let hash = 0;
  for (let i = 0; i < type.length; i += 1) {
    hash = (hash * 31 + type.charCodeAt(i)) % 2147483647;
  }
  return PALETTE[hash % PALETTE.length];
}

function buildLayout(nodes: DebugGraphNode[]): PositionedNode[] {
  if (nodes.length === 0) return [];
  const typeCounts = new Map<string, number>();
  nodes.forEach((node) => {
    const key = node.node_type || 'node';
    typeCounts.set(key, (typeCounts.get(key) ?? 0) + 1);
  });
  const types = Array.from(typeCounts.keys());
  const typeIndex = new Map(types.map((t, idx) => [t, idx]));
  const typeOffsets = new Map<string, number>();
  const ringGap = 90;
  const zGap = 70;

  return nodes.map((node) => {
    const type = node.node_type || 'node';
    const groupIndex = typeIndex.get(type) ?? 0;
    const groupCount = typeCounts.get(type) ?? 1;
    const within = typeOffsets.get(type) ?? 0;
    typeOffsets.set(type, within + 1);

    if (node.layout && typeof node.layout.x === 'number' && typeof node.layout.y === 'number') {
      const z = typeof node.layout.z === 'number' ? node.layout.z : (groupIndex - (types.length - 1) / 2) * zGap;
      return { ...node, x: node.layout.x, y: node.layout.y, z };
    }

    const angle = (within / Math.max(1, groupCount)) * Math.PI * 2;
    const radius = 160 + groupIndex * ringGap;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    const z = (groupIndex - (types.length - 1) / 2) * zGap;
    return { ...node, x, y, z };
  });
}

export function DebugGraph3D({ graph, onNodeSelect, selectedNodeId, height = 420 }: DebugGraph3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const screenNodesRef = useRef<ScreenNode[]>([]);
  const [rotation, setRotation] = useState({ x: -0.35, y: 0.6 });
  const [zoom, setZoom] = useState(900);
  const dragRef = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });

  const positionedNodes = useMemo(() => buildLayout(graph?.nodes ?? []), [graph]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.clientWidth || 1;
    const heightPx = canvas.clientHeight || 1;
    canvas.width = width;
    canvas.height = heightPx;

    ctx.clearRect(0, 0, width, heightPx);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, heightPx);

    const nodes = positionedNodes;
    if (nodes.length === 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.font = '14px ui-sans-serif, system-ui, sans-serif';
      ctx.fillText('No graph data loaded.', 16, 24);
      screenNodesRef.current = [];
      return;
    }

    let minX = nodes[0].x;
    let maxX = nodes[0].x;
    let minY = nodes[0].y;
    let maxY = nodes[0].y;
    let minZ = nodes[0].z;
    let maxZ = nodes[0].z;
    nodes.forEach((n) => {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y);
      maxY = Math.max(maxY, n.y);
      minZ = Math.min(minZ, n.z);
      maxZ = Math.max(maxZ, n.z);
    });

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const centerZ = (minZ + maxZ) / 2;
    const spread = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1);
    const worldScale = Math.min(width, heightPx) / (spread * 1.6);

    const cosY = Math.cos(rotation.y);
    const sinY = Math.sin(rotation.y);
    const cosX = Math.cos(rotation.x);
    const sinX = Math.sin(rotation.x);

    const screenNodes: ScreenNode[] = [];
    const nodeById = new Map(nodes.map((n) => [n.node_id, n]));

    const project = (node: PositionedNode) => {
      const x0 = (node.x - centerX) * worldScale;
      const y0 = (node.y - centerY) * worldScale;
      const z0 = (node.z - centerZ) * worldScale;

      const x1 = x0 * cosY + z0 * sinY;
      const z1 = -x0 * sinY + z0 * cosY;
      const y1 = y0 * cosX - z1 * sinX;
      const z2 = y0 * sinX + z1 * cosX;

      const depth = zoom / (zoom + z2 + 600);
      return {
        sx: width / 2 + x1 * depth,
        sy: heightPx / 2 + y1 * depth,
        scale: depth,
      };
    };

    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
    if (graph?.edges?.length) {
      ctx.beginPath();
      graph.edges.forEach((edge) => {
        const src = nodeById.get(edge.src_id);
        const dst = nodeById.get(edge.dst_id);
        if (!src || !dst) return;
        const p1 = project(src);
        const p2 = project(dst);
        ctx.moveTo(p1.sx, p1.sy);
        ctx.lineTo(p2.sx, p2.sy);
      });
      ctx.stroke();
    }

    nodes.forEach((node) => {
      const projected = project(node);
      const radius = Math.max(3, 6 * projected.scale);
      const isSelected = selectedNodeId === node.node_id;
      ctx.beginPath();
      ctx.fillStyle = isSelected ? '#FCD34D' : colorForType(node.node_type ?? '');
      ctx.globalAlpha = isSelected ? 0.95 : 0.75;
      ctx.arc(projected.sx, projected.sy, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      if (isSelected) {
        ctx.strokeStyle = 'rgba(252, 211, 77, 0.6)';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      screenNodes.push({ ...node, sx: projected.sx, sy: projected.sy, radius });
    });

    screenNodesRef.current = screenNodes;
  }, [graph, positionedNodes, rotation, zoom, selectedNodeId]);

  useEffect(() => {
    if (!graph?.nodes?.length) {
      if (onNodeSelect) onNodeSelect(null);
    }
  }, [graph, onNodeSelect]);

  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    dragRef.current = { x: event.clientX, y: event.clientY, active: true };
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!dragRef.current.active) return;
    const dx = event.clientX - dragRef.current.x;
    const dy = event.clientY - dragRef.current.y;
    dragRef.current = { x: event.clientX, y: event.clientY, active: true };
    setRotation((prev) => ({
      x: Math.max(-1.2, Math.min(1.2, prev.x + dy * 0.004)),
      y: prev.y + dx * 0.004,
    }));
  };

  const handlePointerUp = () => {
    dragRef.current.active = false;
  };

  const handleWheel = (event: React.WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    setZoom((prev) => Math.max(300, Math.min(1400, prev + event.deltaY)));
  };

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best: ScreenNode | null = null;
    let bestDist = Infinity;
    screenNodesRef.current.forEach((node) => {
      const dx = node.sx - x;
      const dy = node.sy - y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= node.radius + 6 && dist < bestDist) {
        best = node;
        bestDist = dist;
      }
    });
    if (onNodeSelect) onNodeSelect(best);
  };

  return (
    <div ref={containerRef} className="relative h-full w-full rounded-xl border" style={{ borderColor: 'var(--color-neutral-300)' }}>
      <canvas
        ref={canvasRef}
        className="h-full w-full touch-none"
        style={{ height, background: '#0f172a' }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onWheel={handleWheel}
        onClick={handleClick}
      />
      <div className="pointer-events-none absolute left-3 top-3 rounded-full bg-white/80 px-3 py-1 text-xs text-slate-700 shadow">
        Drag to rotate · Scroll to zoom · Click a node
      </div>
    </div>
  );
}
