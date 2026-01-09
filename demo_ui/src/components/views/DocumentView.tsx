import { useState } from 'react';
import { WorkspaceMode } from '../../App';
import { FileText, HelpCircle, BookOpenCheck, Camera, Map as MapIcon } from 'lucide-react';
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { DocumentEditor } from '../editor/DocumentEditor';
import { ProvenanceIndicator, StatusBadge } from '../ProvenanceIndicator';
import { NarrativeGuide } from '../NarrativeGuide';
import { MapViewInteractive } from './MapViewInteractive';
import { mockPhotos } from '../../fixtures/extendedMockData';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

const EXPLAINABILITY_LABEL: Record<ExplainabilityMode, string> = {
  summary: 'Summary',
  inspect: 'Inspect',
  forensic: 'Forensic',
};

interface DocumentViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
  onToggleMap?: () => void;
}

const initialBaselineText = `<h1>Place Portrait: Baseline Evidence</h1>
<h2>Introduction</h2>
<p>This place portrait provides the baseline evidence for Cambridge's local plan review under the new plan process. It establishes the current context against which spatial strategy options will be assessed.</p>
<p>The portrait draws on multiple evidence sources including Census 2021, local monitoring data, and commissioned technical studies. All limitations are explicitly noted.</p>

<div class="figure-embed">
  <div class="figure-placeholder">
    <strong>Figure 1:</strong> Cambridge Authority Area and Key Constraints
    <p class="text-xs text-slate-600 mt-1">Interactive map showing Green Belt, conservation areas, and transport corridors. Click to expand or cite.</p>
  </div>
</div>

<h2>Housing Context</h2>
<p>Cambridge faces acute housing pressure. The affordability ratio of 12.8x significantly exceeds both the regional average (8.2x) and represents a deterioration from 10.5x in 2015.</p>
<p>As shown in <strong>Figure 2</strong> (housing trajectory), delivery has averaged 1,200 homes per annum since 2015, but the updated standard method indicates a need for 1,800 dpa to 2041.</p>

<div class="figure-embed">
  <div class="figure-placeholder">
    <strong>Figure 2:</strong> Housing Trajectory 2015-2025
    <p class="text-xs text-slate-600 mt-1">Chart showing completions vs target. Click to cite in reasoning ledger.</p>
  </div>
</div>

<h2>Transport & Connectivity</h2>
<p>Cambridge benefits from strong rail connectivity to London (50 mins) and excellent local cycling infrastructure. However, strategic road capacity remains constrained, particularly on the A14 corridor.</p>
<p>Spatial options will need to balance brownfield intensification (supporting sustainable modes) against greenfield release (requiring highway mitigation).</p>`;

const initialCaseworkText = `<h1>Officer Report: 24/0456/FUL</h1>
<h2>01. Site &amp; Proposal</h2>
<ul>
  <li>Address: 45 Mill Road, Cambridge CB1 2AD</li>
  <li>Ward: Petersfield</li>
  <li>Applicant: Mill Road Developments Ltd</li>
  <li>Agent: Smith Planning Associates</li>
</ul>
<p>The application site comprises a ground floor retail unit (Use Class E) within a two-storey building in the Mill Road District Centre. The proposal seeks to change the use to residential (2 x 1-bed flats), with internal alterations but no external changes.</p>
<h2>02. Planning Assessment</h2>
<h3>Principle of Development</h3>
<p>Policy DM12 requires retention of ground floor retail uses in District Centres unless the unit has been actively marketed for 12 months. Marketing evidence shows 15 months of offers at market rates with no uptake.</p>
<h3>Residential Amenity</h3>
<p>The proposed flats meet minimum space standards (Policy H9) and benefit from rear courtyard access. Natural light to habitable rooms is adequate based on the site inspection.</p>
<h3>Comments and Conditions</h3>
<ul>
  <li>Highways: No objection; requires secure cycle storage.</li>
  <li>Conservation: Satisfied with internal conversion approach.</li>
  <li>Evidence source: Site visit 12 Dec.</li>
</ul>
<h2>03. Recommendation</h2>
<p><strong>APPROVE</strong>, subject to conditions:</p>
<ul>
  <li>Secure cycle storage (2 spaces)</li>
  <li>Removal of permitted development rights</li>
  <li>Retention of front elevation details</li>
</ul>`;

