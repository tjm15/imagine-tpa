import { createContext, useContext, useState, ReactNode } from 'react';

export interface Authority {
    id: string;
    name: string;
    slug: string;
}

// Mock generic authorities based on the file system listing
export const AVAILABLE_AUTHORITIES: Authority[] = [
    { id: 'cambridge', name: 'Cambridge City Council', slug: 'cambridge' },
    { id: 'south-cambridgeshire', name: 'South Cambridgeshire', slug: 'south_cambridgeshire' },
    { id: 'stroud', name: 'Stroud District Council', slug: 'stroud' },
    { id: 'cornwall', name: 'Cornwall Council', slug: 'cornwall' },
    { id: 'westminster', name: 'Westminster City Council', slug: 'westminster' },
];

interface ProjectContextType {
    authority: Authority | null;
    projectId: string | null;
    setAuthority: (authority: Authority | null) => void;
    setProjectId: (id: string | null) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
    const [authority, setAuthority] = useState<Authority | null>(null);
    const [projectId, setProjectId] = useState<string | null>(null);

    return (
        <ProjectContext.Provider value={{ authority, projectId, setAuthority, setProjectId }}>
            {children}
        </ProjectContext.Provider>
    );
}

export function useProject() {
    const context = useContext(ProjectContext);
    if (context === undefined) {
        throw new Error('useProject must be used within a ProjectProvider');
    }
    return context;
}
