import { ReactNode } from 'react';
import { Map, FolderOpen, Globe, Zap, Settings, Menu, Bell } from 'lucide-react';
import { Logo } from './Logo';
import { Button } from './ui/button';
import { WorkspaceMode } from '../App';

interface ShellProps {
  children: ReactNode;
  activeMode: WorkspaceMode;
  onNavigate: (mode: WorkspaceMode) => void;
}

export function Shell({ children, activeMode, onNavigate }: ShellProps) {
  return (
    <div className="flex min-h-screen w-full bg-slate-50">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r bg-white flex flex-col sticky top-0 h-screen" style={{ borderColor: 'var(--color-neutral-300)' }}>
        <div className="p-4 border-b flex items-center gap-3" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <Logo className="w-8 h-7" />
          <span className="font-semibold text-sm tracking-tight" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</span>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          <div className="text-xs font-medium text-slate-400 mb-2 px-2 uppercase tracking-wider">Workspaces</div>
          
          <button
            onClick={() => onNavigate('plan')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeMode === 'plan'
                ? 'bg-blue-50 text-blue-700'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <Map className={`w-4 h-4 ${activeMode === 'plan' ? 'text-blue-600' : 'text-slate-400'}`} />
            Strategic Planning
          </button>

          <button
            onClick={() => onNavigate('casework')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeMode === 'casework'
                ? 'bg-emerald-50 text-emerald-700'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <FolderOpen className={`w-4 h-4 ${activeMode === 'casework' ? 'text-emerald-600' : 'text-slate-400'}`} />
            Development Management
          </button>

          <div className="mt-6 text-xs font-medium text-slate-400 mb-2 px-2 uppercase tracking-wider">Labs</div>

          <button
            disabled
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 cursor-not-allowed opacity-75"
          >
            <Globe className="w-4 h-4 text-purple-300" />
            Planning Exploration
            <span className="ml-auto text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">Soon</span>
          </button>

          <button
            disabled
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 cursor-not-allowed opacity-75"
          >
            <Zap className="w-4 h-4 text-amber-300" />
            NSIP Assistant
            <span className="ml-auto text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">Soon</span>
          </button>
        </nav>

        <div className="p-4 border-t" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <button className="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs">TM</div>
            <div className="flex-1 text-left">
              <div className="text-slate-900">Tim Mayoh</div>
              <div className="text-[10px] text-slate-500">Senior Planner</div>
            </div>
            <Settings className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Top Bar - Sticky */}
        <header className="h-14 border-b bg-white flex items-center justify-between px-6 flex-shrink-0 sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="flex items-center gap-4 text-sm text-slate-500">
            <span className="font-medium text-slate-900">
              {activeMode === 'plan' ? 'Cambridge Local Plan 2025' : 'Development Management'}
            </span>
            <span className="text-slate-300">/</span>
            <span>{activeMode === 'plan' ? 'Baseline Stage' : 'Inbox'}</span>
          </div>
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" className="relative text-slate-500 hover:text-slate-900">
              <Bell className="w-4 h-4" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />
            </Button>
          </div>
        </header>

        {/* Canvas - Natural Flow */}
        <main className="flex-1 bg-slate-50/50">
          {children}
        </main>
      </div>
    </div>
  );
}