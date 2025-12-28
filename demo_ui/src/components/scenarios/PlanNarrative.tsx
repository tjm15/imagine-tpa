/**
 * PlanNarrative Component
 * 
 * AI-generated narrative summary for the selected scenario
 */

import { Sparkles, Info, ExternalLink } from 'lucide-react';
import { cn } from '../ui/utils';

interface PlanNarrativeProps {
  narrative: string;
  scenarioName: string;
  onViewTrace?: () => void;
}

export function PlanNarrative({ narrative, scenarioName, onViewTrace }: PlanNarrativeProps) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-indigo-100 rounded-md flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
          </div>
          <span className="text-sm font-bold text-slate-800">Plan Narrative</span>
        </div>
        {onViewTrace && (
          <button
            onClick={onViewTrace}
            className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline flex items-center gap-1"
          >
            View Inspector's Trace
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
      </div>
      
      {/* Content */}
      <div className="p-4">
        <p className="text-sm text-slate-700 leading-relaxed">
          {narrative}
        </p>
      </div>
    </div>
  );
}
