import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, HelpCircle, Minus, Plus, Scale } from 'lucide-react';
import { Badge } from './ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';
import { useAppState } from '../lib/appState';
import { Consideration } from '../fixtures/mockData';
import type { TraceTarget } from '../lib/trace';

interface ReasoningTrayProps {
  runId: string;
  onOpenTrace?: (target?: TraceTarget) => void;
}

type ReasoningMove = 'framing' | 'issues' | 'evidence' | 'interpretation' | 'considerations' | 'balance' | 'negotiation' | 'positioning';

const moveOrder: ReasoningMove[] = [
  'framing',
  'issues',
  'evidence',
  'interpretation',
  'considerations',
  'balance',
  'negotiation',
  'positioning',
];

const moveLabels: Record<ReasoningMove, string> = {
  framing: 'Framing',
  issues: 'Issues',
  evidence: 'Evidence',
  interpretation: 'Interpretation',
  considerations: 'Considerations',
  balance: 'Balance',
  negotiation: 'Negotiation',
  positioning: 'Positioning',
};

const getValence = (c: Consideration): 'for' | 'against' | 'neutral' => {
  if (c.valence) return c.valence;
  if (c.direction === 'supports') return 'for';
  if (c.direction === 'against') return 'against';
  return 'neutral';
};

const getTitle = (c: Consideration): string => c.title || c.issue;

function WhyIconButton({ onClick, label }: { onClick?: () => void; label: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="h-7 w-7 rounded-md flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            aria-label={label}
            onClick={onClick}
          >
            <HelpCircle className="w-4 h-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">Open trace</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function ReasoningTrayInteractive({ runId, onOpenTrace }: ReasoningTrayProps) {
  const { reasoningMoves, considerations } = useAppState();
  const [isExpanded, setIsExpanded] = useState(false);

  const completedMoves = useMemo(() => moveOrder.filter((m) => reasoningMoves[m] === 'complete'), [reasoningMoves]);
  const currentMove = useMemo(() => moveOrder.find((m) => reasoningMoves[m] === 'in-progress') || 'framing', [reasoningMoves]);
  const progressPercent = useMemo(() => Math.round((completedMoves.length / 8) * 100), [completedMoves.length]);

  const ledgerSummary = useMemo(() => {
    const forItems = considerations.filter((c) => getValence(c) === 'for');
    const againstItems = considerations.filter((c) => getValence(c) === 'against');
    const neutralItems = considerations.filter((c) => getValence(c) === 'neutral');

    const net = considerations.reduce((acc, c) => {
      const weight = Number(c.weight ?? 0) || 0;
      const direction = getValence(c) === 'for' ? 1 : getValence(c) === 'against' ? -1 : 0;
      return acc + weight * direction;
    }, 0);

    return { forItems, againstItems, neutralItems, net };
  }, [considerations]);

  const headlineConsiderations = useMemo(() => {
    const copy = [...considerations];
    copy.sort((a, b) => {
      const wa = Number(a.weight ?? 0) || 0;
      const wb = Number(b.weight ?? 0) || 0;
      return wb - wa;
    });
    return copy.slice(0, 5);
  }, [considerations]);

  const tensions = useMemo(
    () => [
      'Housing uplift vs town centre heritage risk',
      'Parking removal tension with disability access',
    ],
    []
  );

  const heightPx = isExpanded ? 260 : 44;

  return (
    <div
      className="border-t bg-white transition-[height] duration-200 ease-in-out overflow-hidden"
      style={{ height: heightPx, borderColor: 'var(--color-neutral-300)' }}
    >
      {/* Handle */}
      <button
        type="button"
        className="w-full h-[44px] px-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-3 min-w-0">
          <Scale className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
          <span className="text-sm font-medium text-slate-800 truncate">
            Reasoning ({considerations.length})
          </span>
          <div className="hidden md:flex items-center gap-2 text-xs text-slate-600">
            <Badge variant="outline" className="h-5 text-[10px] bg-white">
              For {ledgerSummary.forItems.length}
            </Badge>
            <Badge variant="outline" className="h-5 text-[10px] bg-white">
              Against {ledgerSummary.againstItems.length}
            </Badge>
            <Badge variant="outline" className="h-5 text-[10px] bg-white">
              Neutral {ledgerSummary.neutralItems.length}
            </Badge>
            <Badge variant="secondary" className="h-5 text-[10px] bg-slate-100 text-slate-700">
              Net {ledgerSummary.net >= 0 ? `+${ledgerSummary.net}` : `${ledgerSummary.net}`}
            </Badge>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden lg:flex items-center gap-2 text-xs text-slate-600">
            <Badge variant="outline" className="h-5 text-[10px] font-mono bg-white">
              {runId}
            </Badge>
            <span className="text-[11px]">
              {progressPercent}% · {moveLabels[currentMove]}
            </span>
            <div className="flex items-center gap-1">
              {(moveOrder as ReasoningMove[]).map((m) => {
                const status = reasoningMoves[m];
                const bg =
                  status === 'complete'
                    ? 'bg-emerald-500'
                    : status === 'in-progress'
                      ? 'bg-amber-400'
                      : 'bg-slate-200';
                return <span key={m} className={`w-2 h-2 rounded-full ${bg}`} title={`${m} · ${status}`} />;
              })}
            </div>
          </div>
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          )}
        </div>
      </button>

      {/* Content */}
      <div className="h-[216px] px-4 py-3 grid grid-cols-1 lg:grid-cols-2 gap-3 border-t border-neutral-200">
        <div className="min-w-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">Headline considerations</span>
            <WhyIconButton
              label="Open trace"
              onClick={() => onOpenTrace?.({ kind: 'run', label: 'Current run' })}
            />
          </div>
          <div className="space-y-2">
            {headlineConsiderations.map((c) => {
              const valence = getValence(c);
              const icon =
                valence === 'for' ? (
                  <Plus className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
                ) : valence === 'against' ? (
                  <Minus className="w-3.5 h-3.5 text-slate-500" />
                ) : (
                  <Scale className="w-3.5 h-3.5 text-slate-500" />
                );

              return (
                <div key={c.id} className="flex items-center gap-2 bg-white border border-neutral-200 rounded-lg px-2.5 py-2">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {icon}
                    <span className="text-sm font-medium text-slate-800 truncate">{getTitle(c)}</span>
                  </div>
                  <Badge variant="outline" className="text-[10px] h-5 bg-white">
                    {c.weight}
                  </Badge>
                  <WhyIconButton
                    label="Open trace"
                    onClick={() => onOpenTrace?.({ kind: 'consideration', id: c.id, label: getTitle(c) })}
                  />
                </div>
              );
            })}
          </div>
        </div>

        <div className="min-w-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">Tensions</span>
            <WhyIconButton
              label="Open trace"
              onClick={() => onOpenTrace?.({ kind: 'run', label: 'Current run' })}
            />
          </div>
          <div className="space-y-2">
            {tensions.map((t) => (
              <div key={t} className="flex items-center gap-2 bg-white border border-neutral-200 rounded-lg px-2.5 py-2">
                <span className="text-sm text-slate-800 truncate flex-1">{t}</span>
                <WhyIconButton
                  label="Open trace"
                  onClick={() => onOpenTrace?.({ kind: 'tension', id: `tension-${t.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}`, label: t })}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
