/**
 * Interactive Process Rail for CULP Stages
 * 
 * Features:
 * - Visual timeline of CULP stages
 * - Click to navigate between stages
 * - Progress indicators and status badges
 * - Gateway checkpoint visualization
 * - Stage-specific deliverables
 */

import { useState, useCallback } from 'react';
import { 
  CheckCircle2, Circle, Clock, AlertTriangle, ChevronRight, 
  ChevronDown, FileText, Map, Users, Scale, PenTool, Send, 
  Eye, Loader2, Lock, Unlock, Play, Pause, RotateCcw
} from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { culpStageConfigs } from '../../fixtures/extendedMockData';
import { simulateGatewayCheck, GatewayCheckResult } from '../../lib/aiSimulation';
import { toast } from 'sonner';

interface ProcessRailProps {
  onStageSelect?: (stageId: string) => void;
}

type StageStatus = 'completed' | 'in-progress' | 'pending' | 'blocked';

interface StageProgress {
  id: string;
  status: StageStatus;
  completedDeliverables: string[];
  warnings: string[];
}

// Stage icons mapping
const stageIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  baseline: FileText,
  vision: Eye,
  'options-testing': Scale,
  'sites': Map,
  'gateway-1': Lock,
  'draft-policies': PenTool,
  'consultation-reg18': Users,
  'gateway-2': Lock,
  'submission': Send,
};

// Phase definitions
const phases = [
  {
    id: 'getting-ready',
    name: 'Getting Ready',
    stages: ['baseline', 'vision'],
    color: 'bg-blue-500',
  },
  {
    id: 'preparation',
    name: 'Preparation',
    stages: ['options-testing', 'sites', 'gateway-1'],
    color: 'bg-amber-500',
  },
  {
    id: 'submission',
    name: 'Submission',
    stages: ['draft-policies', 'consultation-reg18', 'gateway-2', 'submission'],
    color: 'bg-green-500',
  },
];

