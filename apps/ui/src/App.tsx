import { useState } from 'react';
import { WorkbenchShell } from './components/WorkbenchShell';
import { StrategicHome } from './components/StrategicHome';
import { CaseworkHome } from './components/CaseworkHome';
import { ProjectProvider, useProject } from './contexts/AuthorityContext';

export type WorkspaceMode = 'plan' | 'casework';
export type ViewMode = 'document' | 'map' | 'judgement' | 'reality';

function AppContent() {
    const [workspace, setWorkspace] = useState<WorkspaceMode>('plan');
    const [activeView, setActiveView] = useState<ViewMode | null>(null);
    const { projectId, setProjectId, authority } = useProject();

    const handleOpenProject = (projectId: string) => {
        setProjectId(projectId);
        setActiveView('document');
    };

    const handleBackToHome = () => {
        setProjectId(null);
        setActiveView(null);
    };

    if (!projectId) {
        // If no project is selected, show the Home Screen for the current workspace
        // The homescreen should handle "Empty" state if no authority is selected yet, 
        // or provide a way to select one.
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
            projectId={projectId}
        />
    );
}

export default function App() {
    return (
        <ProjectProvider>
            <AppContent />
        </ProjectProvider>
    );
}
