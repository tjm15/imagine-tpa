/**
 * Interactive Reasoning Tray with Drag-Drop
 * 
 * Features:
 * - Progress visualization with clickable moves
 * - Draggable considerations for reordering
 * - AI balance synthesis
 * - Trace auditing
 * - Add consideration modal trigger
 */

import { useState, useCallback, useMemo } from 'react';
import { 
  ChevronUp, ChevronDown, Scale, FileText, Lightbulb, 
  CheckCircle, Clock, Circle, AlertTriangle, Sparkles, User,
  ArrowRight, ExternalLink, Plus, Minus, GripVertical, 
  Loader2, Play, Trash2, Edit2, Eye
} from 'lucide-react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { useAppState, useAppDispatch } from '../lib/appState';
import { toast } from 'sonner';
import { Consideration } from '../fixtures/mockData';

interface ReasoningTrayProps {
  runId: string;
  onOpenTrace?: () => void;
  onSelectConsideration?: (id: string) => void;
}

type ReasoningMove = 'framing' | 'issues' | 'evidence' | 'interpretation' | 'considerations' | 'balance' | 'negotiation' | 'positioning';

// Helper to get unified valence/direction from Consideration
const getValence = (c: Consideration): 'for' | 'against' | 'neutral' => {
  if (c.valence) return c.valence;
  if (c.direction === 'supports') return 'for';
  if (c.direction === 'against') return 'against';
  return 'neutral';
};

// Helper to get title from Consideration
const getTitle = (c: Consideration): string => {
  return c.title || c.issue;
};

const moveLabels: Record<ReasoningMove, { label: string; icon: typeof Scale; description: string }> = {
  framing: { label: 'Framing', icon: Lightbulb, description: 'Establish context and political framing' },
  issues: { label: 'Issues', icon: FileText, description: 'Identify key planning issues' },
  evidence: { label: 'Evidence', icon: FileText, description: 'Curate and review evidence base' },
  interpretation: { label: 'Interpretation', icon: Lightbulb, description: 'Interpret evidence in context' },
  considerations: { label: 'Considerations', icon: Scale, description: 'Form material considerations' },
  balance: { label: 'Balance', icon: Scale, description: 'Weigh considerations' },
  negotiation: { label: 'Negotiation', icon: FileText, description: 'Explore modifications' },
  positioning: { label: 'Positioning', icon: FileText, description: 'Draft recommendation' }
};

const moveOrder: ReasoningMove[] = [
  'framing', 'issues', 'evidence', 'interpretation', 
  'considerations', 'balance', 'negotiation', 'positioning'
];

