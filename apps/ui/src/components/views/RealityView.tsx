import { useEffect, useMemo, useState } from 'react';
import { Camera, Eye, Download, AlertTriangle, Maximize2, Sparkles, Layers } from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { ExplainabilityLevel } from '../../contexts/ExplainabilityContext';
import { useProject } from '../../contexts/AuthorityContext';
import { Button } from '../ui/button';

interface RealityViewProps {
  workspace: WorkspaceMode;
  explainabilityLevel?: ExplainabilityLevel;
}

interface VisualAsset {
  visual_asset_id: string;
  document_id?: string | null;
  page_number?: number | null;
  asset_type: string;
  blob_path: string;
  metadata: Record<string, any>;
  created_at?: string | null;
}

export function RealityView({ workspace, explainabilityLevel = 'summary' }: RealityViewProps) {
  const { planProject } = useProject();
  const [assets, setAssets] = useState<VisualAsset[]>([]);
  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showParsed, setShowParsed] = useState(true);
  const [showGenerated, setShowGenerated] = useState(true);
  const [analysis, setAnalysis] = useState<any | null>(null);

  const fetchJson = async (url: string, options?: RequestInit) => {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      throw new Error(`Request failed: ${resp.status}`);
    }
    return resp.json();
  };

  const loadAssets = async () => {
    if (!planProject?.plan_project_id) return;
    const data = await fetchJson(`/api/visual-assets?plan_project_id=${planProject.plan_project_id}&limit=60`);
    setAssets(Array.isArray(data.visual_assets) ? data.visual_assets : []);
  };

  useEffect(() => {
    if (workspace !== 'plan') return;
    loadAssets().catch((err) => console.error(err));
  }, [workspace, planProject?.plan_project_id]);

  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      const origin = asset.metadata?.origin;
      const isGenerated = origin === 'generated';
      if (isGenerated && !showGenerated) return false;
      if (!isGenerated && !showParsed) return false;
      return true;
    });
  }, [assets, showGenerated, showParsed]);

  const loadPreview = async (assetId: string) => {
    if (assetUrls[assetId]) return;
    try {
      const data = await fetchJson(`/api/visual-assets/${assetId}/blob`);
      if (data.data_url) {
        setAssetUrls((prev) => ({ ...prev, [assetId]: data.data_url }));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const toggleSelect = (assetId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) {
        next.delete(assetId);
      } else {
        next.add(assetId);
      }
      return next;
    });
  };

  const runAssessment = async () => {
    if (!planProject?.plan_project_id || selected.size === 0) return;
    const selectedRefs = Array.from(selected).map((id) => `visual_asset::${id}::image`);
    try {
      const run = await fetchJson('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anchors: { plan_project_id: planProject.plan_project_id } }),
      });
      const toolRequest = await fetchJson('/api/tool-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: run.run_id,
          tool_name: 'request_instrument',
          instrument_id: 'townscape_vlm_assessment',
          inputs: { visual_asset_refs: selectedRefs, viewpoint_context: { context: 'Plan studio visual review' } },
          blocking: true,
        }),
      });
      const executed = await fetchJson(`/api/tool-requests/${toolRequest.tool_request.tool_request_id}/run`, {
        method: 'POST',
      });
      setAnalysis(executed.tool_request.outputs);
    } catch (err) {
      console.error(err);
    }
  };

  const renderAnalysis = () => {
    if (!analysis) return null;
    const output = analysis.output_data || analysis.parsed_json || analysis;
    return (
      <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm">
        <div className="flex items-center gap-2 text-amber-800 font-medium">
          <Sparkles className="w-4 h-4" />
          Visual assessment summary
        </div>
        {explainabilityLevel === 'summary' && (
          <p className="text-neutral-700 mt-2">{output?.summary || 'Visual assessment completed. See inspector output for detail.'}</p>
        )}
        {explainabilityLevel !== 'summary' && (
          <pre className="text-xs text-neutral-600 mt-2 whitespace-pre-wrap">{JSON.stringify(output, null, 2)}</pre>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      <div className="bg-white border-b border-neutral-200 p-4 flex items-center justify-between flex-shrink-0">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Camera className="w-5 h-5 text-[color:var(--color-gov-blue)]" />
            <h2 className="text-lg">
              {workspace === 'plan' ? 'Visual Evidence & Overlays' : 'Site Photos & Context'}
            </h2>
          </div>
          <p className="text-sm text-neutral-600">
            {workspace === 'plan'
              ? 'Visuospatial reasoning with plan-reality registration'
              : 'Photographic evidence from site visit with caveated interpretations'}
          </p>
        </div>
        <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
          <Download className="w-4 h-4" />
          Export Evidence Pack
        </button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto space-y-6">
          {workspace === 'plan' ? (
            <>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  <Layers className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
                  Visual sources
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant={showParsed ? 'default' : 'outline'} onClick={() => setShowParsed(!showParsed)}>
                    Parsed
                  </Button>
                  <Button size="sm" variant={showGenerated ? 'default' : 'outline'} onClick={() => setShowGenerated(!showGenerated)}>
                    Generated
                  </Button>
                  <Button size="sm" variant="secondary" onClick={runAssessment} disabled={selected.size === 0}>
                    Run Visual Assessment
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {filteredAssets.length === 0 && (
                  <div className="col-span-2 text-sm text-neutral-500 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    No visual assets yet. Ingest a plan or generate visuals to populate this tab.
                  </div>
                )}
                {filteredAssets.map((asset) => (
                  <div
                    key={asset.visual_asset_id}
                    className={`bg-white rounded-lg border overflow-hidden cursor-pointer transition-shadow ${
                      selected.has(asset.visual_asset_id) ? 'border-[color:var(--color-accent)] shadow-md' : 'border-neutral-200'
                    }`}
                    onClick={() => toggleSelect(asset.visual_asset_id)}
                    onMouseEnter={() => loadPreview(asset.visual_asset_id)}
                  >
                    <div className="aspect-video bg-neutral-100 relative">
                      {assetUrls[asset.visual_asset_id] ? (
                        <img src={assetUrls[asset.visual_asset_id]} alt="visual asset" className="h-full w-full object-cover" />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center text-neutral-400">
                          <Eye className="w-10 h-10" />
                        </div>
                      )}
                      <div className="absolute top-2 left-2 bg-white px-2 py-1 rounded text-xs shadow">
                        {asset.asset_type}
                      </div>
                      <button className="absolute top-2 right-2 p-1.5 bg-white rounded shadow hover:bg-neutral-50" onClick={(e) => e.stopPropagation()}>
                        <Maximize2 className="w-3 h-3" />
                      </button>
                    </div>
                    <div className="p-3 text-xs text-neutral-600">
                      <div className="flex items-center justify-between">
                        <span>{asset.metadata?.role || asset.metadata?.classification?.label || 'Visual asset'}</span>
                        {asset.metadata?.origin === 'generated' && (
                          <span className="text-[color:var(--color-accent)]">Generated</span>
                        )}
                      </div>
                      {asset.page_number !== null && asset.page_number !== undefined && (
                        <div className="text-[10px] text-neutral-400 mt-1">Page {asset.page_number}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {renderAnalysis()}
            </>
          ) : (
            <div className="text-sm text-neutral-500">Casework visuals will appear here.</div>
          )}
        </div>
      </div>
    </div>
  );
}
