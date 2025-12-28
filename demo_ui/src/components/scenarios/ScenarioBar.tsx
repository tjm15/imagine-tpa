/**
 * ScenarioBar Component
 * 
 * Horizontal bar showing strategic scenario cards with selection state.
 * Matches reference design with "STRATEGIC SCENARIOS" section label.
 */

import { Plus } from 'lucide-react';
import { StrategicScenario } from '../../fixtures/extendedMockData';
import { ScenarioCard } from './ScenarioCard';
import { cn } from '../ui/utils';

interface ScenarioBarProps {
  scenarios: StrategicScenario[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

export function ScenarioBar({ scenarios, selectedId, onSelect, onCreateNew }: ScenarioBarProps) {
  return (
    <div className="bg-slate-50 border-b border-slate-200 px-6 pt-4 pb-5 flex-shrink-0">
      {/* Section Label */}
      <h2 className="text-xs font-bold text-slate-500 tracking-[0.1em] uppercase mb-3">
        Strategic Scenarios
      </h2>
      
      {/* Scenario Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {scenarios.map(scenario => (
          <ScenarioCard
            key={scenario.id}
            scenario={scenario}
            selected={selectedId === scenario.id}
            onClick={() => onSelect(scenario.id)}
          />
        ))}
        
        {/* Create New Button */}
        <button
          onClick={onCreateNew}
          className="flex flex-col items-center justify-center p-4 rounded-xl border-2 border-dashed border-slate-300 bg-white hover:bg-slate-50 hover:border-indigo-400 hover:text-indigo-600 text-slate-400 transition-all duration-200 gap-2 group min-h-[140px]"
        >
          <div className="w-10 h-10 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center group-hover:scale-110 group-hover:bg-white transition-all shadow-sm">
            <Plus size={20} />
          </div>
          <span className="font-semibold text-sm">Create Strategy</span>
        </button>
      </div>
    </div>
  );
}
