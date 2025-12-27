import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Circle, Eye, MinusCircle, Sparkles } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { useTraceGraph } from '../hooks/useTraceGraph';

interface ReasoningTrayProps {
  runId: string | null;
  mode: 'summary' | 'inspect' | 'forensic';
  onOpenTrace?: () => void;
}

const MOVE_ORDER = [
  { key: 'framing', label: 'Framing' },
  { key: 'issue_surfacing', label: 'Issues' },
  { key: 'evidence_curation', label: 'Evidence' },
  { key: 'evidence_interpretation', label: 'Interpretation' },
  { key: 'considerations_formation', label: 'Considerations' },
  { key: 'weighing_and_balance', label: 'Balance' },
  { key: 'negotiation_and_alteration', label: 'Negotiation' },
  { key: 'positioning_and_narration', label: 'Position' },
];

type MoveStatus = 'pending' | 'complete' | 'partial' | 'error';

const STATUS_META: Record<MoveStatus, { icon: any; tone: string; label: string }> = {
  pending: { icon: Circle, tone: 'text-slate-400', label: 'Pending' },
  complete: { icon: CheckCircle2, tone: 'text-emerald-600', label: 'Complete' },
  partial: { icon: MinusCircle, tone: 'text-amber-600', label: 'Partial' },
  error: { icon: AlertTriangle, tone: 'text-rose-600', label: 'Error' },
};

export function ReasoningTray({ runId, mode, onOpenTrace }: ReasoningTrayProps) {
  const { graph } = useTraceGraph(runId, mode);
  const [expanded, setExpanded] = useState(true);

  const moveStatus = useMemo(() => {
    const statusByMove = new Map<string, MoveStatus>();
    if (!graph) return statusByMove;
    graph.nodes
      .filter((node) => node.node_type === 'move')
      .forEach((node) => {
        const moveType = node.ref?.move_type;
        const rawStatus = node.ref?.status;
        if (!moveType) return;
        let status: MoveStatus = 'pending';
        if (rawStatus === 'success') status = 'complete';
        else if (rawStatus === 'partial') status = 'partial';
        else if (rawStatus === 'error') status = 'error';
        statusByMove.set(moveType, status);
      });
    return statusByMove;
  }, [graph]);

  const completed = MOVE_ORDER.filter((move) => moveStatus.get(move.key) === 'complete').length;
  const progress = Math.round((completed / MOVE_ORDER.length) * 100);

  return (
    <div className="border-t bg-white/90 backdrop-blur-sm px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Sparkles className="w-4 h-4 text-[color:var(--color-accent)]" />
            Reasoning Tray
          </div>
          <Badge variant="outline" className="text-[10px]">
            {runId ? `Run ${runId.slice(0, 8)}` : 'No active run'}
          </Badge>
          <span className="text-xs text-slate-500">{progress}% complete</span>
        </div>
        <div className="flex items-center gap-2">
          {onOpenTrace && (
            <Button size="sm" variant="outline" onClick={onOpenTrace}>
              <Eye className="w-4 h-4 mr-1" />
              Trace Canvas
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setExpanded((prev) => !prev)}>
            {expanded ? 'Collapse' : 'Expand'}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 grid gap-2 md:grid-cols-4 xl:grid-cols-8">
          {MOVE_ORDER.map((move) => {
            const status = moveStatus.get(move.key) || 'pending';
            const meta = STATUS_META[status];
            const Icon = meta.icon;
            return (
              <div key={move.key} className="rounded-md border border-slate-200 px-2 py-2 bg-white">
                <div className="flex items-center gap-1 text-xs font-medium text-slate-700">
                  <Icon className={`w-3.5 h-3.5 ${meta.tone}`} />
                  {move.label}
                </div>
                <div className={`text-[10px] ${meta.tone}`}>{meta.label}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
