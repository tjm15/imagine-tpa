/**
 * Interactive Map View with MapLibre GL
 * 
 * Features:
 * - OSM base tiles (Carto Voyager)
 * - GeoJSON layers: sites, constraints, boundary
 * - Layer visibility toggles
 * - Click-to-identify on allocations
 * - Drawing tools for spatial queries
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import Map, { 
  Source, 
  Layer, 
  Popup, 
  NavigationControl,
  ScaleControl,
  GeolocateControl,
  type MapRef,
  type MapLayerMouseEvent
} from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { 
  Layers, ZoomIn, ZoomOut, Maximize2, MapPin, Circle, Square, 
  Download, Eye, EyeOff, Info, X, ChevronRight, Database
} from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { 
  cambridgeBoundary, 
  siteAllocations, 
  constraintsLayers 
} from '../../fixtures/extendedMockData';
import { useAppState } from '../../lib/appState';
import { toast } from 'sonner';
import { ProvenanceIndicator, StatusBadge } from '../ProvenanceIndicator';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface MapViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
  // Scenario modelling support
  scenarioId?: string;
  allocatedSiteIds?: string[];
  omittedSiteIds?: string[];
}

interface PopupInfo {
  longitude: number;
  latitude: number;
  properties: Record<string, unknown>;
  layerType: 'site' | 'constraint' | 'boundary';
}

// Layer style definitions
const boundaryStyle = {
  id: 'boundary-line',
  type: 'line' as const,
  paint: {
    'line-color': '#1e40af',
    'line-width': 3,
    'line-dasharray': [2, 2],
  },
};

const sitesStyle = {
  id: 'sites-fill',
  type: 'fill' as const,
  paint: {
    'fill-color': [
      'match',
      ['get', 'status'],
      'committed', '#10b981',
      'shortlisted', '#f59e0b',
      'under-assessment', '#6366f1',
      '#94a3b8',
    ] as unknown as string,
    'fill-opacity': 0.6,
  },
};

const sitesOutlineStyle = {
  id: 'sites-outline',
  type: 'line' as const,
  paint: {
    'line-color': '#1e293b',
    'line-width': 2,
  },
};

const greenBeltStyle = {
  id: 'greenbelt-fill',
  type: 'fill' as const,
  paint: {
    'fill-color': '#22c55e',
    'fill-opacity': 0.2,
  },
};

const floodZoneStyle = {
  id: 'flood-fill',
  type: 'fill' as const,
  paint: {
    'fill-color': '#3b82f6',
    'fill-opacity': 0.3,
  },
};

const conservationStyle = {
  id: 'conservation-fill',
  type: 'fill' as const,
  paint: {
    'fill-color': '#a855f7',
    'fill-opacity': 0.25,
  },
};

export function MapView({ 
  workspace, 
  explainabilityMode = 'summary', 
  onOpenTrace,
  scenarioId,
  allocatedSiteIds,
  omittedSiteIds,
}: MapViewProps) {
  const mapRef = useRef<MapRef>(null);
  const { openModal, notify, adjustedSiteIds, highlightedSiteId } = useAppState();
  
  // When in scenario mode, filter sites by allocated/omitted
  const isScenarioMode = Boolean(scenarioId && allocatedSiteIds);
  
  // Create scenario-aware site data
  const scenarioSiteAllocations = useMemo(() => {
    return {
      ...siteAllocations,
      features: siteAllocations.features.map(f => ({
        ...f,
        properties: {
          ...f.properties,
          adjusted: adjustedSiteIds.has(f.properties.id),
          ...(isScenarioMode ? { allocated: allocatedSiteIds?.includes(f.properties.id) ?? false } : null),
        },
      })),
    };
  }, [adjustedSiteIds, isScenarioMode, allocatedSiteIds]);

  const sitesOutlineStyleWithAdjustments = useMemo(() => {
    return {
      ...sitesOutlineStyle,
      paint: {
        ...sitesOutlineStyle.paint,
        'line-color': [
          'case',
          ['get', 'adjusted'],
          '#f59e0b',
          '#1e293b',
        ] as unknown as string,
        'line-width': [
          'case',
          ['get', 'adjusted'],
          3,
          2,
        ] as unknown as number,
      },
    };
  }, []);
  
  // Scenario-aware site styles
  const scenarioSitesStyle = useMemo(() => {
    if (!isScenarioMode) return sitesStyle;
    
    return {
      ...sitesStyle,
      paint: {
        ...sitesStyle.paint,
        'fill-color': [
          'case',
          ['get', 'allocated'],
          '#10b981', // emerald for allocated
          '#94a3b8', // grey for omitted
        ] as unknown as string,
        'fill-opacity': [
          'case',
          ['get', 'allocated'],
          0.6,
          0.3,
        ] as unknown as number,
      },
    };
  }, [isScenarioMode]);
  
  const scenarioSitesOutlineStyle = useMemo(() => {
    if (!isScenarioMode) return sitesOutlineStyleWithAdjustments;
    
    return {
      ...sitesOutlineStyle,
      paint: {
        ...sitesOutlineStyle.paint,
        'line-color': [
          'case',
          ['get', 'adjusted'],
          '#f59e0b',
          ['get', 'allocated'],
          '#059669', // darker emerald
          '#64748b', // grey
        ] as unknown as string,
        'line-width': [
          'case',
          ['get', 'adjusted'],
          3,
          ['get', 'allocated'],
          2.5,
          1.5,
        ] as unknown as number,
      },
    };
  }, [isScenarioMode, sitesOutlineStyleWithAdjustments]);

  const highlightOutlineStyle = useMemo(() => {
    return {
      id: 'site-highlight',
      type: 'line' as const,
      filter: highlightedSiteId ? ['==', ['get', 'id'], highlightedSiteId] : ['==', ['get', 'id'], '__none__'],
      paint: {
        'line-color': '#2563eb',
        'line-width': 4,
        'line-opacity': highlightedSiteId ? 0.95 : 0,
      },
    };
  }, [highlightedSiteId]);
  
  const [viewState, setViewState] = useState({
    longitude: 0.1218,
    latitude: 52.2053,
    zoom: 12,
  });

  const [layerVisibility, setLayerVisibility] = useState({
    boundary: true,
    sites: true,
    greenBelt: workspace === 'plan',
    floodZone: true,
    conservation: true,
  });

  const [popupInfo, setPopupInfo] = useState<PopupInfo | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedSite, setSelectedSite] = useState<string | null>(null);
  const [drawingMode, setDrawingMode] = useState<'none' | 'point' | 'circle' | 'polygon'>('none');

  const toggleLayer = (layer: keyof typeof layerVisibility) => {
    setLayerVisibility(prev => ({ ...prev, [layer]: !prev[layer] }));
    toast.success(`${layer} layer ${layerVisibility[layer] ? 'hidden' : 'shown'}`);
  };

  const handleMapClick = useCallback((event: MapLayerMouseEvent) => {
    const features = event.features;
    
    if (features && features.length > 0) {
      const feature = features[0];
      const layerId = feature.layer?.id;
      
      let layerType: PopupInfo['layerType'] = 'site';
      if (layerId?.includes('greenbelt') || layerId?.includes('flood') || layerId?.includes('conservation')) {
        layerType = 'constraint';
      } else if (layerId?.includes('boundary')) {
        layerType = 'boundary';
      }

      setPopupInfo({
        longitude: event.lngLat.lng,
        latitude: event.lngLat.lat,
        properties: feature.properties as Record<string, unknown>,
        layerType,
      });

      if (layerType === 'site' && feature.properties?.id) {
        setSelectedSite(feature.properties.id as string);
      }
    } else {
      setPopupInfo(null);
      setSelectedSite(null);
    }
  }, []);

  const handleExportSnapshot = useCallback(() => {
    if (mapRef.current) {
      const canvas = mapRef.current.getCanvas();
      const link = document.createElement('a');
      link.download = `map-snapshot-${new Date().toISOString().slice(0, 10)}.png`;
      link.href = canvas.toDataURL();
      link.click();
      toast.success('Map snapshot exported');
    }
  }, []);

  const handleFullscreen = useCallback(() => {
    const container = document.getElementById('map-container');
    if (container) {
      if (!isFullscreen) {
        container.requestFullscreen?.();
      } else {
        document.exitFullscreen?.();
      }
      setIsFullscreen(!isFullscreen);
    }
  }, [isFullscreen]);

  const handleDrawTool = useCallback((mode: typeof drawingMode) => {
    setDrawingMode(mode);
    if (mode !== 'none') {
      toast.info(`Draw a ${mode} on the map to query features`);
    }
  }, []);

  const zoomToSite = useCallback((siteId: string) => {
    const site = siteAllocations.features.find(f => f.properties?.id === siteId);
    if (site && mapRef.current) {
      const coords = (site.geometry as GeoJSON.Polygon).coordinates[0];
      const lngs = coords.map(c => c[0]);
      const lats = coords.map(c => c[1]);
      const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2;
      const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;
      
      mapRef.current.flyTo({
        center: [centerLng, centerLat],
        zoom: 15,
        duration: 1000,
      });
      setSelectedSite(siteId);
    }
  }, []);

  return (
    <div id="map-container" className="h-full flex flex-col">
      {/* Map Controls Header */}
      <div className="bg-white border-b border-neutral-200 p-4 flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-semibold mb-1">
            {workspace === 'plan' ? 'Strategic Map Canvas' : 'Site Context Map'}
          </h2>
          <p className="text-sm text-neutral-600">
            Click features to identify · Toggle layers · Export snapshots
          </p>
          {onOpenTrace && (
            <button
              className="text-[11px] text-[color:var(--color-gov-blue)] underline-offset-2 hover:underline mt-1"
              onClick={() => {
                if (selectedSite) {
                  onOpenTrace({ kind: 'site', id: selectedSite, label: `Site: ${selectedSite}` });
                  return;
                }
                if (popupInfo?.layerType === 'constraint') {
                  onOpenTrace({ kind: 'constraint', id: String(popupInfo.properties.name ?? 'constraint'), label: String(popupInfo.properties.name ?? 'Constraint') });
                  return;
                }
                onOpenTrace({ kind: 'run', label: 'Current run' });
              }}
            >
              Trace selection
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={handleExportSnapshot}
            className="gap-2"
          >
            <Download className="w-4 h-4" />
            Export Snapshot
          </Button>
          <Button 
            variant="outline" 
            size="sm"
            onClick={handleFullscreen}
            className="gap-2"
          >
            <Maximize2 className="w-4 h-4" />
            {isFullscreen ? 'Exit' : 'Fullscreen'}
          </Button>
        </div>
      </div>

      {/* Map Container */}
      <div className="flex-1 relative">
        <Map
          ref={mapRef}
          {...viewState}
          onMove={evt => setViewState(evt.viewState)}
          onClick={handleMapClick}
          interactiveLayerIds={[
            'sites-fill',
            'greenbelt-fill',
            'flood-fill',
            'conservation-fill',
          ]}
          style={{ width: '100%', height: '100%' }}
          mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
        >
          {/* Navigation Controls */}
          <NavigationControl position="top-right" />
          <ScaleControl position="bottom-right" />
          <GeolocateControl position="top-right" />

          {/* Authority Boundary */}
          {layerVisibility.boundary && (
            <Source type="geojson" data={cambridgeBoundary}>
              <Layer {...boundaryStyle} />
            </Source>
          )}

          {/* Constraints Layers */}
          {layerVisibility.greenBelt && (
            <Source type="geojson" data={constraintsLayers.greenBelt}>
              <Layer {...greenBeltStyle} />
            </Source>
          )}

          {layerVisibility.floodZone && (
            <Source type="geojson" data={constraintsLayers.floodZone}>
              <Layer {...floodZoneStyle} />
            </Source>
          )}

          {layerVisibility.conservation && (
            <Source type="geojson" data={constraintsLayers.conservationAreas}>
              <Layer {...conservationStyle} />
            </Source>
          )}

          {/* Site Allocations */}
          {layerVisibility.sites && (
            <Source type="geojson" data={scenarioSiteAllocations}>
              <Layer {...scenarioSitesStyle} />
              <Layer {...scenarioSitesOutlineStyle} />
              <Layer {...highlightOutlineStyle} />
            </Source>
          )}

          {/* Popup */}
          {popupInfo && (
            <Popup
              longitude={popupInfo.longitude}
              latitude={popupInfo.latitude}
              anchor="bottom"
              onClose={() => setPopupInfo(null)}
              closeButton={true}
              closeOnClick={false}
              className="map-popup"
            >
              <div className="p-2 min-w-[200px]">
                {popupInfo.layerType === 'site' && (
                  <>
                    <div className="flex items-center gap-2 mb-2">
                      <MapPin className="w-4 h-4 text-amber-600" />
                      <span className="font-semibold text-sm">
                        {popupInfo.properties.name as string}
                      </span>
                    </div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Reference:</span>
                        <span className="font-mono">{popupInfo.properties.id as string}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Capacity:</span>
                        <span>{popupInfo.properties.capacity as number} dwellings</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-slate-500">Status:</span>
                        <Badge variant="outline" className="text-[10px] h-5">
                          {popupInfo.properties.status as string}
                        </Badge>
                      </div>
                      {popupInfo.properties.greenBelt as boolean && (
                        <div className="flex items-center gap-1 text-amber-600 mt-1">
                          <Info className="w-3 h-3" />
                          <span>Green Belt site</span>
                        </div>
                      )}
                      {(popupInfo.properties.constraints as string[])?.length > 0 && (
                        <div className="mt-2">
                          <span className="text-slate-500">Constraints:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {(popupInfo.properties.constraints as string[]).map((c: string) => (
                              <Badge key={c} variant="secondary" className="text-[9px]">
                                {c}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                    <Button 
                      size="sm" 
                      className="w-full mt-3 text-xs"
                      onClick={() => {
                        openModal('site-detail', { siteId: popupInfo.properties.id });
                        setPopupInfo(null);
                      }}
                    >
                      View Full Assessment
                    </Button>
                    {onOpenTrace && (
                      <Button 
                        variant="ghost"
                        size="sm" 
                        className="w-full mt-2 text-xs"
                        onClick={() => onOpenTrace({ kind: 'site', id: String(popupInfo.properties.id), label: String(popupInfo.properties.name ?? popupInfo.properties.id) })}
                      >
                        Trace this site
                      </Button>
                    )}
                  </>
                )}

                {popupInfo.layerType === 'constraint' && (
                  <>
                    <div className="font-semibold text-sm mb-1">
                      {popupInfo.properties.name as string}
                    </div>
                    {popupInfo.properties.designated && (
                      <p className="text-xs text-slate-500">
                        Designated: {popupInfo.properties.designated as string}
                      </p>
                    )}
                    {popupInfo.properties.risk && (
                      <p className="text-xs text-blue-600">
                        Risk level: {popupInfo.properties.risk as string}
                      </p>
                    )}
                  </>
                )}
              </div>
            </Popup>
          )}
        </Map>

        {/* Layer Panel */}
        <div className="absolute top-4 left-4 bg-white rounded-lg shadow-lg border border-neutral-200 w-56">
          <div className="p-3 border-b border-neutral-200">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-slate-600" />
              <span className="text-sm font-medium">Map Layers</span>
            </div>
          </div>
          <ScrollArea className="max-h-[300px]">
            <div className="p-3 space-y-3">
              {/* Sites */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-amber-500" />
                  <span className="text-sm">Site Allocations</span>
                </div>
                <button onClick={() => toggleLayer('sites')}>
                  {layerVisibility.sites ? (
                    <Eye className="w-4 h-4 text-slate-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>

              {/* Boundary */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded border-2 border-dashed border-blue-800" />
                  <span className="text-sm">Authority Boundary</span>
                </div>
                <button onClick={() => toggleLayer('boundary')}>
                  {layerVisibility.boundary ? (
                    <Eye className="w-4 h-4 text-slate-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>

              <Separator />

              {/* Green Belt */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-green-500/50" />
                  <span className="text-sm">Green Belt</span>
                </div>
                <button onClick={() => toggleLayer('greenBelt')}>
                  {layerVisibility.greenBelt ? (
                    <Eye className="w-4 h-4 text-slate-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>

              {/* Flood Zone */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-blue-500/50" />
                  <span className="text-sm">Flood Zones</span>
                </div>
                <button onClick={() => toggleLayer('floodZone')}>
                  {layerVisibility.floodZone ? (
                    <Eye className="w-4 h-4 text-slate-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>

              {/* Conservation */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-purple-500/50" />
                  <span className="text-sm">Conservation Areas</span>
                </div>
                <button onClick={() => toggleLayer('conservation')}>
                  {layerVisibility.conservation ? (
                    <Eye className="w-4 h-4 text-slate-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>
            </div>
          </ScrollArea>
        </div>

        {/* Drawing Tools */}
        <div className="absolute top-4 right-16 flex flex-col gap-1 bg-white rounded-lg shadow-lg border border-neutral-200 p-1">
          <button
            onClick={() => handleDrawTool('point')}
            className={`p-2 rounded hover:bg-slate-100 transition-colors ${
              drawingMode === 'point' ? 'bg-blue-100 text-blue-600' : 'text-slate-600'
            }`}
            title="Draw point"
          >
            <MapPin className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleDrawTool('circle')}
            className={`p-2 rounded hover:bg-slate-100 transition-colors ${
              drawingMode === 'circle' ? 'bg-blue-100 text-blue-600' : 'text-slate-600'
            }`}
            title="Draw circle"
          >
            <Circle className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleDrawTool('polygon')}
            className={`p-2 rounded hover:bg-slate-100 transition-colors ${
              drawingMode === 'polygon' ? 'bg-blue-100 text-blue-600' : 'text-slate-600'
            }`}
            title="Draw polygon"
          >
            <Square className="w-4 h-4" />
          </button>
        </div>

        {/* Draw-to-ask helper */}
        {drawingMode !== 'none' && (
          <div className="absolute bottom-4 right-4 bg-white/95 backdrop-blur rounded-lg shadow-lg border border-blue-200 p-3 max-w-sm">
            <div className="flex items-center justify-between mb-1">
              <div className="text-sm font-semibold text-slate-800">Draw to ask</div>
              <StatusBadge status="draft" />
            </div>
            <p className="text-xs text-slate-600">Sketch a {drawingMode} to query constraints and nearby evidence. We’ll pin the evidence stack and open trace.</p>
            <div className="flex items-center gap-2 mt-2 text-xs">
              <ProvenanceIndicator
                provenance={{ source: 'human', confidence: 'medium', status: 'provisional', evidenceIds: ['ev-shlaa-2024','ev-affordability'] }}
                onOpenTrace={onOpenTrace}
              />
              {onOpenTrace ? (
                <button className="text-blue-600 hover:underline" onClick={() => onOpenTrace({ kind: 'evidence', id: 'ev-shlaa-2024', label: 'SHLAA 2024' })}>
                  Open trace
                </button>
              ) : null}
            </div>
          </div>
        )}

        {/* Site List (Plan mode) */}
        {workspace === 'plan' && (
          <div className="absolute bottom-4 left-4 bg-white rounded-lg shadow-lg border border-neutral-200 w-56">
            <div className="p-3 border-b border-neutral-200">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-slate-600" />
                <span className="text-sm font-medium">Candidate Sites</span>
              </div>
            </div>
            <ScrollArea className="max-h-[200px]">
              <div className="p-2 space-y-1">
                {siteAllocations.features.map((site) => (
                  <button
                    key={site.properties?.id}
                    onClick={() => zoomToSite(site.properties?.id as string)}
                    className={`w-full text-left p-2 rounded text-xs hover:bg-slate-50 transition-colors flex items-center justify-between ${
                      selectedSite === site.properties?.id ? 'bg-blue-50 ring-1 ring-blue-200' : ''
                    }`}
                  >
                    <div>
                      <div className="font-medium">{site.properties?.name}</div>
                      <div className="text-slate-500">{site.properties?.capacity} units</div>
                    </div>
                    <ChevronRight className="w-3 h-3 text-slate-400" />
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Provenance info (Inspect/Forensic mode) */}
        {explainabilityMode !== 'summary' && (
          <div className="absolute bottom-4 right-4 bg-white/95 backdrop-blur rounded-lg shadow-lg border border-neutral-200 p-3 max-w-xs">
            <div className="text-xs">
              <div className="font-medium text-slate-700 mb-1">Map Data Sources</div>
              <div className="space-y-1 text-slate-600">
                <div>• Base tiles: Carto Voyager (OSM)</div>
                <div>• Boundary: ONS Geography Dec 2024</div>
                <div>• Sites: SHLAA 2024 (internal)</div>
                <div>• Constraints: EA, Historic England</div>
              </div>
              {explainabilityMode === 'forensic' && (
                <div className="mt-2 pt-2 border-t border-slate-200 text-[10px] font-mono text-slate-500">
                  Last updated: 2024-12-18T14:30:00Z<br/>
                  CRS: EPSG:4326 (WGS84)
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Also export as MapViewInteractive for scenario modelling
export { MapView as MapViewInteractive };
