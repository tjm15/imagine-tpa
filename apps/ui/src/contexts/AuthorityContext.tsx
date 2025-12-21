import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

export interface Authority {
    id: string;
    name: string;
    slug: string;
}

interface ProjectContextType {
    authority: Authority | null;
    projectId: string | null;
    authorities: Authority[];
    loadingAuthorities: boolean;
    setAuthority: (authority: Authority | null) => void;
    setProjectId: (id: string | null) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
    const [authority, setAuthority] = useState<Authority | null>(null);
    const [projectId, setProjectId] = useState<string | null>(null);
    const [authorities, setAuthorities] = useState<Authority[]>([]);
    const [loadingAuthorities, setLoadingAuthorities] = useState(true);

    useEffect(() => {
        const controller = new AbortController();
        async function loadAuthorities() {
            try {
                const resp = await fetch('/api/spec/authorities/selected', { signal: controller.signal });
                if (!resp.ok) {
                    throw new Error(`Failed to load authorities: ${resp.status}`);
                }
                const data = (await resp.json()) as { selected_authorities?: Array<Record<string, any>> };
                const items = Array.isArray(data.selected_authorities) ? data.selected_authorities : [];
                const mapped = items
                    .map((item) => {
                        const authorityId = typeof item.authority_id === 'string' ? item.authority_id : null;
                        const name = typeof item.name === 'string' ? item.name : authorityId || 'Unknown authority';
                        if (!authorityId) {
                            return null;
                        }
                        return { id: authorityId, name, slug: authorityId };
                    })
                    .filter((item): item is Authority => Boolean(item));
                setAuthorities(mapped);
            } catch (err) {
                console.error(err);
                setAuthorities([]);
            } finally {
                setLoadingAuthorities(false);
            }
        }
        loadAuthorities();
        return () => controller.abort();
    }, []);

    return (
        <ProjectContext.Provider
            value={{ authority, projectId, authorities, loadingAuthorities, setAuthority, setProjectId }}
        >
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
