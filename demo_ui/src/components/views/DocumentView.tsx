import { WorkspaceMode } from '../../App';
import { FileText, HelpCircle } from 'lucide-react';
import { Badge } from "../ui/badge";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { DocumentEditor } from '../editor/DocumentEditor';
import { ProvenanceIndicator, StatusBadge } from '../ProvenanceIndicator';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface DocumentViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
}

const initialBaselineText = `<h1>Place Portrait: Baseline Evidence</h1>
<h2>Introduction</h2>
<p>This place portrait provides the baseline evidence for Cambridge's local plan review under the new CULP system. It establishes the current context against which spatial strategy options will be assessed.</p>
<p>The portrait draws on multiple evidence sources including Census 2021, local monitoring data, and commissioned technical studies. All limitations are explicitly noted.</p>
<h2>Housing Context</h2>
<p>Cambridge faces acute housing pressure. The affordability ratio of 12.8x significantly exceeds both the regional average (8.2x) and represents a deterioration from 10.5x in 2015.</p>
<h2>Transport & Connectivity</h2>
<p>Cambridge benefits from strong rail connectivity to London (50 mins) and excellent local cycling infrastructure. However, strategic road capacity remains constrained, particularly on the A14 corridor.</p>`;

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

export function DocumentView({ workspace, explainabilityMode = 'summary', onOpenTrace }: DocumentViewProps) {
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
    <div className="max-w-4xl mx-auto p-8 font-sans">
      {/* Document Header */}
      <div className="mb-6 pb-4 border-b border-slate-200 group">
        <div className="flex items-center gap-2 text-sm text-blue-600 font-medium mb-3">
          <FileText className="w-4 h-4" />
          <span className="uppercase tracking-wider text-xs">{workspace === 'plan' ? 'Deliverable Document' : 'Officer Report'}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{title}</h1>
          <Badge variant="secondary" className="text-[11px] bg-blue-50 text-blue-700 border-blue-200">{explainabilityMode} mode</Badge>
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

      {/* Inline callouts to anchor provenance and state language */}
      <div className="flex flex-wrap items-center gap-3 mb-4 text-sm">
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
      />
    </div>
  );
}
