import { useEffect, useMemo } from 'react';
import {
  ArrowRight,
  Clock,
  ExternalLink,
  HelpCircle,
  Sparkles,
  User,
  X,
} from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import {
  getEvidenceById,
  getPolicyById,
  getTraceForElement,
  mockAuditEvents,
  mockConsiderations,
  mockMoveEvents,
  mockToolRuns,
  type AuditEvent,
  type MoveEvent,
  type ReasoningMove,
  type ToolRun,
} from '../../fixtures/mockData';
import { useAppState } from '../../lib/appState';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface TraceOverlayProps {
  open: boolean;
  mode: ExplainabilityMode;
  runId: string;
  target?: TraceTarget | null;
  onClose: () => void;
  onRequestModeChange?: (mode: ExplainabilityMode) => void;
}

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

const moveLabel: Record<ReasoningMove, string> = {
  framing: 'Framing',
  issues: 'Issues',
  evidence: 'Evidence',
  interpretation: 'Interpretation',
  considerations: 'Considerations',
  balance: 'Balance',
  negotiation: 'Negotiation',
  positioning: 'Positioning',
};

function statusBadge(status: 'complete' | 'in-progress' | 'pending') {
  if (status === 'complete') return <Badge className="h-5 text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200">Complete</Badge>;
  if (status === 'in-progress') return <Badge className="h-5 text-[10px] bg-amber-50 text-amber-800 border-amber-200">In progress</Badge>;
  return <Badge variant="outline" className="h-5 text-[10px] bg-white">Pending</Badge>;
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function deriveTitle(target?: TraceTarget | null) {
  if (!target) return { title: 'Trace', subtitle: 'Run-level trace and audit trail' };
  if (target.label) return { title: target.label, subtitle: `Trace for ${target.kind}` };
  if (!target.id) return { title: 'Trace', subtitle: `Trace for ${target.kind}` };

  const evidence = getEvidenceById(target.id);
  if (evidence) return { title: evidence.title, subtitle: 'Evidence trace' };

  const policy = getPolicyById(target.id);
  if (policy) return { title: `${policy.reference} · ${policy.title}`, subtitle: 'Policy trace' };

  const consideration = mockConsiderations.find((c) => c.id === target.id);
  if (consideration) return { title: consideration.title || consideration.issue, subtitle: 'Consideration trace' };

  return { title: target.id, subtitle: `Trace for ${target.kind}` };
}

function summarizeTrace(target: TraceTarget | null | undefined, moves: MoveEvent[], tools: ToolRun[]) {
  const moveNames = Array.from(new Set(moves.map((m) => moveLabel[m.move]))).join(', ');
  const toolNames = Array.from(new Set(tools.map((t) => t.tool))).join(', ');

  if (!target?.id) {
    return {
      headline: 'Run-level trace is available for contestable accountability.',
      details: [
        `Moves recorded: ${moves.length}`,
        `Tool runs recorded: ${tools.length}`,
        toolNames ? `Tools: ${toolNames}` : 'Tools: none recorded',
      ],
    };
  }

  const evidence = getEvidenceById(target.id);
  const policy = getPolicyById(target.id);

  const kindLine = evidence
    ? 'This evidence item was curated and then used in interpretation/formation.'
    : policy
      ? 'This policy clause is cited as a normative constraint in the chain.'
      : 'This element participates in the recorded move chain.';

  return {
    headline: kindLine,
    details: [
      moveNames ? `Touches moves: ${moveNames}` : 'Touches moves: none found',
      tools.length ? `Used by tools: ${toolNames || 'unknown'}` : 'Used by tools: none found',
    ],
  };
}

function MoveTimeline({
  runId,
  relatedMoveIds,
  statuses,
}: {
  runId: string;
  relatedMoveIds: Set<ReasoningMove>;
  statuses: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'>;
}) {
  const eventsByMove = useMemo(() => {
    const events = mockMoveEvents.filter((m) => m.runId === runId);
    const map = new Map<ReasoningMove, MoveEvent>();
    for (const m of events) map.set(m.move, m);
    return map;
  }, [runId]);

  return (
    <div className="w-[240px] border-r border-neutral-200 bg-white min-h-0 flex flex-col">
      <div className="px-3 py-2 border-b border-neutral-200">
        <div className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">Move chain</div>
        <div className="text-[11px] text-slate-500 mt-0.5">8-move grammar</div>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-2 space-y-1.5">
          {moveOrder.map((move, idx) => {
            const status = statuses[move] ?? 'pending';
            const isRelated = relatedMoveIds.has(move);
            const evt = eventsByMove.get(move);

            const dot =
              status === 'complete'
                ? 'bg-emerald-500'
                : status === 'in-progress'
                  ? 'bg-amber-400'
                  : 'bg-slate-200';

            return (
              <div
                key={move}
                className={`rounded-lg border px-2.5 py-2 transition-colors ${
                  isRelated ? 'border-amber-200 bg-amber-50/50' : 'border-neutral-200 bg-white'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-2.5 h-2.5 rounded-full ${dot}`} aria-hidden="true" />
                    <span className="text-sm font-medium text-slate-800 truncate">
                      {idx + 1}. {moveLabel[move]}
                    </span>
                  </div>
                  <div className="flex-shrink-0">{statusBadge(status)}</div>
                </div>
                {evt?.timestamp ? (
                  <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-500">
                    <Clock className="w-3 h-3" />
                    {new Date(evt.timestamp).toLocaleString()}
                  </div>
                ) : (
                  <div className="mt-1 text-[10px] text-slate-400">No event yet</div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}

function ToolsSection({ tools, mode }: { tools: ToolRun[]; mode: ExplainabilityMode }) {
  if (tools.length === 0) {
    return <div className="text-sm text-slate-500">No tool runs recorded for this element.</div>;
  }

  return (
    <div className="space-y-3">
      {tools.map((t) => (
        <div key={t.id} className="border border-neutral-200 rounded-lg bg-white overflow-hidden">
          <div className="px-3 py-2 flex items-center justify-between bg-slate-50 border-b border-neutral-200">
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="w-4 h-4 text-violet-600" />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-800 truncate">{t.tool}</div>
                <div className="text-[11px] text-slate-500 truncate">
                  {t.model ? `Model: ${t.model}` : 'Model: n/a'}
                  {t.promptVersion ? ` · ${t.promptVersion.startsWith('v') ? t.promptVersion : `v${t.promptVersion}`}` : ''}
                </div>
              </div>
            </div>
            <Badge variant="outline" className="text-[10px] font-mono bg-white">
              {t.durationMs}ms
            </Badge>
          </div>

          <div className="p-3 space-y-2">
            {t.limitations ? (
              <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-2">
                <span className="font-semibold">Limitations:</span> {t.limitations}
              </div>
            ) : null}

            {mode === 'summary' ? (
              <div className="text-sm text-slate-700">
                Tool run logged with inputs/outputs; open Inspect/Forensic for details.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
                  <div className="border border-neutral-200 rounded-md bg-white">
                    <div className="px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 border-b border-neutral-200">Inputs</div>
                    <pre className="text-[11px] leading-snug p-2.5 overflow-auto max-h-40">{formatJson(t.inputs)}</pre>
                  </div>
                  <div className="border border-neutral-200 rounded-md bg-white">
                    <div className="px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 border-b border-neutral-200">Outputs</div>
                    <pre className="text-[11px] leading-snug p-2.5 overflow-auto max-h-40">{formatJson(t.outputs)}</pre>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function AuditSection({ audit, mode }: { audit: AuditEvent[]; mode: ExplainabilityMode }) {
  if (audit.length === 0) return <div className="text-sm text-slate-500">No user audit events recorded for this element.</div>;

  return (
    <div className="space-y-2">
      {audit.map((a) => (
        <div key={a.id} className="border border-neutral-200 rounded-lg bg-white px-3 py-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <User className="w-4 h-4 text-slate-500" />
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-800 truncate">{a.userId}</div>
                <div className="text-[11px] text-slate-500 truncate">{a.action.replaceAll('_', ' ')}</div>
              </div>
            </div>
            <Badge variant="outline" className="text-[10px] bg-white">
              {a.timestamp ? new Date(a.timestamp).toLocaleString() : 'n/a'}
            </Badge>
          </div>
          {mode !== 'summary' && a.note ? (
            <div className="mt-2 text-[11px] text-slate-700 bg-slate-50 border border-neutral-200 rounded-md px-2.5 py-2">
              “{a.note}”
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function MovesForensic({ moves }: { moves: MoveEvent[] }) {
  if (moves.length === 0) return <div className="text-sm text-slate-500">No move events recorded for this element.</div>;

  return (
    <div className="space-y-2">
      {moves.map((m) => (
        <div key={m.id} className="border border-neutral-200 rounded-lg bg-white overflow-hidden">
          <div className="px-3 py-2 flex items-center justify-between bg-slate-50 border-b border-neutral-200">
            <div className="text-sm font-semibold text-slate-800">
              {moveLabel[m.move]}
            </div>
            {statusBadge(m.status)}
          </div>
          <div className="p-3 grid grid-cols-1 lg:grid-cols-2 gap-2 text-[11px]">
            <div className="border border-neutral-200 rounded-md bg-white">
              <div className="px-2.5 py-1.5 font-semibold text-slate-600 border-b border-neutral-200">Inputs</div>
              <div className="p-2.5 text-slate-700">{m.inputIds.length ? m.inputIds.join(', ') : '—'}</div>
            </div>
            <div className="border border-neutral-200 rounded-md bg-white">
              <div className="px-2.5 py-1.5 font-semibold text-slate-600 border-b border-neutral-200">Outputs</div>
              <div className="p-2.5 text-slate-700">{m.outputIds.length ? m.outputIds.join(', ') : '—'}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function TraceOverlay({
  open,
  mode,
  runId,
  target,
  onClose,
  onRequestModeChange,
}: TraceOverlayProps) {
  const { reasoningMoves } = useAppState();

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  const { title, subtitle } = useMemo(() => deriveTitle(target), [target]);

  const { moves, tools, audit, relatedMoves, fallbackToRun } = useMemo(() => {
    const baseMoves = mockMoveEvents.filter((m) => m.runId === runId);
    const baseTools = mockToolRuns.filter((t) => t.runId === runId);
    const baseAudit = mockAuditEvents.filter((a) => a.runId === runId);

    if (!target?.id) {
      return { moves: baseMoves, tools: baseTools, audit: baseAudit, relatedMoves: new Set<ReasoningMove>(), fallbackToRun: false };
    }

    const trace = getTraceForElement(target.id);
    const relatedMoveIds = new Set(trace.moves.map((m) => m.move));
    const hasAny = trace.moves.length > 0 || trace.tools.length > 0 || trace.audit.length > 0;
    if (!hasAny) {
      return { moves: baseMoves, tools: baseTools, audit: baseAudit, relatedMoves: new Set<ReasoningMove>(), fallbackToRun: true };
    }

    return { moves: trace.moves, tools: trace.tools, audit: trace.audit, relatedMoves: relatedMoveIds, fallbackToRun: false };
  }, [runId, target]);

  const summary = useMemo(() => summarizeTrace(target ?? null, moves, tools), [target, moves, tools]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="absolute inset-y-0 right-0 w-full max-w-5xl bg-white shadow-2xl flex flex-col">
        <div className="h-14 px-4 border-b border-neutral-200 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-lg flex items-center justify-center bg-slate-50 border border-neutral-200">
              <HelpCircle className="w-4 h-4 text-slate-700" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-900 truncate">{title}</div>
              <div className="text-[11px] text-slate-500 truncate">{subtitle}</div>
            </div>
            <Separator orientation="vertical" className="h-6" />
            <Badge variant="outline" className="text-[10px] font-mono bg-white">
              {runId}
            </Badge>
            <Badge variant="secondary" className="text-[10px] bg-slate-100 text-slate-700">
              {mode === 'summary' ? 'Summary' : mode === 'inspect' ? 'Inspect' : 'Forensic'}
            </Badge>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {mode === 'summary' && onRequestModeChange ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-2"
                onClick={() => onRequestModeChange('forensic')}
              >
                Go Forensic
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            ) : null}
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex">
          <MoveTimeline runId={runId} relatedMoveIds={relatedMoves} statuses={reasoningMoves} />

          <div className="flex-1 min-h-0 flex flex-col bg-slate-50">
            <div className="px-4 py-3 border-b border-neutral-200 bg-white">
              <div className="text-sm font-semibold text-slate-800">Position (what can be said)</div>
              <div className="mt-1 text-sm text-slate-700">{summary.headline}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {summary.details.map((d) => (
                  <Badge key={d} variant="outline" className="text-[10px] bg-white">
                    {d}
                  </Badge>
                ))}
              </div>
              {target?.note ? (
                <div className="mt-2 text-[11px] text-slate-600">{target.note}</div>
              ) : null}
            </div>

            <ScrollArea className="flex-1 min-h-0">
              <div className="p-4 space-y-6">
                {fallbackToRun ? (
                  <div className="text-[11px] text-slate-700 bg-slate-50 border border-neutral-200 rounded-lg px-3 py-2">
                    No element-level log found for this target; showing run-level trace for context.
                  </div>
                ) : null}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">Move log</div>
                    {mode === 'summary' ? (
                      <div className="text-[11px] text-slate-500">Open Inspect for move I/O</div>
                    ) : null}
                  </div>
                  {mode === 'summary' ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {Array.from(new Set(moves.map((m) => m.move))).map((m) => (
                        <div key={m} className="bg-white border border-neutral-200 rounded-lg px-3 py-2 text-sm text-slate-700">
                          {moveLabel[m]}
                        </div>
                      ))}
                      {moves.length === 0 ? (
                        <div className="text-sm text-slate-500">No related moves found for this element.</div>
                      ) : null}
                    </div>
                  ) : (
                    <MovesForensic moves={moves} />
                  )}
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">Tools</div>
                    <a className="text-[11px] text-slate-500 hover:underline inline-flex items-center gap-1" href="#" onClick={(e) => e.preventDefault()}>
                      Provider notes <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <ToolsSection tools={tools} mode={mode} />
                </div>

                <div>
                  <div className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase mb-2">Audit</div>
                  <AuditSection audit={audit} mode={mode} />
                </div>
              </div>
            </ScrollArea>
          </div>
        </div>
      </div>
    </div>
  );
}
