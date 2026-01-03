import { useMemo } from 'react';
import { Calendar, CheckCircle2, Circle, Clock, AlertTriangle, ArrowRight, Sparkles } from 'lucide-react';
import { WorkspaceMode, type ViewMode } from '../../App';
import { culpStageConfigs } from '../../fixtures/extendedMockData';
import { useAppDispatch, useAppState } from '../../lib/appState';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { toast } from 'sonner';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface OverviewViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
  onViewChange?: (view: ViewMode) => void;
  onRequestPatchBundle?: () => void;
}

function StageStatusIcon({ status }: { status: (typeof culpStageConfigs)[number]['status'] }) {
  if (status === 'complete') return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
  if (status === 'in-progress') return <Clock className="w-4 h-4 text-amber-600" />;
  if (status === 'blocked') return <AlertTriangle className="w-4 h-4 text-red-600" />;
  return <Circle className="w-4 h-4 text-slate-300" />;
}

export function OverviewView({
  workspace,
  explainabilityMode = 'summary',
  onOpenTrace,
  onViewChange,
  onRequestPatchBundle,
}: OverviewViewProps) {
  const dispatch = useAppDispatch();
  const { currentStageId } = useAppState();

  const stages = useMemo(() => {
    if (workspace !== 'plan') return [];
    return culpStageConfigs;
  }, [workspace]);

  const currentStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === currentStageId) ?? stages[0];
  }, [stages, currentStageId]);

  const completedCount = stages.filter((s) => s.status === 'complete').length;
  const progress = stages.length ? Math.round((completedCount / stages.length) * 100) : 0;

  if (workspace !== 'plan') {
    return (
      <div className="h-full flex items-center justify-center text-sm text-slate-600">
        Overview is only available in the Plan workspace.
      </div>
    );
  }

  if (!currentStage) return null;

  return (
    <div className="h-full min-h-0 bg-white">
      <ScrollArea className="h-full">
        <div className="p-6 space-y-6">
          {/* Programme header (inside the project) */}
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="bg-slate-100 text-slate-700 border border-slate-200">
                  CULP programme
                </Badge>
                <Badge variant="outline" className="font-mono text-[10px] bg-white">
                  stage:{currentStage.id}
                </Badge>
              </div>
              <h2 className="text-2xl font-semibold mt-2" style={{ color: 'var(--color-ink)' }}>
                {currentStage.name}
              </h2>
              <p className="text-sm mt-1" style={{ color: 'var(--color-text)' }}>
                {currentStage.description}
              </p>
            </div>

            <div className="flex flex-col items-end gap-2 flex-shrink-0">
              <Badge
                variant="outline"
                className="text-xs bg-white"
                style={{ borderColor: 'var(--color-neutral-300)', color: 'var(--color-text)' }}
              >
                Overall {progress}%
              </Badge>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onViewChange?.('studio')}
                >
                  Open deliverable
                </Button>
                <Button
                  size="sm"
                  onClick={() => onViewChange?.('map')}
                  style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
                >
                  Open map & plans
                </Button>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between text-xs mb-2" style={{ color: 'var(--color-text)' }}>
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5" />
                Programme progress
              </span>
              <span>{completedCount}/{stages.length} stages complete</span>
            </div>
            <Progress value={progress} className="h-2" />
          </div>

          {/* Stage timeline (explicit CULP spine) */}
          <div className="bg-slate-50 border rounded-xl p-4" style={{ borderColor: 'var(--color-neutral-200)' }}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                CULP stage spine
              </div>
              <Badge variant="outline" className="text-[10px] bg-white">
                Click a stage to switch context
              </Badge>
            </div>
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              {stages.map((stage, idx) => {
                const isActive = stage.id === currentStage.id;
                return (
                  <button
                    key={stage.id}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors ${
                      isActive ? 'bg-white shadow-sm' : 'bg-white/60 hover:bg-white'
                    }`}
                    style={{ borderColor: isActive ? 'var(--color-accent)' : 'var(--color-neutral-200)' }}
                    onClick={() => dispatch({ type: 'SET_STAGE', payload: { stageId: stage.id } })}
                  >
                    <StageStatusIcon status={stage.status} />
                    <div className="min-w-0">
                      <div
                        className="text-xs font-semibold truncate"
                        style={{ color: isActive ? 'var(--color-ink)' : 'var(--color-text)' }}
                      >
                        {stage.name}
                      </div>
                      <div className="text-[10px] text-slate-500 truncate">{stage.dueDate}</div>
                    </div>
                    {idx < stages.length - 1 && (
                      <ArrowRight className="w-3.5 h-3.5 text-slate-300 ml-1 flex-shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Core stage cockpit */}
          <div className="grid lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-4">
              <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--color-neutral-200)' }}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <StageStatusIcon status={currentStage.status} />
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                        Current stage
                      </span>
                      <Badge variant="outline" className="text-[10px] bg-white">
                        {currentStage.phase}
                      </Badge>
                    </div>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text)' }}>
                      This is the procedural cockpit for the selected stage: required artefacts, blockers, and tools.
                    </p>
                  </div>
                  {onOpenTrace && (
                    <button
                      className="text-[11px] underline-offset-2 hover:underline"
                      style={{ color: 'var(--color-gov-blue)' }}
                      onClick={() =>
                        onOpenTrace({
                          kind: 'stage',
                          id: currentStage.id,
                          label: `Stage: ${currentStage.name}`,
                        })
                      }
                    >
                      Trace
                    </button>
                  )}
                </div>
              </div>

              <div className="bg-white border rounded-xl" style={{ borderColor: 'var(--color-neutral-200)' }}>
                <div className="p-4 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
                  <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                    Next steps (checklist)
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--color-text)' }}>
                    Phase-sensitive without a rules engine: required items must be closed before gateway prep.
                  </div>
                </div>
                <div className="p-4 space-y-2">
                  {currentStage.checklist.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start justify-between gap-3 rounded-lg border p-3 bg-white"
                      style={{ borderColor: 'var(--color-neutral-200)' }}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-sm ${item.checked ? 'line-through text-slate-400' : ''}`}
                            style={{ color: item.checked ? undefined : 'var(--color-ink)' }}
                          >
                            {item.label}
                          </span>
                          {item.required && (
                            <Badge variant="outline" className="text-[10px] bg-white">
                              Required
                            </Badge>
                          )}
                        </div>
                        {!item.checked && item.required && (
                          <div className="text-[11px] text-amber-700 mt-1">
                            Open item — will block gateway readiness if unresolved.
                          </div>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => toast.info('Checklist editing is demo-only (v1).')}
                      >
                        {item.checked ? 'View' : 'Open'}
                      </Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white border rounded-xl" style={{ borderColor: 'var(--color-neutral-200)' }}>
                <div className="p-4 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
                  <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                    Required artefacts
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--color-text)' }}>
                    Click to open the relevant workspace surface.
                  </div>
                </div>
                <div className="p-4 space-y-2">
                  {currentStage.deliverables.map((deliverable) => {
                    const statusColor =
                      deliverable.status === 'complete'
                        ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                        : deliverable.status === 'draft'
                          ? 'text-amber-700 bg-amber-50 border-amber-200'
                          : 'text-slate-600 bg-slate-50 border-slate-200';
                    return (
                      <div
                        key={deliverable.id}
                        className="flex items-center justify-between gap-3 rounded-lg border p-3 bg-white"
                        style={{ borderColor: 'var(--color-neutral-200)' }}
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                            {deliverable.name}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            Due {deliverable.dueDate} · {deliverable.type}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className={`text-[10px] border ${statusColor}`}>
                            {deliverable.status}
                          </Badge>
                          <Button
                            size="sm"
                            className="h-7 text-xs"
                            variant="outline"
                            onClick={() => {
                              dispatch({ type: 'SELECT_DELIVERABLE', payload: { deliverableId: deliverable.id } });
                              onViewChange?.(deliverable.type === 'map' ? 'map' : 'studio');
                            }}
                          >
                            Open
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="lg:col-span-2 space-y-4">
              <div className="bg-slate-50 border rounded-xl p-4" style={{ borderColor: 'var(--color-neutral-200)' }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                    Attention & risk
                  </div>
                  <Badge variant="outline" className="text-[10px] bg-white">
                    Mode: {explainabilityMode}
                  </Badge>
                </div>
                <div className="text-xs mb-3" style={{ color: 'var(--color-text)' }}>
                  Issues are mode-dependent: overview summarises; inspection/forensic expands and links to trace.
                </div>
                {currentStage.warnings.length === 0 ? (
                  <div className="text-sm text-slate-600 bg-white rounded-lg border p-3" style={{ borderColor: 'var(--color-neutral-200)' }}>
                    No stage warnings recorded.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {currentStage.warnings.map((warning) => {
                      const accent =
                        warning.severity === 'critical'
                          ? 'border-l-red-500 bg-red-50'
                          : warning.severity === 'major'
                            ? 'border-l-amber-500 bg-amber-50'
                            : 'border-l-slate-300 bg-white';
                      return (
                        <div
                          key={warning.id}
                          className={`rounded-lg border border-slate-200 border-l-4 p-3 ${accent}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-slate-800">{warning.message}</div>
                              <div className="text-[11px] text-slate-600 mt-1">
                                Severity: {warning.severity}
                              </div>
                            </div>
                            {warning.actionLabel && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs"
                                onClick={() => toast.info(`Action queued: ${warning.actionLabel} (demo)`)}
                              >
                                {warning.actionLabel}
                              </Button>
                            )}
                          </div>
                          {onOpenTrace && explainabilityMode !== 'summary' && (
                            <button
                              className="mt-2 text-[11px] text-[color:var(--color-gov-blue)] underline-offset-2 hover:underline inline-flex items-center gap-1"
                              onClick={() =>
                                onOpenTrace({
                                  kind: 'issue',
                                  id: warning.id,
                                  label: warning.message,
                                })
                              }
                            >
                              Trace <ArrowRight className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--color-neutral-200)' }}>
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
                  <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                    Co‑drafter (demo)
                  </div>
                </div>
                <div className="text-xs mt-1" style={{ color: 'var(--color-text)' }}>
                  Structural suggestions should arrive as patch bundles (policy + spatial + justification + issues), not cursor-level inserts.
                </div>
                <Separator className="my-3" />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    className="gap-2"
                    style={{ backgroundColor: 'var(--color-brand)', color: 'var(--color-ink)' }}
                    onClick={() =>
                      onRequestPatchBundle
                        ? onRequestPatchBundle()
                        : toast.info('Patch bundle UX is next (see ux/AI_CODRAFTER_SPEC.md).')
                    }
                  >
                    Request patch bundle
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => onViewChange?.('scenarios')}>
                    Open scenarios
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
