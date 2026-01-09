import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, HelpCircle, MapPinned, X } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';
import type { TraceTarget } from '../../lib/trace';
import type { DraftingPhase, PatchBundle, PatchItem, PatchItemType } from './types';

function severityBadge(severity: PatchBundle['severity']) {
  if (severity === 'blocker') return <Badge className="h-5 text-[10px] bg-red-50 text-red-700 border-red-200">Blocker</Badge>;
  if (severity === 'risk') return <Badge className="h-5 text-[10px] bg-amber-50 text-amber-800 border-amber-200">Risk</Badge>;
  if (severity === 'attention') return <Badge className="h-5 text-[10px] bg-slate-100 text-slate-700 border-slate-200">Attention</Badge>;
  return <Badge variant="outline" className="h-5 text-[10px] bg-white">Info</Badge>;
}

function confidenceBadge(confidence: PatchBundle['confidence']) {
  if (confidence === 'high') return <Badge className="h-5 text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200">High</Badge>;
  if (confidence === 'low') return <Badge className="h-5 text-[10px] bg-slate-100 text-slate-700 border-slate-200">Low</Badge>;
  return <Badge variant="outline" className="h-5 text-[10px] bg-white">Med</Badge>;
}

function typeIcon(type: PatchItemType) {
  if (type === 'allocation_geometry') return <MapPinned className="w-4 h-4 text-emerald-600" />;
  if (type === 'evidence_links') return <span className="text-xs">EV</span>;
  if (type === 'issue_update') return <span className="text-xs">IS</span>;
  if (type === 'justification') return <span className="text-xs">J</span>;
  return <span className="text-xs">P</span>;
}

export interface PatchBundleReviewProps {
  open: boolean;
  bundle: PatchBundle | null;
  phase: DraftingPhase;
  canApply: boolean;
  readOnlyReason?: string;
  onClose: () => void;
  onApply: (bundleId: string, itemIds?: string[]) => void;
  onShowOnMap?: (siteId: string) => void;
  onOpenTrace?: (target?: TraceTarget) => void;
}

