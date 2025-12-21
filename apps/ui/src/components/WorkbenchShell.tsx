import { useState } from 'react';
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
import { ContextMargin } from './ContextMargin';
import { ProcessRail } from './ProcessRail';
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { Separator } from "./ui/separator";
import { Logo } from "./Logo";
import { useProject } from "../contexts/AuthorityContext";
import { useExplainability } from "../contexts/ExplainabilityContext";

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
  const { authority, planProject } = useProject();
  const [showTraceCanvas, setShowTraceCanvas] = useState(false);
  const { level: explainabilityMode, setGlobalLevel } = useExplainability();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const viewConfig: Record<ViewMode, { icon: any, label: string, component: any, description: string }> = {
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
                  <span>{authority?.name || 'Local Authority'}</span>
                  <span style={{ color: 'var(--color-neutral-400)' }}>/</span>
                  <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                    {workspace === 'plan' ? (planProject?.title || 'Local Plan') : '24/0456/FUL'}
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
                    <Button size="sm" variant="default" className="shadow-sm gap-2" style={{
                      backgroundColor: 'var(--color-brand)',
                      color: 'var(--color-ink)'
                    }}>
                      <Sparkles className="w-4 h-4" />
                      <span className="hidden sm:inline">Draft</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Generate content with AI</TooltipContent>
                </Tooltip>
              </TooltipProvider>

              <Button size="sm" variant="outline" className="hidden sm:flex border gap-2" style={{
                borderColor: 'var(--color-neutral-300)',
                color: 'var(--color-text)'
              }}>
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
            <span style={{ color: 'var(--color-text)' }}>Explainability Level:</span>
            <div className="flex p-0.5 rounded-md" style={{ backgroundColor: 'var(--color-neutral-300)' }}>
              {(['summary', 'inspect', 'forensic'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setGlobalLevel(mode)}
                  className="px-2.5 py-0.5 rounded text-[10px] font-medium transition-all"
                  style={{
                    backgroundColor: explainabilityMode === mode ? 'white' : 'transparent',
                    color: explainabilityMode === mode ? 'var(--color-accent)' : 'var(--color-text)',
                    boxShadow: explainabilityMode === mode ? '0 1px 2px rgba(0,0,0,0.05)' : 'none'
                  }}
                >
                  {mode.charAt(0).toUpperCase() + mode.slice(1)}
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
          <ProcessRail workspace={workspace} />
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
                        // ringColor is not a valid style property, removed
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
                <ActiveViewComponent workspace={workspace} explainabilityLevel={explainabilityMode} />
              </div>
            </div>
          </div>

          {/* Context Margin (Right Sidebar) */}
          <div
            className={`
                border-l bg-white transition-all duration-300 ease-in-out flex flex-col
                ${sidebarOpen ? 'w-[350px] translate-x-0' : 'w-0 translate-x-full opacity-0 overflow-hidden border-l-0'}
            `}
            style={{ borderColor: 'var(--color-neutral-300)' }}
          >
            <ContextMargin workspace={workspace} />
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
