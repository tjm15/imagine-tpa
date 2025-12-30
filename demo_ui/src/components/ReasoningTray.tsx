import { useState } from 'react';
import { 
  ChevronUp, ChevronDown, Scale, FileText, Lightbulb, 
  CheckCircle, Clock, Circle, AlertTriangle, Sparkles, User,
  ArrowRight, ExternalLink
} from 'lucide-react';
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { 
  mockMoveEvents, 
  mockConsiderations, 
  mockInterpretations,
  mockPolicies,
  type ReasoningMove,
} from '../fixtures/mockData';
import type { TraceTarget } from '../lib/trace';
import { useAppState } from '../lib/appState';

interface ReasoningTrayProps {
  runId: string;
  onOpenTrace?: (target?: TraceTarget) => void;
  onSelectConsideration?: (id: string) => void;
}

const moveLabels: Record<ReasoningMove, { label: string; icon: typeof Scale }> = {
  framing: { label: 'Framing', icon: Lightbulb },
  issues: { label: 'Issues', icon: FileText },
  evidence: { label: 'Evidence', icon: FileText },
  interpretation: { label: 'Interpretation', icon: Lightbulb },
  considerations: { label: 'Considerations', icon: Scale },
  balance: { label: 'Balance', icon: Scale },
  negotiation: { label: 'Negotiation', icon: FileText },
  positioning: { label: 'Positioning', icon: FileText }
};

const moveOrder: ReasoningMove[] = [
  'framing', 'issues', 'evidence', 'interpretation', 
  'considerations', 'balance', 'negotiation', 'positioning'
];

const moveBlurb: Record<ReasoningMove, string> = {
  framing: 'Confirming purpose, scope, and political framing before proceeding.',
  issues: 'Surfacing material issues, constraints, and policy hooks to test.',
  evidence: 'Curating sources, checking gaps, and recording limitations.',
  interpretation: 'Interpreting evidence against tests and plan requirements.',
  considerations: 'Forming the considerations ledger (benefits, harms, conflicts).',
  balance: 'Weighing considerations under the chosen framing to reach a view.',
  negotiation: 'Altering proposals/conditions/obligations to resolve conflicts.',
  positioning: 'Producing the final position and a coherent, challenge-ready narrative.'
};

function deriveCurrentMove(moveStatus: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'>): ReasoningMove {
  return moveOrder.find(m => moveStatus[m] === 'in-progress')
    || [...moveOrder].reverse().find(m => moveStatus[m] === 'complete')
    || 'framing';
}

