import type { TraceTarget } from '../../lib/trace';

export type DraftingPhase = 'controlled' | 'free';

export type BundleSeverity = 'info' | 'attention' | 'risk' | 'blocker';
export type BundleConfidence = 'high' | 'medium' | 'low';

export type PatchItemType =
  | 'policy_text'
  | 'allocation_geometry'
  | 'justification'
  | 'evidence_links'
  | 'issue_update';

export interface PatchItem {
  id: string;
  type: PatchItemType;
  title: string;
  artefactLabel: string;
  before?: string;
  after?: string;
  siteId?: string;
  traceTarget?: TraceTarget;
}

export type PatchBundleStatus =
  | 'proposed'
  | 'applied'
  | 'auto-applied'
  | 'reverted'
  | 'dismissed'
  | 'partial';

export interface PatchBundle {
  id: string;
  title: string;
  rationale: string;
  createdAt: string;
  severity: BundleSeverity;
  confidence: BundleConfidence;
  items: PatchItem[];
  status: PatchBundleStatus;
  appliedAt?: string;
  appliedItemIds?: string[];
}

export interface PatchSnapshot {
  documentHtml: string;
  documentText: string;
  adjustedSiteIds: string[];
  highlightedSiteId: string | null;
}