export function ProcessRail({ onStageSelect }: ProcessRailProps) {
  const { currentStageId, reasoningMoves } = useAppState();
  const dispatch = useAppDispatch();
  
  const [expandedPhases, setExpandedPhases] = useState<string[]>(['getting-ready', 'preparation']);
  const [stageProgress, setStageProgress] = useState<StageProgress[]>(
    culpStageConfigs.map((config, index) => ({
      id: config.id,
      status: index === 0 ? 'in-progress' : index < 2 ? 'completed' : 'pending',
      completedDeliverables: index < 2 ? ['all'] : [],
      warnings: config.id === 'sites' ? ['3 sites lack sustainability assessment'] : [],
    }))
  );
  const [gatewayCheckInProgress, setGatewayCheckInProgress] = useState(false);
  const [gatewayResult, setGatewayResult] = useState<GatewayCheckResult | null>(null);

  const togglePhase = useCallback((phaseId: string) => {
    setExpandedPhases(prev => 
      prev.includes(phaseId) 
        ? prev.filter(p => p !== phaseId)
        : [...prev, phaseId]
    );
  }, []);

  const handleStageSelect = useCallback((stageId: string) => {
    const progress = stageProgress.find(s => s.id === stageId);
    if (progress?.status === 'blocked') {
      toast.error('Complete previous stages first');
      return;
    }
    
    dispatch({ type: 'SET_STAGE', payload: { stageId } });
    onStageSelect?.(stageId);
    const stage = culpStageConfigs.find(s => s.id === stageId);
    toast.success(`Navigated to ${stage?.name || stageId}`);
  }, [stageProgress, dispatch, onStageSelect]);

  const handleGatewayCheck = useCallback(async (gatewayId: string) => {
    setGatewayCheckInProgress(true);
    setGatewayResult(null);
    
    // Map gateway ID to number
    const gatewayNumber: 1 | 2 | 3 = gatewayId === 'gateway-1' ? 1 : gatewayId === 'gateway-2' ? 2 : 3;
    
    const result = await simulateGatewayCheck(
      gatewayNumber,
      (progress, message) => {
        // Could show progress indicator
        console.log(`${progress}%: ${message}`);
      }
    );
    
    setGatewayResult(result);
    setGatewayCheckInProgress(false);
    
    // Update stage status based on result
    if (result.gaps.length === 0) {
      setStageProgress(prev => prev.map(s => 
        s.id === gatewayId ? { ...s, status: 'completed' } : s
      ));
      toast.success('Gateway check passed!');
    } else {
      toast.warning(`${result.gaps.length} gaps identified`);
    }
  }, []);

  const handleMarkComplete = useCallback((stageId: string) => {
    setStageProgress(prev => prev.map(s => 
      s.id === stageId ? { ...s, status: 'completed' } : s
    ));
    
    // Unlock next stage
    const currentIndex = stageProgress.findIndex(s => s.id === stageId);
    if (currentIndex < stageProgress.length - 1) {
      setStageProgress(prev => prev.map((s, i) => 
        i === currentIndex + 1 ? { ...s, status: 'in-progress' } : s
      ));
    }
    
    toast.success('Stage marked complete');
  }, [stageProgress]);

  const handleReset = useCallback(() => {
    dispatch({ type: 'RESET_DEMO' });
    setStageProgress(
      Object.keys(culpStageConfigs).map((id, index) => ({
        id,
        status: index === 0 ? 'in-progress' : 'pending',
        completedDeliverables: [],
        warnings: [],
      }))
    );
    setGatewayResult(null);
    toast.success('Demo reset');
  }, [dispatch]);

  const getStatusIcon = (status: StageStatus) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />;
      case 'in-progress':
        return <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />;
      case 'pending':
        return <Circle className="w-4 h-4 text-slate-300" />;
      case 'blocked':
        return <Lock className="w-4 h-4 text-slate-400" />;
    }
  };

  const getOverallProgress = () => {
    const completed = stageProgress.filter(s => s.status === 'completed').length;
    return Math.round((completed / stageProgress.length) * 100);
  };

  return (
    <div className="h-full flex flex-col bg-white border-r border-neutral-200 overflow-hidden min-h-0">
      {/* Header */}
      <div className="p-3 border-b border-neutral-200 bg-white sticky top-0 z-10 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold leading-tight">Plan Process</h2>
            <p className="text-[11px] text-slate-500">Planner-first workflow for plan-making</p>
          </div>
          <Badge variant="secondary" className="text-[10px]">Demo</Badge>
        </div>
        
        {/* Overall Progress */}
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-600">Overall</span>
            <span className="font-medium">{getOverallProgress()}%</span>
          </div>
          <Progress value={getOverallProgress()} className="h-1.5" />
        </div>
      </div>

      {/* Phase List */}
      <ScrollArea className="flex-1 min-h-0 pr-1">
        <div className="p-2 space-y-2">
          {phases.map((phase) => {
            const isExpanded = expandedPhases.includes(phase.id);
            const phaseStages = stageProgress.filter(s => phase.stages.includes(s.id));
            const phaseComplete = phaseStages.every(s => s.status === 'completed');
            const phaseInProgress = phaseStages.some(s => s.status === 'in-progress');
            
            return (
              <div key={phase.id} className="bg-slate-50 border border-neutral-200 rounded-lg">
                {/* Phase Header */}
                <button
                  onClick={() => togglePhase(phase.id)}
                  className="w-full flex items-center gap-2 p-2.5 rounded-t-lg hover:bg-white transition-colors"
                >
                  <div className={`w-2 h-2 rounded-full ${phase.color}`} />
                  <span className="text-sm font-medium flex-1 text-left">{phase.name}</span>
                  {phaseComplete && <CheckCircle2 className="w-4 h-4 text-green-600" />}
                  {phaseInProgress && !phaseComplete && <Clock className="w-4 h-4 text-blue-600" />}
                  <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                </button>

                {/* Stage List */}
                {isExpanded && (
                  <div className="mt-1 space-y-1.5 p-2.5 pt-0">
                    {phase.stages.map((stageId) => {
                      const stage = culpStageConfigs.find(s => s.id === stageId);
                      const progress = stageProgress.find(s => s.id === stageId);
                      const isGateway = stageId.startsWith('gateway');
                      const isActive = currentStageId === stageId;
                      const Icon = stageIcons[stageId] || FileText;

                      if (!stage) return null;

                      return (
                        <div key={stageId}>
                          <button
                            onClick={() => handleStageSelect(stageId)}
                            disabled={progress?.status === 'blocked'}
                            className={`w-full flex items-center gap-2.5 p-2.5 rounded-md border transition-colors text-left ${
                              isActive 
                                ? 'bg-white border-blue-200 shadow-sm' 
                                : progress?.status === 'blocked'
                                  ? 'opacity-50 cursor-not-allowed border-dashed'
                                  : 'bg-white hover:border-blue-100'
                            }`}
                          >
                            <div className="flex items-center gap-1.5 w-16 flex-shrink-0">
                              {getStatusIcon(progress?.status || 'pending')}
                              <Icon className="w-4 h-4 text-slate-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-[13px] font-medium leading-tight">{stage.name}</span>
                                {isGateway && <Badge variant="outline" className="text-[9px] flex-shrink-0">Gateway</Badge>}
                                {progress?.status === 'completed' && <Badge variant="secondary" className="text-[9px] flex-shrink-0">Done</Badge>}
                              </div>
                              <p className="text-[11px] text-slate-500 line-clamp-2">{stage.description}</p>
                            </div>
                            <ChevronRight className="w-3 h-3 text-slate-400" />
                          </button>

                          {/* Expanded Stage Details (when active) */}
                          {isActive && (
                            <div className="mt-1.5 mb-2.5 space-y-2 bg-slate-50 rounded-md p-2.5 border border-dashed border-neutral-200">
                              {/* Deliverables */}
                              <div className="text-xs">
                                <span className="font-medium text-slate-600">Deliverables:</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {stage.deliverables.map((d: { id: string; name: string }, i: number) => (
                                    <Badge key={i} variant="outline" className="text-[10px]">{d.name}</Badge>
                                  ))}
                                </div>
                              </div>

                              {/* Warnings */}
                              {progress?.warnings && progress.warnings.length > 0 && (
                                <div className="bg-amber-50 rounded p-2 text-xs">
                                  <div className="flex items-center gap-1 text-amber-700 font-medium mb-1">
                                    <AlertTriangle className="w-3 h-3" />
                                    Attention
                                  </div>
                                  {progress.warnings.map((w: string, i: number) => (
                                    <p key={i} className="text-amber-600">{w}</p>
                                  ))}
                                </div>
                              )}

                              {/* Gateway Check Button */}
                              {isGateway && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleGatewayCheck(stageId)}
                                  disabled={gatewayCheckInProgress}
                                  className="w-full gap-2"
                                >
                                  {gatewayCheckInProgress ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                  ) : (
                                    <Lock className="w-3 h-3" />
                                  )}
                                  Run Gateway Check
                                </Button>
                              )}

                              {/* Mark Complete Button */}
                              {!isGateway && progress?.status === 'in-progress' && (
                                <Button
                                  variant="default"
                                  size="sm"
                                  onClick={() => handleMarkComplete(stageId)}
                                  className="w-full gap-2"
                                >
                                  <CheckCircle2 className="w-3 h-3" />
                                  Mark Complete
                                </Button>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* Gateway Result Panel */}
      {gatewayResult && (
        <div className="border-t border-neutral-200 p-3 bg-slate-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Gateway Check Result</span>
            <button 
              onClick={() => setGatewayResult(null)}
              className="text-xs text-slate-500 hover:text-slate-700"
            >
              Dismiss
            </button>
          </div>
          
          {gatewayResult.gaps.length === 0 ? (
            <div className="flex items-center gap-2 text-green-700 text-sm">
              <CheckCircle2 className="w-4 h-4" />
              All requirements met
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-xs">
                <span className="font-medium text-red-700">Gaps ({gatewayResult.gaps.length}):</span>
                <ul className="mt-1 space-y-1">
                  {gatewayResult.gaps.slice(0, 3).map((gap, i) => (
                    <li key={i} className="text-red-600 flex items-start gap-1">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span>
                        <strong>{gap.area}</strong>: {gap.description}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              {gatewayResult.inspectorQuestions.length > 0 && (
                <div className="text-xs">
                  <span className="font-medium text-amber-700">Inspector may ask:</span>
                  <ul className="mt-1 space-y-1">
                    {gatewayResult.inspectorQuestions.slice(0, 2).map((q, i) => (
                      <li key={i} className="text-amber-600 italic">"{q}"</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-neutral-200 p-3">
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={handleReset}
          className="w-full gap-2 text-slate-600"
        >
          <RotateCcw className="w-4 h-4" />
          Reset Demo
        </Button>
      </div>
    </div>
  );
}
