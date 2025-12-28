import React, { useState, useMemo, useEffect } from 'react';
import { Site, Scenario, LocationContext } from './types';
import ScenarioSwitcher from './components/ScenarioSwitcher';
import PlanStory from './components/PlanStory';
import SiteCard from './components/SiteCard';
import TraceView from './components/TraceView';
import SpatialMap from './components/SpatialMap';
import CreateScenarioModal from './components/CreateScenarioModal';
import LandingPage from './components/LandingPage';
import { generatePlanningData } from './services/geminiService';
import { Layout, MapPin, Loader2, RefreshCcw, ArrowLeft } from 'lucide-react';

export default function App() {
  // Application State
  const [locationContext, setLocationContext] = useState<LocationContext | null>(null);
  
  // Data State
  const [loading, setLoading] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [allSites, setAllSites] = useState<Site[]>([]);
  
  // UI State
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [expandedSiteId, setExpandedSiteId] = useState<string | null>(null);
  const [traceSite, setTraceSite] = useState<Site | null>(null);
  const [isCreatingScenario, setIsCreatingScenario] = useState(false);

  // Trigger data generation when location is selected
  useEffect(() => {
    if (locationContext && scenarios.length === 0) {
      loadData(locationContext);
    }
  }, [locationContext]);

  const loadData = async (context: LocationContext) => {
    setLoading(true);
    const { sites, scenarios } = await generatePlanningData(context);
    setAllSites(sites);
    setScenarios(scenarios);
    if (scenarios.length > 0) {
      setSelectedScenarioId(scenarios[0].id);
    }
    setLoading(false);
  };

  // Derived Data
  const selectedScenario = useMemo(() => 
    scenarios.find(s => s.id === selectedScenarioId) || scenarios[0],
  [selectedScenarioId, scenarios]);

  const scenarioSites = useMemo(() => {
    if (!selectedScenario) return [];
    return allSites.filter(site => selectedScenario.includedSiteIds.includes(site.id));
  }, [selectedScenario, allSites]);

  const handleCreateScenario = (newScenario: Scenario) => {
    setScenarios([...scenarios, newScenario]);
    setSelectedScenarioId(newScenario.id);
  };

  const handleRefresh = async () => {
    if (locationContext) {
      loadData(locationContext);
    }
  };

  // If no location selected, show Landing Page
  if (!locationContext) {
    return <LandingPage onLocationSelect={setLocationContext} />;
  }

  // Loading State
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4">
        <div className="bg-white p-8 rounded-2xl shadow-xl flex flex-col items-center max-w-md text-center border border-slate-100">
          <div className="w-16 h-16 bg-indigo-50 rounded-full flex items-center justify-center mb-6">
            <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
          </div>
          <h2 className="text-xl font-bold text-slate-800 mb-2">Analyzing {locationContext.name}</h2>
          <p className="text-slate-500 mb-6">
            The AI is identifying development sites and strategic scenarios based on the spatial context of {locationContext.displayName}...
          </p>
          <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
             <div className="h-full bg-indigo-500 w-1/2 animate-[pulse_1.5s_ease-in-out_infinite]"></div>
          </div>
        </div>
      </div>
    );
  }

  // Main App Interface
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="bg-indigo-600 p-1.5 rounded-lg text-white">
              <Layout size={20} />
            </div>
            <h1 className="font-bold text-lg tracking-tight text-slate-800 hidden sm:block">
              The Planner's Assistant <span className="font-normal text-slate-400">| Local Plan Mode</span>
            </h1>
            <h1 className="font-bold text-lg tracking-tight text-slate-800 sm:hidden">
              TPA <span className="font-normal text-slate-400">| Plan</span>
            </h1>
          </div>
          <div className="flex items-center gap-3">
             <button 
                onClick={() => { setLocationContext(null); setScenarios([]); }}
                className="text-xs font-medium px-3 py-1.5 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors flex items-center gap-1"
             >
                <ArrowLeft size={14} />
                <span className="hidden sm:inline">Change Location</span>
             </button>
             <div className="h-4 w-px bg-slate-200"></div>
             <button 
                onClick={handleRefresh}
                className="text-xs font-medium px-3 py-1.5 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors flex items-center gap-1"
                title="Regenerate Data"
             >
                <RefreshCcw size={14} />
                <span className="hidden sm:inline">Regenerate</span>
             </button>
             <div className="text-xs font-bold px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full border border-indigo-100 truncate max-w-[150px]">
                {locationContext.name}
             </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        
        {/* Scenario Selection */}
        <section>
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400 mb-4">Strategic Scenarios</h2>
          <ScenarioSwitcher 
            scenarios={scenarios}
            selectedId={selectedScenarioId}
            onSelect={setSelectedScenarioId}
            onAdd={() => setIsCreatingScenario(true)}
          />
        </section>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
          
          {/* LEFT: Map & Narrative (Sticky on Desktop) */}
          <div className="lg:col-span-5 space-y-6">
             {/* Map Card */}
             <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-1 aspect-video lg:aspect-square relative overflow-hidden">
                <SpatialMap 
                  allSites={allSites} 
                  includedSiteIds={selectedScenario?.includedSiteIds || []} 
                  locationContext={locationContext}
                />
                <div className="absolute top-4 left-4 bg-white/90 backdrop-blur px-3 py-1 rounded shadow-sm border border-slate-200 text-sm font-semibold z-10 pointer-events-none">
                   Spatial Strategy Map
                </div>
             </div>
             
             {/* Story Card */}
             <div className="lg:sticky lg:top-24">
                {selectedScenario && <PlanStory scenario={selectedScenario} />}
             </div>
          </div>

          {/* RIGHT: Site List */}
          <div className="lg:col-span-7">
             <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                  <MapPin className="text-indigo-500" size={20} />
                  Allocated Sites
                  <span className="ml-2 bg-slate-200 text-slate-600 text-xs px-2 py-0.5 rounded-full">
                    {scenarioSites.length}
                  </span>
                </h2>
                <div className="text-sm text-slate-500">
                  Total Capacity: <span className="font-bold text-slate-800">{selectedScenario?.metrics.totalCapacity.toLocaleString() || 0}</span> units
                </div>
             </div>

             <div className="space-y-4">
               {scenarioSites.map(site => (
                 <SiteCard 
                   key={site.id} 
                   site={site} 
                   isExpanded={expandedSiteId === site.id}
                   onToggle={() => setExpandedSiteId(expandedSiteId === site.id ? null : site.id)}
                   onViewTrace={() => setTraceSite(site)}
                 />
               ))}
               
               {scenarioSites.length === 0 && (
                 <div className="p-8 text-center text-slate-400 border-2 border-dashed border-slate-200 rounded-lg">
                   No sites allocated in this scenario.
                 </div>
               )}
             </div>
          </div>

        </div>
      </main>

      {/* Trace View Modal */}
      {traceSite && selectedScenario && (
        <TraceView 
          scenario={selectedScenario}
          site={traceSite}
          onClose={() => setTraceSite(null)}
        />
      )}

      {/* Create Scenario Modal */}
      {isCreatingScenario && (
        <CreateScenarioModal
          allSites={allSites}
          onClose={() => setIsCreatingScenario(false)}
          onCreate={handleCreateScenario}
        />
      )}
    </div>
  );
}