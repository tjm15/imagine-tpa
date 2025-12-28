/**
 * ConstraintChip Component
 * 
 * Clickable constraint badge that expands inline to show implications & mitigation
 */

import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Info, Shield } from 'lucide-react';
import { SiteConstraint } from '../../fixtures/extendedMockData';
import { cn } from '../ui/utils';

interface ConstraintChipProps {
  constraint: SiteConstraint;
  expanded?: boolean;
  onToggle?: () => void;
}

const severityConfig = {
  high: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-300', icon: 'text-red-500' },
  medium: { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-300', icon: 'text-amber-500' },
  low: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-300', icon: 'text-blue-500' },
};

export function ConstraintChip({ constraint, expanded, onToggle }: ConstraintChipProps) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const isExpanded = expanded !== undefined ? expanded : localExpanded;
  const handleToggle = onToggle || (() => setLocalExpanded(!localExpanded));
  
  const config = severityConfig[constraint.severity];
  const ChevronIcon = isExpanded ? ChevronUp : ChevronDown;

  return (
    <div className={cn('rounded-lg border transition-all', config.border, isExpanded ? 'p-3' : 'inline-flex')}>
      <button
        onClick={handleToggle}
        className={cn(
          'inline-flex items-center gap-1.5 text-[11px] font-medium transition-colors',
          isExpanded ? 'w-full justify-between mb-2' : cn('px-2 py-1 rounded-lg', config.bg, config.text)
        )}
      >
        <div className="flex items-center gap-1.5">
          <AlertTriangle className={cn('w-3 h-3', config.icon)} />
          <span className={isExpanded ? 'font-semibold text-neutral-900' : ''}>{constraint.name}</span>
        </div>
        <ChevronIcon className={cn('w-3.5 h-3.5', isExpanded ? 'text-neutral-500' : '')} />
      </button>
      
      {isExpanded && (
        <div className="space-y-3 text-xs animate-in slide-in-from-top-1 duration-200">
          {/* Implications */}
          <div className="flex gap-2">
            <Info className="w-4 h-4 text-neutral-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-neutral-700 mb-0.5">Implications</div>
              <p className="text-neutral-600 leading-relaxed">{constraint.implications}</p>
            </div>
          </div>
          
          {/* Mitigation */}
          <div className="flex gap-2">
            <Shield className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-emerald-700 mb-0.5">Mitigation</div>
              <p className="text-neutral-600 leading-relaxed">{constraint.mitigation}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ConstraintChipListProps {
  constraints: SiteConstraint[];
}

export function ConstraintChipList({ constraints }: ConstraintChipListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (constraints.length === 0) {
    return (
      <div className="text-[11px] text-emerald-600 flex items-center gap-1.5">
        <Shield className="w-3.5 h-3.5" />
        <span>No significant constraints identified</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {constraints.map(c => (
          <ConstraintChip
            key={c.id}
            constraint={c}
            expanded={expandedId === c.id}
            onToggle={() => setExpandedId(expandedId === c.id ? null : c.id)}
          />
        ))}
      </div>
      
      {/* Expanded detail appears below the chips */}
      {expandedId && (
        <div className="mt-2">
          {constraints
            .filter(c => c.id === expandedId)
            .map(c => (
              <ConstraintChipExpanded key={c.id} constraint={c} onClose={() => setExpandedId(null)} />
            ))}
        </div>
      )}
    </div>
  );
}

function ConstraintChipExpanded({ constraint, onClose }: { constraint: SiteConstraint; onClose: () => void }) {
  const config = severityConfig[constraint.severity];
  
  return (
    <div className={cn('rounded-lg border p-3', config.border, config.bg.replace('100', '50'))}>
      <button
        onClick={onClose}
        className="flex items-center justify-between w-full mb-2"
      >
        <div className="flex items-center gap-1.5">
          <AlertTriangle className={cn('w-3.5 h-3.5', config.icon)} />
          <span className="font-semibold text-sm text-neutral-900">{constraint.name}</span>
        </div>
        <ChevronUp className="w-4 h-4 text-neutral-500" />
      </button>
      
      <div className="space-y-3 text-xs">
        <div className="flex gap-2">
          <Info className="w-4 h-4 text-neutral-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-medium text-neutral-700 mb-0.5">Implications</div>
            <p className="text-neutral-600 leading-relaxed">{constraint.implications}</p>
          </div>
        </div>
        
        <div className="flex gap-2">
          <Shield className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-medium text-emerald-700 mb-0.5">Mitigation</div>
            <p className="text-neutral-600 leading-relaxed">{constraint.mitigation}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
