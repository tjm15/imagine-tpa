import { useState } from 'react';
import { 
  Sparkles, User, Info, ExternalLink, AlertTriangle, 
  CheckCircle, FileText, GitBranch, Clock
} from 'lucide-react';
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Separator } from "./ui/separator";
import { 
  getEvidenceById, 
  mockToolRuns,
  mockAuditEvents,
  type EvidenceCard,
  type ToolRun 
} from '../fixtures/mockData';

// ============================================================================
// CONFIDENCE & STATUS TYPES
// ============================================================================

export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type ContentStatus = 'draft' | 'provisional' | 'settled' | 'contested' | 'stale';
export type ContentSource = 'ai' | 'human' | 'mixed';

interface ProvenanceData {
  source: ContentSource;
  confidence: ConfidenceLevel;
  status: ContentStatus;
  evidenceIds?: string[];
  toolRunId?: string;
  auditEventId?: string;
  assumptions?: string[];
  limitations?: string;
}

// ============================================================================
// PROVENANCE INDICATOR (small inline badge)
// ============================================================================

interface ProvenanceIndicatorProps {
  provenance: ProvenanceData;
  size?: 'sm' | 'md';
  showConfidence?: boolean;
  onOpenTrace?: () => void;
}

export function ProvenanceIndicator({ 
  provenance, 
  size = 'sm',
  showConfidence = false,
  onOpenTrace 
}: ProvenanceIndicatorProps) {
  const [isOpen, setIsOpen] = useState(false);
  
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';
  
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button 
          className={`inline-flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-slate-100 ${
            size === 'sm' ? 'text-[10px]' : 'text-xs'
          }`}
          title="View provenance"
        >
          {provenance.source === 'ai' ? (
            <Sparkles className={`${iconSize} text-blue-500`} />
          ) : provenance.source === 'human' ? (
            <User className={`${iconSize} text-slate-500`} />
          ) : (
            <GitBranch className={`${iconSize} text-purple-500`} />
          )}
          
          {showConfidence && (
            <span className={`font-medium ${
              provenance.confidence === 'high' 
                ? 'text-emerald-600' 
                : provenance.confidence === 'medium' 
                  ? 'text-amber-600' 
                  : 'text-red-600'
            }`}>
              {provenance.confidence === 'high' ? '●' : provenance.confidence === 'medium' ? '◐' : '○'}
            </span>
          )}
        </button>
      </PopoverTrigger>
      
      <PopoverContent 
        className="w-80 p-0" 
        align="start"
        side="bottom"
      >
        <ProvenanceDetail 
          provenance={provenance} 
          onOpenTrace={onOpenTrace}
          onClose={() => setIsOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}

// ============================================================================
// PROVENANCE DETAIL (popover content)
// ============================================================================

interface ProvenanceDetailProps {
  provenance: ProvenanceData;
  onOpenTrace?: () => void;
  onClose?: () => void;
}

function ProvenanceDetail({ provenance, onOpenTrace, onClose }: ProvenanceDetailProps) {
  const evidence = provenance.evidenceIds?.map(id => getEvidenceById(id)).filter(Boolean) as EvidenceCard[] || [];
  const toolRun = provenance.toolRunId 
    ? mockToolRuns.find(t => t.id === provenance.toolRunId) 
    : undefined;
  const auditEvent = provenance.auditEventId
    ? mockAuditEvents.find(a => a.id === provenance.auditEventId)
    : undefined;

  return (
    <div className="text-sm">
      {/* Header */}
      <div className="p-3 border-b" style={{ 
        backgroundColor: 'var(--color-surface-light)',
        borderColor: 'var(--color-neutral-200)'
      }}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <SourceBadge source={provenance.source} />
            <ConfidenceBadge confidence={provenance.confidence} />
            <StatusBadge status={provenance.status} />
          </div>
        </div>
        
        <p className="text-xs" style={{ color: 'var(--color-text)' }}>
          {getSourceDescription(provenance.source)}
        </p>
      </div>
      
      {/* Evidence Section */}
      {evidence.length > 0 && (
        <div className="p-3 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="flex items-center gap-1 mb-2 text-xs font-medium" style={{ color: 'var(--color-text)' }}>
            <FileText className="w-3 h-3" />
            Based on {evidence.length} evidence source{evidence.length > 1 ? 's' : ''}
          </div>
          <div className="space-y-1.5">
            {evidence.map(ev => (
              <div 
                key={ev.id}
                className="flex items-start gap-2 p-2 rounded bg-white border"
                style={{ borderColor: 'var(--color-neutral-200)' }}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate" style={{ color: 'var(--color-ink)' }}>
                    {ev.title}
                  </p>
                  <p className="text-[10px]" style={{ color: 'var(--color-text)' }}>
                    {ev.source} · {ev.date}
                  </p>
                </div>
                <ConfidenceBadge confidence={ev.confidence} size="sm" />
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Tool Run Section */}
      {toolRun && (
        <div className="p-3 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="flex items-center gap-1 mb-2 text-xs font-medium" style={{ color: 'var(--color-text)' }}>
            <Sparkles className="w-3 h-3 text-blue-500" />
            Generated by
          </div>
          <ToolRunCard toolRun={toolRun} />
        </div>
      )}
      
      {/* Audit Section */}
      {auditEvent && (
        <div className="p-3 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
          <div className="flex items-center gap-1 mb-2 text-xs font-medium" style={{ color: 'var(--color-text)' }}>
            <User className="w-3 h-3" />
            User action
          </div>
          <div className="p-2 rounded bg-emerald-50 border border-emerald-100">
            <p className="text-xs text-emerald-800">
              <span className="font-medium">{auditEvent.userId}</span> {getActionLabel(auditEvent.action)}
            </p>
            <p className="text-[10px] text-emerald-600 mt-0.5">
              {new Date(auditEvent.timestamp).toLocaleString()}
            </p>
            {auditEvent.note && (
              <p className="text-[10px] text-emerald-700 mt-1 italic">
                "{auditEvent.note}"
              </p>
            )}
          </div>
        </div>
      )}
      
      {/* Assumptions & Limitations */}
      {(provenance.assumptions?.length || provenance.limitations) && (
        <div className="p-3 border-b" style={{ borderColor: 'var(--color-neutral-200)' }}>
          {provenance.assumptions?.length ? (
            <div className="mb-2">
              <div className="flex items-center gap-1 mb-1 text-xs font-medium text-amber-700">
                <Info className="w-3 h-3" />
                Assumptions
              </div>
              <ul className="text-[10px] space-y-0.5" style={{ color: 'var(--color-text)' }}>
                {provenance.assumptions.map((a, i) => (
                  <li key={i} className="flex items-start gap-1">
                    <span className="text-amber-500">•</span>
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          
          {provenance.limitations && (
            <div className="p-2 rounded bg-amber-50 border border-amber-100">
              <div className="flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-[10px] text-amber-800">
                  {provenance.limitations}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* Actions */}
      <div className="p-3 flex items-center justify-between">
        <Button 
          variant="ghost" 
          size="sm" 
          className="h-7 text-xs gap-1"
          onClick={onOpenTrace}
        >
          <GitBranch className="w-3 h-3" />
          Open Trace Canvas
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          className="h-7 text-xs"
          onClick={onClose}
        >
          Close
        </Button>
      </div>
    </div>
  );
}

// ============================================================================
// TOOL RUN CARD
// ============================================================================

function ToolRunCard({ toolRun }: { toolRun: ToolRun }) {
  return (
    <div className="p-2 rounded bg-blue-50 border border-blue-100">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-blue-800">
          {toolRun.tool}
        </span>
        <span className="text-[10px] text-blue-600">
          {toolRun.durationMs}ms
        </span>
      </div>
      {toolRun.model && (
        <p className="text-[10px] text-blue-700">
          Model: <span className="font-mono">{toolRun.model}</span>
          {toolRun.promptVersion && <span> · v{toolRun.promptVersion}</span>}
        </p>
      )}
      {toolRun.limitations && (
        <div className="mt-1.5 p-1.5 rounded bg-white border border-blue-200">
          <p className="text-[10px] text-blue-800">
            <AlertTriangle className="w-3 h-3 inline mr-1 text-amber-500" />
            {toolRun.limitations}
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// BADGE COMPONENTS
// ============================================================================

function SourceBadge({ source }: { source: ContentSource }) {
  if (source === 'ai') {
    return (
      <Badge className="text-[10px] h-5 bg-blue-100 text-blue-700 hover:bg-blue-100">
        <Sparkles className="w-3 h-3 mr-1" />
        AI Generated
      </Badge>
    );
  }
  if (source === 'human') {
    return (
      <Badge className="text-[10px] h-5 bg-slate-100 text-slate-700 hover:bg-slate-100">
        <User className="w-3 h-3 mr-1" />
        Human Input
      </Badge>
    );
  }
  return (
    <Badge className="text-[10px] h-5 bg-purple-100 text-purple-700 hover:bg-purple-100">
      <GitBranch className="w-3 h-3 mr-1" />
      Mixed
    </Badge>
  );
}

interface ConfidenceBadgeProps {
  confidence: ConfidenceLevel;
  size?: 'sm' | 'md';
}

export function ConfidenceBadge({ confidence, size = 'md' }: ConfidenceBadgeProps) {
  const colors = {
    high: 'bg-emerald-100 text-emerald-700',
    medium: 'bg-amber-100 text-amber-700',
    low: 'bg-red-100 text-red-700'
  };
  
  return (
    <Badge 
      variant="secondary"
      className={`${size === 'sm' ? 'text-[9px] h-4 px-1' : 'text-[10px] h-5'} ${colors[confidence]}`}
    >
      {confidence === 'high' ? '● High' : confidence === 'medium' ? '◐ Medium' : '○ Low'}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: ContentStatus }) {
  const config: Record<ContentStatus, { icon: typeof CheckCircle; className: string; label: string }> = {
    draft: { 
      icon: Clock, 
      className: 'border-dashed border-slate-300 text-slate-500 bg-white',
      label: 'Draft'
    },
    provisional: { 
      icon: Clock, 
      className: 'border-amber-300 text-amber-700 bg-amber-50',
      label: 'Provisional'
    },
    settled: { 
      icon: CheckCircle, 
      className: 'border-emerald-300 text-emerald-700 bg-emerald-50',
      label: 'Settled'
    },
    contested: { 
      icon: AlertTriangle, 
      className: 'border-red-300 text-red-700 bg-red-50',
      label: 'Contested'
    },
    stale: { 
      icon: AlertTriangle, 
      className: 'border-slate-300 text-slate-500 bg-slate-100',
      label: 'Stale'
    }
  };
  
  const { icon: Icon, className, label } = config[status];
  
  return (
    <Badge variant="outline" className={`text-[10px] h-5 ${className}`}>
      <Icon className="w-3 h-3 mr-1" />
      {label}
    </Badge>
  );
}

// ============================================================================
// CONTENT WRAPPER (for wrapping content with provenance)
// ============================================================================

interface ProvenanceWrapperProps {
  provenance: ProvenanceData;
  children: React.ReactNode;
  className?: string;
  onOpenTrace?: () => void;
}

export function ProvenanceWrapper({ 
  provenance, 
  children, 
  className = '',
  onOpenTrace 
}: ProvenanceWrapperProps) {
  const borderStyle = {
    draft: 'border-dashed border-slate-300',
    provisional: 'border-solid border-amber-200',
    settled: 'border-solid border-emerald-200',
    contested: 'border-solid border-red-200 border-l-2 border-l-red-400',
    stale: 'border-solid border-slate-200 opacity-75'
  };
  
  return (
    <div className={`relative group ${className}`}>
      <div className={`border rounded-lg p-4 ${borderStyle[provenance.status]}`}>
        {children}
        
        {/* Floating provenance indicator */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <ProvenanceIndicator 
            provenance={provenance} 
            showConfidence 
            onOpenTrace={onOpenTrace}
          />
        </div>
      </div>
      
      {/* Status ribbon for non-settled content */}
      {provenance.status !== 'settled' && provenance.status !== 'draft' && (
        <div className={`absolute -left-1 top-3 px-1.5 py-0.5 text-[9px] font-medium rounded-r ${
          provenance.status === 'provisional' 
            ? 'bg-amber-500 text-white' 
            : provenance.status === 'contested'
              ? 'bg-red-500 text-white'
              : 'bg-slate-400 text-white'
        }`}>
          {provenance.status.charAt(0).toUpperCase() + provenance.status.slice(1)}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// HELPERS
// ============================================================================

function getSourceDescription(source: ContentSource): string {
  if (source === 'ai') {
    return 'This content was generated by an AI model based on the evidence below.';
  }
  if (source === 'human') {
    return 'This content was written or confirmed by a planning officer.';
  }
  return 'This content combines AI-generated suggestions with human edits.';
}

function getActionLabel(action: string): string {
  const labels: Record<string, string> = {
    tab_selected: 'selected this tab',
    suggestion_accepted: 'accepted this suggestion',
    suggestion_rejected: 'rejected this suggestion',
    consideration_added: 'added this consideration',
    sign_off: 'signed off this content'
  };
  return labels[action] || action;
}
