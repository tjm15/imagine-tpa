import { useEffect, useState, useCallback } from 'react';
import { 
  ChevronLeft,
  FileText,
  Map,
  Scale,
  Camera,
  BarChart3,
  Sparkles,
  AlertCircle,
  Eye,
  Download,
  PanelRightClose,
  PanelRightOpen,
  BookOpen,
  ShieldAlert,
  Bell,
  LayoutGrid,
} from 'lucide-react';
import { WorkspaceMode, ViewMode } from '../App';
import { DocumentView } from './views/DocumentView';
import { StrategyView } from './views/StrategyView';
import { MonitoringView } from './views/MonitoringView';
import { ContextMarginInteractive } from './layout/ContextMarginInteractive';
import { ProcessRail } from './layout/ProcessRail';
import { ReasoningTray } from './ReasoningTray';
import { TraceOverlay } from './modals/TraceOverlay';
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { Separator } from "./ui/separator";
import { useAppState, useAppDispatch } from '../lib/appState';
import { simulateDraft } from '../lib/aiSimulation';
import { toast } from 'sonner';
import type { TraceTarget } from '../lib/trace';
import { Shell } from './Shell';

type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';
type ContextSection = 'evidence' | 'policy' | 'constraints' | 'feed' | 'map';

const ICON_RAIL_WIDTH_PX = 56;
const DEFAULT_LEFT_PANEL_WIDTH_PX = 320;
const DEFAULT_RIGHT_PANEL_WIDTH_PX = 360;
const MIN_PANEL_WIDTH_PX = 280;
const MAX_PANEL_WIDTH_PX = 460;
const MIN_MAIN_CONTENT_WIDTH_PX = 780;
const OVERLAY_BREAKPOINT_PX = 1280;

function clampPanelWidth(px: number) {
  return Math.min(MAX_PANEL_WIDTH_PX, Math.max(MIN_PANEL_WIDTH_PX, Math.round(px)));
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const media = window.matchMedia(query);
    const listener = () => setMatches(media.matches);
    listener();

    if (media.addEventListener) {
      media.addEventListener('change', listener);
      return () => media.removeEventListener('change', listener);
    }
    media.addListener(listener);
    return () => media.removeListener(listener);
  }, [query]);

  return matches;
}

function getStoredNumber(key: string) {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function getStoredBoolean(key: string, fallback: boolean) {
  if (typeof window === 'undefined') return fallback;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw === 'true';
}

function setStoredValue(key: string, value: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, value);
}

