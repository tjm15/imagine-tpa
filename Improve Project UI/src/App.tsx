import { useState } from 'react';
import { WorkbenchShell } from './components/WorkbenchShell';
import { StrategicHome } from './components/StrategicHome';
import { CaseworkHome } from './components/CaseworkHome';

export type WorkspaceMode = 'plan' | 'casework';
export type ViewMode = 'document' | 'map' | 'judgement' | 'reality';

function App() {
  const [workspace, setWorkspace] = useState<WorkspaceMode>('plan');
  const [activeView, setActiveView] = useState<ViewMode | null>(null);
  const [activeProject, setActiveProject] = useState<string | null>(null);

  const handleOpenProject = (projectId: string) => {
    setActiveProject(projectId);
    setActiveView('document');
  };

  const handleBackToHome = () => {
    setActiveProject(null);
    setActiveView(null);
  };

  if (!activeProject) {
    return workspace === 'plan' ? (
      <StrategicHome 
        onOpenProject={handleOpenProject}
        onSwitchWorkspace={() => setWorkspace('casework')}
      />
    ) : (
      <CaseworkHome 
        onOpenCase={handleOpenProject}
        onSwitchWorkspace={() => setWorkspace('plan')}
      />
    );
  }

  return (
    <WorkbenchShell
      workspace={workspace}
      activeView={activeView!}
      onViewChange={setActiveView}
      onWorkspaceChange={setWorkspace}
      onBackToHome={handleBackToHome}
      projectId={activeProject}
    />
  );
}

export default App;
