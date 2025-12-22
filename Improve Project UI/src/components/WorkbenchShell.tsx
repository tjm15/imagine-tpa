import { useState, useCallback } from 'react';
import { 
  LayoutGrid, ChevronLeft, FileText, Map, Scale, Camera, 
  Sparkles, AlertCircle, Eye, Download, Play, Menu, Bell, ChevronDown, 
  Search, Settings, Share2, PanelRightOpen, PanelRightClose, ArrowRight
} from 'lucide-react';
import { WorkspaceMode, ViewMode } from '../App';
import { DocumentView } from './views/DocumentView';
import { MapView } from './views/MapView';
import { JudgementView } from './views/JudgementView';
import { RealityView } from './views/RealityView';
import { ContextMarginInteractive } from './layout/ContextMarginInteractive';
import { ProcessRail } from './layout/ProcessRail';
import { ReasoningTrayInteractive } from './ReasoningTrayInteractive';
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { Separator } from "./ui/separator";
import { Logo } from "./Logo";
import { useAppState, useAppDispatch } from '../lib/appState';
import { simulateDraft } from '../lib/aiSimulation';
import { toast } from 'sonner';

interface WorkbenchShellProps {
  workspace: WorkspaceMode;
  activeView: ViewMode;
  onViewChange: (view: ViewMode) => void;
  onWorkspaceChange: (mode: WorkspaceMode) => void;
  onBackToHome: () => void;
  projectId: string;
}