// Sortable Consideration Card
function SortableConsiderationCard({ 
  consideration, 
  onEdit, 
  onDelete, 
  onView 
}: { 
  consideration: Consideration;
  onEdit: () => void;
  onDelete: () => void;
  onView: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: consideration.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const valence = getValence(consideration);
  
  const getValenceColor = () => {
    switch (valence) {
      case 'for': return 'border-l-green-500 bg-green-50/50';
      case 'against': return 'border-l-red-500 bg-red-50/50';
      default: return 'border-l-slate-400 bg-slate-50/50';
    }
  };

  const getValenceIcon = () => {
    switch (valence) {
      case 'for': return <Plus className="w-3 h-3 text-green-600" />;
      case 'against': return <Minus className="w-3 h-3 text-red-600" />;
      default: return <Scale className="w-3 h-3 text-slate-500" />;
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 p-2 rounded-lg border border-l-4 ${getValenceColor()} ${
        isDragging ? 'shadow-lg ring-2 ring-blue-200' : ''
      }`}
    >
      {/* Drag Handle */}
      <button
        {...attributes}
        {...listeners}
        className="p-1 text-slate-400 hover:text-slate-600 cursor-grab active:cursor-grabbing"
      >
        <GripVertical className="w-4 h-4" />
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {getValenceIcon()}
          <span className="text-sm font-medium truncate">{getTitle(consideration)}</span>
          <Badge variant="outline" className="text-[9px] ml-auto">
            {consideration.weight}
          </Badge>
        </div>
        {(consideration.description || consideration.summary) && (
          <p className="text-xs text-slate-500 truncate mt-0.5">{consideration.description || consideration.summary}</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1">
        <button onClick={onView} className="p-1 text-slate-400 hover:text-blue-600">
          <Eye className="w-3.5 h-3.5" />
        </button>
        <button onClick={onEdit} className="p-1 text-slate-400 hover:text-amber-600">
          <Edit2 className="w-3.5 h-3.5" />
        </button>
        <button onClick={onDelete} className="p-1 text-slate-400 hover:text-red-600">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export function ReasoningTrayInteractive({ runId, onOpenTrace, onSelectConsideration }: ReasoningTrayProps) {
  const { reasoningMoves, considerations, aiState } = useAppState();
  const dispatch = useAppDispatch();
  
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<'progress' | 'ledger' | 'trace'>('ledger');
  const [localConsiderations, setLocalConsiderations] = useState(considerations);

  // Sync with global state
  useState(() => {
    setLocalConsiderations(considerations);
  });

  // Drag sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setLocalConsiderations((items) => {
        const oldIndex = items.findIndex((i) => i.id === active.id);
        const newIndex = items.findIndex((i) => i.id === over.id);
        const newOrder = arrayMove(items, oldIndex, newIndex);
        
        dispatch({ type: 'REORDER_CONSIDERATIONS', payload: { considerations: newOrder } });
        toast.success('Considerations reordered');
        
        return newOrder;
      });
    }
  }, [dispatch]);

  const handleAddConsideration = useCallback(() => {
    dispatch({ type: 'OPEN_MODAL', payload: { modalId: 'consideration-form', data: {} } });
  }, [dispatch]);

  const handleDeleteConsideration = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_CONSIDERATION', payload: { id } });
    setLocalConsiderations(prev => prev.filter(c => c.id !== id));
    toast.success('Consideration removed');
  }, [dispatch]);

  const handleAdvanceMove = useCallback((move: ReasoningMove) => {
    dispatch({ type: 'ADVANCE_MOVE', payload: { move } });
    toast.success(`Advanced to ${moveLabels[move].label}`);
  }, [dispatch]);

  const handleRunBalance = useCallback(() => {
    dispatch({ type: 'OPEN_MODAL', payload: { modalId: 'balance', data: {} } });
  }, [dispatch]);

  // Calculate progress and ledger rollup
  const completedMoves = moveOrder.filter(m => reasoningMoves[m] === 'complete');
  const currentMove = moveOrder.find(m => reasoningMoves[m] === 'in-progress') || 'framing';
  const progressPercent = Math.round((completedMoves.length / 8) * 100);
  const ledgerSummary = useMemo(() => {
    const forCount = localConsiderations.filter(c => getValence(c) === 'for');
    const againstCount = localConsiderations.filter(c => getValence(c) === 'against');
    const neutralCount = localConsiderations.filter(c => getValence(c) === 'neutral');
    const net = localConsiderations.reduce((acc, c) => {
      const weight = Number(c.weight ?? 0) || 0;
      const direction = getValence(c) === 'for' ? 1 : getValence(c) === 'against' ? -1 : 0;
      return acc + weight * direction;
    }, 0);
    return { forCount, againstCount, neutralCount, net };
  }, [localConsiderations]);
  const tensions = useMemo(() => [
    'Housing uplift vs town centre heritage risk',
    'Parking removal tension with disability access',
  ], []);

  return (
    <div className="border-t border-neutral-200 bg-white transition-all duration-300 ease-in-out">
      {/* Collapsed Header */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleTrigger asChild>
          <button className="w-full px-4 py-2 flex items-center justify-between hover:bg-slate-50 transition-colors">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-violet-600" />
                <span className="text-sm font-medium text-slate-800">Reasoning</span>
              </div>
              
              {/* Progress Dots (Clickable) */}
              <div className="flex items-center gap-1.5">
                {moveOrder.map((move) => {
                  const status = reasoningMoves[move] || 'pending';
                  return (
                    <button
                      key={move}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectConsideration?.(move);
                      }}
                      title={`${moveLabels[move].label}: ${status}`}
                      className={`w-2.5 h-2.5 rounded-full transition-all hover:scale-125 ${
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
              
              <span className="text-xs text-slate-500">
                {progressPercent}% · <span className="font-medium">{moveLabels[currentMove].label}</span>
              </span>
            </div>
            
            <div className="flex items-center gap-3">
              {aiState.isGenerating && (
                <span className="flex items-center gap-1 text-xs text-violet-600">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Processing...
                </span>
              )}
              <Badge variant="outline" className="font-mono text-[10px]">
                {runId}
              </Badge>
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-slate-400" />
              ) : (
                <ChevronUp className="w-4 h-4 text-slate-400" />
              )}
            </div>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <Separator />
          {/* Ledger and trace micro-summary */}
          <div className="px-4 py-2 flex flex-wrap items-center gap-3 bg-white">
            <div className="flex items-center gap-2 text-xs">
              <Badge variant="outline" className="text-[10px] text-green-700">For {ledgerSummary.forCount.length}</Badge>
              <Badge variant="outline" className="text-[10px] text-red-700">Against {ledgerSummary.againstCount.length}</Badge>
              <Badge variant="outline" className="text-[10px] text-slate-600">Neutral {ledgerSummary.neutralCount.length}</Badge>
              <span className={`px-2 py-0.5 rounded-full text-[11px] ${ledgerSummary.net >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                Net weight {ledgerSummary.net >= 0 ? '+' : ''}{ledgerSummary.net}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-amber-700">
              <AlertTriangle className="w-3 h-3" />
              {tensions[0]}
            </div>
            <Button variant="ghost" size="sm" className="ml-auto text-xs gap-1" onClick={onOpenTrace}>
              <ExternalLink className="w-3 h-3" />
              Open trace
            </Button>
          </div>
          
          {/* Tab Bar */}
          <div className="flex items-center gap-1 px-4 py-2 border-b border-neutral-200 bg-slate-50">
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
                    ? 'bg-white shadow-sm text-violet-700' 
                    : 'text-slate-600 hover:bg-white/50'
                }`}
              >
                {tab.label}
              </button>
            ))}
            
            <div className="ml-auto">
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handleRunBalance}
                className="gap-1 text-xs"
              >
                <Sparkles className="w-3 h-3" />
                Run Balance
              </Button>
            </div>
          </div>

          {/* Tab Content */}
          <div className="h-56">
            {/* Progress Tab */}
            {activeTab === 'progress' && (
              <ScrollArea className="h-full">
                <div className="p-4 space-y-2">
                  {moveOrder.map((move, index) => {
                    const status = reasoningMoves[move] || 'pending';
                    const Icon = moveLabels[move].icon;
                    const isCurrentOrPast = index <= moveOrder.indexOf(currentMove);
                    
                    return (
                      <div 
                        key={move}
                        className={`flex items-center gap-3 p-2 rounded-lg transition-colors ${
                          status === 'in-progress' ? 'bg-amber-50 ring-1 ring-amber-200' : 
                          status === 'complete' ? 'bg-slate-50' : 'opacity-50'
                        }`}
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
                          status === 'complete' ? 'bg-emerald-100 text-emerald-600' :
                          status === 'in-progress' ? 'bg-amber-100 text-amber-600' :
                          'bg-slate-100 text-slate-400'
                        }`}>
                          {status === 'complete' ? (
                            <CheckCircle className="w-4 h-4" />
                          ) : status === 'in-progress' ? (
                            <Clock className="w-4 h-4" />
                          ) : (
                            <Circle className="w-4 h-4" />
                          )}
                        </div>
                        
                        <div className="flex-1">
                          <div className="text-sm font-medium">{moveLabels[move].label}</div>
                          <div className="text-xs text-slate-500">{moveLabels[move].description}</div>
                        </div>
                        
                        {status === 'in-progress' && (
                          <Button 
                            variant="outline" 
                            size="sm" 
                            onClick={() => handleAdvanceMove(move)}
                            className="text-xs gap-1"
                          >
                            <Play className="w-3 h-3" />
                            Complete
                          </Button>
                        )}
                        
                        {status === 'complete' && (
                          <Badge variant="secondary" className="text-[10px]">Done</Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            )}

            {/* Ledger Tab */}
            {activeTab === 'ledger' && (
              <div className="h-full flex flex-col">
                {/* Header */}
                <div className="px-4 py-2 flex items-center justify-between border-b border-neutral-100">
                  <div className="flex items-center gap-4 text-xs">
                    <span className="text-green-600">
                      <Plus className="w-3 h-3 inline mr-1" />
                      {localConsiderations.filter(c => getValence(c) === 'for').length} For
                    </span>
                    <span className="text-red-600">
                      <Minus className="w-3 h-3 inline mr-1" />
                      {localConsiderations.filter(c => getValence(c) === 'against').length} Against
                    </span>
                    <span className="text-slate-500">
                      <Scale className="w-3 h-3 inline mr-1" />
                      {localConsiderations.filter(c => getValence(c) === 'neutral').length} Neutral
                    </span>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={handleAddConsideration}
                    className="text-xs gap-1"
                  >
                    <Plus className="w-3 h-3" />
                    Add
                  </Button>
                </div>
                
                {/* Draggable List */}
                <ScrollArea className="flex-1">
                  <div className="p-3 space-y-2">
                    <DndContext
                      sensors={sensors}
                      collisionDetection={closestCenter}
                      onDragEnd={handleDragEnd}
                    >
                      <SortableContext
                        items={localConsiderations.map(c => c.id)}
                        strategy={verticalListSortingStrategy}
                      >
                        {localConsiderations.map((consideration) => (
                          <SortableConsiderationCard
                            key={consideration.id}
                            consideration={consideration}
                            onEdit={() => toast.info('Edit modal not implemented in demo')}
                            onDelete={() => handleDeleteConsideration(consideration.id)}
                            onView={() => onSelectConsideration?.(consideration.id)}
                          />
                        ))}
                      </SortableContext>
                    </DndContext>
                    
                    {localConsiderations.length === 0 && (
                      <div className="text-center py-8 text-slate-400">
                        <Scale className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No considerations yet</p>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={handleAddConsideration}
                          className="mt-2"
                        >
                          Add your first consideration
                        </Button>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            )}

            {/* Trace Tab */}
            {activeTab === 'trace' && (
              <ScrollArea className="h-full">
                <div className="p-4 space-y-3">
                  <p className="text-xs text-slate-500 mb-3">
                    Audit trail of AI tool invocations and reasoning steps
                  </p>
                  
                  {/* Sample trace events */}
                  {[
                    { time: '14:32:05', tool: 'policy_retriever', input: 'green belt policy', output: '3 policies found' },
                    { time: '14:32:12', tool: 'site_assessor', input: 'SHLAA/045', output: 'Score: 7.2/10' },
                    { time: '14:32:18', tool: 'constraint_checker', input: 'flood zone query', output: 'Zone 2 partial' },
                    { time: '14:32:25', tool: 'balance_calculator', input: '5 considerations', output: 'Net: +0.3' },
                  ].map((event, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="font-mono text-slate-400 w-16">{event.time}</span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[9px]">{event.tool}</Badge>
                          <ArrowRight className="w-3 h-3 text-slate-300" />
                          <span className="text-slate-700">{event.output}</span>
                        </div>
                        <div className="text-slate-400 mt-0.5">Input: {event.input}</div>
                      </div>
                    </div>
                  ))}
                  
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={onOpenTrace}
                    className="w-full gap-1 text-xs mt-4"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open Full Trace
                  </Button>
                </div>
              </ScrollArea>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
