/**
 * Interactive Context Margin with Drag-Drop Evidence
 * 
 * Features:
 * - Draggable evidence cards
 * - Photo thumbnails with lightbox
 * - Policy expansion panels
 * - Consultee responses
 * - Filter and search
 */

import { useState, useCallback, useMemo } from 'react';
import { 
  Search, FileText, Map, Image, MessageSquare, 
  Users, ChevronRight, ExternalLink, GripVertical, 
  Plus, Eye, Star, BookOpen, LayoutGrid, List as ListIcon, HelpCircle,
} from 'lucide-react';
import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import Lightbox from 'yet-another-react-lightbox';
import 'yet-another-react-lightbox/styles.css';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { 
  mockPhotosForLightbox,
  mockPolicyDetails, 
  mockConsulteeResponses,
  mockEvidence,
  PolicyDetail,
  ConsulteeResponse
} from '../../fixtures/extendedMockData';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { toast } from 'sonner';
import type { TraceTarget } from '../../lib/trace';

import { WorkspaceMode } from '../../App';

interface ContextMarginProps {
  onEvidenceSelect?: (evidenceId: string) => void;
  section?: ContextSection;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
  workspace?: WorkspaceMode;
}

type ViewMode = 'grid' | 'list';
type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';
type ContextSection = 'evidence' | 'policy' | 'constraints' | 'feed';
type EvidenceCategory = 'all' | 'documents' | 'photos' | 'responses';
type DemoFilter = 'members-briefed' | 'site-shlaa' | 'consultation-heat';

function WhyIconButton({ onClick, tooltip }: { onClick?: () => void; tooltip: string }) {
  return (
    <button
      type="button"
      className="h-7 w-7 rounded-md flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
      aria-label="Open trace"
      title={tooltip}
      onClick={onClick}
    >
      <HelpCircle className="w-4 h-4" />
    </button>
  );
}