export function WorkbenchShell({
  workspace,
  activeView,
  onViewChange,
  onWorkspaceChange,
  onBackToHome,
}: WorkbenchShellProps) {
  const dispatch = useAppDispatch();
  const { currentStageId, aiState } = useAppState();
  const [showTraceCanvas, setShowTraceCanvas] = useState(false);
  const [explainabilityMode, setExplainabilityMode] = useState<'summary' | 'inspect' | 'forensic'>('summary');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleDraftClick = useCallback(async () => {
    dispatch({ type: 'START_AI_GENERATION', payload: { task: 'draft' } });
    toast.info('Generating AI draft...');
    
    await simulateDraft(
      currentStageId,
      (chunk) => {
        dispatch({ type: 'UPDATE_AI_STREAM', payload: { text: chunk } });
      },
      () => {
        dispatch({ type: 'COMPLETE_AI_GENERATION' });
        toast.success('Draft generated! Check the document view.');
      }
    );
  }, [dispatch, currentStageId]);

  const handleExportClick = useCallback(() => {
    dispatch({ type: 'OPEN_MODAL', payload: { modalId: 'export', data: {} } });
  }, [dispatch]);

  const handleStageSelect = useCallback((stageId: string) => {
    dispatch({ type: 'SET_STAGE', payload: { stageId } });
  }, [dispatch]);

  const viewConfig = {
    document: { 
      icon: FileText, 
      label: workspace === 'plan' ? 'Deliverable' : 'Officer Report',
      component: DocumentView,
      description: "Draft and edit the primary document"
    },
    map: { 
      icon: Map, 
      label: workspace === 'plan' ? 'Map & Plans' : 'Site & Plans',
      component: MapView,
      description: "Geospatial context and constraints"
    },
    judgement: { 
      icon: Scale, 
      label: workspace === 'plan' ? 'Scenarios' : 'Balance',
      component: JudgementView,
      description: "Weighing evidence and policy"
    },
    reality: { 
      icon: Camera, 
      label: workspace === 'plan' ? 'Visuals' : 'Photos',
      component: RealityView,
      description: "Site photos and 3D visualisations"
    },
  };

  const ActiveViewComponent = viewConfig[activeView].component;

  type ExplainabilityMode = typeof explainabilityMode;

  return (
    <div className="h-screen flex flex-col overflow-hidden font-sans" style={{ 
      backgroundColor: 'var(--color-surface)',
      color: 'var(--color-text)'
    }}>
      {/* Top Header - Global Navigation */}
      <header className="bg-white border-b flex-shrink-0 z-20 shadow-sm relative" style={{ borderColor: 'var(--color-neutral-300)' }}>
        <div className="flex items-center justify-between h-14 px-4">
          {/* Left: Branding & Navigation */}
          <div className="flex items-center gap-4">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={onBackToHome}
              className="hover:bg-white/50"
              style={{ color: 'var(--color-text)' }}
            >
              <ChevronLeft className="w-5 h-5" />
            </Button>
            
            <div className="flex items-center gap-3">
              <Logo className="w-9 h-8" />
              <div className="flex flex-col">
                <span className="text-sm font-semibold leading-none" style={{ color: 'var(--color-ink)' }}>
                  {workspace === 'plan' ? 'Plan Studio' : 'Casework'}
                </span>
                <div className="flex items-center gap-1.5 text-xs mt-0.5" style={{ color: 'var(--color-text)' }}>
                    <span>Cambridge City Council</span>
                    <span style={{ color: 'var(--color-neutral-400)' }}>/</span>
                    <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                        {workspace === 'plan' ? 'Local Plan 2025' : '24/0456/FUL'}
                    </span>
                </div>
              </div>
            </div>

            <div className="h-6 w-px mx-2" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

            {/* Context Switcher Button */}
             <Button
                variant="ghost"
                size="sm"
                onClick={() => onWorkspaceChange(workspace === 'plan' ? 'casework' : 'plan')}
                className="text-xs gap-1 hidden md:flex"
                style={{ color: 'var(--color-text)' }}
            >
                Switch Workspace <Share2 className="w-3 h-3 ml-1" />
            </Button>
          </div>

          {/* Center: View Tabs */}
          <div className="absolute left-1/2 transform -translate-x-1/2 hidden md:flex p-1 rounded-lg border" style={{
            backgroundColor: 'var(--color-surface)',
            borderColor: 'var(--color-neutral-300)'
          }}>
            {(Object.entries(viewConfig) as [ViewMode, typeof viewConfig[ViewMode]][]).map(([key, config]) => {
              const Icon = config.icon;
              const isActive = activeView === key;
              return (
                <button
                  key={key}
                  onClick={() => onViewChange(key)}
                  className={`
                    flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200
                  `}
                  style={{
                    backgroundColor: isActive ? 'white' : 'transparent',
                    color: isActive ? 'var(--color-ink)' : 'var(--color-text)',
                    boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
                  }}
                >
                  <Icon className="w-4 h-4" style={{ 
                    color: isActive ? 'var(--color-accent)' : 'var(--color-text-light)' 
                  }} />
                  <span>{config.label}</span>
                </button>
              );
            })}
          </div>

          {/* Right: Actions & User */}
          <div className="flex items-center gap-3">
             <div className="hidden lg:flex items-center gap-2 mr-2">
                <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border" style={{
                  backgroundColor: 'rgba(245, 195, 21, 0.1)',
                  color: 'var(--color-brand-dark)',
                  borderColor: 'rgba(245, 195, 21, 0.3)'
                }}>
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>{workspace === 'plan' ? 'Stage: Baseline' : '12 days left'}</span>
                </div>
             </div>

            <div className="flex items-center gap-2">
                <TooltipProvider>
                    <Tooltip>
                        <TooltipTrigger asChild>
                             <Button 
                               size="sm" 
                               variant="default" 
                               className="shadow-sm gap-2" 
                               style={{
                                 backgroundColor: 'var(--color-brand)',
                                 color: 'var(--color-ink)'
                               }}
                               onClick={handleDraftClick}
                               disabled={aiState.isGenerating}
                             >
                                <Sparkles className={`w-4 h-4 ${aiState.isGenerating ? 'animate-spin' : ''}`} />
                                <span className="hidden sm:inline">{aiState.isGenerating ? 'Generating...' : 'Draft'}</span>
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>Generate content with AI</TooltipContent>
                    </Tooltip>
                </TooltipProvider>

                <Button 
                  size="sm" 
                  variant="outline" 
                  className="hidden sm:flex border gap-2" 
                  style={{
                    borderColor: 'var(--color-neutral-300)',
                    color: 'var(--color-text)'
                  }}
                  onClick={handleExportClick}
                >
                    <Download className="w-4 h-4" />
                    Export
                </Button>
            </div>
            
            <Separator orientation="vertical" className="h-6 mx-1" style={{ backgroundColor: 'var(--color-neutral-300)' }} />
            
            <Avatar className="w-8 h-8 border cursor-pointer" style={{ borderColor: 'var(--color-neutral-300)' }}>
                <AvatarImage src="https://github.com/shadcn.png" />
                <AvatarFallback>SM</AvatarFallback>
            </Avatar>
          </div>
        </div>
        
        {/* Sub-header / Audit Bar */}
        <div className="border-b px-4 py-1.5 flex items-center justify-between text-xs" style={{
          backgroundColor: 'var(--color-surface-light)',
          borderColor: 'var(--color-neutral-300)'
        }}>
            <div className="flex items-center gap-4">
                 <div className="flex items-center gap-1.5" style={{ color: 'var(--color-text)' }}>
                    <span>Current Run:</span>
                    <Badge variant="outline" className="font-mono text-[10px] h-5 px-1.5 bg-white" style={{
                      borderColor: 'var(--color-neutral-300)',
                      color: 'var(--color-text)'
                    }}>run_8a4f2e</Badge>
                </div>
                <button 
                    onClick={() => setShowTraceCanvas(!showTraceCanvas)}
                    className="flex items-center gap-1.5 hover:underline transition-colors"
                    style={{ 
                      color: showTraceCanvas ? 'var(--color-accent)' : 'var(--color-text)',
                      fontWeight: showTraceCanvas ? 500 : 400
                    }}
                >
                    <Eye className="w-3.5 h-3.5" />
                    {showTraceCanvas ? 'Hide Trace Canvas' : 'Show Trace Canvas'}
                </button>
            </div>

            <div className="flex items-center gap-3">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="flex items-center gap-1" style={{ color: 'var(--color-text)' }}>
                        <Eye className="w-3.5 h-3.5" />
                        Detail:
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-xs text-xs">
                      <p className="font-medium mb-1">Explainability Levels</p>
                      <p><strong>Summary:</strong> Clean narrative view for reports</p>
                      <p><strong>Inspect:</strong> See evidence sources & assumptions</p>
                      <p><strong>Forensic:</strong> Full audit trail with tool runs</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <div className="flex p-0.5 rounded-md" style={{ backgroundColor: 'var(--color-neutral-300)' }}>
                    {([
                      { id: 'summary' as const, label: 'Summary', icon: '📄' },
                      { id: 'inspect' as const, label: 'Inspect', icon: '🔍' },
                      { id: 'forensic' as const, label: 'Forensic', icon: '🔬' }
                    ]).map((mode) => (
                        <button
                            key={mode.id}
                            onClick={() => setExplainabilityMode(mode.id)}
                            className="px-2.5 py-1 rounded text-[11px] font-medium transition-all flex items-center gap-1"
                            style={{
                              backgroundColor: explainabilityMode === mode.id ? 'white' : 'transparent',
                              color: explainabilityMode === mode.id ? 'var(--color-accent)' : 'var(--color-text)',
                              boxShadow: explainabilityMode === mode.id ? '0 1px 2px rgba(0,0,0,0.08)' : 'none'
                            }}
                        >
                            <span>{mode.icon}</span>
                            <span>{mode.label}</span>
                        </button>
                    ))}
                </div>
            </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Process Rail (Left Sidebar) */}
        <div className="hidden lg:block border-r bg-white z-10 w-64 flex-shrink-0" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <ProcessRail onStageSelect={handleStageSelect} />
        </div>

        {/* Main Workspace */}
        <div className="flex-1 flex overflow-hidden" style={{ backgroundColor: 'var(--color-surface-light)' }}>
          {/* Main View */}
          <div className="flex-1 overflow-hidden flex flex-col relative">
            
            {/* Trace Canvas Overlay */}
            {showTraceCanvas && (
              <div className="border-b backdrop-blur-sm p-4 animate-in slide-in-from-top-4 duration-200 z-10 absolute top-0 left-0 right-0 shadow-sm" style={{
                backgroundColor: 'rgba(50, 156, 133, 0.08)',
                borderColor: 'var(--color-accent)'
              }}>
                <div className="flex items-start gap-4 max-w-5xl mx-auto">
                  <div className="p-2 rounded-full mt-1" style={{ backgroundColor: 'var(--color-accent-light)' }}>
                     <Play className="w-4 h-4" style={{ color: 'var(--color-accent-dark)' }} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>Reasoning Trace Canvas</h4>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowTraceCanvas(false)} style={{ color: 'var(--color-accent)' }}>
                            <span className="sr-only">Close</span>
                            <span aria-hidden="true">×</span>
                        </Button>
                    </div>
                    
                    <div className="flex items-center gap-2 text-xs overflow-x-auto pb-2 scrollbar-hide">
                      <div className="flex-shrink-0 px-3 py-1.5 bg-white rounded border shadow-sm" style={{
                        borderColor: 'var(--color-accent)',
                        color: 'var(--color-ink)'
                      }}>1. Framing</div>
                      <ArrowRight className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />
                      <div className="flex-shrink-0 px-3 py-1.5 bg-white rounded border shadow-sm" style={{
                        borderColor: 'var(--color-accent)',
                        color: 'var(--color-ink)'
                      }}>2. Issue Surfacing</div>
                      <ArrowRight className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />
                      <div className="flex-shrink-0 px-3 py-1.5 bg-white rounded border shadow-sm" style={{
                        borderColor: 'var(--color-accent)',
                        color: 'var(--color-ink)'
                      }}>3. Evidence Curation</div>
                      <ArrowRight className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />
                      <div className="flex-shrink-0 px-3 py-1.5 text-white rounded shadow-md ring-2 ring-offset-1" style={{
                        backgroundColor: 'var(--color-accent)',
                        ringColor: 'var(--color-accent-light)'
                      }}>4. Interpretation</div>
                    </div>
                    <p className="text-xs mt-2" style={{ color: 'var(--color-text)' }}>
                      Click any element below to reveal upstream evidence and tool runs that support it.
                    </p>
                  </div>
                </div>
              </div>
            )}
            
            <div className={`flex-1 overflow-auto transition-all duration-300 ${showTraceCanvas ? 'pt-[140px]' : ''}`}>
               <div className="h-full w-full">
                 <ActiveViewComponent workspace={workspace} explainabilityMode={explainabilityMode} />
               </div>
            </div>
            
            {/* Reasoning Tray */}
            <ReasoningTrayInteractive 
              runId="run_8a4f2e"
              onOpenTrace={() => setShowTraceCanvas(true)}
            />
          </div>

          {/* Context Margin (Right Sidebar) */}
          <div 
            className={`
                border-l bg-white transition-all duration-300 ease-in-out flex flex-col
                ${sidebarOpen ? 'w-[350px] translate-x-0' : 'w-0 translate-x-full opacity-0 overflow-hidden border-l-0'}
            `}
            style={{ borderColor: 'var(--color-neutral-300)' }}
          >
            <ContextMarginInteractive />
          </div>
        </div>

        {/* Sidebar Toggle Button */}
        <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className={`
                absolute right-0 top-1/2 transform -translate-y-1/2 z-20 
                bg-white border shadow-md p-1.5 rounded-l-md 
                hover:bg-white/80 transition-all
                ${sidebarOpen ? 'right-[350px]' : 'right-0'}
            `}
            style={{ 
              borderColor: 'var(--color-neutral-300)',
              color: 'var(--color-text)'
            }}
        >
            {sidebarOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}