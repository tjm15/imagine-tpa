import React from 'react';
import { Scenario } from '../types';
import { Map, Home, Plus } from 'lucide-react';

interface ScenarioSwitcherProps {
  scenarios: Scenario[];
  selectedId: string;
  onSelect: (id: string) => void;
  onAdd: () => void;
}

const ScenarioSwitcher: React.FC<ScenarioSwitcherProps> = ({ scenarios, selectedId, onSelect, onAdd }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      {scenarios.map((scenario) => {
        const isSelected = scenario.id === selectedId;
        return (
          <button
            key={scenario.id}
            onClick={() => onSelect(scenario.id)}
            className={`
              relative flex flex-col items-start p-4 rounded-xl border-2 transition-all duration-200 text-left
              ${isSelected 
                ? 'border-indigo-600 bg-indigo-50 shadow-md' 
                : 'border-slate-200 bg-white hover:border-indigo-200 hover:bg-slate-50'
              }
            `}
          >
            <div className="mb-2 w-full flex justify-between items-center">
              <span className={`font-bold text-sm uppercase tracking-wider ${isSelected ? 'text-indigo-700' : 'text-slate-500'}`}>
                {scenario.label}
              </span>
              {isSelected && <div className="h-2 w-2 rounded-full bg-indigo-600 animate-pulse" />}
            </div>
            
            <p className="text-slate-600 text-xs mb-4 line-clamp-2 h-8">
              {scenario.description}
            </p>

            <div className="flex space-x-4 text-xs font-medium text-slate-700 w-full pt-3 border-t border-slate-200/60">
              <div className="flex items-center space-x-1">
                <Map size={14} className="text-slate-400" />
                <span>{scenario.metrics.totalSites} Sites</span>
              </div>
              <div className="flex items-center space-x-1">
                <Home size={14} className="text-slate-400" />
                <span>{scenario.metrics.totalCapacity.toLocaleString()}</span>
              </div>
            </div>
          </button>
        );
      })}

      {/* Add New Scenario Button */}
      <button
        onClick={onAdd}
        className="flex flex-col items-center justify-center p-4 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 hover:bg-slate-100 hover:border-indigo-400 hover:text-indigo-600 text-slate-400 transition-all duration-200 gap-2 group"
      >
        <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center group-hover:scale-110 transition-transform shadow-sm">
          <Plus size={20} />
        </div>
        <span className="font-semibold text-sm">Create Strategy</span>
      </button>
    </div>
  );
};

export default ScenarioSwitcher;