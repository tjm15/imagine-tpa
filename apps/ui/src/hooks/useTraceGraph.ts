import { useEffect, useState } from 'react';

export type TraceGraphNode = {
  node_id: string;
  node_type: string;
  label: string;
  ref?: Record<string, any> | null;
  layout?: { x?: number; y?: number; group?: string | null } | null;
  severity?: string | null;
};

export type TraceGraphEdge = {
  edge_id: string;
  src_id: string;
  dst_id: string;
  edge_type: string;
  label?: string | null;
};

export type TraceGraphData = {
  trace_graph_id: string;
  run_id: string;
  mode: string;
  nodes: TraceGraphNode[];
  edges: TraceGraphEdge[];
  created_at?: string | null;
};

export function useTraceGraph(runId: string | null, mode: 'summary' | 'inspect' | 'forensic') {
  const [graph, setGraph] = useState<TraceGraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setGraph(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch(`/api/trace/runs/${runId}?mode=${mode}`, { signal: controller.signal });
        if (!resp.ok) {
          throw new Error(`Trace unavailable (${resp.status})`);
        }
        const data = (await resp.json()) as TraceGraphData;
        setGraph(data);
      } catch (err: any) {
        if (err?.name !== 'AbortError') {
          setError(err?.message || 'Trace unavailable');
          setGraph(null);
        }
      } finally {
        setLoading(false);
      }
    };
    load();
    return () => controller.abort();
  }, [runId, mode]);

  return { graph, loading, error };
}
