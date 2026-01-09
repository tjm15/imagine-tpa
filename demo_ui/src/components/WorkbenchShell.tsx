import { useEffect, useState, useCallback, useMemo } from 'react';
import { 
  ChevronLeft,
  FileText,
  Map,
  Scale,
  Camera,
  BarChart3,
  Sparkles,
  AlertCircle,
  Eye,
  Download,
  PanelRightClose,
  PanelRightOpen,
  BookOpen,
  ShieldAlert,
  Bell,
  LayoutGrid,
} from 'lucide-react';
import { WorkspaceMode, ViewMode } from '../App';
import { DocumentView } from './views/DocumentView';
import { MapViewInteractive } from './views/MapViewInteractive';
import { JudgementView } from './views/JudgementView';
import { MonitoringView } from './views/MonitoringView';
import { OverviewView } from './views/OverviewView';
import { RealityView } from './views/RealityView';
import { CoDrafterDrawer } from './codrafter/CoDrafterDrawer';
import { PatchBundleReview } from './codrafter/PatchBundleReview';
import { createDemoPatchBundle } from './codrafter/demoBundles';
import type { DraftingPhase, PatchBundle, PatchSnapshot } from './codrafter/types';
import { ContextMarginInteractive } from './layout/ContextMarginInteractive';
import { ProcessRail } from './layout/ProcessRail';
import { ReasoningTray } from './ReasoningTray';
import { TraceOverlay } from './modals/TraceOverlay';
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { Separator } from "./ui/separator";
import { useAppState, useAppDispatch } from '../lib/appState';
import { toast } from 'sonner';
import type { TraceTarget } from '../lib/trace';
import { Shell } from './Shell';
import { planBaselineDeliverableHtml } from '../fixtures/documentTemplates';
import { culpStageConfigs } from '../fixtures/extendedMockData';

type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';
type ContextSection = 'evidence' | 'policy' | 'constraints' | 'feed';

const ICON_RAIL_WIDTH_PX = 56;
const DEFAULT_LEFT_PANEL_WIDTH_PX = 320;
const DEFAULT_RIGHT_PANEL_WIDTH_PX = 360;
const MIN_PANEL_WIDTH_PX = 280;
const MAX_PANEL_WIDTH_PX = 460;
const MIN_MAIN_CONTENT_WIDTH_PX = 780;
const OVERLAY_BREAKPOINT_PX = 1280;

function clampPanelWidth(px: number) {
  return Math.min(MAX_PANEL_WIDTH_PX, Math.max(MIN_PANEL_WIDTH_PX, Math.round(px)));
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const media = window.matchMedia(query);
    const listener = () => setMatches(media.matches);
    listener();

    if (media.addEventListener) {
      media.addEventListener('change', listener);
      return () => media.removeEventListener('change', listener);
    }
    media.addListener(listener);
    return () => media.removeListener(listener);
  }, [query]);

  return matches;
}

function getStoredNumber(key: string) {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function getStoredBoolean(key: string, fallback: boolean) {
  if (typeof window === 'undefined') return fallback;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw === 'true';
}

function setStoredValue(key: string, value: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, value);
}

function sidebarKey(side: 'left' | 'right', workspace: WorkspaceMode, key: 'open' | 'width') {
  return `tpa.demo_ui.sidebar.${side}.${workspace}.${key}`;
}

