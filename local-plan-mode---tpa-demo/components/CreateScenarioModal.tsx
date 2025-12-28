import React, { useState, useMemo } from 'react';
import { Site, Scenario } from '../types';
import { X, Check, MapPin, Home } from 'lucide-react';

interface CreateScenarioModalProps {
  allSites: Site[];
  onClose: () => void;
  onCreate: (scenario: Scenario) => void;
}

const CreateScenarioModal: React.FC<CreateScenarioModalProps> = ({ allSites, onClose, onCreate }) => {
  const [label, setLabel] = useState('');
  const [description, setDescription] = useState('');
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);

  const metrics = useMemo(() => {
    const selected = allSites.filter(s => selectedSiteIds.includes(s.id));
    return {
      totalSites: selected.length,
      totalCapacity: selected.reduce((acc, s) => acc + s.capacity, 0)
    };
  }, [selectedSiteIds, allSites]);

  const toggleSite = (id: string) => {
    setSelectedSiteIds(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const handleCreate = () => {
    if (!label) return;
    
    const newScenario: Scenario = {
      id: `custom-${Date.now()}`,
      label,
      description: description || "Custom user-defined scenario.",
      metrics,
      includedSiteIds: selectedSiteIds,
      narrative: `**${label}**\n\nThis is a custom strategy defined by the user. It allocates **${metrics.totalSites} sites** to deliver a total capacity of **${metrics.totalCapacity.toLocaleString()} homes**.\n\nThe strategy focuses on specific user-selected opportunities to meet local planning objectives.`
    };
    
    onCreate(newScenario);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
        
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h2 className="font-bold text-slate-800 text-lg">Define New Strategy</h2>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="space-y-3">
            <label className="block text-sm font-medium text-slate-700">Strategy Name</label>
            <input 
              type="text" 
              className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
              placeholder="e.g. Brownfield Priority"
              value={label}
              onChange={e => setLabel(e.target.value)}
            />
          </div>

          <div className="space-y-3">
            <label className="block text-sm font-medium text-slate-700">Description</label>
            <textarea 
              className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all h-20 resize-none"
              placeholder="Briefly describe the focus of this strategy..."
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          <div className="space-y-3">
             <div className="flex justify-between items-end">
                <label className="block text-sm font-medium text-slate-700">Select Sites to Allocate</label>
                <span className="text-xs text-slate-500">{selectedSiteIds.length} selected</span>
             </div>
             <div className="grid grid-cols-1 gap-2 max-h-60 overflow-y-auto pr-2 border border-slate-200 rounded-lg p-2 bg-slate-50/50">
               {allSites.map(site => {
                 const isSelected = selectedSiteIds.includes(site.id);
                 return (
                   <div 
                     key={site.id} 
                     onClick={() => toggleSite(site.id)}
                     className={`flex items-center justify-between p-3 rounded-md cursor-pointer border transition-all ${
                       isSelected ? 'bg-indigo-50 border-indigo-200 shadow-sm' : 'bg-white border-transparent hover:bg-white hover:border-slate-200'
                     }`}
                   >
                     <div className="flex items-center gap-3">
                       <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${isSelected ? 'bg-indigo-600 border-indigo-600' : 'border-slate-300 bg-white'}`}>
                         {isSelected && <Check size={12} className="text-white" />}
                       </div>
                       <div>
                         <div className={`text-sm font-medium ${isSelected ? 'text-indigo-900' : 'text-slate-700'}`}>{site.name}</div>
                         <div className="text-xs text-slate-500">{site.category}</div>
                       </div>
                     </div>
                     <div className="text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-1 rounded">
                       {site.capacity} units
                     </div>
                   </div>
                 );
               })}
             </div>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
           <div className="flex gap-4 text-sm text-slate-600">
              <div className="flex items-center gap-1"><MapPin size={16}/> <strong>{metrics.totalSites}</strong> Sites</div>
              <div className="flex items-center gap-1"><Home size={16}/> <strong>{metrics.totalCapacity.toLocaleString()}</strong> Capacity</div>
           </div>
           <button 
             disabled={!label || metrics.totalSites === 0}
             onClick={handleCreate}
             className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium shadow-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
           >
             Create Strategy
           </button>
        </div>
      </div>
    </div>
  );
};

export default CreateScenarioModal;