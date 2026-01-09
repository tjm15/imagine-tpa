import { useMemo, useState } from 'react';
import { HelpCircle, Sparkles, X } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';
import type { TraceTarget } from '../../lib/trace';
import type { DraftingPhase, PatchBundle, PatchItemType } from './types';

type BundleFilter = 'all' | 'policies' | 'allocations' | 'evidence' | 'issues' | 'monitoring';

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

function typeCounts(items: { type: PatchItemType }[]) {
  const counts = { policies: 0, allocations: 0, evidence: 0, issues: 0, monitoring: 0 };
  for (const item of items) {
    if (item.type === 'policy_text' || item.type === 'justification') counts.policies += 1;
    if (item.type === 'allocation_geometry') counts.allocations += 1;
    if (item.type === 'evidence_links') counts.evidence += 1;
    if (item.type === 'issue_update') {
      counts.issues += 1;
      counts.monitoring += 1;
    }
  }
  return counts;
}

function matchesFilter(bundle: PatchBundle, filter: BundleFilter) {
  if (filter === 'all') return true;
  const counts = typeCounts(bundle.items);
  return counts[filter] > 0;
}

export interface CoDrafterDrawerProps {
  open: boolean;
  phase: DraftingPhase;
  canApply: boolean;
  proposed: PatchBundle[];
  applied: PatchBundle[];
  autoApplied: PatchBundle[];
  onClose: () => void;
  onPhaseChange: (phase: DraftingPhase) => void;
  onRequestProposal: () => void;
  onReview: (bundleId: string) => void;
  onApply: (bundleId: string) => void;
  onUndo: (bundleId: string) => void;
  onOpenTrace?: (target?: TraceTarget) => void;
}

