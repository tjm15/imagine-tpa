/**
 * StrategyView - Unified Spatial Strategy Workspace
 * 
 * Merges scenario modelling, map canvas, and visual evidence into a single integrated view.
 * Replaces the previous fragmentation of Scenarios/Map/Visuals into separate views.
 * 
 * Key Features:
 * - Scenario comparison with live spatial visualization
 * - Site selection/allocation with immediate map feedback
 * - Inline visual evidence (photos, plan-reality overlays) for selected sites
 * - Drawing tools for spatial queries
 * - Narrative generation tied to scenario selection
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Layers, MapPin, Plus, Minus, Home, Map as MapIcon, Camera, Eye,
  Download, Maximize2, Circle, Square, AlertTriangle, X
} from 'lucide-react';
import Map, {
  Source,
  Layer,
  NavigationControl,
  ScaleControl,
  Popup,
  type MapRef
} from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { WorkspaceMode } from '../../App';
import {
  strategicScenarios,
  getSitesForScenario,
  StrategicScenario,
  siteAllocations,
  constraintsLayers,
  cambridgeBoundary
} from '../../fixtures/extendedMockData';
import { ScenarioBar } from '../scenarios/ScenarioBar';
import { AllocatedSitesPanel } from '../scenarios/AllocatedSitesPanel';
import { PlanNarrative } from '../scenarios/PlanNarrative';
import { CreateStrategyModal, NewScenarioData } from '../scenarios/CreateStrategyModal';
import { Button } from '../ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface StrategyViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
}

export function StrategyView({
  workspace,
  explainabilityMode = 'summary',
  onOpenTrace
}: StrategyViewProps) {
  const mapRef = useRef<MapRef>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState(strategicScenarios[0].id);
  const [scenarios, setScenarios] = useState<StrategicScenario[]>(strategicScenarios);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [showVisualEvidence, setShowVisualEvidence] = useState(false);
  const [hoveredSite, setHoveredSite] = useState<string | null>(null);
  const [popupInfo, setPopupInfo] = useState<{
    longitude: number;
    latitude: number;
    name: string;
    landType: string;
    capacity: number;
    allocated: boolean;
  } | null>(null);
  const [activeLayers, setActiveLayers] = useState({
    constraints: true,
    transport: true,
    sites: true,
    boundaries: true,
  });

  const selectedScenario = scenarios.find(s => s.id === selectedScenarioId) || scenarios[0];
  const { allocated, omitted } = getSitesForScenario(selectedScenarioId);

  const handleCreateScenario = useCallback((data: NewScenarioData) => {
    const newScenario: StrategicScenario = {
      id: `scenario-${Date.now()}`,
      name: data.name,
      description: data.description,
      allocatedSiteIds: data.allocatedSiteIds,
      omittedSiteIds: siteAllocations.features
        .map(f => f.properties.id)
        .filter(id => !data.allocatedSiteIds.includes(id)),
      totalCapacity: siteAllocations.features
        .filter(f => data.allocatedSiteIds.includes(f.properties.id))
        .reduce((sum, f) => sum + f.properties.capacity, 0),
      narrative: `This is a custom strategy "${data.name}" allocating ${data.allocatedSiteIds.length} sites. ` +
        `The AI narrative for this scenario will be generated based on the selected sites and their characteristics. ` +
        `Review the allocated sites below to understand the spatial implications of this approach.`,
      color: data.color,
    };

    setScenarios(prev => [...prev, newScenario]);
    setSelectedScenarioId(newScenario.id);
    setShowCreateModal(false);
  }, []);

  const scenarioSiteData = {
    ...siteAllocations,
    features: siteAllocations.features.map(f => ({
      ...f,
      properties: {
        ...f.properties,
        allocated: selectedScenario.allocatedSiteIds.includes(f.properties.id),
      },
    })),
  };

  const toggleLayer = (layer: keyof typeof activeLayers) => {
    setActiveLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
  };

  const handleSiteClick = (siteId: string) => {
    setSelectedSiteId(siteId);
    setShowVisualEvidence(true);
  };

  // Mock visual evidence for selected site
  const visualEvidence = selectedSiteId ? [
    { id: 'aerial', label: 'Aerial View', note: 'Current site conditions showing access and vegetation', captured: '2024' },
    { id: 'north', label: 'View North', note: 'Context to existing development', captured: '2024' },
    { id: 'overlay', label: 'Plan-Reality Overlay', note: 'Proposed allocation boundary vs actual conditions', captured: '2024' }
  ] : [];

  return (
    <div className="h-full min-h-0 flex flex-col bg-slate-50 overflow-hidden">
      {/* Scenario Bar */}
      <ScenarioBar
        scenarios={scenarios}
        selectedId={selectedScenarioId}
        onSelect={setSelectedScenarioId}
        onCreateNew={() => setShowCreateModal(true)}
      />

      {/* Main Content - Two Column Layout (50/50 Split via Grid) */}
      <div className="flex-1 min-h-0 w-full grid grid-cols-2 overflow-hidden">
        {/* Left Column: Map + Narrative */}
        <div className="flex flex-col min-w-0 min-h-0 bg-white border-r border-slate-200 h-full max-h-full overflow-hidden">
          {/* Map Container - Fixed height */}
          <div className="flex-none shrink-0 relative w-full border-b border-slate-200" style={{ height: '500px', minHeight: '500px' }}>
            {/* Map Label */}
            <div className="absolute top-4 left-4 z-10 bg-white rounded-lg shadow-sm border border-slate-200 px-3 py-2 flex items-center gap-2">
              <MapIcon className="w-4 h-4 text-slate-600" />
              <span className="text-xs font-semibold text-slate-700">
                {workspace === 'plan' ? 'Spatial Strategy Map' : 'Site Context Map'}
              </span>
            </div>

            {/* Drawing Tools */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
              <div className="bg-white rounded-lg shadow-lg border border-slate-200 px-4 py-2 flex items-center gap-3">
                <span className="text-sm text-slate-600">Draw to query:</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button className="p-2 hover:bg-slate-100 rounded transition-colors">
                        <MapPin className="w-4 h-4" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>Point marker</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button className="p-2 hover:bg-slate-100 rounded transition-colors">
                        <Circle className="w-4 h-4" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>Radius query</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button className="p-2 hover:bg-slate-100 rounded transition-colors">
                        <Square className="w-4 h-4" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>Polygon selection</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>

            {/* Layer Controls */}
            <div className="absolute top-4 right-4 z-10">
              <div className="bg-white rounded-lg shadow-lg border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  Layers
                </div>
                <div className="space-y-1.5 text-xs">
                  {(Object.keys(activeLayers) as (keyof typeof activeLayers)[]).map((layer) => (
                    <label key={layer} className="flex items-center gap-2 cursor-pointer hover:bg-slate-50 px-2 py-1 rounded">
                      <input
                        type="checkbox"
                        checked={activeLayers[layer]}
                        onChange={() => toggleLayer(layer)}
                        className="w-3.5 h-3.5"
                      />
                      <span className="capitalize">{layer}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <Map
              ref={mapRef}
              initialViewState={{
                longitude: 0.1218,
                latitude: 52.2053,
                zoom: workspace === 'plan' ? 11.5 : 16,
              }}
              style={{ width: '100%', height: '100%' }}
              mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
              interactiveLayerIds={['sites-fill']}
              onClick={(e) => {
                const features = e.features;
                if (features && features.length > 0) {
                  const f = features[0];
                  handleSiteClick(f.properties?.id);
                  const coords = (f.geometry as GeoJSON.Polygon).coordinates[0];
                  const lngs = coords.map((c: number[]) => c[0]);
                  const lats = coords.map((c: number[]) => c[1]);
                  setPopupInfo({
                    longitude: (Math.min(...lngs) + Math.max(...lngs)) / 2,
                    latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
                    name: f.properties?.name || 'Unknown',
                    landType: f.properties?.landType || 'unknown',
                    capacity: f.properties?.capacity || 0,
                    allocated: f.properties?.allocated || false,
                  });
                } else {
                  setPopupInfo(null);
                }
              }}
              onMouseMove={(e) => {
                const features = e.features;
                if (features && features.length > 0) {
                  setHoveredSite(features[0].properties?.id);
                } else {
                  setHoveredSite(null);
                }
              }}
            >
              {/* Boundary */}
              <Source type="geojson" data={cambridgeBoundary}>
                <Layer
                  id="boundary-line"
                  type="line"
                  paint={{ 'line-color': '#1e40af', 'line-width': 2, 'line-dasharray': [2, 2] }}
                />
              </Source>

              {/* Site Allocations */}
              <Source type="geojson" data={scenarioSiteData}>
                <Layer
                  id="sites-fill"
                  type="fill"
                  paint={{
                    'fill-color': [
                      'case',
                      ['==', ['get', 'allocated'], true],
                      selectedScenario.color || '#10b981',
                      '#94a3b8'
                    ],
                    'fill-opacity': ['case', ['==', ['id'], hoveredSite], 0.8, 0.5],
                  }}
                />
                <Layer
                  id="sites-outline"
                  type="line"
                  paint={{
                    'line-color': [
                      'case',
                      ['==', ['get', 'allocated'], true],
                      selectedScenario.color || '#10b981',
                      '#475569'
                    ],
                    'line-width': ['case', ['==', ['id'], hoveredSite], 3, 1.5],
                  }}
                />
              </Source>

              {/* Constraints (if enabled) */}
              {activeLayers.constraints && constraintsLayers.greenBelt && (
                <Source type="geojson" data={constraintsLayers.greenBelt}>
                  <Layer
                    id="green-belt"
                    type="fill"
                    paint={{ 'fill-color': '#10b981', 'fill-opacity': 0.2 }}
                  />
                </Source>
              )}

              <NavigationControl position="bottom-right" />
              <ScaleControl />

              {popupInfo && (
                <Popup
                  longitude={popupInfo.longitude}
                  latitude={popupInfo.latitude}
                  onClose={() => setPopupInfo(null)}
                  closeButton={true}
                  closeOnClick={false}
                >
                  <div className="p-2">
                    <h3 className="font-semibold text-sm mb-1">{popupInfo.name}</h3>
                    <p className="text-xs text-slate-600 mb-1">
                      {popupInfo.landType} · {popupInfo.capacity} homes
                    </p>
                    <div className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${popupInfo.allocated
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-100 text-slate-600'
                      }`}>
                      {popupInfo.allocated ? 'Allocated' : 'Available'}
                    </div>
                  </div>
                </Popup>
              )}
            </Map>
          </div>

          {/* Narrative Section - Scrollable independently */}
          <div className="flex-1 min-h-0 bg-slate-50" style={{ overflowY: 'auto' }}>
            <PlanNarrative
              narrative={selectedScenario.narrative}
              scenarioName={selectedScenario.name}
              onViewTrace={() => onOpenTrace?.({ kind: 'run', label: 'Current run' })}
            />
          </div>
        </div>

        {/* Right Column: Site Details + Visual Evidence (50%) */}
        <div className="flex flex-col min-w-0 min-h-0 bg-white shadow-xl z-20 h-full max-h-full overflow-hidden">
          <div className="flex-1 min-h-0 overflow-x-hidden" style={{ overflowY: 'auto' }}>
            {showVisualEvidence && selectedSiteId ? (
              /* Visual Evidence Panel */
              <div className="flex flex-col min-h-min">
                <div className="flex-none p-4 border-b border-slate-200 flex items-center justify-between sticky top-0 bg-white z-10">
                  <div className="flex items-center gap-2">
                    <Camera className="w-4 h-4 text-slate-600" />
                    <h3 className="text-sm font-semibold">Visual Evidence</h3>
                  </div>
                  <button
                    onClick={() => setShowVisualEvidence(false)}
                    className="p-1 hover:bg-slate-100 rounded transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="p-4 space-y-4">
                  {visualEvidence.map((photo) => (
                    <div key={photo.id} className="bg-slate-50 rounded-lg border border-slate-200 overflow-hidden">
                      <div className="aspect-video bg-slate-200 relative flex items-center justify-center">
                        <Eye className="w-8 h-8 text-slate-400" />
                      </div>
                      <div className="p-3">
                        <h4 className="text-sm font-medium mb-1">{photo.label}</h4>
                        <p className="text-xs text-slate-600 mb-2">{photo.note}</p>
                        <div className="text-xs text-slate-500">Captured: {photo.captured}</div>
                      </div>
                    </div>
                  ))}

                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div className="text-xs">
                        <span className="text-amber-800 font-medium">Evidence Limitation:</span>
                        <span className="text-slate-700 ml-1">
                          Aerial imagery dated 2023. Ground conditions may have changed. Site visit recommended for verification.
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* Site Allocations Panel (default) */
              <div className="min-h-min">
                <AllocatedSitesPanel
                  allocatedSites={allocated}
                  omittedSites={omitted}
                  onOpenTrace={onOpenTrace}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      <CreateStrategyModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreateScenario={handleCreateScenario}
      />
    </div>
  );
}
