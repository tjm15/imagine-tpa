/**
 * ScenarioModellingView Component
 * 
 * Main view for spatial strategy scenario modelling.
 * Combines scenario bar, interactive map, site allocations panel, and plan narrative.
 * 
 * Layout matches the TPA AI Studio reference design:
 * - "STRATEGIC SCENARIOS" section header with horizontal scenario cards
 * - Two-column layout: Map+Narrative (left) | Sites Panel (right)
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { Layers, MapPin, Plus, Minus, Home, Map as MapIcon } from 'lucide-react';
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
import { ScenarioBar } from './ScenarioBar';
import { AllocatedSitesPanel } from './AllocatedSitesPanel';
import { PlanNarrative } from './PlanNarrative';
import { CreateStrategyModal, NewScenarioData } from './CreateStrategyModal';
import type { TraceTarget } from '../../lib/trace';
import type { ExplainabilityMode } from '../views/JudgementView';

interface ScenarioModellingViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
}

export function ScenarioModellingView({ 
  workspace, 
  explainabilityMode = 'summary',
  onOpenTrace 
}: ScenarioModellingViewProps) {
  const mapRef = useRef<MapRef>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState(strategicScenarios[0].id);
  const [scenarios, setScenarios] = useState<StrategicScenario[]>(strategicScenarios);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [hoveredSite, setHoveredSite] = useState<string | null>(null);
  const [popupInfo, setPopupInfo] = useState<{
    longitude: number;
    latitude: number;
    name: string;
    landType: string;
    capacity: number;
    allocated: boolean;
  } | null>(null);

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

  // Create scenario-aware site data with allocated property
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

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Scenario Bar */}
      <ScenarioBar
        scenarios={scenarios}
        selectedId={selectedScenarioId}
        onSelect={setSelectedScenarioId}
        onCreateNew={() => setShowCreateModal(true)}
      />

      {/* Main Content - Two Column Layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Column: Map + Narrative */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0 bg-white min-h-[400px] lg:min-h-0">
          {/* Map Container */}
          <div className="flex-1 relative min-h-[300px]">
            {/* Map Label */}
            <div className="absolute top-4 left-4 z-10 bg-white rounded-lg shadow-sm border border-slate-200 px-3 py-2 flex items-center gap-2">
              <MapIcon className="w-4 h-4 text-slate-600" />
              <span className="text-xs font-semibold text-slate-700">Spatial Strategy Map</span>
            </div>

            <Map
              ref={mapRef}
              initialViewState={{
                longitude: 0.1218,
                latitude: 52.2053,
                zoom: 11.5,
              }}
              style={{ width: '100%', height: '100%' }}
              mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
              interactiveLayerIds={['sites-fill']}
              onClick={(e) => {
                const features = e.features;
                if (features && features.length > 0) {
                  const f = features[0];
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
            >
              <NavigationControl position="top-right" showCompass={false} />
              <ScaleControl position="bottom-left" />

              {/* Green Belt */}
              <Source type="geojson" data={constraintsLayers.greenBelt}>
                <Layer
                  id="greenbelt-fill"
                  type="fill"
                  paint={{
                    'fill-color': '#22c55e',
                    'fill-opacity': 0.15,
                  }}
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
                      ['get', 'allocated'],
                      '#3b82f6', // blue for allocated
                      '#94a3b8', // grey for omitted
                    ],
                    'fill-opacity': [
                      'case',
                      ['get', 'allocated'],
                      0.6,
                      0.3,
                    ],
                  }}
                />
                <Layer
                  id="sites-outline"
                  type="line"
                  paint={{
                    'line-color': [
                      'case',
                      ['get', 'allocated'],
                      '#1d4ed8',
                      '#64748b',
                    ],
                    'line-width': [
                      'case',
                      ['get', 'allocated'],
                      2,
                      1,
                    ],
                  }}
                />
                {/* Site markers/circles */}
                <Layer
                  id="sites-circles"
                  type="circle"
                  paint={{
                    'circle-radius': 8,
                    'circle-color': [
                      'case',
                      ['get', 'allocated'],
                      '#3b82f6',
                      '#94a3b8',
                    ],
                    'circle-stroke-width': 2,
                    'circle-stroke-color': '#ffffff',
                  }}
                />
              </Source>

              {/* Popup */}
              {popupInfo && (
                <Popup
                  longitude={popupInfo.longitude}
                  latitude={popupInfo.latitude}
                  anchor="bottom"
                  onClose={() => setPopupInfo(null)}
                  closeButton={true}
                  closeOnClick={false}
                >
                  <div className="p-2 min-w-[180px]">
                    <div className="font-semibold text-sm text-neutral-900 mb-1">{popupInfo.name}</div>
                    <div className="text-xs text-neutral-500 capitalize mb-2">{popupInfo.landType.replace('-', ' ')}</div>
                    <div className="flex items-center justify-between text-xs">
                      <span className={popupInfo.allocated ? 'text-blue-600 font-medium' : 'text-neutral-500'}>
                        {popupInfo.allocated ? 'Allocated' : 'Omitted'}
                      </span>
                      <span className="text-neutral-700 font-medium">{popupInfo.capacity.toLocaleString()} units</span>
                    </div>
                  </div>
                </Popup>
              )}
            </Map>

            {/* Legend */}
            <div className="absolute bottom-4 left-4 z-10 bg-white rounded-lg shadow-sm border border-slate-200 px-3 py-2">
              <div className="flex items-center gap-4 text-[11px] font-medium">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="text-slate-600">Allocated</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-slate-400" />
                  <span className="text-slate-500">Omitted</span>
                </div>
              </div>
            </div>
          </div>

          {/* Narrative */}
          <div className="p-5 border-t border-slate-200 bg-white flex-shrink-0">
            <PlanNarrative
              narrative={selectedScenario.narrative}
              scenarioName={selectedScenario.name}
              onViewTrace={() => onOpenTrace?.({ 
                kind: 'narrative', 
                id: selectedScenarioId, 
                label: `${selectedScenario.name} narrative` 
              })}
            />
          </div>
        </div>

        {/* Right Column: Sites Panel */}
        <div className="w-full lg:w-[420px] flex-shrink-0 border-t lg:border-t-0 lg:border-l border-slate-200 overflow-hidden bg-slate-50 max-h-[500px] lg:max-h-none">
          <AllocatedSitesPanel
            allocatedSites={allocated}
            omittedSites={omitted}
            onOpenTrace={onOpenTrace}
          />
        </div>
      </div>

      {/* Create Strategy Modal */}
      <CreateStrategyModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreateScenario={handleCreateScenario}
      />
    </div>
  );
}