export function CoDrafterDrawer({
  open,
  phase,
  canApply,
  proposed,
  applied,
  autoApplied,
  onClose,
  onPhaseChange,
  onRequestProposal,
  onReview,
  onApply,
  onUndo,
  onOpenTrace,
}: CoDrafterDrawerProps) {
  const [filter, setFilter] = useState<BundleFilter>('all');

  const filteredProposed = useMemo(() => proposed.filter((b) => matchesFilter(b, filter)), [proposed, filter]);
  const filteredApplied = useMemo(() => applied.filter((b) => matchesFilter(b, filter)), [applied, filter]);
  const filteredAutoApplied = useMemo(() => autoApplied.filter((b) => matchesFilter(b, filter)), [autoApplied, filter]);

  const proposedCount = proposed.length;
  const autoCount = autoApplied.length;

  if (!open) return null;

  const overlayZIndex = 120;

  return (
    <>
      <button
        className="fixed inset-0 bg-black/30"
        style={{ zIndex: overlayZIndex }}
        aria-label="Close co-drafter"
        onClick={onClose}
      />
      <aside
        className="fixed right-0 top-0 bottom-0 bg-white border-l flex flex-col"
        style={{
          borderColor: 'var(--color-neutral-300)',
          zIndex: overlayZIndex + 1,
          width: 'min(420px, 100vw)',
        }}
      >
        <div className="px-4 py-3 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-600" />
              <div className="text-sm font-semibold text-slate-900">Co‑Drafter</div>
              <Badge variant="outline" className="text-[10px] bg-white font-mono">{proposedCount} proposal{proposedCount === 1 ? '' : 's'}</Badge>
              {autoCount ? (
                <Badge className="text-[10px] bg-blue-50 text-blue-700 border-blue-200">Auto‑applied {autoCount}</Badge>
              ) : null}
            </div>
            <div className="text-[11px] text-slate-600 mt-1">
              Structural proposals as patch bundles (policies · spatial · justification · issues).
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="flex-shrink-0">
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="px-4 py-3 space-y-3 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-slate-700">Drafting phase</div>
            <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-50 border" style={{ borderColor: 'var(--color-neutral-200)' }}>
              {([
                { id: 'controlled' as const, label: 'Controlled' },
                { id: 'free' as const, label: 'Free drafting' },
              ] as const).map((mode) => {
                const active = phase === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    className={`h-7 px-2.5 rounded-md text-[11px] font-medium transition-colors ${
                      active ? 'bg-white shadow-sm' : 'text-slate-600 hover:bg-white/70'
                    }`}
                    style={{ color: active ? 'var(--color-accent)' : undefined }}
                    onClick={() => onPhaseChange(mode.id)}
                  >
                    {mode.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button size="sm" className="gap-2" onClick={onRequestProposal}>
              <Sparkles className="w-4 h-4" />
              Request proposal
            </Button>
            <div className="text-[11px] text-slate-600">
              {phase === 'free' ? 'Auto-apply enabled (demo).' : 'Review and apply explicitly.'}
            </div>
          </div>

          <div className="flex flex-wrap gap-1">
            {(
              [
                { id: 'all' as const, label: 'All' },
                { id: 'policies' as const, label: 'Policies' },
                { id: 'allocations' as const, label: 'Allocations' },
                { id: 'evidence' as const, label: 'Evidence' },
                { id: 'issues' as const, label: 'Issues' },
                { id: 'monitoring' as const, label: 'Monitoring' },
              ] as const
            ).map((chip) => (
              <button
                key={chip.id}
                type="button"
                onClick={() => setFilter(chip.id)}
                className={`px-2 py-1 text-[11px] rounded-full border transition-colors ${
                  filter === chip.id ? 'border-blue-500 text-blue-700 bg-blue-50' : 'border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        <ScrollArea className="flex-1 min-h-0">
          <div className="p-4 space-y-6">
            <Section
              title="Proposed bundles"
              empty="No proposals yet. Request one above."
              bundles={filteredProposed}
              canApply={canApply}
              onReview={onReview}
              onApply={onApply}
              onUndo={onUndo}
              onOpenTrace={onOpenTrace}
            />

            <Section
              title="Applied this session"
              empty="No applied bundles yet."
              bundles={filteredApplied}
              canApply={false}
              onReview={onReview}
              onApply={onApply}
              onUndo={onUndo}
              onOpenTrace={onOpenTrace}
            />

            {phase === 'free' ? (
              <Section
                title="Auto‑applied log"
                empty="No auto-applied bundles yet."
                bundles={filteredAutoApplied}
                canApply={false}
                onReview={onReview}
                onApply={onApply}
                onUndo={onUndo}
                onOpenTrace={onOpenTrace}
              />
            ) : null}
          </div>
        </ScrollArea>
      </aside>
    </>
  );
}

function Section({
  title,
  empty,
  bundles,
  canApply,
  onReview,
  onApply,
  onUndo,
  onOpenTrace,
}: {
  title: string;
  empty: string;
  bundles: PatchBundle[];
  canApply: boolean;
  onReview: (bundleId: string) => void;
  onApply: (bundleId: string) => void;
  onUndo: (bundleId: string) => void;
  onOpenTrace?: (target?: TraceTarget) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-slate-700">{title}</div>
        <Badge variant="outline" className="text-[10px] bg-white">{bundles.length}</Badge>
      </div>
      <Separator className="my-2" />
      {bundles.length === 0 ? (
        <div className="text-sm text-slate-600 bg-slate-50 rounded-lg border border-slate-200 p-3">{empty}</div>
      ) : (
        <div className="space-y-2">
          {bundles.map((bundle) => {
            const counts = typeCounts(bundle.items);
            const summaryParts = [
              counts.policies ? `${counts.policies} policy` + (counts.policies === 1 ? '' : 'ies') : null,
              counts.allocations ? `${counts.allocations} allocation` + (counts.allocations === 1 ? '' : 's') : null,
              counts.evidence ? `${counts.evidence} evidence` : null,
              counts.issues ? `${counts.issues} issue` + (counts.issues === 1 ? '' : 's') : null,
            ].filter(Boolean) as string[];

            const statusBadge =
              bundle.status === 'reverted'
                ? <Badge className="h-5 text-[10px] bg-slate-100 text-slate-700 border-slate-200">Reverted</Badge>
                : bundle.status === 'auto-applied'
                  ? <Badge className="h-5 text-[10px] bg-blue-50 text-blue-700 border-blue-200">Auto‑applied</Badge>
                  : bundle.status === 'applied'
                    ? <Badge className="h-5 text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200">Applied</Badge>
                    : bundle.status === 'partial'
                      ? <Badge className="h-5 text-[10px] bg-amber-50 text-amber-800 border-amber-200">Partial</Badge>
                      : null;

            return (
              <div key={bundle.id} className="bg-white border border-neutral-200 rounded-xl p-3 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="text-sm font-semibold text-slate-900 truncate">{bundle.title}</div>
                      <Badge variant="outline" className="text-[10px] font-mono bg-white">{bundle.id}</Badge>
                      {statusBadge}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {severityBadge(bundle.severity)}
                      {confidenceBadge(bundle.confidence)}
                      <span className="text-[11px] text-slate-600">
                        {summaryParts.length ? summaryParts.join(' · ') : `${bundle.items.length} item${bundle.items.length === 1 ? '' : 's'}`}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="h-8 w-8 rounded-md flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                            aria-label="Open trace"
                            onClick={() => onOpenTrace?.({ kind: 'ai_hint', id: bundle.id, label: `${bundle.title} · ${bundle.id}` })}
                          >
                            <HelpCircle className="w-4 h-4" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="left">Why? (open trace)</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => onReview(bundle.id)}>
                    Review
                  </Button>

                  {canApply && bundle.status === 'proposed' ? (
                    <Button size="sm" className="h-8 text-xs" onClick={() => onApply(bundle.id)}>
                      Apply bundle
                    </Button>
                  ) : null}

                  {(bundle.status === 'applied' || bundle.status === 'auto-applied') ? (
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-slate-700" onClick={() => onUndo(bundle.id)}>
                      Undo
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