export function PatchBundleReview({
  open,
  bundle,
  phase,
  canApply,
  readOnlyReason,
  onClose,
  onApply,
  onShowOnMap,
  onOpenTrace,
}: PatchBundleReviewProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [applyInParts, setApplyInParts] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());

  const canApplyHere = canApply && phase !== 'controlled' ? true : canApply;

  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  if (!open || !bundle) return null;

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const applyDisabled = !canApplyHere;

  return (
    <>
      <button
        className="fixed inset-0 bg-black/30"
        style={{ zIndex: 1000 }}
        aria-label="Close bundle review"
        onClick={onClose}
      />
      <div
        className="fixed inset-4 md:inset-8 bg-white rounded-2xl shadow-2xl border border-neutral-200 overflow-hidden flex flex-col"
        style={{ zIndex: 1010 }}
      >
        <div className="px-4 py-3 border-b border-neutral-200 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-semibold text-slate-900 truncate">{bundle.title}</div>
              <Badge variant="outline" className="text-[10px] font-mono bg-white">{bundle.id}</Badge>
              {severityBadge(bundle.severity)}
              {confidenceBadge(bundle.confidence)}
              <Badge variant="outline" className="text-[10px] bg-white">
                {new Date(bundle.createdAt).toLocaleString()}
              </Badge>
            </div>
            <div className="mt-2 flex items-start gap-2">
              <div className="text-[11px] text-slate-700 leading-snug max-w-3xl">
                {bundle.rationale}
              </div>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="h-7 w-7 rounded-md flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                      aria-label="Open trace"
                      onClick={() => onOpenTrace?.({ kind: 'ai_hint', id: bundle.id, label: `${bundle.title} · ${bundle.id}` })}
                    >
                      <HelpCircle className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">Why? (open trace)</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="flex-shrink-0">
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="px-4 py-2 border-b border-neutral-200 bg-slate-50 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] bg-white">
              Drafting: {phase === 'free' ? 'Free drafting' : 'Controlled'}
            </Badge>
            {applyDisabled && readOnlyReason ? (
              <span className="text-[11px] text-slate-600">{readOnlyReason}</span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              onClick={() => setApplyInParts((v) => !v)}
            >
              {applyInParts ? 'Cancel parts' : 'Apply in parts'}
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs"
              disabled={applyDisabled || (applyInParts && selected.size === 0)}
              onClick={() => onApply(bundle.id, applyInParts ? selectedIds : undefined)}
            >
              {applyInParts ? 'Apply selected' : 'Apply bundle'}
            </Button>
          </div>
        </div>

        <ScrollArea className="flex-1 min-h-0">
          <div className="p-4 space-y-3">
            <div className="text-xs font-semibold text-slate-700">Patch items</div>
            <Separator />

            <div className="space-y-2">
              {bundle.items.map((item) => {
                const isOpen = expanded.has(item.id);
                const isChecked = selected.has(item.id);

                return (
                  <div key={item.id} className="border border-neutral-200 rounded-xl overflow-hidden bg-white">
                    <button
                      type="button"
                      className="w-full px-3 py-2.5 flex items-center gap-3 hover:bg-slate-50 transition-colors"
                      onClick={() => toggleExpanded(item.id)}
                    >
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <div className="w-7 h-7 rounded-md bg-slate-100 border border-slate-200 flex items-center justify-center flex-shrink-0">
                          {typeIcon(item.type)}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-sm font-semibold text-slate-900 truncate">{item.title}</div>
                            <Badge variant="outline" className="text-[10px] font-mono bg-white">{item.id}</Badge>
                          </div>
                          <div className="text-[11px] text-slate-600 truncate">{item.artefactLabel}</div>
                        </div>
                      </div>

                      {applyInParts ? (
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelected(item.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-4 h-4"
                          aria-label="Select patch item"
                        />
                      ) : null}

                      {isOpen ? (
                        <ChevronDown className="w-4 h-4 text-slate-500" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-500" />
                      )}
                    </button>

                    {isOpen ? (
                      <div className="border-t border-neutral-200 p-3 bg-white">
                        <ItemDiff item={item} onOpenTrace={onOpenTrace} onShowOnMap={onShowOnMap} />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </ScrollArea>
      </div>
    </>
  );
}

function ItemDiff({
  item,
  onOpenTrace,
  onShowOnMap,
}: {
  item: PatchItem;
  onOpenTrace?: (target?: TraceTarget) => void;
  onShowOnMap?: (siteId: string) => void;
}) {
  const before = item.before ?? '—';
  const after = item.after ?? '—';

  if (item.type === 'allocation_geometry') {
    return (
      <div className="space-y-2">
        <div className="text-[11px] text-slate-700">
          <span className="font-semibold">Geometry change</span> (demo preview)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <DiffPanel title="Before" tone="before" content={before} />
          <DiffPanel title="After" tone="after" content={after} />
        </div>
        <div className="flex items-center gap-2">
          {item.siteId ? (
            <Button size="sm" variant="outline" className="h-8 text-xs gap-2" onClick={() => onShowOnMap?.(item.siteId!)}>
              <MapPinned className="w-4 h-4" />
              Show on map
            </Button>
          ) : null}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-slate-700"
                  aria-label="Open trace"
                  onClick={() => onOpenTrace?.(item.traceTarget ?? { kind: 'run', label: 'Current run' })}
                >
                  <HelpCircle className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">Open trace</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <DiffPanel title="Before" tone="before" content={before} />
        <DiffPanel title="After" tone="after" content={after} />
      </div>
      <div className="flex items-center gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-slate-700"
                aria-label="Open trace"
                onClick={() => onOpenTrace?.(item.traceTarget ?? { kind: 'run', label: 'Current run' })}
              >
                <HelpCircle className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Open trace</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );
}

function DiffPanel({
  title,
  tone,
  content,
}: {
  title: string;
  tone: 'before' | 'after';
  content: string;
}) {
  const toneClasses =
    tone === 'before'
      ? 'border-red-200 bg-red-50/30'
      : 'border-emerald-200 bg-emerald-50/30';

  return (
    <div className={`border rounded-lg overflow-hidden ${toneClasses}`}>
      <div className="px-3 py-1.5 border-b border-neutral-200 bg-white/70 text-[11px] font-semibold text-slate-700">
        {title}
      </div>
      <div className="p-3">
        <pre className="text-[11px] leading-snug whitespace-pre-wrap text-slate-800">{content}</pre>
      </div>
    </div>
  );
}