// Draggable Evidence Card Component
function DraggableEvidenceCard({ 
  evidence, 
  onSelect 
}: { 
  evidence: typeof mockEvidence[0]; 
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: evidence.id,
    data: { type: 'evidence', evidence }
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    opacity: isDragging ? 0.5 : 1,
  };

  const getTypeIcon = () => {
    switch (evidence.type) {
      case 'policy':
        return <BookOpen className="w-4 h-4 text-blue-600" />;
      case 'map':
        return <Map className="w-4 h-4 text-green-600" />;
      case 'consultation':
        return <MessageSquare className="w-4 h-4 text-purple-600" />;
      default:
        return <FileText className="w-4 h-4 text-slate-600" />;
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-white rounded-lg border border-neutral-200 p-3 cursor-grab active:cursor-grabbing transition-shadow ${
        isDragging ? 'shadow-lg ring-2 ring-blue-200' : 'hover:shadow-md'
      }`}
    >
      {/* Drag Handle */}
      <div className="flex items-start gap-2">
        <button
          {...attributes}
          {...listeners}
          className="p-1 -ml-1 text-slate-400 hover:text-slate-600"
        >
          <GripVertical className="w-4 h-4" />
        </button>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {getTypeIcon()}
            <span className="text-sm font-medium truncate">{evidence.title}</span>
          </div>
          
          <p className="text-xs text-slate-500 line-clamp-2 mb-2">
            {evidence.summary}
          </p>
          
          <div className="flex items-center justify-between">
            <Badge variant="outline" className="text-[10px]">
              {evidence.type}
            </Badge>
            <div className="flex items-center gap-1">
              <button 
                onClick={onSelect}
                className="p-1 text-slate-400 hover:text-blue-600"
                title="View details"
              >
                <Eye className="w-3.5 h-3.5" />
              </button>
              <button 
                className="p-1 text-slate-400 hover:text-green-600"
                title="Star"
              >
                <Star className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Photo Card with Lightbox Trigger
function PhotoCard({ 
  photo, 
  onClick 
}: { 
  photo: typeof mockPhotosForLightbox[0]; 
  onClick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `photo-${photo.id}`,
    data: { type: 'photo', photo }
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={`relative rounded-lg overflow-hidden cursor-grab active:cursor-grabbing group ${
        isDragging ? 'shadow-lg ring-2 ring-blue-200' : ''
      }`}
      onClick={onClick}
    >
      <img 
        src={photo.thumbnailUrl || photo.url + '&h=150'} 
        alt={photo.caption}
        className="w-full h-24 object-cover"
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center">
        <Eye className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2">
        <p className="text-[10px] text-white truncate">{photo.caption}</p>
      </div>
    </div>
  );
}

// Policy Expansion Panel
function PolicyPanel({ policy }: { policy: PolicyDetail }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const dispatch = useAppDispatch();

  const handleCite = () => {
    dispatch({
      type: 'ADD_CITATION',
      payload: {
        evidenceId: policy.id,
        text: policy.reference,
      }
    });
    toast.success(`Cited ${policy.reference}`);
  };

  return (
    <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 p-3 hover:bg-slate-50 transition-colors"
      >
        <BookOpen className="w-4 h-4 text-blue-600" />
        <div className="flex-1 text-left">
          <span className="text-sm font-medium">{policy.reference}</span>
          <p className="text-xs text-slate-500">{policy.title}</p>
        </div>
        <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
      </button>
      
      {isExpanded && (
        <div className="border-t border-neutral-200 p-3 bg-slate-50">
          <p className="text-xs text-slate-700 mb-3">{policy.fullText}</p>
          
          {policy.caseReferences && policy.caseReferences.length > 0 && (
            <div className="mb-3">
              <span className="text-[10px] font-medium text-slate-600">Case References:</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {policy.caseReferences.map((ref: string, i: number) => (
                  <Badge key={i} variant="secondary" className="text-[9px]">
                    {ref}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="flex-1 text-xs gap-1" onClick={handleCite}>
              <Plus className="w-3 h-3" />
              Cite
            </Button>
            <Button variant="ghost" size="sm" className="text-xs gap-1">
              <ExternalLink className="w-3 h-3" />
              Source
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Consultee Response Card
function ConsulteeCard({ response }: { response: ConsulteeResponse }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const getStatusColor = () => {
    switch (response.status) {
      case 'support':
        return 'text-green-600';
      case 'objection':
        return 'text-red-600';
      case 'holding':
        return 'text-amber-600';
      default:
        return 'text-slate-600';
    }
  };

  const getStatusLabel = () => {
    switch (response.status) {
      case 'no-objection': return 'No Objection';
      case 'objection': return 'Objection';
      case 'holding': return 'Holding';
      case 'support': return 'Support';
      default: return response.status;
    }
  };

  return (
    <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 p-3 hover:bg-slate-50 transition-colors"
      >
        <Users className="w-4 h-4 text-purple-600" />
        <div className="flex-1 text-left">
          <span className="text-sm font-medium">{response.consultee}</span>
          <p className={`text-xs font-medium ${getStatusColor()}`}>
            {getStatusLabel()}
          </p>
        </div>
        <Badge variant="outline" className="text-[10px]">
          {response.receivedDate}
        </Badge>
      </button>
      
      {isExpanded && (
        <div className="border-t border-neutral-200 p-3 bg-slate-50">
          <p className="text-xs text-slate-700 mb-2">{response.summary}</p>
          
          {response.conditions && response.conditions.length > 0 && (
            <div className="bg-amber-50 rounded p-2 text-xs text-amber-700">
              <strong>Conditions:</strong> {response.conditions.join('; ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ContextMarginInteractive({
  onEvidenceSelect,
  section = 'evidence',
  explainabilityMode = 'summary',
  onOpenTrace,
  workspace = 'plan',
}: ContextMarginProps) {
  const { citedEvidence: citedEvidenceIds } = useAppState();
  const dispatch = useAppDispatch();

  const citedEvidence = useMemo(() => mockEvidence.filter((ev) => citedEvidenceIds.has(ev.id)), [citedEvidenceIds]);

  // Evidence UI state
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState<EvidenceCategory>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [demoFilter, setDemoFilter] = useState<DemoFilter | null>(() => (workspace === 'plan' ? 'members-briefed' : null));

  // Policy UI state
  const [policySearchQuery, setPolicySearchQuery] = useState('');

  const filteredEvidence = useMemo(() => {
    return mockEvidence.filter((e) => {
      if (e.type === 'policy') return false;

      const matchesSearch =
        searchQuery === '' ||
        e.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        e.summary?.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCategory =
        category === 'all' ||
        (category === 'documents' && e.type === 'document') ||
        (category === 'responses' && e.type === 'consultation');

      const matchesFilter =
        demoFilter === null ||
        (demoFilter === 'members-briefed' && e.source === 'member briefing') ||
        (demoFilter === 'site-shlaa' && e.title.toLowerCase().includes('shlaa')) ||
        (demoFilter === 'consultation-heat' && e.type === 'consultation');

      return matchesSearch && matchesCategory && matchesFilter;
    });
  }, [searchQuery, category, demoFilter]);

  const filteredPolicies = useMemo(() => {
    const q = policySearchQuery.trim().toLowerCase();
    if (!q) return mockPolicyDetails;
    return mockPolicyDetails.filter((p) => {
      return (
        p.reference.toLowerCase().includes(q) ||
        p.title.toLowerCase().includes(q) ||
        p.fullText.toLowerCase().includes(q)
      );
    });
  }, [policySearchQuery]);

  const handleEvidenceSelect = useCallback((evidenceId: string) => {
    onEvidenceSelect?.(evidenceId);
    dispatch({
      type: 'OPEN_MODAL',
      payload: { modalId: 'evidence-detail', data: { evidenceId } }
    });
  }, [onEvidenceSelect, dispatch]);

  const openLightbox = useCallback((index: number) => {
    setLightboxIndex(index);
    setLightboxOpen(true);
  }, []);

  const curatedPulls = useMemo(() => [
    {
      id: 'cur-1',
      title: 'Member Briefing: Housing Delivery (Dec 2024)',
      why: 'Sets political steer for uplift in brownfield allocations and town centre densification.',
      tag: 'Political framing',
      trace: 'FR-01 · CULP framing move',
      traceTarget: { kind: 'ai_hint' as const, id: 'high-growth', label: 'Political framing steer' },
    },
    {
      id: 'cur-2',
      title: 'Policy H2: Mix & Tenure (Reg 18 draft)',
      why: 'Critical policy for viability sensitivity; cite for minimum 40% affordable ask.',
      tag: 'Policy-critical',
      trace: 'EV-17 · Evidence move',
      traceTarget: { kind: 'policy' as const, id: 'pol-h1', label: 'Policy H2: Mix & Tenure' },
    },
    {
      id: 'cur-3',
      title: 'SHLAA/045 Site Sheet',
      why: 'Top candidate allocation; aligns with “Homes first” political framing and high PTAL.',
      tag: 'Site dossier',
      trace: 'INT-04 · Interpretation move',
      traceTarget: { kind: 'evidence' as const, id: 'ev-transport-dft', label: 'DfT Connectivity Tool output' },
    },
  ], []);

  const constraints = useMemo(() => [
    { id: 'gb', title: 'Green Belt', detail: 'Designation intersects northern edge (demo)', severity: 'info' as const },
    { id: 'fz', title: 'Flood Zones', detail: 'Zone 2/3 present along river corridor (demo)', severity: 'attention' as const },
    { id: 'ca', title: 'Conservation Areas', detail: 'Multiple areas within centre; character sensitivity', severity: 'attention' as const },
    { id: 'tn', title: 'Transport Network', detail: 'Active travel emphasis; assumptions apply', severity: 'info' as const },
  ], []);

  const sidebarTitle = section === 'evidence'
    ? 'Evidence'
    : section === 'policy'
      ? 'Policy'
      : section === 'constraints'
        ? 'Constraints'
        : 'Feed';

  const sidebarSubtitle = section === 'evidence'
    ? 'Drag cards into the editor to cite'
    : section === 'policy'
      ? 'Normative context and clauses'
      : section === 'constraints'
        ? 'Spatial / statutory triggers'
        : 'What was pinned, cited, or updated';

  return (
    <div className="h-full flex flex-col bg-neutral-50 overflow-hidden min-h-0">
      {/* Header */}
      <div className="p-4 bg-white border-b border-neutral-200 sticky top-0 z-10 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">{sidebarTitle}</h3>
            <p className="text-xs text-slate-500">{sidebarSubtitle}</p>
          </div>
          <Badge variant="secondary" className="text-[10px]">Demo</Badge>
        </div>

        {section === 'evidence' && (
          <>
            <div className="relative mt-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search evidence..."
                className="pl-9 h-9 text-sm"
              />
            </div>

            <div className="flex gap-1 flex-wrap mt-3 mb-2">
              {(['all', 'documents', 'photos', 'responses'] as EvidenceCategory[]).map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={`px-2 py-1 text-xs rounded-full transition-colors ${
                    category === cat
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </button>
              ))}
            </div>

            <div className="flex gap-1 flex-wrap">
              {([
                { id: 'members-briefed', label: 'Members briefed' },
                { id: 'site-shlaa', label: 'SHLAA focus' },
                { id: 'consultation-heat', label: 'Consultation heat' },
              ] as { id: DemoFilter; label: string }[]).map((f) => (
                <button
                  key={f.id}
                  onClick={() => setDemoFilter(prev => prev === f.id ? null : f.id)}
                  className={`px-2 py-1 text-[11px] rounded-full border transition-colors ${
                    demoFilter === f.id
                      ? 'border-blue-500 text-blue-700 bg-blue-50'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </>
        )}

        {section === 'policy' && (
          <div className="relative mt-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={policySearchQuery}
              onChange={(e) => setPolicySearchQuery(e.target.value)}
              placeholder="Search policies..."
              className="pl-9 h-9 text-sm"
            />
          </div>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3 space-y-4 pb-6">
          {section === 'evidence' && (
            <>
              {/* Cited Evidence */}
              {citedEvidence.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Star className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-medium text-slate-600">Cited ({citedEvidence.length})</span>
                  </div>
                  <div className="space-y-2">
                    {citedEvidence.map((ev) => (
                      <DraggableEvidenceCard
                        key={ev.id}
                        evidence={ev}
                        onSelect={() => handleEvidenceSelect(ev.id)}
                      />
                    ))}
                  </div>
                  <Separator className="my-4" />
                </div>
              )}

              {(category === 'all' || category === 'photos') && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Image className="w-4 h-4 text-green-600" />
                      <span className="text-xs font-medium text-slate-600">Site Photos</span>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => setViewMode('grid')}
                        className={`p-1 rounded ${viewMode === 'grid' ? 'bg-slate-200' : 'hover:bg-slate-100'}`}
                      >
                        <LayoutGrid className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setViewMode('list')}
                        className={`p-1 rounded ${viewMode === 'list' ? 'bg-slate-200' : 'hover:bg-slate-100'}`}
                      >
                        <ListIcon className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className={viewMode === 'grid' ? 'grid grid-cols-2 gap-2' : 'space-y-2'}>
                    {mockPhotosForLightbox.map((photo, index) => (
                      <PhotoCard key={photo.id} photo={photo} onClick={() => openLightbox(index)} />
                    ))}
                  </div>
                  <Separator className="my-4" />
                </div>
              )}

              {(category === 'all' || category === 'responses') && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-4 h-4 text-purple-600" />
                    <span className="text-xs font-medium text-slate-600">Consultee Responses</span>
                  </div>
                  <div className="space-y-2">
                    {mockConsulteeResponses.map((response) => (
                      <ConsulteeCard key={response.id} response={response} />
                    ))}
                  </div>
                  <Separator className="my-4" />
                </div>
              )}

              {(category === 'all' || category === 'documents') && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-slate-600" />
                    <span className="text-xs font-medium text-slate-600">Documents</span>
                  </div>
                  <div className="space-y-2">
                    {filteredEvidence.map((evidence) => (
                      <DraggableEvidenceCard
                        key={evidence.id}
                        evidence={evidence}
                        onSelect={() => handleEvidenceSelect(evidence.id)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {section === 'policy' && (
            <div className="space-y-2">
              {filteredPolicies.map((policy) => (
                <PolicyPanel key={policy.id} policy={policy} />
              ))}
            </div>
          )}

          {section === 'constraints' && (
            <div className="space-y-2">
              {constraints.map((c) => (
                <div
                  key={c.id}
                  className="bg-white rounded-lg border border-neutral-200 p-3"
                  style={{
                    borderLeftWidth: 3,
                    borderLeftColor: c.severity === 'attention' ? 'var(--color-warning)' : 'var(--color-neutral-300)'
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-800">{c.title}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {c.severity === 'attention' ? 'Review' : 'Info'}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{c.detail}</p>
                </div>
              ))}
              <div className="text-[11px] text-slate-500 px-1">
                Layer provenance and currency are shown in Trace (Inspect/Forensic).
              </div>
            </div>
          )}

          {section === 'feed' && (
            <div className="space-y-4">
              <div className="bg-white border border-neutral-200 rounded-xl p-3 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Star className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-semibold text-slate-700">Pinned for this run</span>
                  </div>
                </div>
                <div className="space-y-2">
                  {curatedPulls.map((item) => (
                    <div key={item.id} className="p-2 rounded-lg border border-neutral-200 bg-slate-50">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="secondary" className="text-[10px]">{item.tag}</Badge>
                        <span className="text-sm font-medium text-slate-800">{item.title}</span>
                      </div>
                      <p className="text-xs text-slate-600 mb-2 line-clamp-2">{item.why}</p>
                      <div className="flex items-center justify-between gap-2 text-[11px] text-slate-600">
                        <Badge variant="outline" className="text-[10px]">{item.trace}</Badge>
                        <WhyIconButton
                          tooltip={
                            explainabilityMode === 'forensic'
                              ? 'Open trace'
                              : explainabilityMode === 'inspect'
                                ? 'Inspect chain · 2–3 sources (demo)'
                                : 'Based on logged move chain (demo)'
                          }
                          onClick={() => onOpenTrace?.(item.traceTarget)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {citedEvidence.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Star className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-medium text-slate-600">Cited ({citedEvidence.length})</span>
                  </div>
                  <div className="space-y-2">
                    {citedEvidence.map((ev) => (
                      <DraggableEvidenceCard
                        key={ev.id}
                        evidence={ev}
                        onSelect={() => handleEvidenceSelect(ev.id)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Lightbox */}
      <Lightbox
        open={lightboxOpen}
        close={() => setLightboxOpen(false)}
        index={lightboxIndex}
        slides={mockPhotosForLightbox.map(p => ({ src: p.fullUrl || p.url, alt: p.caption }))}
      />
    </div>
  );
}
