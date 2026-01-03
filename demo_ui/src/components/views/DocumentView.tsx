import { WorkspaceMode } from '../../App';
import { FileText, HelpCircle, Camera, Map as MapIcon } from 'lucide-react';
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { DocumentEditor } from '../editor/DocumentEditor';
import { ProvenanceIndicator, StatusBadge } from '../ProvenanceIndicator';
import { mockPhotos } from '../../fixtures/extendedMockData';
import { caseworkOfficerReportHtml, planBaselineDeliverableHtml } from '../../fixtures/documentTemplates';
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
  onOpenCoDrafter?: () => void;
  onRequestPatchBundle?: () => void;
}

export function DocumentView({
  workspace,
  explainabilityMode = 'summary',
  onOpenTrace,
  onToggleMap,
  onOpenCoDrafter,
  onRequestPatchBundle,
}: DocumentViewProps) {
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
                <ProvenanceIndicator provenance={{ source: 'ai', confidence: 'medium', status: 'provisional', evidenceIds: ['ev-census-2021', 'ev-affordability'] }} showConfidence onOpenTrace={onOpenTrace} />
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
              Map & Plans
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content Area - Split Layout */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        <div className="flex-1 min-h-0 flex flex-row min-w-0">
          {/* Editor Area */}
          <div className="flex-1 min-w-0 flex flex-col min-h-0 overflow-hidden bg-white">
            <div
              data-testid="studio-scroll"
              className="flex-1 min-h-0 overflow-y-auto"
              style={{ overflowY: 'auto' }}
            >
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
                          <img
                            src={photo.url}
                            alt={photo.caption}
                            className="w-12 h-12 rounded-md border border-slate-200 bg-slate-50 object-cover flex-shrink-0"
                            loading="lazy"
                          />
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
                  initialContent={workspace === 'plan' ? planBaselineDeliverableHtml : caseworkOfficerReportHtml}
                  stageId={workspace === 'plan' ? 'baseline' : 'casework'}
                  explainabilityMode={explainabilityMode}
                  onOpenTrace={onOpenTrace}
                  onOpenCoDrafter={onOpenCoDrafter}
                  onRequestPatchBundle={onRequestPatchBundle}
                  placeholder="Start drafting your planning document..."
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
