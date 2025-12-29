/**
 * SiteAllocationCard Component
 * 
 * Expandable card showing site details, SAAD indicators, constraints, and scores
 */

import { useState } from 'react';
import { ChevronDown, ChevronUp, MapPin, Home, Sparkles, Eye, GitBranch } from 'lucide-react';
import { EnrichedSiteProperties } from '../../fixtures/extendedMockData';
import { SAADIndicatorRow } from './SAADIndicator';
import { AccessibilitySustainabilityScores } from './ScoreBar';
import { ConstraintChipList } from './ConstraintChip';
import { Badge } from '../ui/badge';
import { cn } from '../ui/utils';

interface SiteAllocationCardProps {
  site: EnrichedSiteProperties;
  expanded?: boolean;
  onToggle?: () => void;
  onViewTrace?: () => void;
  isAllocated?: boolean;
}

const landTypeConfig = {
  brownfield: { label: 'Brownfield', bg: 'bg-amber-100', text: 'text-amber-700' },
  greenfield: { label: 'Greenfield', bg: 'bg-emerald-100', text: 'text-emerald-700' },
  'urban-extension': { label: 'Urban Extension', bg: 'bg-blue-100', text: 'text-blue-700' },
};

export function SiteAllocationCard({ 
  site, 
  expanded: controlledExpanded, 
  onToggle, 
  onViewTrace,
  isAllocated = true 
}: SiteAllocationCardProps) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = controlledExpanded !== undefined ? controlledExpanded : localExpanded;
  const handleToggle = onToggle || (() => setLocalExpanded(!localExpanded));
  
  const landTypeStyle = landTypeConfig[site.landType];
  const ChevronIcon = expanded ? ChevronUp : ChevronDown;

  return (
    <div 
      className={cn(
        'bg-white border border-slate-200 rounded-lg shadow-sm transition-all duration-300',
        expanded && 'ring-1 ring-slate-200',
        !isAllocated && 'opacity-60 hover:opacity-80'
      )}
    >
      {/* Header - always visible */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between p-4 cursor-pointer hover:bg-slate-50 transition-colors rounded-lg text-left"
      >
        <div className="flex flex-col min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-bold text-slate-800 text-base truncate">{site.name}</h4>
            <Badge className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs font-semibold border border-indigo-100 h-auto flex-shrink-0">
              {site.capacity} homes
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">{site.id}</span>
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium', landTypeStyle.bg, landTypeStyle.text)}>
              {landTypeStyle.label}
            </span>
            {site.greenBelt && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700 border border-green-100">
                Green Belt
              </span>
            )}
          </div>
        </div>
        
        <div className={cn(
          "ml-4 flex items-center justify-center transition-colors",
          expanded ? "text-slate-600" : "text-slate-400"
        )}>
          <ChevronIcon className="w-5 h-5" />
        </div>
      </button>
      
      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100 pt-4">
          {/* AI Summary */}
          <div className="bg-violet-50/50 rounded-lg p-3 border border-violet-100/50">
            <div className="flex items-center gap-1.5 mb-1.5">
              <Sparkles className="w-3.5 h-3.5 text-violet-600" />
              <span className="text-[11px] font-semibold text-violet-700">AI Summary</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              {site.aiSummary}
            </p>
          </div>
          
          {/* SAAD Indicators */}
          <div>
            <div className="text-[11px] font-medium text-neutral-600 mb-2">
              Site Assessment (SAAD)
              <span className="ml-1 text-[10px] font-normal text-neutral-400">
                — suitability, availability, achievability, deliverability
              </span>
            </div>
            <SAADIndicatorRow saad={site.saad} size="sm" />
          </div>
          
          {/* Scores */}
          <div>
            <div className="text-[11px] font-medium text-neutral-600 mb-2">Performance Scores</div>
            <AccessibilitySustainabilityScores 
              accessibilityScore={site.accessibilityScore}
              sustainabilityScore={site.sustainabilityScore}
            />
          </div>
          
          {/* Constraints */}
          <div>
            <div className="text-[11px] font-medium text-neutral-600 mb-2">
              Key Constraints
              {Array.isArray(site.constraints) && site.constraints.length > 0 && (
                <span className="ml-1 text-[10px] font-normal text-neutral-400">
                  — click to view implications & mitigation
                </span>
              )}
            </div>
            <ConstraintChipList constraints={Array.isArray(site.constraints) ? site.constraints : []} />
          </div>
          
          {/* Actions */}
          <div className="pt-2 border-t border-neutral-100 flex items-center justify-between">
            <button 
              onClick={(e) => { e.stopPropagation(); onViewTrace?.(); }}
              className="text-[11px] text-[color:var(--color-gov-blue)] hover:underline flex items-center gap-1"
            >
              <GitBranch className="w-3 h-3" />
              View Inspector's Trace
            </button>
            <button className="text-[11px] text-neutral-500 hover:text-neutral-700 flex items-center gap-1">
              <Eye className="w-3 h-3" />
              Focus on Map
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
