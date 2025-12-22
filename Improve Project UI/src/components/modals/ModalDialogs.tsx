/**
 * Modal Dialogs for Planning UI
 * 
 * Provides various modal dialogs:
 * - Evidence Detail Sheet
 * - Site Assessment Modal
 * - Gateway Check Modal
 * - Consideration Form Modal
 * - Export Dialog
 * - AI Draft Modal
 */

import { useState, useEffect, useCallback } from 'react';
import { 
  X, FileText, Map, CheckCircle2, AlertTriangle, Download, 
  Sparkles, Plus, Minus, Scale, ChevronRight, ExternalLink,
  Loader2, Copy, Eye, BookOpen, MapPin, Calendar, User
} from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Progress } from '../ui/progress';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { siteAllocations, mockPolicyDetails, culpStageConfigs, mockEvidence } from '../../fixtures/extendedMockData';
import { simulateBalance } from '../../lib/aiSimulation';
import { toast } from 'sonner';
import { Consideration } from '../../fixtures/mockData';

// Helper to get unified valence/direction from Consideration
const getValence = (c: Consideration): 'for' | 'against' | 'neutral' => {
  if (c.valence) return c.valence;
  if (c.direction === 'supports') return 'for';
  if (c.direction === 'against') return 'against';
  return 'neutral';
};

// Modal Container
interface ModalContainerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}

export function ModalContainer({ 
  isOpen, 
  onClose, 
  title, 
  subtitle, 
  size = 'md', 
  children 
}: ModalContainerProps) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEsc);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className={`relative bg-white rounded-xl shadow-2xl w-full ${sizeClasses[size]} mx-4 max-h-[90vh] flex flex-col animate-in fade-in zoom-in-95 duration-200`}>
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b border-neutral-200">
          <div>
            <h2 className="text-lg font-semibold">{title}</h2>
            {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}

// Evidence Detail Modal
interface EvidenceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  evidenceId: string | null;
}

export function EvidenceDetailModal({ isOpen, onClose, evidenceId }: EvidenceDetailModalProps) {
  const dispatch = useAppDispatch();
  const evidence = mockEvidence.find(e => e.id === evidenceId);

  const handleCite = () => {
    if (evidence) {
      dispatch({
        type: 'ADD_CITATION',
        payload: { evidenceId: evidence.id, text: evidence.title, range: null }
      });
      toast.success('Evidence cited');
    }
  };

  if (!evidence) return null;

  return (
    <ModalContainer
      isOpen={isOpen}
      onClose={onClose}
      title={evidence.title}
      subtitle={evidence.type}
      size="lg"
    >
      <div className="p-4 space-y-4">
        {/* Summary */}
        <div>
          <h3 className="text-sm font-medium text-slate-600 mb-1">Summary</h3>
          <p className="text-sm">{evidence.summary}</p>
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <h3 className="text-sm font-medium text-slate-600 mb-1">Source</h3>
            <p className="text-sm">{evidence.source || 'Internal'}</p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-slate-600 mb-1">Date</h3>
            <p className="text-sm">{evidence.date || '2024'}</p>
          </div>
        </div>

        {/* Relevance */}
        <div>
          <h3 className="text-sm font-medium text-slate-600 mb-1">Relevance Score</h3>
          <div className="flex items-center gap-2">
            <Progress value={(evidence.weight || 0.5) * 100} className="h-2 flex-1" />
            <span className="text-sm font-medium">{Math.round((evidence.weight || 0.5) * 100)}%</span>
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex gap-2">
          <Button variant="default" className="gap-2" onClick={handleCite}>
            <Plus className="w-4 h-4" />
            Cite in Document
          </Button>
          <Button variant="outline" className="gap-2">
            <ExternalLink className="w-4 h-4" />
            Open Source
          </Button>
          <Button variant="ghost" className="gap-2">
            <Copy className="w-4 h-4" />
            Copy Reference
          </Button>
        </div>
      </div>
    </ModalContainer>
  );
}

// Site Assessment Modal
interface SiteAssessmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  siteId: string | null;
}

