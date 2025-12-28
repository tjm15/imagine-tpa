import React, { useState } from 'react';
import { Site } from '../types';
import { ChevronDown, ChevronUp, Search, Leaf, PersonStanding, Info, Loader2, X } from 'lucide-react';
import { generateConstraintAnalysis } from '../services/geminiService';

interface SiteCardProps {
  site: Site;
  isExpanded: boolean;
  onToggle: () => void;
  onViewTrace: () => void;
}

const ScoreBar: React.FC<{ label: string; value: number; icon: React.ReactNode }> = ({ label, value, icon }) => {
  let normalizedValue = value;
  if (value > 10) {
    normalizedValue = value / 10;
  } else if (value <= 1 && value >= 0) {
    normalizedValue = value * 10;
  }

  const displayValue = Math.min(10, Math.max(0, normalizedValue));
  const percentage = Math.min(100, Math.max(0, displayValue * 10));

  return (
    <div className="flex flex-col space-y-1">
      <div className="flex justify-between text-xs text-slate-600 font-medium">
        <span className="flex items-center gap-1">{icon} {label}</span>
        <span>{displayValue.toFixed(1)}/10</span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
        <div 
          className={`h-full rounded-full ${displayValue >= 8 ? 'bg-emerald-500' : displayValue >= 5 ? 'bg-amber-400' : 'bg-red-400'}`} 
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

const RAGBadge: React.FC<{ label: string; status: 'High' | 'Medium' | 'Low' }> = ({ label, status }) => {
  let colorClass = 'bg-slate-100 text-slate-600';
  let dotClass = 'bg-slate-400';

  const isGreen = status === 'High'; 
  const isAmber = status === 'Medium';
  const isRed = status === 'Low';

  if (isGreen) { colorClass = 'bg-emerald-50 text-emerald-700 border-emerald-200'; dotClass = 'bg-emerald-500'; }
  if (isAmber) { colorClass = 'bg-amber-50 text-amber-700 border-amber-200'; dotClass = 'bg-amber-500'; }
  if (isRed) { colorClass = 'bg-red-50 text-red-700 border-red-200'; dotClass = 'bg-red-500'; }

  return (
    <div className={`flex items-center space-x-1.5 px-2 py-1 rounded border text-[10px] uppercase font-bold tracking-wide ${colorClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
      <span>{label}</span>
    </div>
  );
};

// Interactive Constraint Badge Component
const ConstraintBadge: React.FC<{ constraint: string; site: Site }> = ({ constraint, site }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isOpen) {
      setIsOpen(false);
      return;
    }

    setIsOpen(true);
    if (!analysis) {
      setLoading(true);
      const result = await generateConstraintAnalysis(site, constraint);
      setAnalysis(result);
      setLoading(false);
    }
  };

  return (
    <div className="relative inline-block">
      <button 
        onClick={handleClick}
        className={`group flex items-center gap-1.5 px-2 py-1 border rounded text-xs font-medium shadow-sm transition-all duration-200
          ${isOpen 
            ? 'bg-indigo-50 border-indigo-200 text-indigo-700 ring-2 ring-indigo-100' 
            : 'bg-white border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-600'
          }
        `}
      >
        <span>{constraint}</span>
        <Info size={12} className={`${isOpen ? 'text-indigo-500' : 'text-slate-300 group-hover:text-indigo-400'}`} />
      </button>

      {/* Popover / Progressive Disclosure */}
      {isOpen && (
        <div className="absolute left-0 top-full mt-2 z-20 w-64 md:w-80 bg-white rounded-lg shadow-xl border border-indigo-100 p-3 animate-in fade-in zoom-in-95 duration-200 origin-top-left">
          <div className="flex justify-between items-start mb-2">
            <h5 className="text-xs font-bold text-indigo-900 uppercase tracking-wider flex items-center gap-1">
              Implications & Mitigation
            </h5>
            <button 
              onClick={(e) => { e.stopPropagation(); setIsOpen(false); }}
              className="text-slate-400 hover:text-slate-600"
            >
              <X size={12} />
            </button>
          </div>
          
          <div className="text-xs text-slate-600 leading-relaxed bg-indigo-50/50 p-2 rounded border border-indigo-50/50">
            {loading ? (
              <div className="flex items-center gap-2 text-indigo-500 py-2">
                <Loader2 size={12} className="animate-spin" />
                <span>Analyzing policy implications...</span>
              </div>
            ) : (
              analysis
            )}
          </div>
          
          {/* Arrow */}
          <div className="absolute top-0 left-4 -mt-1.5 w-3 h-3 bg-white border-t border-l border-indigo-100 transform rotate-45"></div>
        </div>
      )}
    </div>
  );
};

const SiteCard: React.FC<SiteCardProps> = ({ site, isExpanded, onToggle, onViewTrace }) => {
  return (
    <div className={`bg-white border border-slate-200 rounded-lg shadow-sm transition-all duration-300 ${isExpanded ? 'ring-1 ring-slate-200' : ''}`}>
      {/* Header (Always Visible) */}
      <div 
        onClick={onToggle}
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-50 transition-colors rounded-lg"
      >
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-slate-800 text-lg">{site.name}</h3>
            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs font-semibold rounded-full border border-indigo-100">
              {site.capacity} homes
            </span>
          </div>
          <span className="text-slate-500 text-sm">{site.category}</span>
        </div>

        <div className="flex items-center space-x-4">
           {/* Mini Metrics for collapsed view */}
           {!isExpanded && (
              <div className="hidden md:flex space-x-2">
                <RAGBadge label="Suitability" status={site.suitability} />
                <RAGBadge label="Achievability" status={site.achievability} />
              </div>
           )}
           {isExpanded ? <ChevronUp className="text-slate-400" /> : <ChevronDown className="text-slate-400" />}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-slate-100 bg-slate-50/30 rounded-b-lg">
          
          {/* Main Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
            
            {/* Left Col: Summary & Constraints */}
            <div className="space-y-4">
              <div className="bg-blue-50/50 p-3 rounded-md border border-blue-100">
                <p className="text-slate-700 text-sm leading-relaxed italic">
                  <span className="font-semibold text-blue-800 not-italic block mb-1 text-xs uppercase">AI Summary</span>
                  "{site.summary}"
                </p>
              </div>

              <div className="relative">
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                  Key Constraints <span className="text-[10px] font-normal normal-case text-slate-400">(Click to analyze)</span>
                </h4>
                <div className="flex flex-wrap gap-2">
                  {site.constraintsList.length > 0 ? site.constraintsList.map(c => (
                    <ConstraintBadge key={c} constraint={c} site={site} />
                  )) : <span className="text-slate-400 text-xs">No major constraints identified.</span>}
                </div>
              </div>
            </div>

            {/* Right Col: Metrics & Scores */}
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                 <RAGBadge label="Suitability" status={site.suitability} />
                 <RAGBadge label="Availability" status={site.availability} />
                 <RAGBadge label="Achievability" status={site.achievability} />
                 <RAGBadge label="Deliverability" status={site.deliverability} />
              </div>

              <div className="space-y-3 pt-2">
                <ScoreBar label="Accessibility" value={site.accessibilityScore} icon={<PersonStanding size={12} />} />
                <ScoreBar label="Sustainability" value={site.sustainabilityScore} icon={<Leaf size={12} />} />
              </div>

              <button 
                onClick={(e) => { e.stopPropagation(); onViewTrace(); }}
                className="w-full mt-4 flex items-center justify-center gap-2 bg-white border border-indigo-200 text-indigo-700 py-2 rounded-md font-medium text-sm hover:bg-indigo-50 hover:border-indigo-300 transition-all shadow-sm active:scale-[0.98]"
              >
                <Search size={16} />
                View Inspector's Trace
              </button>
            </div>
          </div>

        </div>
      )}
    </div>
  );
};

export default SiteCard;