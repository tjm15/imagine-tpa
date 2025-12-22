import { WorkspaceMode } from '../../App';
import { 
  Layers, ZoomIn, ZoomOut, Maximize2, MapPin, Circle, Square, 
  Download, Eye, EyeOff 
} from 'lucide-react';
import { useState } from 'react';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface MapViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
}

export function MapView({ workspace, explainabilityMode = 'summary' }: MapViewProps) {
  const [activeLayers, setActiveLayers] = useState({
    constraints: true,
    transport: true,
    sites: workspace === 'plan',
    boundaries: true,
  });

  const toggleLayer = (layer: keyof typeof activeLayers) => {
    setActiveLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
  };

  return (
    <div className="h-full flex flex-col">
      {/* Map Controls Header */}
      <div className="bg-white border-b border-neutral-200 p-4 flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg mb-1">
            {workspace === 'plan' ? 'Strategic Map Canvas' : 'Site Context Map'}
          </h2>
          <p className="text-sm text-neutral-600">
            Draw to query, snapshot to cite
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
            <Download className="w-4 h-4" />
            Export Snapshot
          </button>
          <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
            <Maximize2 className="w-4 h-4" />
            Fullscreen
          </button>
        </div>
      </div>

      {/* Map Container */}
      <div className="flex-1 relative bg-neutral-100">
        {/* Map Placeholder */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <MapPin className="w-16 h-16 text-neutral-300 mx-auto mb-4" />
            <p className="text-neutral-600 mb-2">Interactive Map Canvas</p>
            <p className="text-sm text-neutral-500">
              {workspace === 'plan' 
                ? 'Cambridge authority area with constraints and site options'
                : '45 Mill Road, Cambridge CB1 2AD'}
            </p>
          </div>
        </div>

        {/* Site Marker (for Casework) */}
        {workspace === 'casework' && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="relative">
              <div className="w-8 h-8 bg-[color:var(--color-warning)] rounded-full border-4 border-white shadow-lg animate-pulse" />
              <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-white px-3 py-1 rounded shadow-lg whitespace-nowrap text-sm">
                45 Mill Road
              </div>
            </div>
          </div>
        )}

        {/* Map Controls */}
        <div className="absolute top-4 right-4 flex flex-col gap-2">
          <div className="bg-white rounded-lg shadow-lg border border-neutral-200 p-2 flex flex-col gap-1">
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Zoom in">
              <ZoomIn className="w-4 h-4" />
            </button>
            <div className="h-px bg-neutral-200" />
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Zoom out">
              <ZoomOut className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Drawing Tools */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
          <div className="bg-white rounded-lg shadow-lg border border-neutral-200 px-4 py-2 flex items-center gap-3">
            <span className="text-sm text-neutral-600">Draw to query:</span>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Point marker">
              <MapPin className="w-4 h-4" />
            </button>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Circle">
              <Circle className="w-4 h-4" />
            </button>
            <button className="p-2 hover:bg-neutral-100 rounded transition-colors" title="Polygon">
              <Square className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Layer Control Panel */}
        <div className="absolute top-4 left-4 bg-white rounded-lg shadow-lg border border-neutral-200 p-4 w-64">
          <div className="flex items-center gap-2 mb-3">
            <Layers className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
            <h3 className="text-sm">Map Layers</h3>
          </div>
          <div className="space-y-2">
            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.boundaries}
                  onChange={() => toggleLayer('boundaries')}
                  className="rounded"
                />
                <span className="text-sm">Authority Boundary</span>
              </div>
              {activeLayers.boundaries ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.constraints}
                  onChange={() => toggleLayer('constraints')}
                  className="rounded"
                />
                <span className="text-sm">Constraints</span>
              </div>
              {activeLayers.constraints ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            {activeLayers.constraints && (
              <div className="ml-6 space-y-1 text-xs">
                <div className="flex items-center gap-2 py-1">
                  <div className="w-3 h-3 bg-green-500 rounded" />
                  <span className="text-neutral-600">Green Belt</span>
                </div>
                <div className="flex items-center gap-2 py-1">
                  <div className="w-3 h-3 bg-blue-400 rounded" />
                  <span className="text-neutral-600">Flood Zones</span>
                </div>
                <div className="flex items-center gap-2 py-1">
                  <div className="w-3 h-3 bg-amber-400 rounded" />
                  <span className="text-neutral-600">Conservation Areas</span>
                </div>
              </div>
            )}

            <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={activeLayers.transport}
                  onChange={() => toggleLayer('transport')}
                  className="rounded"
                />
                <span className="text-sm">Transport Network</span>
              </div>
              {activeLayers.transport ? (
                <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
              ) : (
                <EyeOff className="w-4 h-4 text-neutral-400" />
              )}
            </label>

            {workspace === 'plan' && (
              <label className="flex items-center justify-between gap-3 cursor-pointer p-2 hover:bg-neutral-50 rounded transition-colors">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={activeLayers.sites}
                    onChange={() => toggleLayer('sites')}
                    className="rounded"
                  />
                  <span className="text-sm">Candidate Sites</span>
                </div>
                {activeLayers.sites ? (
                  <Eye className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
                ) : (
                  <EyeOff className="w-4 h-4 text-neutral-400" />
                )}
              </label>
            )}
          </div>

          {workspace === 'plan' && activeLayers.sites && (
            <div className="mt-4 pt-3 border-t border-neutral-200">
              <p className="text-xs text-neutral-600 mb-2">Site Status Legend:</p>
              <div className="space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-[color:var(--color-success)] rounded" />
                  <span>Allocated (24)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-[color:var(--color-stage)] rounded" />
                  <span>Under Assessment (67)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-neutral-300 rounded" />
                  <span>Not Suitable (142)</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