export function SiteAssessmentModal({ isOpen, onClose, siteId }: SiteAssessmentModalProps) {
  const site = siteAllocations.features.find(f => f.properties?.id === siteId);

  if (!site) return null;

  const props = site.properties!;

  return (
    <ModalContainer
      isOpen={isOpen}
      onClose={onClose}
      title={props.name as string}
      subtitle={`Site Reference: ${props.id}`}
      size="xl"
    >
      <div className="p-4 space-y-4">
        {/* Key Stats */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{props.capacity}</div>
            <div className="text-xs text-slate-500">Dwelling Capacity</div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{props.area || 'N/A'}</div>
            <div className="text-xs text-slate-500">Hectares</div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <Badge 
              variant={props.status === 'committed' ? 'default' : 'outline'}
              className="text-sm"
            >
              {props.status as string}
            </Badge>
            <div className="text-xs text-slate-500 mt-1">Status</div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <div className={`text-2xl font-bold ${props.greenBelt ? 'text-amber-600' : 'text-slate-400'}`}>
              {props.greenBelt ? 'Yes' : 'No'}
            </div>
            <div className="text-xs text-slate-500">Green Belt</div>
          </div>
        </div>

        {/* Constraints */}
        {(props.constraints as string[])?.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-slate-600 mb-2">Constraints</h3>
            <div className="flex flex-wrap gap-2">
              {(props.constraints as string[]).map((c) => (
                <Badge key={c} variant="secondary">{c}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Assessment Criteria */}
        <div>
          <h3 className="text-sm font-medium text-slate-600 mb-2">Sustainability Assessment</h3>
          <div className="space-y-2">
            {['Accessibility', 'Biodiversity', 'Flood Risk', 'Heritage', 'Landscape'].map((criterion) => {
              const score = Math.random(); // Demo purposes
              return (
                <div key={criterion} className="flex items-center gap-3">
                  <span className="text-sm w-28">{criterion}</span>
                  <Progress value={score * 100} className="h-2 flex-1" />
                  <span className={`text-sm w-16 text-right ${
                    score > 0.7 ? 'text-green-600' : score > 0.4 ? 'text-amber-600' : 'text-red-600'
                  }`}>
                    {score > 0.7 ? 'Good' : score > 0.4 ? 'Medium' : 'Poor'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex gap-2">
          <Button variant="default" className="gap-2">
            <Plus className="w-4 h-4" />
            Add to Shortlist
          </Button>
          <Button variant="outline" className="gap-2">
            <Map className="w-4 h-4" />
            View on Map
          </Button>
          <Button variant="ghost" className="gap-2">
            <Download className="w-4 h-4" />
            Export Assessment
          </Button>
        </div>
      </div>
    </ModalContainer>
  );
}

// Consideration Form Modal
interface ConsiderationFormModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ConsiderationFormModal({ isOpen, onClose }: ConsiderationFormModalProps) {
  const dispatch = useAppDispatch();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [valence, setValence] = useState<'for' | 'against' | 'neutral'>('neutral');
  const [weight, setWeight] = useState(50);
  const [linkedEvidence, setLinkedEvidence] = useState<string[]>([]);

  const handleSubmit = () => {
    if (!title.trim()) {
      toast.error('Please enter a title');
      return;
    }

    // Map slider weight to weight category
    const weightCategory = weight >= 80 ? 'decisive' 
      : weight >= 60 ? 'significant' 
      : weight >= 40 ? 'moderate' 
      : 'limited';

    // Map valence to direction
    const direction = valence === 'for' ? 'supports' 
      : valence === 'against' ? 'against' 
      : 'neutral';

    dispatch({
      type: 'ADD_CONSIDERATION',
      payload: {
        id: `consideration-${Date.now()}`,
        issue: title,
        interpretationId: 'manual-entry',
        policyIds: [],
        weight: weightCategory as 'decisive' | 'significant' | 'moderate' | 'limited',
        direction: direction as 'supports' | 'against' | 'neutral',
        settled: false,
        // UI aliases
        title,
        description,
        valence,
        linkedEvidence,
      }
    });

    toast.success('Consideration added to ledger');
    onClose();
    setTitle('');
    setDescription('');
    setValence('neutral');
    setWeight(50);
  };

  return (
    <ModalContainer
      isOpen={isOpen}
      onClose={onClose}
      title="Add Consideration"
      subtitle="Add a material consideration to the planning balance"
      size="md"
    >
      <div className="p-4 space-y-4">
        {/* Title */}
        <div>
          <label className="text-sm font-medium text-slate-600">Title</label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Impact on Green Belt"
            className="mt-1"
          />
        </div>

        {/* Description */}
        <div>
          <label className="text-sm font-medium text-slate-600">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the consideration and its relevance..."
            className="mt-1 w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>

        {/* Valence */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">Position</label>
          <div className="flex gap-2">
            <button
              onClick={() => setValence('for')}
              className={`flex-1 p-3 rounded-lg border-2 transition-colors ${
                valence === 'for' 
                  ? 'border-green-500 bg-green-50 text-green-700' 
                  : 'border-neutral-200 hover:border-green-200'
              }`}
            >
              <Plus className="w-5 h-5 mx-auto mb-1" />
              <span className="text-sm">For</span>
            </button>
            <button
              onClick={() => setValence('neutral')}
              className={`flex-1 p-3 rounded-lg border-2 transition-colors ${
                valence === 'neutral' 
                  ? 'border-slate-500 bg-slate-50 text-slate-700' 
                  : 'border-neutral-200 hover:border-slate-200'
              }`}
            >
              <Scale className="w-5 h-5 mx-auto mb-1" />
              <span className="text-sm">Neutral</span>
            </button>
            <button
              onClick={() => setValence('against')}
              className={`flex-1 p-3 rounded-lg border-2 transition-colors ${
                valence === 'against' 
                  ? 'border-red-500 bg-red-50 text-red-700' 
                  : 'border-neutral-200 hover:border-red-200'
              }`}
            >
              <Minus className="w-5 h-5 mx-auto mb-1" />
              <span className="text-sm">Against</span>
            </button>
          </div>
        </div>

        {/* Weight */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-600">Weight</label>
            <span className="text-sm text-slate-500">{weight}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={weight}
            onChange={(e) => setWeight(parseInt(e.target.value))}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-slate-400">
            <span>Minor</span>
            <span>Moderate</span>
            <span>Significant</span>
          </div>
        </div>

        {/* Evidence Link */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">Link Evidence</label>
          <div className="flex flex-wrap gap-2">
            {mockEvidence.slice(0, 4).map((ev) => (
              <button
                key={ev.id}
                onClick={() => setLinkedEvidence(prev => 
                  prev.includes(ev.id) ? prev.filter(id => id !== ev.id) : [...prev, ev.id]
                )}
                className={`px-2 py-1 text-xs rounded-full transition-colors ${
                  linkedEvidence.includes(ev.id)
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {ev.title}
              </button>
            ))}
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="default" onClick={handleSubmit}>
            Add Consideration
          </Button>
        </div>
      </div>
    </ModalContainer>
  );
}

// Export Dialog
interface ExportDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ExportDialog({ isOpen, onClose }: ExportDialogProps) {
  const [format, setFormat] = useState<'pdf' | 'docx' | 'html' | 'json'>('pdf');
  const [includeOptions, setIncludeOptions] = useState({
    considerations: true,
    evidence: true,
    map: true,
    provenance: true,
  });
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    // Simulate export
    await new Promise(resolve => setTimeout(resolve, 2000));
    setIsExporting(false);
    toast.success(`Exported as ${format.toUpperCase()}`);
    onClose();
  };

  return (
    <ModalContainer
      isOpen={isOpen}
      onClose={onClose}
      title="Export Document"
      subtitle="Choose format and options"
      size="md"
    >
      <div className="p-4 space-y-4">
        {/* Format Selection */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">Format</label>
          <div className="grid grid-cols-4 gap-2">
            {(['pdf', 'docx', 'html', 'json'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFormat(f)}
                className={`p-3 rounded-lg border-2 transition-colors text-center ${
                  format === f
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-neutral-200 hover:border-blue-200'
                }`}
              >
                <FileText className="w-5 h-5 mx-auto mb-1" />
                <span className="text-xs uppercase font-medium">{f}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Include Options */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">Include</label>
          <div className="space-y-2">
            {Object.entries(includeOptions).map(([key, value]) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={value}
                  onChange={() => setIncludeOptions(prev => ({ ...prev, [key]: !prev[key as keyof typeof prev] }))}
                  className="w-4 h-4 rounded border-neutral-300"
                />
                <span className="text-sm capitalize">{key}</span>
              </label>
            ))}
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="default" onClick={handleExport} disabled={isExporting} className="gap-2">
            {isExporting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            {isExporting ? 'Exporting...' : 'Export'}
          </Button>
        </div>
      </div>
    </ModalContainer>
  );
}

// Balance Synthesis Modal
interface BalanceSynthesisModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BalanceSynthesisModal({ isOpen, onClose }: BalanceSynthesisModalProps) {
  const { considerations } = useAppState();
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamedText, setStreamedText] = useState('');
  const [framingId, setFramingId] = useState('balanced');

  const handleGenerate = async () => {
    setIsGenerating(true);
    setStreamedText('');

    await simulateBalance(
      considerations,
      framingId,
      (chunk) => setStreamedText(prev => prev + chunk),
      () => {
        setIsGenerating(false);
        toast.success('Balance synthesis complete');
      }
    );
  };

  return (
    <ModalContainer
      isOpen={isOpen}
      onClose={onClose}
      title="Planning Balance Synthesis"
      subtitle="AI-assisted weighing of considerations"
      size="lg"
    >
      <div className="p-4 space-y-4">
        {/* Framing Selection */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">Political Framing</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: 'balanced', name: 'Balanced Growth' },
              { id: 'protection', name: 'Environmental Protection' },
              { id: 'delivery', name: 'Housing Delivery' },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setFramingId(f.id)}
                className={`p-2 rounded-lg border-2 transition-colors text-sm ${
                  framingId === f.id
                    ? 'border-violet-500 bg-violet-50 text-violet-700'
                    : 'border-neutral-200 hover:border-violet-200'
                }`}
              >
                {f.name}
              </button>
            ))}
          </div>
        </div>

        {/* Considerations Summary */}
        <div>
          <label className="text-sm font-medium text-slate-600 mb-2 block">
            Considerations ({considerations.length})
          </label>
          <div className="flex gap-4">
            <div className="flex items-center gap-1 text-sm text-green-600">
              <Plus className="w-4 h-4" />
              {considerations.filter(c => getValence(c) === 'for').length} For
            </div>
            <div className="flex items-center gap-1 text-sm text-red-600">
              <Minus className="w-4 h-4" />
              {considerations.filter(c => getValence(c) === 'against').length} Against
            </div>
            <div className="flex items-center gap-1 text-sm text-slate-600">
              <Scale className="w-4 h-4" />
              {considerations.filter(c => getValence(c) === 'neutral').length} Neutral
            </div>
          </div>
        </div>

        {/* Generate Button */}
        <Button 
          variant="default" 
          onClick={handleGenerate} 
          disabled={isGenerating}
          className="w-full gap-2"
        >
          {isGenerating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {isGenerating ? 'Generating synthesis...' : 'Generate Planning Balance'}
        </Button>

        {/* Streamed Output */}
        {streamedText && (
          <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
            <h4 className="text-sm font-medium text-slate-700 mb-2">Synthesis</h4>
            <p className="text-sm text-slate-600 whitespace-pre-wrap">{streamedText}</p>
          </div>
        )}

        <Separator />

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {streamedText && (
            <Button variant="default" className="gap-2">
              <Copy className="w-4 h-4" />
              Copy to Document
            </Button>
          )}
        </div>
      </div>
    </ModalContainer>
  );
}

// Modal Manager Component
export function ModalManager() {
  const { activeModal, modalData, closeModal } = useAppState();

  if (!activeModal) return null;

  switch (activeModal) {
    case 'evidence-detail':
      return (
        <EvidenceDetailModal
          isOpen={true}
          onClose={closeModal}
          evidenceId={(modalData?.evidenceId as string) ?? null}
        />
      );
    case 'site-detail':
      return (
        <SiteAssessmentModal
          isOpen={true}
          onClose={closeModal}
          siteId={(modalData?.siteId as string) ?? null}
        />
      );
    case 'consideration-form':
      return (
        <ConsiderationFormModal
          isOpen={true}
          onClose={closeModal}
        />
      );
    case 'export':
      return (
        <ExportDialog
          isOpen={true}
          onClose={closeModal}
        />
      );
    case 'balance':
      return (
        <BalanceSynthesisModal
          isOpen={true}
          onClose={closeModal}
        />
      );
    default:
      return null;
  }
}
