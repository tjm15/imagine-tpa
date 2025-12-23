import { useState } from 'react';
import { WorkspaceMode } from '../../App';
import { FileText, Link2, GitBranch } from 'lucide-react';
import { Badge } from "../ui/badge";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { DocumentEditor } from '../editor/DocumentEditor';
import { ProvenanceIndicator, StatusBadge } from '../ProvenanceIndicator';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface DocumentViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: () => void;
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

const inlineAnchors = [
  {
    id: 'affordability',
    title: 'Housing affordability ratios',
    summary: '12.8x vs 8.2x regional average; deterioration since 2015',
    status: 'provisional' as const,
    provenance: { source: 'ai', confidence: 'medium', status: 'provisional', evidenceIds: ['ev-affordability', 'ev-census-2021'], assumptions: ['Uses ONS East of England boundary'], limitations: 'Does not adjust for recent mortgage rate shifts.' }
  },
  {
    id: 'supply-gap',
    title: 'Housing supply gap',
    summary: '11k identified vs 27k required over plan period',
    status: 'contested' as const,
    provenance: { source: 'ai', confidence: 'medium', status: 'contested', evidenceIds: ['ev-shlaa-2024'], assumptions: ['Delivery rates match 5y average'], limitations: 'Viability testing incomplete.' }
  },
  {
    id: 'transport',
    title: 'Transport constraints',
    summary: 'A14 capacity constraint and mode shift dependency',
    status: 'draft' as const,
    provenance: { source: 'human', confidence: 'medium', status: 'draft', evidenceIds: ['ev-dft-connectivity'], limitations: 'Local congestion modelling pending.' }
  }
];

export function DocumentView({ workspace, explainabilityMode = 'summary', onOpenTrace }: DocumentViewProps) {
  const title = workspace === 'plan'
    ? 'Place Portrait: Baseline Evidence'
    : 'Officer Report: 24/0456/FUL';
  const [activeAnchor, setActiveAnchor] = useState(inlineAnchors[0]);

  const handleWhy = () => {
    onOpenTrace?.();
  };

  return (
    <div className="max-w-4xl mx-auto p-8 font-sans">
      {/* Document Header */}
      <div className="mb-6 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-2 text-sm text-blue-600 font-medium mb-3">
          <FileText className="w-4 h-4" />
          <span className="uppercase tracking-wider text-xs">{workspace === 'plan' ? 'Deliverable Document' : 'Officer Report'}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{title}</h1>
          <Badge variant="secondary" className="text-[11px] bg-blue-50 text-blue-700 border-blue-200">{explainabilityMode} mode</Badge>
          <StatusBadge status="provisional" />
          <ProvenanceIndicator provenance={{ source: 'ai', confidence: 'medium', status: 'provisional', evidenceIds: ['ev-census-2021','ev-affordability'] }} showConfidence onOpenTrace={onOpenTrace} />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500 mt-2">
          <Badge variant="outline" className="bg-slate-50 border-slate-200 text-slate-600 rounded-sm font-normal">Draft v2.3</Badge>
          <span>Last edited 18 Dec 2024</span>
          <span>by <span className="text-slate-900 font-medium">Sarah Mitchell</span></span>
          <Separator orientation="vertical" className="h-4" />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-blue-600 hover:underline flex items-center gap-1" onClick={handleWhy}>
                  <GitBranch className="w-4 h-4" />
                  Why is this here?
                </button>
              </TooltipTrigger>
              <TooltipContent>Open the trace canvas for this section</TooltipContent>
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
        placeholder="Start drafting your planning document..."
      />

      {/* Inline provenance anchors + trace */}
      <div className="mt-6 p-4 bg-slate-50 border border-slate-200 rounded-lg">
        <div className="flex items-center justify-between mb-2 text-sm">
          <div className="flex items-center gap-2 text-slate-700">
            <Link2 className="w-4 h-4 text-blue-500" />
            <span>Inline provenance anchors</span>
          </div>
          <button className="text-xs text-blue-600 hover:underline" onClick={handleWhy}>Why is this here?</button>
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {inlineAnchors.map(anchor => (
            <button
              key={anchor.id}
              onClick={() => setActiveAnchor(anchor)}
              className={`text-left p-3 rounded border transition-colors ${
                activeAnchor.id === anchor.id ? 'bg-white border-blue-200 shadow-sm' : 'bg-white/80 border-slate-200 hover:border-blue-200'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <StatusBadge status={anchor.status} />
                <ProvenanceIndicator provenance={anchor.provenance} compact onOpenTrace={onOpenTrace} />
              </div>
              <div className="text-sm font-medium text-slate-800">{anchor.title}</div>
              <p className="text-xs text-slate-600 mt-1 line-clamp-2">{anchor.summary}</p>
            </button>
          ))}
        </div>
        {activeAnchor && (
          <div className="mt-3 p-3 border border-dashed border-blue-200 rounded-md bg-white">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <GitBranch className="w-4 h-4 text-blue-600" />
              Trace detail
            </div>
            <p className="text-xs text-slate-600 mt-1">{activeAnchor.summary}</p>
            <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px]">
              {activeAnchor.provenance.evidenceIds?.map(eid => (
                <Badge key={eid} variant="outline" className="bg-slate-50">{eid}</Badge>
              ))}
              {activeAnchor.provenance.assumptions && activeAnchor.provenance.assumptions.map(a => (
                <Badge key={a} variant="secondary" className="bg-amber-50 text-amber-700 border-amber-200">Assumption</Badge>
              ))}
              {activeAnchor.provenance.limitations && (
                <Badge variant="secondary" className="bg-red-50 text-red-700 border-red-200">Limitation</Badge>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
