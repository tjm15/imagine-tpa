import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { FileText, Sparkles, AlertTriangle, CheckCircle2, Clock, Wand2 } from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { useProject } from '../../contexts/AuthorityContext';
import { EvidenceMark } from '../editor/EvidenceMark';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';

interface DocumentViewProps {
  workspace: WorkspaceMode;
}

interface AuthoredArtefact {
  authored_artefact_id: string;
  workspace: string;
  plan_project_id?: string | null;
  application_id?: string | null;
  culp_stage_id?: string | null;
  artefact_type: string;
  title: string;
  status: string;
  content_format: string;
  content: Record<string, any>;
  updated_at?: string | null;
}

interface DraftSuggestion {
  suggestion_id: string;
  block_type: string;
  content: string;
  evidence_refs: string[];
  limitations_text?: string | null;
  requires_judgement_run?: boolean;
}

const DEFAULT_CONTENT = {
  type: 'doc',
  content: [
    {
      type: 'paragraph',
      content: [{ type: 'text', text: 'Start drafting here.' }],
    },
  ],
};

function buildDefaultTitle(workspace: WorkspaceMode) {
  return workspace === 'plan' ? 'Place Portrait' : 'Officer Report';
}

export function DocumentView({ workspace }: DocumentViewProps) {
  const { authority, planProject, projectId } = useProject();
  const [artefact, setArtefact] = useState<AuthoredArtefact | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [draftPrompt, setDraftPrompt] = useState('');
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<DraftSuggestion[]>([]);

  const saveTimeoutRef = useRef<number | null>(null);
  const lastSavedRef = useRef<string>('');

  const artefactType = workspace === 'plan' ? 'place_portrait' : 'officer_report';
  const title = artefact?.title || buildDefaultTitle(workspace);
  const authorityId = authority?.id || planProject?.authority_id || null;
  const planProjectId = workspace === 'plan' ? planProject?.plan_project_id ?? null : null;
  const applicationId = workspace === 'casework' ? projectId ?? null : null;

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: 'Draft your narrative, policies, or analysis here. Evidence refs stay attached to each claim.',
      }),
      EvidenceMark,
    ],
    content: DEFAULT_CONTENT,
    editorProps: {
      attributes: {
        class:
          'min-h-[420px] rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 focus:outline-none',
      },
    },
  });

  const saveArtefact = async (nextContent: Record<string, any>) => {
    if (!artefact) return;
    setSaveState('saving');
    try {
      const resp = await fetch(`/api/authored-artefacts/${artefact.authored_artefact_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_jsonb: nextContent }),
      });
      if (!resp.ok) {
        throw new Error(`Failed to save (${resp.status})`);
      }
      const data = (await resp.json()) as AuthoredArtefact;
      setArtefact(data);
      lastSavedRef.current = JSON.stringify(nextContent);
      setSaveState('saved');
    } catch (err: any) {
      setSaveState('error');
      console.error(err);
    }
  };

  useEffect(() => {
    if (!editor) return;
    const handler = () => {
      if (!artefact) return;
      const json = editor.getJSON();
      const serialized = JSON.stringify(json);
      if (serialized === lastSavedRef.current) return;
      if (saveTimeoutRef.current) {
        window.clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = window.setTimeout(() => {
        saveArtefact(json);
      }, 800);
    };
    editor.on('update', handler);
    return () => {
      editor.off('update', handler);
      if (saveTimeoutRef.current) {
        window.clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [editor, artefact?.authored_artefact_id]);

  useEffect(() => {
    if (!editor || !artefact) return;
    const incoming = artefact.content && Object.keys(artefact.content).length ? artefact.content : DEFAULT_CONTENT;
    const serialized = JSON.stringify(incoming);
    if (serialized === lastSavedRef.current) return;
    lastSavedRef.current = serialized;
    editor.commands.setContent(incoming, false);
  }, [editor, artefact?.authored_artefact_id]);

  useEffect(() => {
    const loadArtefact = async () => {
      if (!authorityId || (!planProjectId && !applicationId)) return;
      setLoading(true);
      setLoadError(null);
      try {
        const params = new URLSearchParams({
          workspace,
          artefact_type: artefactType,
          limit: '1',
        });
        if (planProjectId) params.set('plan_project_id', planProjectId);
        if (applicationId) params.set('application_id', applicationId);

        const resp = await fetch(`/api/authored-artefacts?${params.toString()}`);
        if (!resp.ok) {
          throw new Error(`Failed to load drafts (${resp.status})`);
        }
        const data = await resp.json();
        const existing = Array.isArray(data.authored_artefacts) ? data.authored_artefacts[0] : null;
        if (existing) {
          setArtefact(existing);
          return;
        }

        const createResp = await fetch('/api/authored-artefacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            workspace,
            artefact_type: artefactType,
            title: buildDefaultTitle(workspace),
            plan_project_id: planProjectId,
            application_id: applicationId,
            culp_stage_id: planProject?.current_stage_id ?? null,
            status: 'draft',
            content_format: 'tiptap_json',
            created_by: 'planner',
          }),
        });
        if (!createResp.ok) {
          throw new Error(`Failed to create draft (${createResp.status})`);
        }
        const created = (await createResp.json()) as AuthoredArtefact;
        setArtefact(created);
      } catch (err: any) {
        setLoadError(err?.message || 'Failed to load draft');
      } finally {
        setLoading(false);
      }
    };
    loadArtefact();
  }, [workspace, planProjectId, applicationId, authorityId]);

  const saveStatus = useMemo(() => {
    if (saveState === 'saving') return { label: 'Saving...', icon: Clock, tone: 'text-slate-500' };
    if (saveState === 'saved') return { label: 'Saved', icon: CheckCircle2, tone: 'text-emerald-600' };
    if (saveState === 'error') return { label: 'Save failed', icon: AlertTriangle, tone: 'text-amber-600' };
    return { label: 'Draft', icon: FileText, tone: 'text-slate-500' };
  }, [saveState]);

  const StatusIcon = saveStatus.icon;

  const handleGenerateDraft = async () => {
    if (!artefact) return;
    setDraftLoading(true);
    setDraftError(null);
    try {
      const resp = await fetch('/api/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          draft_request_id: window.crypto.randomUUID(),
          requested_at: new Date().toISOString(),
          requested_by: 'planner',
          artefact_type: artefact.artefact_type,
          user_prompt: draftPrompt || artefact.title,
          constraints: {
            authority_id: authorityId,
            plan_cycle_id: planProject?.metadata?.plan_cycle_id ?? null,
          },
        }),
      });
      if (!resp.ok) {
        throw new Error(`Draft request failed (${resp.status})`);
      }
      const data = await resp.json();
      const nextSuggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
      setSuggestions(nextSuggestions);
    } catch (err: any) {
      setDraftError(err?.message || 'Draft generation failed');
    } finally {
      setDraftLoading(false);
    }
  };

  const insertSuggestion = (suggestion: DraftSuggestion) => {
    if (!editor) return;
    const refs = Array.isArray(suggestion.evidence_refs) ? suggestion.evidence_refs : [];
    const marks = refs.length ? [{ type: 'evidenceRef', attrs: { refs } }] : [];
    editor
      .chain()
      .focus()
      .insertContent({
        type: 'paragraph',
        content: [{ type: 'text', text: suggestion.content, marks }],
      })
      .run();
  };

  if (loading) {
    return <div className="p-6 text-sm text-slate-500">Loading draft workspace…</div>;
  }

  if (loadError) {
    return <div className="p-6 text-sm text-amber-700">{loadError}</div>;
  }

  if (!artefact) {
    return <div className="p-6 text-sm text-slate-500">No draft is available yet.</div>;
  }

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <header className="space-y-2">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
          <FileText className="w-4 h-4" />
          {workspace === 'plan' ? 'Living Document' : 'Officer Report Draft'}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-slate-900">{title}</h1>
          <Badge variant="outline" className="text-xs">
            {artefact.status}
          </Badge>
          <div className={`flex items-center gap-1 text-xs ${saveStatus.tone}`}>
            <StatusIcon className="w-3.5 h-3.5" />
            <span>{saveStatus.label}</span>
          </div>
        </div>
        <p className="text-sm text-slate-500">
          Drafts are stored as authored artefacts with embedded evidence marks. AI suggestions remain advisory.
        </p>
      </header>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wand2 className="w-4 h-4 text-[color:var(--color-accent)]" />
              Generate drafting prompts
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              value={draftPrompt}
              onChange={(event) => setDraftPrompt(event.target.value)}
              placeholder="Ask for a draft section, argument, or policy clause"
            />
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={handleGenerateDraft} disabled={draftLoading}>
                <Sparkles className="w-4 h-4 mr-1" />
                {draftLoading ? 'Generating…' : 'Generate'}
              </Button>
              {draftError && <span className="text-xs text-amber-700">{draftError}</span>}
            </div>
            {suggestions.length > 0 && (
              <div className="space-y-3">
                {suggestions.map((suggestion) => (
                  <div key={suggestion.suggestion_id} className="border border-slate-200 rounded-md p-3 bg-white">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm text-slate-800 whitespace-pre-line">{suggestion.content}</p>
                        {suggestion.evidence_refs?.length > 0 && (
                          <p className="mt-2 text-[11px] text-slate-500">
                            Evidence: {suggestion.evidence_refs.join(', ')}
                          </p>
                        )}
                      </div>
                      <Button size="sm" variant="outline" onClick={() => insertSuggestion(suggestion)}>
                        Insert
                      </Button>
                    </div>
                    {suggestion.requires_judgement_run && (
                      <div className="mt-2 text-[11px] text-amber-700">
                        Requires judgement run before sign-off.
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Draft metadata</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-slate-600">
            <div className="flex justify-between"><span>Workspace</span><span>{workspace}</span></div>
            <div className="flex justify-between"><span>Artefact type</span><span>{artefact.artefact_type}</span></div>
            <div className="flex justify-between"><span>Authority</span><span>{authority?.name || authorityId || '—'}</span></div>
            <div className="flex justify-between"><span>Updated</span><span>{artefact.updated_at || '—'}</span></div>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3">
        {editor && <EditorContent editor={editor} />}
      </section>
    </div>
  );
}
