import { ReactNode } from 'react';
import { Map, FolderOpen, Globe, Zap, Settings, Bell, PanelLeftClose, PanelLeftOpen, BarChart3 } from 'lucide-react';
import { Logo } from './Logo';
import { Button } from './ui/button';
import { WorkspaceMode } from '../App';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";

interface ShellProps {
  children: ReactNode;
  activeMode: WorkspaceMode;
  onNavigate: (mode: WorkspaceMode) => void;
  variant?: 'home' | 'project';
  railExtra?: ReactNode;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

export function Shell({ 
  children, 
  activeMode, 
  onNavigate, 
  variant = 'home',
  railExtra,
  onToggleSidebar,
  isSidebarOpen = true
}: ShellProps) {
  const isProject = variant === 'project';
  const sidebarWidth = isProject ? 56 : 256; // 56px matches ICON_RAIL_WIDTH_PX

  return (
    <div className="flex min-h-screen w-full bg-slate-50 overflow-hidden">
      {/* Sidebar */}
      <aside 
        className="flex-shrink-0 border-r bg-white flex flex-col sticky top-0 h-screen transition-all duration-300 z-40" 
        style={{ borderColor: 'var(--color-neutral-300)', width: sidebarWidth }}
      >
        {/* Logo Area */}
        <div className={`h-14 flex items-center ${isProject ? 'justify-center' : 'px-4 gap-3'} border-b`} style={{ borderColor: 'var(--color-neutral-200)' }}>
          <Logo className="w-8 h-7 flex-shrink-0" />
          {!isProject && <span className="font-semibold text-sm tracking-tight truncate" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</span>}
        </div>

        {/* Navigation */}
        <nav className={`flex-1 ${isProject ? 'px-1 py-2 items-center' : 'p-4'} flex flex-col gap-1 overflow-y-auto`}>
          
          {/* Project Mode: Toggle Sidebar Button */}
          {isProject && onToggleSidebar && (
             <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      className="h-10 w-10 rounded-md flex items-center justify-center hover:bg-slate-100 transition-colors mb-2"
                      onClick={onToggleSidebar}
                    >
                      {isSidebarOpen ? (
                        <PanelLeftClose className="w-5 h-5 text-slate-600" />
                      ) : (
                        <PanelLeftOpen className="w-5 h-5 text-slate-600" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">{isSidebarOpen ? 'Collapse' : 'Expand'}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
          )}

          {isProject && <div className="w-8 h-px my-1 bg-slate-200 mx-auto" />}

          {/* Workspaces */}
          {!isProject && <div className="text-xs font-medium text-slate-400 mb-2 px-2 uppercase tracking-wider">Workspaces</div>}
          
          <NavButton 
            active={activeMode === 'plan'} 
            onClick={() => onNavigate('plan')} 
            icon={Map} 
            label="Strategic Planning" 
            collapsed={isProject}
          />

          <NavButton 
            active={activeMode === 'casework'} 
            onClick={() => onNavigate('casework')} 
            icon={FolderOpen} 
            label="Development Management" 
            collapsed={isProject}
          />

          <NavButton 
            active={activeMode === 'monitoring'} 
            onClick={() => onNavigate('monitoring')} 
            icon={BarChart3} 
            label="Monitoring" 
            collapsed={isProject}
          />

          {/* Labs (Home only) */}
          {!isProject && (
            <>
              <div className="mt-6 text-xs font-medium text-slate-400 mb-2 px-2 uppercase tracking-wider">Labs</div>
              <NavButton disabled icon={Globe} label="Planning Exploration" collapsed={false} badge="Soon" />
              <NavButton disabled icon={Zap} label="NSIP Assistant" collapsed={false} badge="Soon" />
            </>
          )}

          {/* Extra Rail Content (Project only) */}
          {isProject && railExtra && (
            <>
              <div className="w-8 h-px my-2 bg-slate-200 mx-auto" />
              {railExtra}
            </>
          )}

        </nav>

        {/* User Profile */}
        <div className={`p-2 ${isProject ? 'flex justify-center' : 'p-4'} border-t`} style={{ borderColor: 'var(--color-neutral-200)' }}>
           {isProject ? (
             <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs cursor-pointer" title="Tim Mayoh">TM</div>
           ) : (
             <button className="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">
                <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs">TM</div>
                <div className="flex-1 text-left truncate">
                  <div className="text-slate-900">Tim Mayoh</div>
                  <div className="text-[10px] text-slate-500">Senior Planner</div>
                </div>
                <Settings className="w-4 h-4 text-slate-400" />
              </button>
           )}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header (Home only - Project has its own header inside children) */}
        {!isProject && (
          <header className="h-14 border-b bg-white flex items-center justify-between px-6 flex-shrink-0 sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-200)' }}>
            <div className="flex items-center gap-4 text-sm text-slate-500">
              <span className="font-medium text-slate-900">
                {activeMode === 'plan' ? 'Cambridge Local Plan 2025' : activeMode === 'casework' ? 'Development Management' : 'Monitoring'}
              </span>
              <span className="text-slate-300">/</span>
              <span>{activeMode === 'plan' ? 'Baseline Stage' : activeMode === 'casework' ? 'Inbox' : 'Dashboard'}</span>
            </div>
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon" className="relative text-slate-500 hover:text-slate-900">
                <Bell className="w-4 h-4" />
                <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />
              </Button>
            </div>
          </header>
        )}

        {/* Canvas */}
        <main className="flex-1 bg-slate-50/50 flex flex-col overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}

function NavButton({ active, onClick, icon: Icon, label, collapsed, disabled, badge }: any) {
  if (collapsed) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onClick}
              disabled={disabled}
              className={`h-10 w-10 rounded-md flex items-center justify-center transition-colors ${
                active ? 'bg-white shadow-sm border border-slate-200' : 'hover:bg-slate-100 text-slate-500'
              } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <Icon className={`w-5 h-5 ${active ? 'text-blue-600' : ''}`} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">{label}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
        active
          ? 'bg-blue-50 text-blue-700'
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
      } ${disabled ? 'opacity-75 cursor-not-allowed' : ''}`}
    >
      <Icon className={`w-4 h-4 ${active ? 'text-blue-600' : 'text-slate-400'}`} />
      <span className="truncate">{label}</span>
      {badge && <span className="ml-auto text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">{badge}</span>}
    </button>
  );
}