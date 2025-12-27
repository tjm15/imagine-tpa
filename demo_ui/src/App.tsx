import { useState, useCallback } from 'react';
import { DndContext, DragEndEvent, DragOverlay, closestCenter } from '@dnd-kit/core';
import { Toaster, toast } from 'sonner';
import { WorkbenchShell } from './components/WorkbenchShell';
import { StrategicHome } from './components/StrategicHome';
import { CaseworkHome } from './components/CaseworkHome';
import { AppStateProvider, useAppDispatch } from './lib/appState';
import { ModalManager } from './components/modals/ModalDialogs';
import { processDroppedEvidence } from './lib/aiSimulation';

export type WorkspaceMode = 'plan' | 'casework' | 'monitoring';
export type ViewMode = 'document' | 'map' | 'judgement' | 'reality' | 'monitoring';

// Main app content with DnD handling
function AppContent() {
  const dispatch = useAppDispatch();
  const [workspace, setWorkspace] = useState<WorkspaceMode>('plan');
  const [activeView, setActiveView] = useState<ViewMode | null>(null);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [draggedItem, setDraggedItem] = useState<{ id: string; type: string } | null>(null);

  const handleWorkspaceChange = useCallback((next: WorkspaceMode) => {
    setWorkspace(next);
    setActiveView((prev) => {
      if (next === 'monitoring') return 'monitoring';
      if (prev === 'monitoring') return 'document';
      return prev;
    });
  }, []);

  const handleOpenProject = (projectId: string) => {
    setActiveProject(projectId);
    setActiveView(workspace === 'monitoring' ? 'monitoring' : 'document');
  };

  const handleBackToHome = () => {
    setActiveProject(null);
    setActiveView(null);
  };

  // Handle drag-drop of evidence into document editor
  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    setDraggedItem(null);

    if (over?.id === 'document-editor' && active.data.current?.type === 'evidence') {
      const evidence = active.data.current.evidence;
      const citation = processDroppedEvidence(evidence.id, { location: 'document' });
      
      dispatch({
        type: 'ADD_CITATION',
        payload: {
          evidenceId: evidence.id,
          text: evidence.title,
          range: null,
          citation,
        }
      });
      
      toast.success(`Cited: ${evidence.title}`);
    }

    if (over?.id === 'document-editor' && active.data.current?.type === 'photo') {
      const photo = active.data.current.photo;
      toast.success(`Photo "${photo.caption}" added to document`);
    }
  }, [dispatch]);

  const handleDragStart = useCallback((event: DragEndEvent) => {
    if (event.active.data.current) {
      setDraggedItem({
        id: event.active.id as string,
        type: event.active.data.current.type,
      });
    }
  }, []);

  if (!activeProject) {
    return workspace === 'casework' ? (
      <CaseworkHome 
        onOpenCase={handleOpenProject}
        onSwitchWorkspace={() => handleWorkspaceChange('plan')}
      />
    ) : (
      <StrategicHome 
        onOpenProject={handleOpenProject}
        onSwitchWorkspace={() => handleWorkspaceChange('casework')}
      />
    );
  }

  return (
    <DndContext 
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <WorkbenchShell
        workspace={workspace}
        activeView={activeView!}
        onViewChange={setActiveView}
        onWorkspaceChange={handleWorkspaceChange}
        onBackToHome={handleBackToHome}
        projectId={activeProject}
      />
      
      {/* Drag Overlay for visual feedback */}
      <DragOverlay>
        {draggedItem && (
          <div className="bg-white rounded-lg shadow-xl p-3 border-2 border-blue-400 max-w-xs">
            <span className="text-sm font-medium text-blue-700">
              {draggedItem.type === 'evidence' ? '📄 Dragging evidence' : '🖼️ Dragging photo'}
            </span>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function App() {
  return (
    <AppStateProvider>
      <AppContent />
      <ModalManager />
      <Toaster 
        position="bottom-right" 
        richColors 
        closeButton
        toastOptions={{
          duration: 3000,
          className: 'text-sm',
        }}
      />
    </AppStateProvider>
  );
}

export default App;
