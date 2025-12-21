import { useEffect, useMemo, useState } from 'react';
import {
  Layers, ZoomIn, ZoomOut, Maximize2, MapPin, Circle, Square,
  Download, Eye, EyeOff, Sparkles, AlertTriangle
} from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { ExplainabilityLevel } from '../../contexts/ExplainabilityContext';
import { useProject } from '../../contexts/AuthorityContext';
import { Button } from '../ui/button';

interface MapViewProps {
  workspace: WorkspaceMode;
  explainabilityLevel?: ExplainabilityLevel;
}

interface SiteItem {
  site_id: string;
  geometry: any;
  metadata: Record<string, any>;
}

interface SiteDraft {
  site_draft_id: string;
  plan_project_id: string;
  geometry: any;
  status: string;
  metadata: Record<string, any>;
  expires_at?: string;
}

export function MapView({ workspace, explainabilityLevel = 'summary' }: MapViewProps) {
  const { authority, planProject } = useProject();
  const [activeLayers, setActiveLayers] = useState({
    constraints: true,
    transport: true,
    sites: workspace === 'plan',
    boundaries: true,
  });
  const [sites, setSites] = useState<SiteItem[]>([]);
  const [drafts, setDrafts] = useState<SiteDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftWkt, setDraftWkt] = useState('');
  const [analysis, setAnalysis] = useState<Record<string, any>>({});

  const toggleLayer = (layer: keyof typeof activeLayers) => {
    setActiveLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
  };

  const fetchJson = async (url: string, options?: RequestInit) => {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      throw new Error(`Request failed: ${resp.status}`);
    }
    return resp.json();
  };

  const loadSites = async () => {
    if (!planProject?.plan_project_id) return;
    const data = await fetchJson(`/api/sites?plan_project_id=${planProject.plan_project_id}`);
    setSites(Array.isArray(data.sites) ? data.sites : []);
  };

  const loadDrafts = async () => {
    if (!planProject?.plan_project_id) return;
    const data = await fetchJson(`/api/plan-projects/${planProject.plan_project_id}/site-drafts?status=draft`);
    setDrafts(Array.isArray(data.site_drafts) ? data.site_drafts : []);
  };

  useEffect(() => {
    if (workspace !== 'plan') return;
    setLoading(true);
    Promise.all([loadSites(), loadDrafts()])
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [workspace, planProject?.plan_project_id]);

  const createDraft = async () => {
    if (!planProject?.plan_project_id) return;
    const payload = {
      plan_project_id: planProject.plan_project_id,
      geometry_wkt: draftWkt || null,
      metadata: { label: draftName },
    };
    await fetchJson('/api/site-drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setDraftName('');
    setDraftWkt('');
    setDraftOpen(false);
    await loadDrafts();
  };

  const confirmDraft = async (draftId: string) => {
    await fetchJson(`/api/site-drafts/${draftId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    await Promise.all([loadDrafts(), loadSites()]);
  };

  const runFingerprint = async (siteId: string) => {
    if (!planProject?.plan_project_id) return;
    try {
      const run = await fetchJson('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anchors: { plan_project_id: planProject.plan_project_id, site_id: siteId } }),
      });
      const toolRequest = await fetchJson('/api/tool-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: run.run_id,
          tool_name: 'get_site_fingerprint',
          inputs: {
            site_id: siteId,
            authority_id: authority?.id,
            plan_cycle_id: planProject.metadata?.plan_cycle_id,
            limit_features: 120,
          },
          blocking: true,
        }),
      });
      const executed = await fetchJson(`/api/tool-requests/${toolRequest.tool_request.tool_request_id}/run`, {
        method: 'POST',
      });
      setAnalysis((prev) => ({ ...prev, [siteId]: executed.tool_request }));
    } catch (err) {
      console.error(err);
    }
  };

  const siteSummary = useMemo(() => {
    return {
      confirmed: sites.length,
      drafts: drafts.length,
    };
  }, [sites.length, drafts.length]);

  const renderAnalysis = (siteId: string) => {
    const result = analysis[siteId];
    if (!result) return null;
    const fingerprint = result.outputs?.fingerprint || {};
    const summary = fingerprint.summary || 'No summary available.';
    const intersections = fingerprint.intersections || [];
    return (
      <div className="mt-2 rounded border border-neutral-200 bg-white p-3 text-xs">
        <div className="flex items-center gap-2 text-[color:var(--color-gov-blue)]">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Fingerprint summary</span>
        </div>
        <p className="text-neutral-700 mt-1">{summary}</p>
        {explainabilityLevel !== 'summary' && (
          <div className="mt-2 text-neutral-500">
            {intersections.length ? `${intersections.length} intersecting constraints.` : 'No intersections recorded.'}
          </div>
        )}
        {explainabilityLevel === 'forensic' && (
          <pre className="mt-2 whitespace-pre-wrap text-[10px] text-neutral-500">
            {JSON.stringify(result.outputs, null, 2)}
          </pre>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      <div className="bg-white border-b border-neutral-200 p-4 flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg mb-1">
            {workspace === 'plan' ? 'Strategic Map Canvas' : 'Site Context Map'}
          </h2>
          <p className="text-sm text-neutral-600">
            Draw to query, snapshot to cite
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
            <Download className="w-4 h-4" />
            Export Snapshot
          </button>
          <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
            <Maximize2 className="w-4 h-4" />
            Fullscreen
          </button>
        </div>
      </div>

      <div className="flex-1 relative bg-neutral-100">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <MapPin className="w-16 h-16 text-neutral-300 mx-auto mb-4" />
            <p className="text-neutral-600 mb-2">Interactive Map Canvas</p>
            <p className="text-sm text-neutral-500">
              {workspace === 'plan'
                ? 'Upload GIS layers or confirm draft sites to render overlays'
                : '45 Mill Road, Cambridge CB1 2AD'}
            </p>
          </div>
        </div>

        {workspace === 'casework' && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="relative">
              <div className="w-8 h-8 bg-[color:var(--color-warning)] rounded-full border-4 border-white shadow-lg animate-pulse" />
              <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-white px-3 py-1 rounded shadow-lg whitespace-nowrap text-sm">
                45 Mill Road
              </div>
            </div>
          </div>
        )}

        <div className="absolute top-4 right-4 flex flex-col gap-2">
          <div className="bg-white rounded-lg shadow-lg border border-neutral-200 p-2 flex flex-col gap-1">
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Zoom in">
              <ZoomIn className="w-4 h-4" />
            </button>
            <div className="h-px bg-neutral-200" />
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Zoom out">
              <ZoomOut className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
          <div className="bg-white rounded-lg shadow-lg border border-neutral-200 px-4 py-2 flex items-center gap-3">
            <span className="text-sm text-neutral-600">Draw to query:</span>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Point marker">
              <MapPin className="w-4 h-4" />
            </button>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Circle">
              <Circle className="w-4 h-4" />
            </button>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Polygon">
              <Square className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="absolute top-4 left-4 bg-white rounded-lg shadow-lg border border-neutral-200 p-4 w-64">
          <div className="flex items-center gap-2 mb-3">
            <Layers className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
            <h3 className="text-sm">Map Layers</h3>
          </div>
          <div className="space-y-2">
            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.boundaries}
                  onChange={() => toggleLayer('boundaries')}
                  className="rounded"
                />
                <span className="text-sm">Authority Boundary</span>
              </div>
              {activeLayers.boundaries ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.constraints}
                  onChange={() => toggleLayer('constraints')}
                  className="rounded"
                />
                <span className="text-sm">Constraints</span>
              </div>
              {activeLayers.constraints ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.transport}
                  onChange={() => toggleLayer('transport')}
                  className="rounded"
                />
                <span className="text-sm">Transport Network</span>
              </div>
              {activeLayers.transport ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            {workspace === 'plan' && (
              <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={activeLayers.sites}
                    onChange={() => toggleLayer('sites')}
                    className="rounded"
                  />
                  <span className="text-sm">Candidate Sites</span>
                </div>
                {activeLayers.sites ? (
                  <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
                ) : (
                  <EyeOff className="w-4 h-4 text-neutral-400" />
                )}
              </label>
            )}
          </div>

          {workspace === 'plan' && activeLayers.sites && (
            <div className="mt-4 pt-3 border-t border-neutral-200">
              <p className="text-xs text-neutral-600 mb-2">Site Status Legend:</p>
              <div className="space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-[color:var(--color-success)] rounded" />
                  <span>Confirmed ({siteSummary.confirmed})</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-[color:var(--color-stage)] rounded" />
                  <span>Draft ({siteSummary.drafts})</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {workspace === 'plan' && planProject && (
          <div className="absolute top-4 right-20 w-[320px] bg-white rounded-lg shadow-lg border border-neutral-200 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm">Site Queue</h3>
              <Button size="sm" variant="secondary" onClick={() => setDraftOpen(!draftOpen)}>
                New Draft
              </Button>
            </div>
            {draftOpen && (
              <div className="mb-4 space-y-2 text-xs">
                <input
                  className="w-full border border-neutral-200 rounded px-2 py-1"
                  placeholder="Draft label"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                />
                <textarea
                  className="w-full border border-neutral-200 rounded px-2 py-1 h-20"
                  placeholder="Geometry WKT (optional)"
                  value={draftWkt}
                  onChange={(e) => setDraftWkt(e.target.value)}
                />
                <Button size="sm" onClick={createDraft}>Save Draft</Button>
              </div>
            )}
            {loading && (
              <div className="text-xs text-neutral-500">Loading sites…</div>
            )}
            {!loading && (
              <div className="space-y-3">
                {drafts.length === 0 && sites.length === 0 && (
                  <div className="text-xs text-neutral-500 flex items-center gap-2">
                    <AlertTriangle className="w-3 h-3" />
                    No sites yet. Add a draft to begin.
                  </div>
                )}
                {drafts.map((draft) => (
                  <div key={draft.site_draft_id} className="border border-neutral-200 rounded p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span>{draft.metadata?.label || 'Draft site'}</span>
                      <Button size="sm" variant="outline" onClick={() => confirmDraft(draft.site_draft_id)}>
                        Confirm
                      </Button>
                    </div>
                    <div className="text-neutral-500 mt-1">Draft · {draft.expires_at ? `expires ${draft.expires_at}` : 'no expiry set'}</div>
                  </div>
                ))}
                {sites.map((site) => (
                  <div key={site.site_id} className="border border-neutral-200 rounded p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span>{site.metadata?.label || site.site_id.slice(0, 8)}</span>
                      <Button size="sm" variant="outline" onClick={() => runFingerprint(site.site_id)}>
                        Analyze
                      </Button>
                    </div>
                    {renderAnalysis(site.site_id)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