export function ReasoningTray({ runId, onOpenTrace, onSelectConsideration }: ReasoningTrayProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'progress' | 'ledger' | 'trace'>('progress');

  const { reasoningMoves } = useAppState();
  const moveStatus = reasoningMoves;
  const currentMove = deriveCurrentMove(moveStatus);
  
  const completedCount = Object.values(moveStatus).filter(s => s === 'complete').length;
  const progressPercent = Math.round((completedCount / 8) * 100);

  return (
    <div 
      className="border-t bg-white transition-all duration-300 ease-in-out"
      style={{ borderColor: 'var(--color-neutral-300)' }}
    >
      {/* Collapsed Header (always visible) */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleTrigger asChild>
          <button 
            className="w-full px-4 py-2 flex items-center justify-between hover:bg-slate-50 transition-colors"
          >
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
                <span className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                  Reasoning
                </span>
              </div>
              
              {/* Progress Indicator */}
              <div className="flex items-center gap-1.5">
                {moveOrder.map((move) => {
                  const status = moveStatus[move];
                  return (
                    <div
                      key={move}
                      title={`${moveLabels[move].label}: ${status}`}
                      className={`w-2 h-2 rounded-full transition-colors ${
                        status === 'complete' 
                          ? 'bg-emerald-500' 
                          : status === 'in-progress' 
                            ? 'bg-amber-400 animate-pulse' 
                            : 'bg-slate-200'
                      }`}
                    />
                  );
                })}
              </div>
              
              <span className="text-xs" style={{ color: 'var(--color-text)' }}>
                {progressPercent}% · Currently: <span className="font-medium">{moveLabels[currentMove].label}</span>
              </span>
            </div>
            
            <div className="flex items-center gap-3">
              <Badge 
                variant="outline" 
                className="font-mono text-[10px] bg-white"
                style={{ borderColor: 'var(--color-neutral-300)', color: 'var(--color-text)' }}
              >
                {runId}
              </Badge>
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" style={{ color: 'var(--color-text)' }} />
              ) : (
                <ChevronUp className="w-4 h-4" style={{ color: 'var(--color-text)' }} />
              )}
            </div>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <Separator />
          
          {/* Tab Bar */}
          <div className="flex items-center gap-1 px-4 py-2 border-b" style={{ 
            backgroundColor: 'var(--color-surface-light)',
            borderColor: 'var(--color-neutral-200)'
          }}>
            {[
              { id: 'progress' as const, label: 'Progress' },
              { id: 'ledger' as const, label: 'Considerations Ledger' },
              { id: 'trace' as const, label: 'Trace Summary' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                  activeTab === tab.id 
                    ? 'bg-white shadow-sm' 
                    : 'hover:bg-white/50'
                }`}
                style={{ 
                  color: activeTab === tab.id ? 'var(--color-accent)' : 'var(--color-text)'
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div style={{ height: 260 }}>
            {activeTab === 'progress' && (
              <ReasoningProgress moveStatus={moveStatus} currentMove={currentMove} />
            )}
            {activeTab === 'ledger' && (
              <ConsiderationsLedger onSelect={onSelectConsideration} />
            )}
            {activeTab === 'trace' && (
              <TraceSummary runId={runId} onOpenFull={onOpenTrace} />
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

function ReasoningProgress({
  moveStatus,
  currentMove,
}: {
  moveStatus: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'>;
  currentMove: ReasoningMove;
}) {
  return (
    <ScrollArea className="h-full">
      <div className="p-4">
        <div className="flex items-start gap-2">
          {moveOrder.map((move, idx) => {
            const status = moveStatus[move];
            const { label } = moveLabels[move];
            
            return (
              <div key={move} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div 
                    className={`w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors ${
                      status === 'complete'
                        ? 'bg-emerald-50 border-emerald-500'
                        : status === 'in-progress'
                          ? 'bg-amber-50 border-amber-400'
                          : 'bg-slate-50 border-slate-200'
                    }`}
                  >
                    {status === 'complete' ? (
                      <CheckCircle className="w-4 h-4 text-emerald-600" />
                    ) : status === 'in-progress' ? (
                      <Clock className="w-4 h-4 text-amber-600" />
                    ) : (
                      <Circle className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                  <span 
                    className={`text-[10px] mt-1 text-center leading-tight ${
                      status === 'complete'
                        ? 'text-emerald-700 font-medium'
                        : status === 'in-progress'
                          ? 'text-amber-700 font-medium'
                          : 'text-slate-400'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {idx < moveOrder.length - 1 && (
                  <ArrowRight 
                    className={`w-4 h-4 mx-1 mt-[-12px] ${
                      moveStatus[moveOrder[idx + 1]] !== 'pending' 
                        ? 'text-emerald-400' 
                        : 'text-slate-200'
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
        
        {/* Current Move Detail */}
        <div className="mt-4 p-3 rounded-lg border" style={{ 
          backgroundColor: 'var(--color-surface-light)',
          borderColor: 'var(--color-neutral-200)'
        }}>
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-amber-600" />
            <span className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
              Currently: {moveLabels[currentMove].label}
            </span>
          </div>
          <p className="text-xs" style={{ color: 'var(--color-text)' }}>
            {moveBlurb[currentMove]}
          </p>
          <div className="flex gap-2 mt-3">
            <Button size="sm" variant="outline" className="h-7 text-xs">
              View Detail
            </Button>
            <Button size="sm" className="h-7 text-xs" style={{
              backgroundColor: 'var(--color-accent)',
              color: 'white'
            }}>
              Complete Move
            </Button>
          </div>
        </div>
      </div>
    </ScrollArea>
  );
}

function ConsiderationsLedger({ onSelect }: { onSelect?: (id: string) => void }) {
  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-2">
        {mockConsiderations.map((consideration) => {
          const interpretation = mockInterpretations.find(i => i.id === consideration.interpretationId);
          const policies = consideration.policyIds.map(id => mockPolicies.find(p => p.id === id)).filter(Boolean);
          
          return (
            <div
              key={consideration.id}
              onClick={() => onSelect?.(consideration.id)}
              className={`p-3 rounded-lg border cursor-pointer transition-all hover:shadow-sm ${
                consideration.settled 
                  ? 'border-emerald-200 bg-emerald-50/30' 
                  : 'border-slate-200 hover:border-slate-300'
              } ${
                consideration.tensions?.length 
                  ? 'border-l-2 border-l-amber-400' 
                  : ''
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                    {consideration.issue}
                  </span>
                  {interpretation?.source === 'ai' ? (
                    <span title="AI-generated"><Sparkles className="w-3 h-3 text-blue-500" /></span>
                  ) : (
                    <span title="Human input"><User className="w-3 h-3 text-slate-400" /></span>
                  )}
                </div>
                
                <div className="flex items-center gap-1">
                  {consideration.tensions?.length ? (
                    <Badge variant="outline" className="text-[9px] h-4 px-1 border-amber-300 text-amber-700 bg-amber-50">
                      <AlertTriangle className="w-2.5 h-2.5 mr-0.5" />
                      Tension
                    </Badge>
                  ) : null}
                  <Badge 
                    variant="secondary" 
                    className={`text-[9px] h-4 px-1 ${
                      consideration.direction === 'supports' 
                        ? 'bg-emerald-100 text-emerald-700' 
                        : consideration.direction === 'against'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {consideration.direction === 'supports' ? '+ Supports' : 
                     consideration.direction === 'against' ? '− Against' : '○ Neutral'}
                  </Badge>
                  <Badge variant="outline" className="text-[9px] h-4 px-1 bg-white">
                    {consideration.weight}
                  </Badge>
                </div>
              </div>
              
              <p className="text-xs mb-2 line-clamp-2" style={{ color: 'var(--color-text)' }}>
                {interpretation?.statement}
              </p>
              
              <div className="flex items-center gap-1 flex-wrap">
                {policies.map(policy => (
                  <Badge 
                    key={policy!.id}
                    variant="outline" 
                    className="text-[9px] h-4 px-1 font-mono bg-white cursor-pointer hover:bg-blue-50 hover:border-blue-200"
                  >
                    {policy!.reference}
                  </Badge>
                ))}
              </div>
              
              {consideration.settled && (
                <div className="flex items-center gap-1 mt-2 text-[10px] text-emerald-600">
                  <CheckCircle className="w-3 h-3" />
                  Settled
                </div>
              )}
            </div>
          );
        })}
        
        <Button variant="outline" size="sm" className="w-full text-xs mt-2 border-dashed">
          + Add Consideration
        </Button>
      </div>
    </ScrollArea>
  );
}

function TraceSummary({ runId, onOpenFull }: { runId: string; onOpenFull?: () => void }) {
  const moves = mockMoveEvents.filter(m => m.runId === runId && m.status === 'complete');
  
  return (
    <ScrollArea className="h-full">
      <div className="p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium" style={{ color: 'var(--color-text)' }}>
            Reasoning spine for {runId}
          </span>
          <Button 
            variant="ghost" 
            size="sm" 
            className="h-6 text-[10px] gap-1"
            onClick={onOpenFull}
          >
            Open Full Trace <ExternalLink className="w-3 h-3" />
          </Button>
        </div>
        
        <div className="space-y-2">
          {moves.map((move) => (
            <div 
              key={move.id}
              className="flex items-start gap-2 p-2 rounded border bg-white"
              style={{ borderColor: 'var(--color-neutral-200)' }}
            >
              <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium" style={{ color: 'var(--color-ink)' }}>
                    {moveLabels[move.move].label}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--color-text-light)' }}>
                    {new Date(move.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <p className="text-[10px] mt-0.5" style={{ color: 'var(--color-text)' }}>
                  {(Array.isArray(move.inputIds) ? move.inputIds.length : 0)} inputs → {(Array.isArray(move.outputIds) ? move.outputIds.length : 0)} outputs
                </p>
              </div>
            </div>
          ))}
        </div>
        
        {moves.length === 0 && (
          <div className="text-center py-4">
            <Circle className="w-8 h-8 text-slate-200 mx-auto mb-2" />
            <p className="text-xs" style={{ color: 'var(--color-text)' }}>
              No completed moves yet
            </p>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