function stripHtmlToText(html: string) {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function applyBaselineTransportLimitationsPatch(html: string) {
  if (html.includes('Limitations: DfT connectivity outputs')) return html;

  const insertion =
    '\n<p><em>Limitations:</em> DfT connectivity outputs do not model capacity constraints or future growth scenarios; treat results as indicative only.</p>\n';
  const marker = '<h2>Transport & Connectivity</h2>';

  if (!html.includes(marker)) {
    return `${html}\n<h2>Transport limitations</h2>${insertion}`;
  }

  const at = html.indexOf(marker) + marker.length;
  return `${html.slice(0, at)}${insertion}${html.slice(at)}`;
}

interface WorkbenchShellProps {
  workspace: WorkspaceMode;
  activeView: ViewMode;
  onViewChange: (view: ViewMode) => void;
  onWorkspaceChange: (mode: WorkspaceMode) => void;
  onBackToHome: () => void;
  projectId: string;
}

export function WorkbenchShell({
  workspace,
  activeView,
  onViewChange,
  onWorkspaceChange,
  onBackToHome,
}: WorkbenchShellProps) {
  const dispatch = useAppDispatch();
  const { currentStageId, document, adjustedSiteIds, highlightedSiteId, reasoningMoves } = useAppState();
  const currentRunId = 'run_8a4f2e';
  const currentStageName = useMemo(() => {
    if (workspace !== 'plan') return null;
    return culpStageConfigs.find((s) => s.id === currentStageId)?.name ?? currentStageId;
  }, [currentStageId, workspace]);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);
  const [explainabilityMode, setExplainabilityMode] = useState<ExplainabilityMode>('summary');
  const isOverlay = useMediaQuery(`(max-width: ${OVERLAY_BREAKPOINT_PX - 1}px)`);

  // Persisted per-workspace (desktop) sidebar state
  const [leftPanelWidthPx, setLeftPanelWidthPx] = useState(() => {
    const stored = getStoredNumber(sidebarKey('left', workspace, 'width'));
    return clampPanelWidth(stored ?? DEFAULT_LEFT_PANEL_WIDTH_PX);
  });
  const [rightPanelWidthPx, setRightPanelWidthPx] = useState(() => {
    const stored = getStoredNumber(sidebarKey('right', workspace, 'width'));
    return clampPanelWidth(stored ?? DEFAULT_RIGHT_PANEL_WIDTH_PX);
  });
  const [leftOpenDesktop, setLeftOpenDesktop] = useState(() => getStoredBoolean(sidebarKey('left', workspace, 'open'), true));
  const [rightOpenDesktop, setRightOpenDesktop] = useState(() => getStoredBoolean(sidebarKey('right', workspace, 'open'), true));

  // Session-only open state for overlay mode (prevents surprise full-screen coverage on load)
  const [leftOpenOverlay, setLeftOpenOverlay] = useState(false);
  const [rightOpenOverlay, setRightOpenOverlay] = useState(false);

  const leftPanelOpen = isOverlay ? leftOpenOverlay : leftOpenDesktop;
  const rightPanelOpen = isOverlay ? rightOpenOverlay : rightOpenDesktop;

  const [rightSection, setRightSection] = useState<ContextSection>(() => {
    if (activeView === 'overview') return 'feed';
    if (activeView === 'studio') return 'policy';
    if (activeView === 'map') return 'constraints';
    if (activeView === 'scenarios') return 'feed';
    if (activeView === 'monitoring') return 'feed';
    if (activeView === 'visuals') return 'evidence';
    return 'feed';
  });

  // Co‑drafter state (patch bundles)
  const [draftingPhase, setDraftingPhase] = useState<DraftingPhase>('controlled');
  const [coDrafterOpen, setCoDrafterOpen] = useState(false);
  const [bundleSeq, setBundleSeq] = useState(1);
  const [proposedBundles, setProposedBundles] = useState<PatchBundle[]>([]);
  const [appliedBundles, setAppliedBundles] = useState<PatchBundle[]>([]);
  const [autoAppliedBundles, setAutoAppliedBundles] = useState<PatchBundle[]>([]);
  const [reviewBundleId, setReviewBundleId] = useState<string | null>(null);
  const [bundleSnapshots, setBundleSnapshots] = useState<Record<string, PatchSnapshot>>({});

  useEffect(() => {
    // Workspace-specific persistence
    setLeftPanelWidthPx(clampPanelWidth(getStoredNumber(sidebarKey('left', workspace, 'width')) ?? DEFAULT_LEFT_PANEL_WIDTH_PX));
    setRightPanelWidthPx(clampPanelWidth(getStoredNumber(sidebarKey('right', workspace, 'width')) ?? DEFAULT_RIGHT_PANEL_WIDTH_PX));
    setLeftOpenDesktop(getStoredBoolean(sidebarKey('left', workspace, 'open'), true));
    setRightOpenDesktop(getStoredBoolean(sidebarKey('right', workspace, 'open'), true));
  }, [workspace]);

  useEffect(() => {
    setStoredValue(sidebarKey('left', workspace, 'width'), String(leftPanelWidthPx));
  }, [leftPanelWidthPx, workspace]);

  useEffect(() => {
    setStoredValue(sidebarKey('right', workspace, 'width'), String(rightPanelWidthPx));
  }, [rightPanelWidthPx, workspace]);

  useEffect(() => {
    if (isOverlay) {
      setLeftOpenOverlay(false);
      setRightOpenOverlay(false);
    }
  }, [isOverlay]);

  useEffect(() => {
    // Default right sidebar section per view
    if (activeView === 'overview') setRightSection('feed');
    else if (activeView === 'studio') setRightSection('policy');
    else if (activeView === 'map') setRightSection('constraints');
    else if (activeView === 'scenarios') setRightSection('feed');
    else if (activeView === 'visuals') setRightSection('evidence');
    else if (activeView === 'monitoring') setRightSection('feed');
    else setRightSection('feed');
  }, [activeView]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        // Close the top-most surface first.
        if (traceOpen) {
          setTraceOpen(false);
          return;
        }
        if (reviewBundleId) {
          setReviewBundleId(null);
          return;
        }
        if (coDrafterOpen) {
          setCoDrafterOpen(false);
          return;
        }
        if (isOverlay && (leftOpenOverlay || rightOpenOverlay)) {
          setLeftOpenOverlay(false);
          setRightOpenOverlay(false);
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [coDrafterOpen, isOverlay, leftOpenOverlay, reviewBundleId, rightOpenOverlay, traceOpen]);

  const leftDockWidthPx = (isOverlay ? 0 : leftPanelOpen ? leftPanelWidthPx : 0);
  const rightDockWidthPx = ICON_RAIL_WIDTH_PX + (isOverlay ? 0 : rightPanelOpen ? rightPanelWidthPx : 0);

  const setLeftPanelOpen = useCallback((open: boolean) => {
    if (isOverlay) {
      setLeftOpenOverlay(open);
      return;
    }
    setLeftOpenDesktop(open);
    setStoredValue(sidebarKey('left', workspace, 'open'), String(open));
  }, [isOverlay, workspace]);

  const setRightPanelOpen = useCallback((open: boolean) => {
    if (isOverlay) {
      setRightOpenOverlay(open);
      return;
    }
    setRightOpenDesktop(open);
    setStoredValue(sidebarKey('right', workspace, 'open'), String(open));
  }, [isOverlay, workspace]);

  const ensureSpaceForLeftPanel = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (isOverlay) return;
    if (!rightPanelOpen) return;

    const viewportWidth = window.innerWidth;
    const maxSidebarWidth = Math.max(
      MIN_PANEL_WIDTH_PX,
      viewportWidth - ICON_RAIL_WIDTH_PX * 2 - MIN_MAIN_CONTENT_WIDTH_PX,
    );

    const nextLeftWidth = Math.min(leftPanelWidthPx, maxSidebarWidth);
    const nextRightWidth = Math.min(rightPanelWidthPx, maxSidebarWidth);
    const availableWidth = viewportWidth - ICON_RAIL_WIDTH_PX * 2 - nextLeftWidth - nextRightWidth;

    if (availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setRightPanelOpen(false);
    }
  }, [isOverlay, rightPanelOpen, leftPanelWidthPx, rightPanelWidthPx, setRightPanelOpen]);

  const ensureSpaceForRightPanel = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (isOverlay) return;
    if (!leftPanelOpen) return;

    const viewportWidth = window.innerWidth;
    const maxSidebarWidth = Math.max(
      MIN_PANEL_WIDTH_PX,
      viewportWidth - ICON_RAIL_WIDTH_PX * 2 - MIN_MAIN_CONTENT_WIDTH_PX,
    );

    const nextLeftWidth = Math.min(leftPanelWidthPx, maxSidebarWidth);
    const nextRightWidth = Math.min(rightPanelWidthPx, maxSidebarWidth);
    const availableWidth = viewportWidth - ICON_RAIL_WIDTH_PX * 2 - nextLeftWidth - nextRightWidth;

    if (availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setLeftPanelOpen(false);
    }
  }, [isOverlay, leftPanelOpen, leftPanelWidthPx, rightPanelWidthPx, setLeftPanelOpen]);

  const enforceMainWidthBudget = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (isOverlay) return;

    const viewportWidth = window.innerWidth;
    const maxSidebarWidth = Math.max(
      MIN_PANEL_WIDTH_PX,
      viewportWidth - ICON_RAIL_WIDTH_PX * 2 - MIN_MAIN_CONTENT_WIDTH_PX,
    );

    setLeftPanelWidthPx((current) => {
      const next = clampPanelWidth(Math.min(current, maxSidebarWidth));
      return next === current ? current : next;
    });

    setRightPanelWidthPx((current) => {
      const next = clampPanelWidth(Math.min(current, maxSidebarWidth));
      return next === current ? current : next;
    });

    let availableWidth = viewportWidth - ICON_RAIL_WIDTH_PX * 2;
    if (leftPanelOpen) availableWidth -= Math.min(leftPanelWidthPx, maxSidebarWidth);
    if (rightPanelOpen) availableWidth -= Math.min(rightPanelWidthPx, maxSidebarWidth);

    if (availableWidth >= MIN_MAIN_CONTENT_WIDTH_PX) return;

    // Prefer to collapse the right panel first to keep the process rail visible.
    if (rightPanelOpen && availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setRightPanelOpen(false);
      availableWidth += rightPanelWidthPx;
    }

    if (leftPanelOpen && availableWidth < MIN_MAIN_CONTENT_WIDTH_PX) {
      setLeftPanelOpen(false);
    }
  }, [isOverlay, leftPanelOpen, rightPanelOpen, leftPanelWidthPx, rightPanelWidthPx, setLeftPanelOpen, setRightPanelOpen]);

  useEffect(() => {
    enforceMainWidthBudget();
    if (isOverlay) return;

    window.addEventListener('resize', enforceMainWidthBudget);
    return () => window.removeEventListener('resize', enforceMainWidthBudget);
  }, [enforceMainWidthBudget, isOverlay]);

  const startResizeLeft = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = leftPanelWidthPx;

    const onMove = (e: PointerEvent) => {
      const next = clampPanelWidth(startWidth + (e.clientX - startX));
      setLeftPanelWidthPx(next);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [leftPanelWidthPx]);

  const startResizeRight = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = rightPanelWidthPx;

    const onMove = (e: PointerEvent) => {
      const next = clampPanelWidth(startWidth + (startX - e.clientX));
      setRightPanelWidthPx(next);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [rightPanelWidthPx]);

  const openTrace = useCallback((target?: TraceTarget) => {
    setTraceTarget(target ?? { kind: 'run', label: 'Current run' });
    setTraceOpen(true);
  }, []);

  const allBundles = useMemo(
    () => [...proposedBundles, ...appliedBundles, ...autoAppliedBundles],
    [proposedBundles, appliedBundles, autoAppliedBundles],
  );

  const activeReviewBundle = useMemo(() => {
    if (!reviewBundleId) return null;
    return allBundles.find((b) => b.id === reviewBundleId) ?? null;
  }, [allBundles, reviewBundleId]);

  const canApplyBundles = workspace === 'plan' && explainabilityMode === 'summary' && activeView !== 'overview';
  const bundleReadOnlyReason =
    explainabilityMode !== 'summary'
      ? 'Read-only in Inspect/Forensic.'
      : activeView === 'overview'
        ? 'Apply disabled in Overview.'
        : workspace !== 'plan'
          ? 'Patch bundles are v1-plan only.'
          : undefined;

  const showOnMap = useCallback((siteId: string) => {
    dispatch({ type: 'APPLY_PATCH_EFFECTS', payload: { highlightedSiteId: siteId } });
    if (activeView !== 'map') {
      onViewChange('map');
    }
    toast.info(`Highlighted on map: ${siteId}`);
  }, [dispatch, activeView, onViewChange]);

  const captureSnapshot = useCallback((bundleId: string) => {
    setBundleSnapshots((prev) => {
      if (prev[bundleId]) return prev;
      return {
        ...prev,
        [bundleId]: {
          documentHtml: document.html || planBaselineDeliverableHtml,
          documentText: document.text || stripHtmlToText(document.html || planBaselineDeliverableHtml),
          adjustedSiteIds: Array.from(adjustedSiteIds),
          highlightedSiteId,
        },
      };
    });
  }, [adjustedSiteIds, document.html, document.text, highlightedSiteId]);

  const applyBundle = useCallback(
    (bundleId: string, itemIds?: string[], appliedBy: 'manual' | 'auto' = 'manual') => {
      const bundle = proposedBundles.find((b) => b.id === bundleId);
      if (!bundle) return;
      if (!canApplyBundles) {
        toast.error(bundleReadOnlyReason ?? 'Apply disabled');
        return;
      }

      captureSnapshot(bundleId);

      const selectedItemIds = itemIds?.length ? new Set(itemIds) : null;
      const shouldApplyItem = (id: string) => (selectedItemIds ? selectedItemIds.has(id) : true);

      const baseHtml = document.html || planBaselineDeliverableHtml;
      let nextHtml = baseHtml;
      let nextHighlighted = highlightedSiteId;
      const nextAdjusted = new Set(adjustedSiteIds);

      for (const item of bundle.items) {
        if (!shouldApplyItem(item.id)) continue;

        if (item.type === 'policy_text' || item.type === 'justification') {
          nextHtml = applyBaselineTransportLimitationsPatch(nextHtml);
        }

        if (item.type === 'allocation_geometry' && item.siteId) {
          nextAdjusted.add(item.siteId);
          nextHighlighted = item.siteId;
        }
      }

      dispatch({
        type: 'APPLY_PATCH_EFFECTS',
        payload: {
          document: { html: nextHtml, text: stripHtmlToText(nextHtml) },
          adjustedSiteIds: Array.from(nextAdjusted),
          highlightedSiteId: nextHighlighted,
        },
      });

      const updatedBundle: PatchBundle = {
        ...bundle,
        status: appliedBy === 'auto' ? 'auto-applied' : itemIds?.length ? 'partial' : 'applied',
        appliedAt: new Date().toISOString(),
        appliedItemIds: itemIds?.length ? itemIds : bundle.items.map((i) => i.id),
      };

      setProposedBundles((prev) => prev.filter((b) => b.id !== bundleId));
      if (appliedBy === 'auto') {
        setAutoAppliedBundles((prev) => [updatedBundle, ...prev]);
        toast.success(`AI applied: ${bundle.title}`);
      } else {
        setAppliedBundles((prev) => [updatedBundle, ...prev]);
        toast.success(itemIds?.length ? 'Applied selected changes' : 'Applied bundle');
      }
    },
    [
      adjustedSiteIds,
      canApplyBundles,
      captureSnapshot,
      dispatch,
      document.html,
      highlightedSiteId,
      proposedBundles,
      bundleReadOnlyReason,
    ],
  );

  const undoBundle = useCallback((bundleId: string) => {
    const snapshot = bundleSnapshots[bundleId];
    if (!snapshot) {
      toast.error('No snapshot recorded for this bundle');
      return;
    }

    dispatch({ type: 'RESTORE_PATCH_SNAPSHOT', payload: { snapshot } });

    const markReverted = (bundle: PatchBundle) =>
      bundle.id === bundleId ? { ...bundle, status: 'reverted' as const } : bundle;

    setAppliedBundles((prev) => prev.map(markReverted));
    setAutoAppliedBundles((prev) => prev.map(markReverted));
    toast.success('Reverted bundle');
  }, [bundleSnapshots, dispatch]);

  const requestProposal = useCallback(() => {
    const bundle = createDemoPatchBundle({ seq: bundleSeq, stageId: currentStageId });
    setBundleSeq((n) => n + 1);
    setProposedBundles((prev) => [bundle, ...prev]);
    setCoDrafterOpen(true);
    toast.success(`Proposal added (${bundle.id})`);

    if (draftingPhase === 'free' && canApplyBundles) {
      setTimeout(() => applyBundle(bundle.id, undefined, 'auto'), 250);
    }
  }, [applyBundle, bundleSeq, canApplyBundles, currentStageId, draftingPhase]);

  const handleExportClick = useCallback(() => {
    dispatch({ type: 'OPEN_MODAL', payload: { modalId: 'export', data: {} } });
  }, [dispatch]);

  const handleStageSelect = useCallback((stageId: string) => {
    dispatch({ type: 'SET_STAGE', payload: { stageId } });
  }, [dispatch]);

  // Determine if the current view should be full-bleed (no sidebars)
  const isFullBleedView = false;

  const viewConfig = workspace === 'monitoring'
    ? {
        monitoring: {
          icon: BarChart3,
          label: 'Monitoring',
          component: MonitoringView,
          description: 'Plan monitoring dashboard',
        },
      }
    : workspace === 'plan'
      ? {
          overview: {
            icon: LayoutGrid,
            label: 'Overview',
            component: OverviewView,
            description: 'CULP stage cockpit and next steps',
          },
          studio: {
            icon: FileText,
            label: 'Deliverable',
            component: DocumentView,
            description: 'HTML-native deliverable drafting with citations and figures',
          },
          map: {
            icon: Map,
            label: 'Map & Plans',
            component: MapViewInteractive,
            description: 'Visuospatial plan state: allocations, constraints, overlays',
          },
          scenarios: {
            icon: Scale,
            label: 'Scenarios',
            component: JudgementView,
            description: 'Scenario × political framing comparison and balance',
          },
          visuals: {
            icon: Camera,
            label: 'Visuals',
            component: RealityView,
            description: 'Plan–reality overlays and visual evidence',
          },
          monitoring: {
            icon: BarChart3,
            label: 'Monitoring',
            component: MonitoringView,
            description: 'CULP governance loop: signals, currency, readiness',
          },
        }
      : {
          studio: {
            icon: FileText,
            label: 'Report',
            component: DocumentView,
            description: 'Officer report drafting with inline citations',
          },
          map: {
            icon: Map,
            label: 'Assessment',
            component: MapViewInteractive,
            description: 'Site context map with constraints and evidence',
          },
          visuals: {
            icon: Camera,
            label: 'Photos',
            component: RealityView,
            description: 'Site photos and officer-facing overlays',
          },
        };

  const resolvedView: ViewMode = Object.prototype.hasOwnProperty.call(viewConfig, activeView)
    ? activeView
    : (Object.keys(viewConfig)[0] as ViewMode);

  const ActiveViewComponent = (viewConfig as Record<string, any>)[resolvedView].component;

  return (
    <Shell 
      activeMode={workspace} 
      onNavigate={onWorkspaceChange} 
      variant="project"
      onToggleSidebar={() => {
        const next = !leftPanelOpen;
        if (next) ensureSpaceForLeftPanel();
        setLeftPanelOpen(next);
      }}
      isSidebarOpen={leftPanelOpen}
    >
      <div className="h-full min-h-0 flex flex-col overflow-hidden font-sans" style={{ 
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text)'
      }}>
        {/* Top Header - Global Navigation */}
        <header className="bg-white border-b flex-shrink-0 sticky top-0 z-50 shadow-sm" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <div className="flex items-center justify-between h-14 px-4">
            {/* Left: Branding & Navigation */}
            <div className="flex items-center gap-4">
              <Button 
                variant="ghost" 
                size="icon" 
                onClick={onBackToHome}
                className="hover:bg-white/50"
                style={{ color: 'var(--color-text)' }}
              >
                <ChevronLeft className="w-5 h-5" />
              </Button>
              
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <span className="text-sm font-semibold leading-none" style={{ color: 'var(--color-ink)' }}>
                    {workspace === 'plan' ? 'Plan Studio' : workspace === 'casework' ? 'Casework' : 'Monitoring'}
                  </span>
                  <div className="flex items-center gap-1.5 text-xs mt-0.5" style={{ color: 'var(--color-text)' }}>
                      <span>Cambridge City Council</span>
                      <span style={{ color: 'var(--color-neutral-400)' }}>/</span>
                      <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                          {workspace === 'casework' ? '24/0456/FUL' : 'Local Plan 2025'}
                      </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Center: Workspace Switcher (Plan surfaces) */}
            {workspace !== 'monitoring' ? (
              <div className="flex-1 px-2 sm:px-4 md:px-6 flex justify-center min-w-0">
                <div
                  className="flex items-center gap-1 p-1 rounded-xl border bg-slate-50/80 shadow-sm overflow-x-auto"
                  style={{ borderColor: 'var(--color-neutral-300)' }}
                >
                  {(Object.entries(viewConfig) as [ViewMode, any][]).map(([key, config]) => {
                    const Icon = config.icon;
                    const isActive = resolvedView === key;

                    return (
                      <TooltipProvider key={key}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              className={`h-9 px-2 sm:px-3 rounded-lg flex items-center gap-2 text-sm font-medium transition-colors whitespace-nowrap ${
                                isActive ? 'bg-white border shadow-sm' : 'text-slate-600 hover:bg-white/70'
                              }`}
                              style={{ borderColor: isActive ? 'var(--color-neutral-300)' : 'transparent' }}
                              aria-current={isActive ? 'page' : undefined}
                              onClick={() => onViewChange(key)}
                            >
                              <Icon className="w-4 h-4" style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-text)' }} />
                              <span
                                className="hidden sm:inline leading-none"
                                style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-text)' }}
                              >
                                {config.label}
                              </span>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="bottom">{config.description}</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex-1" />
            )}

            {/* Right: Actions & User */}
            <div className="flex items-center gap-3">
              <div className="hidden lg:flex items-center gap-2 mr-2">
                  <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border" style={{
                    backgroundColor: 'rgba(245, 195, 21, 0.1)',
                    color: 'var(--color-brand-dark)',
                    borderColor: 'rgba(245, 195, 21, 0.3)'
                  }}>
                      <AlertCircle className="w-3.5 h-3.5" />
                      <span>{workspace === 'casework' ? '12 days left' : `Stage: ${currentStageName ?? '—'}`}</span>
                  </div>
              </div>

              <div className="flex items-center gap-2">
                  <TooltipProvider>
                      <Tooltip>
                          <TooltipTrigger asChild>
                              <Button 
                                size="sm" 
                                variant="default" 
                                className="shadow-sm gap-2" 
                                style={{
                                  backgroundColor: 'var(--color-brand)',
                                  color: 'var(--color-ink)'
                                }}
                                onClick={() => setCoDrafterOpen(true)}
                              >
                                  <Sparkles className="w-4 h-4" />
                                  <span className="hidden sm:inline">Co‑drafter</span>
                                  {proposedBundles.length ? (
                                    <Badge
                                      variant="outline"
                                      className="hidden md:inline-flex ml-1 h-6 text-[10px] bg-white"
                                      style={{ borderColor: 'rgba(0,0,0,0.12)', color: 'var(--color-text)' }}
                                    >
                                      Proposals {proposedBundles.length}
                                    </Badge>
                                  ) : null}
                              </Button>
                          </TooltipTrigger>
                          <TooltipContent>Open Co‑Drafter (patch bundles)</TooltipContent>
                      </Tooltip>
                  </TooltipProvider>

                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="hidden sm:flex border gap-2" 
                    style={{
                      borderColor: 'var(--color-neutral-300)',
                      color: 'var(--color-text)'
                    }}
                    onClick={handleExportClick}
                  >
                      <Download className="w-4 h-4" />
                      Export
                  </Button>
              </div>
            </div>
          </div>
          
          {/* Sub-header / Audit Bar */}
          <div className="border-b px-4 py-1.5 flex items-center justify-between text-xs" style={{
            backgroundColor: 'var(--color-surface-light)',
            borderColor: 'var(--color-neutral-300)'
          }}>
              <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5" style={{ color: 'var(--color-text)' }}>
                      <span>Current Run:</span>
                      <Badge variant="outline" className="font-mono text-[10px] h-5 px-1.5 bg-white" style={{
                        borderColor: 'var(--color-neutral-300)',
                        color: 'var(--color-text)'
                      }}>run_8a4f2e</Badge>
                  </div>
                  <button
                      onClick={() => {
                        if (traceOpen) {
                          setTraceOpen(false);
                          return;
                        }
                        openTrace({ kind: 'run', label: 'Current run' });
                      }}
                      className="flex items-center gap-1.5 hover:underline transition-colors"
                      style={{
                        color: traceOpen ? 'var(--color-accent)' : 'var(--color-text)',
                        fontWeight: traceOpen ? 500 : 400
                      }}
                  >
                      <Eye className="w-3.5 h-3.5" />
                      {traceOpen ? 'Hide Trace' : 'Show Trace'}
                  </button>
              </div>

              <div className="flex items-center gap-4">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="flex items-center gap-1" style={{ color: 'var(--color-text)' }}>
                          <Eye className="w-3.5 h-3.5" />
                          Detail:
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs text-xs">
                        <p className="font-medium mb-1">Explainability Levels</p>
                        <p><strong>Summary:</strong> Clean narrative view for reports</p>
                        <p><strong>Inspect:</strong> See evidence sources & assumptions</p>
                        <p><strong>Forensic:</strong> Full audit trail with tool runs</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  <div className="flex p-0.5 rounded-md" style={{ backgroundColor: 'var(--color-neutral-300)' }}>
                      {([
                        { id: 'summary' as const, label: 'Summary', icon: '📄' },
                        { id: 'inspect' as const, label: 'Inspect', icon: '🔍' },
                        { id: 'forensic' as const, label: 'Forensic', icon: '🔬' }
                      ]).map((mode) => (
                          <button
                              key={mode.id}
                              onClick={() => setExplainabilityMode(mode.id)}
                              className="px-2.5 py-1 rounded text-[11px] font-medium transition-all flex items-center gap-1"
                              style={{
                                backgroundColor: explainabilityMode === mode.id ? 'white' : 'transparent',
                                color: explainabilityMode === mode.id ? 'var(--color-accent)' : 'var(--color-text)',
                                boxShadow: explainabilityMode === mode.id ? '0 1px 2px rgba(0,0,0,0.08)' : 'none'
                              }}
                          >
                              <span>{mode.icon}</span>
                              <span>{mode.label}</span>
                          </button>
                      ))}
                  </div>

                  {/* 8-move breadcrumb to satisfy wayfinding */}
                  <div className="hidden md:flex items-center gap-1 pl-3 border-l" style={{ borderColor: 'var(--color-neutral-300)' }}>
                    {(
                      ['framing','issues','evidence','interpretation','considerations','balance','negotiation','positioning'] as const
                    ).map((move) => {
                      const status = reasoningMoves[move];
                      const bg = status === 'complete' ? 'bg-emerald-500' : status === 'in-progress' ? 'bg-amber-400' : 'bg-slate-200';
                      return <span key={move} className={`w-2.5 h-2.5 rounded-full ${bg}`} title={`${move} · ${status}`} />;
                    })}
                  </div>
              </div>
          </div>
        </header>

        {/* Main Content Area */}
          <div className="flex-1 min-h-0 flex overflow-hidden relative min-w-0" style={{ backgroundColor: 'var(--color-surface-light)' }}>
          {/* Overlay backdrop (session-only) */}
          {!isFullBleedView && isOverlay && (leftPanelOpen || rightPanelOpen) && (
            <button
              className="absolute inset-0 bg-black/30 z-20"
              aria-label="Close side panels"
              onClick={() => {
                setLeftPanelOpen(false);
                setRightPanelOpen(false);
              }}
            />
          )}

          {/* Left Sidebar (panel only - rail is in Shell) - Hidden in full-bleed views */}
          {!isFullBleedView && (
            <div
              className="relative flex-shrink-0 h-full bg-white border-r z-30"
              style={{ borderColor: 'var(--color-neutral-300)', width: leftDockWidthPx }}
            >
              <div className="h-full flex">
                {/* Docked Panel */}
                {!isOverlay && leftPanelOpen && (
                  <div className="h-full bg-white overflow-hidden relative" style={{ width: leftPanelWidthPx }}>
                    <ProcessRail onStageSelect={handleStageSelect} />
                    <div
                      role="separator"
                      aria-orientation="vertical"
                      onPointerDown={startResizeLeft}
                      className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
                      style={{ backgroundColor: 'transparent' }}
                    />
                  </div>
                )}
              </div>

              {/* Overlay Panel */}
              {isOverlay && leftPanelOpen && (
                <div
                  className="absolute top-0 bottom-0 left-0 bg-white shadow-xl z-40 overflow-hidden border-r"
                  style={{ width: leftPanelWidthPx, borderColor: 'var(--color-neutral-300)' }}
                >
                  <ProcessRail onStageSelect={handleStageSelect} />
                  <div
                    role="separator"
                    aria-orientation="vertical"
                    onPointerDown={startResizeLeft}
                    className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
                    style={{ backgroundColor: 'transparent' }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Main Workspace */}
          <div className="flex-1 flex overflow-hidden relative min-h-0 min-w-0">
            {/* Main View (views manage their own scrolling) */}
            <div className="flex-1 min-h-0 min-w-0 overflow-hidden flex flex-col">
              <div className="flex-1 min-h-0 min-w-0 overflow-hidden">
                <ActiveViewComponent
                  workspace={workspace}
                  explainabilityMode={explainabilityMode}
                  onOpenTrace={openTrace}
                  onViewChange={onViewChange}
                  onOpenCoDrafter={() => setCoDrafterOpen(true)}
                  onRequestPatchBundle={requestProposal}
                  onToggleMap={() => {
                    onViewChange('map');
                  }}
                />
              </div>

              {/* Reasoning Tray - Hidden in full-bleed views */}
              {!isFullBleedView && (
                <div className="flex-shrink-0">
                  <ReasoningTray runId={currentRunId || 'run_8a4f2e'} onOpenTrace={openTrace} />
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar (panel + icon rail) - Hidden in full-bleed views */}
          {!isFullBleedView && (
            <div
              className="relative flex-shrink-0 h-full bg-white border-l z-30"
              style={{ borderColor: 'var(--color-neutral-300)', width: rightDockWidthPx }}
            >
            <div className="h-full flex flex-row-reverse">
              {/* Icon Rail */}
              <div
                className="h-full flex flex-col items-center py-2 px-1 gap-1 border-l relative z-50"
                style={{ width: ICON_RAIL_WIDTH_PX, borderColor: 'var(--color-neutral-300)' }}
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        className="h-10 w-10 rounded-md flex items-center justify-center hover:bg-slate-100 transition-colors"
                        aria-label={rightPanelOpen ? 'Collapse right panel' : 'Expand right panel'}
                        onClick={() => {
                          if (rightPanelOpen) {
                            setRightPanelOpen(false);
                            return;
                          }

                          ensureSpaceForRightPanel();
                          setRightPanelOpen(true);
                        }}
                      >
                        {rightPanelOpen ? (
                          <PanelRightClose className="w-5 h-5" style={{ color: 'var(--color-text)' }} />
                        ) : (
                          <PanelRightOpen className="w-5 h-5" style={{ color: 'var(--color-text)' }} />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="left">{rightPanelOpen ? 'Collapse' : 'Expand'}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                <div className="w-8 h-px my-2" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

                {(
                  [
                    { id: 'evidence' as const, label: 'Evidence', icon: FileText },
                    { id: 'policy' as const, label: 'Policy', icon: BookOpen },
                    { id: 'constraints' as const, label: 'Constraints', icon: ShieldAlert },
                    { id: 'feed' as const, label: 'Feed', icon: Bell },
                  ] satisfies { id: ContextSection; label: string; icon: typeof FileText }[]
                ).map((item) => {
                  const Icon = item.icon;
                  const isActive = rightSection === item.id;
                  return (
                    <TooltipProvider key={item.id}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            className={`h-10 w-10 rounded-md flex items-center justify-center transition-colors ${
                              isActive ? 'bg-white shadow-sm border' : 'hover:bg-slate-100'
                            }`}
                            style={{ borderColor: isActive ? 'var(--color-neutral-300)' : 'transparent' }}
                            aria-label={item.label}
                            onClick={() => {
                              setRightSection(item.id);
                              if (!rightPanelOpen) ensureSpaceForRightPanel();
                              setRightPanelOpen(true);
                            }}
                          >
                            <Icon className="w-5 h-5" style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-text)' }} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="left">{item.label}</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  );
                })}
              </div>

              {/* Docked Panel */}
              {!isOverlay && rightPanelOpen && (
                <div className="h-full bg-white overflow-hidden relative" style={{ width: rightPanelWidthPx }}>
                  <ContextMarginInteractive
                    section={rightSection}
                    explainabilityMode={explainabilityMode}
                    workspace={workspace}
                    onOpenTrace={openTrace}
                  />
                  <div
                    role="separator"
                    aria-orientation="vertical"
                    onPointerDown={startResizeRight}
                    className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize"
                    style={{ backgroundColor: 'transparent' }}
                  />
                </div>
              )}
            </div>

            {/* Overlay Panel */}
            {isOverlay && rightPanelOpen && (
              <div
                className="absolute top-0 bottom-0 bg-white shadow-xl z-40 overflow-hidden border-l"
                style={{ width: rightPanelWidthPx, right: ICON_RAIL_WIDTH_PX, borderColor: 'var(--color-neutral-300)' }}
              >
                <ContextMarginInteractive
                  section={rightSection}
                  explainabilityMode={explainabilityMode}
                  workspace={workspace}
                  onOpenTrace={openTrace}
                />
                <div
                  role="separator"
                  aria-orientation="vertical"
                  onPointerDown={startResizeRight}
                  className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize"
                  style={{ backgroundColor: 'transparent' }}
                />
              </div>
            )}
          </div>
          )}
        </div>

        <CoDrafterDrawer
          open={coDrafterOpen}
          phase={draftingPhase}
          canApply={canApplyBundles}
          proposed={proposedBundles}
          applied={appliedBundles}
          autoApplied={autoAppliedBundles}
          onClose={() => setCoDrafterOpen(false)}
          onPhaseChange={setDraftingPhase}
          onRequestProposal={requestProposal}
          onReview={(bundleId) => {
            setReviewBundleId(bundleId);
            setCoDrafterOpen(false);
          }}
          onApply={(bundleId) => applyBundle(bundleId)}
          onUndo={undoBundle}
          onOpenTrace={openTrace}
        />

        <PatchBundleReview
          open={activeReviewBundle !== null}
          bundle={activeReviewBundle}
          phase={draftingPhase}
          canApply={canApplyBundles}
          readOnlyReason={bundleReadOnlyReason}
          onClose={() => setReviewBundleId(null)}
          onApply={(bundleId, itemIds) => applyBundle(bundleId, itemIds)}
          onShowOnMap={showOnMap}
          onOpenTrace={openTrace}
        />

        <TraceOverlay
          open={traceOpen}
          mode={explainabilityMode}
          runId="run_8a4f2e"
          target={traceTarget}
          onClose={() => setTraceOpen(false)}
          onRequestModeChange={(next) => setExplainabilityMode(next)}
        />
      </div>
    </Shell>
  );
}
