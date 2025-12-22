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

import { useState, useCallback } from 'react';
import { 
  Search, Filter, FileText, Map, Image, MessageSquare, 
  Users, ChevronRight, ExternalLink, GripVertical, 
  Plus, Eye, Download, Star, BookOpen, LayoutGrid, List as ListIcon
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
  mockPhotos,
  mockPhotosForLightbox,
  mockPolicyDetails, 
  mockConsulteeResponses,
  mockEvidence,
  PolicyDetail,
  ConsulteeResponse
} from '../../fixtures/extendedMockData';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { toast } from 'sonner';

interface ContextMarginProps {
  onEvidenceSelect?: (evidenceId: string) => void;
}

type ViewMode = 'grid' | 'list';
type EvidenceCategory = 'all' | 'documents' | 'photos' | 'policies' | 'responses';

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
  photo: typeof mockPhotos[0]; 
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
        src={photo.url + '&h=150'} 
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

export function ContextMarginInteractive({ onEvidenceSelect }: ContextMarginProps) {
  const { citedEvidence: citedEvidenceIds } = useAppState();
  const dispatch = useAppDispatch();
  
  // Convert Set of IDs to array of evidence objects
  const citedEvidence = mockEvidence.filter(ev => citedEvidenceIds.has(ev.id));
  
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState<EvidenceCategory>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const filteredEvidence = mockEvidence.filter(e => {
    const matchesSearch = searchQuery === '' || 
      e.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.summary?.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesCategory = category === 'all' || 
      (category === 'documents' && e.type === 'document') ||
      (category === 'policies' && e.type === 'policy') ||
      (category === 'responses' && e.type === 'consultation');
    
    return matchesSearch && matchesCategory;
  });

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

  return (
    <div className="h-full flex flex-col bg-neutral-50 border-l border-neutral-200">
      {/* Header */}
      <div className="p-4 bg-white border-b border-neutral-200">
        <h3 className="text-lg font-semibold mb-1">Evidence Library</h3>
        <p className="text-xs text-slate-500 mb-3">
          Drag cards into documents to cite
        </p>
        
        {/* Search */}
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search evidence..."
            className="pl-9 h-9 text-sm"
          />
        </div>
        
        {/* Category Tabs */}
        <div className="flex gap-1 flex-wrap">
          {(['all', 'documents', 'policies', 'photos', 'responses'] as EvidenceCategory[]).map((cat) => (
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
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-4">
          {/* Cited Evidence Section */}
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

          {/* Photos Section */}
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
                {mockPhotos.map((photo, index) => (
                  <PhotoCard
                    key={photo.id}
                    photo={photo}
                    onClick={() => openLightbox(index)}
                  />
                ))}
              </div>
              <Separator className="my-4" />
            </div>
          )}

          {/* Policies Section */}
          {(category === 'all' || category === 'policies') && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="w-4 h-4 text-blue-600" />
                <span className="text-xs font-medium text-slate-600">Policies</span>
              </div>
              <div className="space-y-2">
                {mockPolicyDetails.map((policy) => (
                  <PolicyPanel key={policy.id} policy={policy} />
                ))}
              </div>
              <Separator className="my-4" />
            </div>
          )}

          {/* Consultee Responses */}
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

          {/* Document Evidence */}
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
        </div>
      </ScrollArea>

      {/* Lightbox */}
      <Lightbox
        open={lightboxOpen}
        close={() => setLightboxOpen(false)}
        index={lightboxIndex}
        slides={mockPhotos.map(p => ({ src: p.url, alt: p.caption }))}
      />
    </div>
  );
}
