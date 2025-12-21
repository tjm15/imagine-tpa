import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

export interface Authority {
    id: string;
    name: string;
    slug: string;
}

export interface PlanProject {
    plan_project_id: string;
    authority_id: string;
    title: string;
    status: string;
    current_stage_id: string | null;
    metadata: Record<string, any>;
}

interface ProjectContextType {
    authority: Authority | null;
    projectId: string | null;
    planProject: PlanProject | null;
    authorities: Authority[];
    loadingAuthorities: boolean;
    loadingPlanProject: boolean;
    setAuthority: (authority: Authority | null) => void;
    setProjectId: (id: string | null) => void;
    setPlanProject: (project: PlanProject | null) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
    const [authority, setAuthority] = useState<Authority | null>(null);
    const [projectId, setProjectId] = useState<string | null>(null);
    const [planProject, setPlanProject] = useState<PlanProject | null>(null);
    const [authorities, setAuthorities] = useState<Authority[]>([]);
    const [loadingAuthorities, setLoadingAuthorities] = useState(true);
    const [loadingPlanProject, setLoadingPlanProject] = useState(false);

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

    useEffect(() => {
        if (!projectId) {
            setPlanProject(null);
            return;
        }
        const controller = new AbortController();
        async function loadPlanProject() {
            setLoadingPlanProject(true);
            try {
                const resp = await fetch(`/api/plan-projects/${projectId}`, { signal: controller.signal });
                if (!resp.ok) {
                    throw new Error(`Failed to load plan project: ${resp.status}`);
                }
                const data = (await resp.json()) as any;
                const project = {
                    plan_project_id: data.plan_project_id,
                    authority_id: data.authority_id,
                    title: data.title,
                    status: data.status,
                    current_stage_id: data.current_stage_id ?? null,
                    metadata: data.metadata ?? {},
                };
                setPlanProject(project);
            } catch (err) {
                console.error(err);
                setPlanProject(null);
            } finally {
                setLoadingPlanProject(false);
            }
        }
        loadPlanProject();
        return () => controller.abort();
    }, [projectId]);

    return (
        <ProjectContext.Provider
            value={{
                authority,
                projectId,
                planProject,
                authorities,
                loadingAuthorities,
                loadingPlanProject,
                setAuthority,
                setProjectId,
                setPlanProject,
            }}
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