export function DocumentView({ workspace, explainabilityMode = 'summary', onOpenTrace, onToggleMap }: DocumentViewProps) {
  const [showGuide, setShowGuide] = useState(true);
  const [templateToInsert, setTemplateToInsert] = useState<{ content: string; id: number } | null>(null);

  const title = workspace === 'plan'
    ? 'Place Portrait: Baseline Evidence'
    : 'Officer Report: 24/0456/FUL';

  const handleWhy = () => {
    onOpenTrace?.({
      kind: 'document',
      id: workspace === 'plan' ? 'deliverable-place-portrait' : 'case-24-0456',
      label: title,
      note: 'Document-level trace falls back to run-level context unless a specific element is selected.',
    });
  };

  const whyTooltip = (() => {
    if (explainabilityMode === 'forensic') return 'Open trace';
    if (explainabilityMode === 'inspect') {
      return (
        <div className="text-xs space-y-1">
          <div className="font-medium">Provisional · 3 sources</div>
          <div>Policies: H2, DM12</div>
          <div>Constraints: Conservation Area</div>
        </div>
      );
    }
    return 'Based on Policies H2, DM12 (3 sources)';
  })();

  const whyVisibilityClass = explainabilityMode === 'summary' ? 'opacity-0 group-hover:opacity-100' : 'opacity-100';

  return (
    <div className="h-full min-h-0 flex flex-col font-sans bg-white overflow-hidden">
      {/* Document Header */}
      <div className="flex-shrink-0 sticky top-0 z-20 px-4 sm:px-6 pt-4 pb-3 border-b border-slate-200 group bg-white shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-blue-600 font-medium mb-2">
              <FileText className="w-4 h-4" />
              <span className="uppercase tracking-wider text-xs">{workspace === 'plan' ? 'Deliverable Document' : 'Officer Report'}</span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{title}</h1>
              <Badge variant="secondary" className="text-[11px] bg-blue-50 text-blue-700 border-blue-200">{EXPLAINABILITY_LABEL[explainabilityMode]} mode</Badge>
              <StatusBadge status="provisional" />
              <div className={`${whyVisibilityClass} transition-opacity`}>
                <ProvenanceIndicator provenance={{ source: 'ai', confidence: 'medium', status: 'provisional', evidenceIds: ['ev-census-2021','ev-affordability'] }} showConfidence onOpenTrace={onOpenTrace} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500 mt-2">
              <Badge variant="outline" className="bg-slate-50 border-slate-200 text-slate-600 rounded-sm font-normal">Draft v2.3</Badge>
              <span>Last edited 18 Dec 2024</span>
              <span>by <span className="text-slate-900 font-medium">Sarah Mitchell</span></span>
              <Separator orientation="vertical" className="h-4" />
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className={`${whyVisibilityClass} transition-opacity text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-md p-1`}
                      onClick={handleWhy}
                      aria-label="Why?"
                    >
                      <HelpCircle className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="max-w-xs">
                    {whyTooltip}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
          
          <div className="flex items-center gap-2 ml-4">
            <Button 
              variant="outline" 
              size="sm" 
              onClick={onToggleMap}
              className="gap-2"
            >
              <MapIcon className="w-4 h-4" />
              Dock Map
            </Button>
            <Button 
              variant={showGuide ? "secondary" : "outline"} 
              size="sm" 
              onClick={() => setShowGuide(!showGuide)}
              className="gap-2"
            >
              <BookOpenCheck className="w-4 h-4" />
              {showGuide ? 'Hide Guide' : 'Show Guide'}
            </Button>
          </div>
        </div>
      </div>

      {/* Scrollable document body (studio middle pane) */}
      <div data-testid="studio-scroll" className="flex-1 min-h-0 overflow-y-auto">
        <div className="flex flex-col lg:flex-row min-w-0">
          {/* Editor Area */}
          <div className="flex-1 min-w-0">
            <div className="max-w-3xl mx-0 p-4 sm:p-6">
            {/* Visual embeds reintroduced from legacy Map/Visuals */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
              <div className="lg:col-span-5 bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
                <div className="px-3 py-2 flex items-center justify-between border-b border-slate-100 bg-slate-50">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                    <Camera className="w-4 h-4 text-slate-600" />
                    Visual evidence
                  </div>
                  <Badge variant="outline" className="text-[10px] bg-white">Citable</Badge>
                </div>
                <div className="p-3 flex gap-3 overflow-x-auto">
                  {mockPhotos.slice(0, 3).map((photo) => (
                    <div key={photo.id} className="flex-shrink-0 w-48 flex gap-3 items-center border rounded-md p-2">
                      <div className="w-12 h-12 bg-slate-200 rounded-md flex items-center justify-center text-[10px] text-slate-500 flex-shrink-0">
                        img
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-slate-800 truncate">{photo.caption}</div>
                        <div className="text-[10px] text-slate-500">{photo.date}</div>
                        <button
                          className="text-[10px] text-[color:var(--color-gov-blue)] hover:underline"
                          onClick={() => onOpenTrace?.({ kind: 'evidence', id: photo.id, label: photo.caption })}
                        >
                          Trace
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Inline callouts to anchor provenance and state language */}
            <div className="flex flex-wrap items-center gap-3 mb-3 text-sm">
              <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border-emerald-200">Settled: Intro</Badge>
              <Badge variant="secondary" className="bg-amber-50 text-amber-700 border-amber-200">Provisional: Housing</Badge>
              <Badge variant="secondary" className="bg-slate-100 text-slate-600 border-slate-200">Draft: Transport</Badge>
            </div>

            {/* TipTap Editor (fully interactive) */}
            <DocumentEditor 
              initialContent={workspace === 'plan' ? initialBaselineText : initialCaseworkText}
              stageId={workspace === 'plan' ? 'baseline' : 'casework'}
              explainabilityMode={explainabilityMode}
              onOpenTrace={onOpenTrace}
              placeholder="Start drafting your planning document..."
              templateToInsert={templateToInsert}
            />
          </div>
        </div>

        {/* Guide Sidebar */}
          {showGuide && (
            <div className="w-80 border-l bg-slate-50 flex-shrink-0 flex flex-col">
              <NarrativeGuide onInsertTemplate={(content) => setTemplateToInsert({ content, id: Date.now() })} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