function sidebarKey(side: 'left' | 'right', workspace: WorkspaceMode, key: 'open' | 'width') {
  return `tpa.demo_ui.sidebar.${side}.${workspace}.${key}`;
}

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
  const { currentStageId, aiState, reasoningMoves } = useAppState();
  const currentRunId = 'run_8a4f2e';
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);
  const [explainabilityMode, setExplainabilityMode] = useState<ExplainabilityMode>('summary');
  const isOverlay = useMediaQuery(`(max-width: ${OVERLAY_BREAKPOINT_PX - 1}px)`);

  // Persisted per-workspace (desktop) sidebar state
  const [leftPanelWidthPx, setLeftPanelWidthPx] = useState(() => {
    const stored = getStoredNumber(sidebarKey('left', workspace, 'width'));
    return clampPanelWidth(stored ?? DEFAULT_LEFT_PANEL_WIDTH_PX);
  });
  const [rightPanelWidthPx, setRightPanelWidthPx] = useState(() => {
    const stored = getStoredNumber(sidebarKey('right', workspace, 'width'));
    return clampPanelWidth(stored ?? DEFAULT_RIGHT_PANEL_WIDTH_PX);
  });
  const [leftOpenDesktop, setLeftOpenDesktop] = useState(() => getStoredBoolean(sidebarKey('left', workspace, 'open'), true));
  const [rightOpenDesktop, setRightOpenDesktop] = useState(() => getStoredBoolean(sidebarKey('right', workspace, 'open'), true));

  // Session-only open state for overlay mode (prevents surprise full-screen coverage on load)
  const [leftOpenOverlay, setLeftOpenOverlay] = useState(false);
  const [rightOpenOverlay, setRightOpenOverlay] = useState(false);

  const leftPanelOpen = isOverlay ? leftOpenOverlay : leftOpenDesktop;
  const rightPanelOpen = isOverlay ? rightOpenOverlay : rightOpenDesktop;

  const [rightSection, setRightSection] = useState<ContextSection>(() => {
    if (activeView === 'document') return 'policy';
    if (activeView === 'map') return 'constraints';
    if (activeView === 'monitoring') return 'feed';
    return 'evidence';
  });

  useEffect(() => {
    // Workspace-specific persistence
    setLeftPanelWidthPx(clampPanelWidth(getStoredNumber(sidebarKey('left', workspace, 'width')) ?? DEFAULT_LEFT_PANEL_WIDTH_PX));
    setRightPanelWidthPx(clampPanelWidth(getStoredNumber(sidebarKey('right', workspace, 'width')) ?? DEFAULT_RIGHT_PANEL_WIDTH_PX));
    setLeftOpenDesktop(getStoredBoolean(sidebarKey('left', workspace, 'open'), true));
    setRightOpenDesktop(getStoredBoolean(sidebarKey('right', workspace, 'open'), true));
  }, [workspace]);

  useEffect(() => {
    setStoredValue(sidebarKey('left', workspace, 'width'), String(leftPanelWidthPx));
  }, [leftPanelWidthPx, workspace]);

  useEffect(() => {
    setStoredValue(sidebarKey('right', workspace, 'width'), String(rightPanelWidthPx));
  }, [rightPanelWidthPx, workspace]);

  useEffect(() => {
    if (isOverlay) {
      setLeftOpenOverlay(false);
      setRightOpenOverlay(false);
    }
  }, [isOverlay]);

  useEffect(() => {
    // Default right sidebar section per view
    if (activeView === 'studio') setRightSection('policy');
    else if (activeView === 'strategy') setRightSection('constraints');
    else if (activeView === 'monitoring') setRightSection('feed');
    else setRightSection('evidence');
  }, [activeView]);

  useEffect(() => {
    if (!isOverlay) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setLeftOpenOverlay(false);
        setRightOpenOverlay(false);
        setTraceOpen(false);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOverlay]);

  const leftDockWidthPx = (isOverlay ? 0 : leftPanelOpen ? leftPanelWidthPx : 0);
  const rightDockWidthPx = ICON_RAIL_WIDTH_PX + (isOverlay ? 0 : rightPanelOpen ? rightPanelWidthPx : 0);

  const setLeftPanelOpen = useCallback((open: boolean) => {
    if (isOverlay) {
      setLeftOpenOverlay(open);
      return;
    }
    setLeftOpenDesktop(open);
    setStoredValue(sidebarKey('left', workspace, 'open'), String(open));
  }, [isOverlay, workspace]);

  const setRightPanelOpen = useCallback((open: boolean) => {
    if (isOverlay) {
      setRightOpenOverlay(open);
      return;
    }
    setRightOpenDesktop(open);
    setStoredValue(sidebarKey('right', workspace, 'open'), String(open));
  }, [isOverlay, workspace]);

  const enforceMainWidthBudget = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (isOverlay) return;

    const viewportWidth = window.innerWidth;
    const maxSidebarWidth = Math.max(
      MIN_PANEL_WIDTH_PX,
      viewportWidth - ICON_RAIL_WIDTH_PX * 2 - MIN_MAIN_CONTENT_WIDTH_PX,
    );

    setLeftPanelWidthPx((current) => {
      const next = clampPanelWidth(Math.min(current, maxSidebarWidth));
      return next === current ? current : next;
    });

    setRightPanelWidthPx((current) => {
      const next = clampPanelWidth(Math.min(current, maxSidebarWidth));
      return next === current ? current : next;
    });

    let availableWidth = viewportWidth - ICON_RAIL_WIDTH_PX * 2;
    if (leftPanelOpen) availableWidth -= Math.min(leftPanelWidthPx, maxSidebarWidth);
    if (rightPanelOpen) availableWidth -= Math.min(rightPanelWidthPx, maxSidebarWidth);

    if (availableWidth >= MIN_MAIN_CONTENT_WIDTH_PX) return;

    // Prefer to collapse the right panel first to keep the process rail visible.
    if (rightPanelOpen && availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setRightPanelOpen(false);
      availableWidth += rightPanelWidthPx;
    }

    if (leftPanelOpen && availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setLeftPanelOpen(false);
    }
  }, [isOverlay, leftPanelOpen, rightPanelOpen, leftPanelWidthPx, rightPanelWidthPx, setLeftPanelOpen, setRightPanelOpen]);

  useEffect(() => {
    enforceMainWidthBudget();
    if (isOverlay) return;

    window.addEventListener('resize', enforceMainWidthBudget);
    return () => window.removeEventListener('resize', enforceMainWidthBudget);
  }, [enforceMainWidthBudget, isOverlay]);

  const startResizeLeft = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = leftPanelWidthPx;

    const onMove = (e: PointerEvent) => {
      const next = clampPanelWidth(startWidth + (e.clientX - startX));
      setLeftPanelWidthPx(next);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [leftPanelWidthPx]);

  const startResizeRight = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = rightPanelWidthPx;

    const onMove = (e: PointerEvent) => {
      const next = clampPanelWidth(startWidth + (startX - e.clientX));
      setRightPanelWidthPx(next);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [rightPanelWidthPx]);

  const openTrace = useCallback((target?: TraceTarget) => {
    setTraceTarget(target ?? { kind: 'run', label: 'Current run' });
    setTraceOpen(true);
  }, []);

  const handleDraftClick = useCallback(async () => {
    dispatch({ type: 'START_AI_GENERATION', payload: { task: 'draft' } });
    toast.info('Generating AI draft...');
    
    await simulateDraft(
      currentStageId,
      (text, progress) => {
        dispatch({ type: 'UPDATE_AI_STREAM', payload: { text, progress } });
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

  // Determine if the current view should be full-bleed (no sidebars)
  const isFullBleedView = workspace === 'plan' && activeView === 'strategy';

  const viewConfig = workspace === 'monitoring'
    ? {
        monitoring: {
          icon: BarChart3,
          label: 'Monitoring',
          component: MonitoringView,
          description: 'Plan monitoring dashboard',
        },
      }
    : {
        studio: {
          icon: FileText,
          label: workspace === 'plan' ? 'Studio' : 'Report',
          component: DocumentView,
          description: workspace === 'plan' 
            ? 'Document workspace with embedded figures and evidence' 
            : 'Officer report drafting with inline citations',
        },
        strategy: {
          icon: Map,
          label: workspace === 'plan' ? 'Strategy' : 'Assessment',
          component: StrategyView,
          description: workspace === 'plan' 
            ? 'Spatial strategy modelling with scenario comparison' 
            : 'Site assessment with spatial context and visual evidence',
          fullBleed: workspace === 'plan', // Strategy view takes full width in plan mode
        },
      };

  const resolvedView: ViewMode = Object.prototype.hasOwnProperty.call(viewConfig, activeView)
    ? activeView
    : (Object.keys(viewConfig)[0] as ViewMode);

  const ActiveViewComponent = (viewConfig as Record<string, any>)[resolvedView].component;

  const railExtra = (
    <>
      {/* View navigation */}
      {(Object.entries(viewConfig) as [ViewMode, any][]).map(([key, config]) => {
        const Icon = config.icon;
        const isActive = activeView === key;
        return (
          <TooltipProvider key={key}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  className={`h-10 w-10 rounded-md flex items-center justify-center transition-colors ${
                    isActive ? 'bg-white shadow-sm border' : 'hover:bg-slate-100'
                  }`}
                  style={{ borderColor: isActive ? 'var(--color-neutral-300)' : 'transparent' }}
                  aria-label={config.label}
                  onClick={() => onViewChange(key)}
                >
                  <Icon className="w-5 h-5" style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-text)' }} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">{config.label}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      })}
    </>
  );

  return (
    <Shell 
      activeMode={workspace} 
      onNavigate={onWorkspaceChange} 
      variant="project"
      railExtra={railExtra}
      onToggleSidebar={() => setLeftPanelOpen(!leftPanelOpen)}
      isSidebarOpen={leftPanelOpen}
    >
      <div className="h-full min-h-0 flex flex-col overflow-hidden font-sans" style={{ 
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text)'
      }}>
        {/* Top Header - Global Navigation */}
        <header className="bg-white border-b flex-shrink-0 sticky top-0 z-50 shadow-sm" style={{ borderColor: 'var(--color-neutral-300)' }}>
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
                <div className="flex flex-col">
                  <span className="text-sm font-semibold leading-none" style={{ color: 'var(--color-ink)' }}>
                    {workspace === 'plan' ? 'Plan Studio' : workspace === 'casework' ? 'Casework' : 'Monitoring'}
                  </span>
                  <div className="flex items-center gap-1.5 text-xs mt-0.5" style={{ color: 'var(--color-text)' }}>
                      <span>Cambridge City Council</span>
                      <span style={{ color: 'var(--color-neutral-400)' }}>/</span>
                      <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                          {workspace === 'casework' ? '24/0456/FUL' : 'Local Plan 2025'}
                      </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Center: Workspace Switcher - REMOVED (Moved to Shell sidebar) */}
            <div className="hidden" />

            {/* Right: Actions & User */}
            <div className="flex items-center gap-3">
              <div className="hidden lg:flex items-center gap-2 mr-2">
                  <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border" style={{
                    backgroundColor: 'rgba(245, 195, 21, 0.1)',
                    color: 'var(--color-brand-dark)',
                    borderColor: 'rgba(245, 195, 21, 0.3)'
                  }}>
                      <AlertCircle className="w-3.5 h-3.5" />
                      <span>{workspace === 'casework' ? '12 days left' : 'Stage: Baseline'}</span>
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
                      onClick={() => {
                        if (traceOpen) {
                          setTraceOpen(false);
                          return;
                        }
                        openTrace({ kind: 'run', label: 'Current run' });
                      }}
                      className="flex items-center gap-1.5 hover:underline transition-colors"
                      style={{
                        color: traceOpen ? 'var(--color-accent)' : 'var(--color-text)',
                        fontWeight: traceOpen ? 500 : 400
                      }}
                  >
                      <Eye className="w-3.5 h-3.5" />
                      {traceOpen ? 'Hide Trace' : 'Show Trace'}
                  </button>
              </div>

              <div className="flex items-center gap-4">
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

                  {/* 8-move breadcrumb to satisfy wayfinding */}
                  <div className="hidden md:flex items-center gap-1 pl-3 border-l" style={{ borderColor: 'var(--color-neutral-300)' }}>
                    {(
                      ['framing','issues','evidence','interpretation','considerations','balance','negotiation','positioning'] as const
                    ).map((move) => {
                      const status = reasoningMoves[move];
                      const bg = status === 'complete' ? 'bg-emerald-500' : status === 'in-progress' ? 'bg-amber-400' : 'bg-slate-200';
                      return <span key={move} className={`w-2.5 h-2.5 rounded-full ${bg}`} title={`${move} · ${status}`} />;
                    })}
                  </div>
              </div>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex-1 flex overflow-hidden relative" style={{ backgroundColor: 'var(--color-surface-light)' }}>
          {/* Overlay backdrop (session-only) */}
          {!isFullBleedView && isOverlay && (leftPanelOpen || rightPanelOpen) && (
            <button
              className="absolute inset-0 bg-black/30 z-20"
              aria-label="Close side panels"
              onClick={() => {
                setLeftPanelOpen(false);
                setRightPanelOpen(false);
              }}
            />
          )}

          {/* Left Sidebar (panel only - rail is in Shell) - Hidden in full-bleed views */}
          {!isFullBleedView && (
            <div
              className="relative flex-shrink-0 h-full bg-white border-r z-30"
              style={{ borderColor: 'var(--color-neutral-300)', width: leftDockWidthPx }}
            >
              <div className="h-full flex">
                {/* Docked Panel */}
                {!isOverlay && leftPanelOpen && (
                  <div className="h-full bg-white overflow-hidden relative" style={{ width: leftPanelWidthPx }}>
                    <ProcessRail onStageSelect={handleStageSelect} />
                    <div
                      role="separator"
                      aria-orientation="vertical"
                      onPointerDown={startResizeLeft}
                      className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
                      style={{ backgroundColor: 'transparent' }}
                    />
                  </div>
                )}
              </div>

              {/* Overlay Panel */}
              {isOverlay && leftPanelOpen && (
                <div
                  className="absolute top-0 bottom-0 left-0 bg-white shadow-xl z-40 overflow-hidden border-r"
                  style={{ width: leftPanelWidthPx, borderColor: 'var(--color-neutral-300)' }}
                >
                  <ProcessRail onStageSelect={handleStageSelect} />
                  <div
                    role="separator"
                    aria-orientation="vertical"
                    onPointerDown={startResizeLeft}
                    className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
                    style={{ backgroundColor: 'transparent' }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Main Workspace */}
          <div className="flex-1 flex overflow-hidden relative min-h-0">
            {/* Main View */}
            <div className="flex-1 overflow-hidden flex flex-col relative min-h-0">
              <div className="flex-1 overflow-auto min-h-0">
                <div className="h-full w-full">
                  <ActiveViewComponent
                    workspace={workspace}
                    explainabilityMode={explainabilityMode}
                    onOpenTrace={openTrace}
                    onToggleMap={() => {
                      setRightSection('map');
                      setRightPanelOpen(true);
                    }}
                  />
                </div>
              </div>

              {/* Reasoning Tray - Hidden in full-bleed views */}
              {!isFullBleedView && (
                <div className="sticky bottom-0 z-40">
                  <ReasoningTray runId={currentRunId || 'run_8a4f2e'} onOpenTrace={openTrace} />
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar (panel + icon rail) - Hidden in full-bleed views */}
          {!isFullBleedView && (
            <div
              className="relative flex-shrink-0 h-full bg-white border-l z-30"
              style={{ borderColor: 'var(--color-neutral-300)', width: rightDockWidthPx }}
            >
            <div className="h-full flex flex-row-reverse">
              {/* Icon Rail */}
              <div
                className="h-full flex flex-col items-center py-2 px-1 gap-1 border-l"
                style={{ width: ICON_RAIL_WIDTH_PX, borderColor: 'var(--color-neutral-300)' }}
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        className="h-10 w-10 rounded-md flex items-center justify-center hover:bg-slate-100 transition-colors"
                        aria-label={rightPanelOpen ? 'Collapse right panel' : 'Expand right panel'}
                        onClick={() => setRightPanelOpen(!rightPanelOpen)}
                      >
                        {rightPanelOpen ? (
                          <PanelRightClose className="w-5 h-5" style={{ color: 'var(--color-text)' }} />
                        ) : (
                          <PanelRightOpen className="w-5 h-5" style={{ color: 'var(--color-text)' }} />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="left">{rightPanelOpen ? 'Collapse' : 'Expand'}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                <div className="w-8 h-px my-2" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

                {(
                  [
                    { id: 'evidence' as const, label: 'Evidence', icon: FileText },
                    { id: 'policy' as const, label: 'Policy', icon: BookOpen },
                    { id: 'constraints' as const, label: 'Constraints', icon: ShieldAlert },
                    { id: 'feed' as const, label: 'Feed', icon: Bell },
                    { id: 'map' as const, label: 'Map', icon: Map },
                  ] satisfies { id: ContextSection; label: string; icon: typeof FileText }[]
                ).map((item) => {
                  const Icon = item.icon;
                  const isActive = rightSection === item.id;
                  return (
                    <TooltipProvider key={item.id}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            className={`h-10 w-10 rounded-md flex items-center justify-center transition-colors ${
                              isActive ? 'bg-white shadow-sm border' : 'hover:bg-slate-100'
                            }`}
                            style={{ borderColor: isActive ? 'var(--color-neutral-300)' : 'transparent' }}
                            aria-label={item.label}
                            onClick={() => {
                              setRightSection(item.id);
                              setRightPanelOpen(true);
                            }}
                          >
                            <Icon className="w-5 h-5" style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-text)' }} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="left">{item.label}</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  );
                })}
              </div>

              {/* Docked Panel */}
              {!isOverlay && rightPanelOpen && (
                <div className="h-full bg-white overflow-hidden relative" style={{ width: rightPanelWidthPx }}>
                  <ContextMarginInteractive
                    section={rightSection}
                    explainabilityMode={explainabilityMode}
                    workspace={workspace}
                    onOpenTrace={openTrace}
                  />
                  <div
                    role="separator"
                    aria-orientation="vertical"
                    onPointerDown={startResizeRight}
                    className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize"
                    style={{ backgroundColor: 'transparent' }}
                  />
                </div>
              )}
            </div>

            {/* Overlay Panel */}
            {isOverlay && rightPanelOpen && (
              <div
                className="absolute top-0 bottom-0 right-[56px] bg-white shadow-xl z-40 overflow-hidden border-l"
                style={{ width: rightPanelWidthPx, borderColor: 'var(--color-neutral-300)' }}
              >
                <ContextMarginInteractive
                  section={rightSection}
                  explainabilityMode={explainabilityMode}
                  workspace={workspace}
                  onOpenTrace={openTrace}
                />
                <div
                  role="separator"
                  aria-orientation="vertical"
                  onPointerDown={startResizeRight}
                  className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize"
                  style={{ backgroundColor: 'transparent' }}
                />
              </div>
            )}
          </div>
          )}
        </div>

        <TraceOverlay
          open={traceOpen}
          mode={explainabilityMode}
          runId="run_8a4f2e"
          target={traceTarget}
          onClose={() => setTraceOpen(false)}
          onRequestModeChange={(next) => setExplainabilityMode(next)}
        />
      </div>
    </Shell>
  );
}
