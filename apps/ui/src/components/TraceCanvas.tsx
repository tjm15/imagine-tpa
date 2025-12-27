import { useMemo } from 'react';
import { AlertTriangle, EyeOff } from 'lucide-react';
import TraceGraph from './TraceGraph';
import { useTraceGraph } from '../hooks/useTraceGraph';
import type { Node, Edge } from '@xyflow/react';

interface TraceCanvasProps {
  runId: string | null;
  mode: 'summary' | 'inspect' | 'forensic';
  onClose: () => void;
}

const SEVERITY_STYLES: Record<string, string> = {
  error: 'border-rose-300 bg-rose-50',
  warning: 'border-amber-300 bg-amber-50',
  info: 'border-slate-200 bg-white',
};

export function TraceCanvas({ runId, mode, onClose }: TraceCanvasProps) {
  const { graph, loading, error } = useTraceGraph(runId, mode);

  const flow = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const nodes: Node[] = graph.nodes.map((node) => {
      const layout = node.layout || {};
      const severity = node.severity || 'info';
      return {
        id: node.node_id,
        position: { x: layout.x || 0, y: layout.y || 0 },
        data: { label: node.label },
        className: SEVERITY_STYLES[severity] || SEVERITY_STYLES.info,
        style: { borderRadius: 10, padding: 6, borderWidth: 1 },
      };
    });
    const edges: Edge[] = graph.edges.map((edge) => ({
      id: edge.edge_id,
      source: edge.src_id,
      target: edge.dst_id,
      label: edge.label || undefined,
      animated: edge.edge_type === 'USES',
      style: { stroke: '#94a3b8' },
    }));
    return { nodes, edges };
  }, [graph]);

  return (
    <div
      className="border-b bg-white/90 backdrop-blur-sm p-4 shadow-sm"
      style={{ borderColor: 'var(--color-accent)', height: 340 }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-sm font-semibold text-slate-900">Reasoning Trace Canvas</h4>
          <p className="text-xs text-slate-500">Live trace for the current grammar run.</p>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"
        >
          <EyeOff className="w-3 h-3" /> Close
        </button>
      </div>

      {loading && <div className="text-xs text-slate-500">Loading trace…</div>}
      {error && (
        <div className="text-xs text-amber-700 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5" /> {error}
        </div>
      )}
      {!loading && !error && !graph && <div className="text-xs text-slate-400">No trace available yet.</div>}
      {graph && <TraceGraph nodes={flow.nodes} edges={flow.edges} height={240} />}
    </div>
  );
}
