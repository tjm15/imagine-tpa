/**
 * ScenarioCard Component
 * 
 * Displays a strategic scenario in a grid card format.
 * Uses border accent and proper visual hierarchy matching the reference design.
 */

import { MapPin, Home } from 'lucide-react';
import { StrategicScenario } from '../../fixtures/extendedMockData';
import { cn } from '../ui/utils';

interface ScenarioCardProps {
  scenario: StrategicScenario;
  selected: boolean;
  onClick: () => void;
}

const colorConfig = {
  blue: { border: 'border-indigo-600', bg: 'bg-indigo-50', text: 'text-indigo-700', label: 'text-indigo-700', dot: 'bg-indigo-600' },
  amber: { border: 'border-amber-600', bg: 'bg-amber-50', text: 'text-amber-700', label: 'text-amber-700', dot: 'bg-amber-600' },
  emerald: { border: 'border-emerald-600', bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'text-emerald-700', dot: 'bg-emerald-600' },
  purple: { border: 'border-purple-600', bg: 'bg-purple-50', text: 'text-purple-700', label: 'text-purple-700', dot: 'bg-purple-600' },
};

export function ScenarioCard({ scenario, selected, onClick }: ScenarioCardProps) {
  const config = colorConfig[scenario.color];
  const siteCount = scenario.allocatedSiteIds.length;

  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-start p-4 rounded-xl border-2 transition-all duration-200 text-left min-h-[140px] flex-1 min-w-0',
        selected 
          ? cn(config.border, config.bg, 'shadow-md')
          : 'border-slate-200 bg-white hover:border-indigo-200 hover:bg-slate-50'
      )}
    >
      {/* Header */}
      <div className="mb-2 w-full flex justify-between items-center">
        <span className={cn(
          'font-bold text-sm uppercase tracking-wider',
          selected ? config.label : 'text-slate-500'
        )}>
          {scenario.name}
        </span>
        {selected && (
          <div className={cn('h-2 w-2 rounded-full animate-pulse', config.dot)} />
        )}
      </div>
      
      {/* Description */}
      <p className="text-slate-600 text-xs mb-4 line-clamp-2 h-8 flex-1">
        {scenario.description}
      </p>

      {/* Stats */}
      <div className="flex space-x-3 text-xs font-medium text-slate-700 w-full pt-3 border-t border-slate-200/60">
        <div className="flex items-center space-x-1.5">
          <MapPin size={14} className="text-slate-400" />
          <span>{siteCount} Sites</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <Home size={14} className="text-slate-400" />
          <span>{scenario.totalCapacity.toLocaleString()}</span>
        </div>
      </div>
    </button>
  );
}
