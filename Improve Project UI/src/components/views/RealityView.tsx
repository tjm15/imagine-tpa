import { WorkspaceMode } from '../../App';
import { Camera, MapPin, Eye, Download, AlertTriangle, Maximize2, Database, Terminal, Sparkles } from 'lucide-react';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface RealityViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
}

export function RealityView({ workspace, explainabilityMode = 'summary' }: RealityViewProps) {
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-neutral-200 p-4 flex items-center justify-between flex-shrink-0">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Camera className="w-5 h-5 text-[color:var(--color-gov-blue)]" />
            <h2 className="text-lg">
              {workspace === 'plan' ? 'Visual Evidence & Overlays' : 'Site Photos & Context'}
            </h2>
          </div>
          <p className="text-sm text-neutral-600">
            {workspace === 'plan' 
              ? 'Visuospatial reasoning with plan-reality registration'
              : 'Photographic evidence from site visit with caveated interpretations'}
          </p>
        </div>
        <button className="px-3 py-1.5 text-sm border border-neutral-300 rounded hover:bg-neutral-50 transition-colors flex items-center gap-2">
          <Download className="w-4 h-4" />
          Export Evidence Pack
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          {workspace === 'plan' ? (
            <>
              {/* Plan-Reality Overlay */}
              <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
                <div className="p-4 border-b border-neutral-200">
                  <h3 className="mb-2">Site Analysis: Northern Fringe Candidate Site</h3>
                  <p className="text-sm text-neutral-600">
                    Plan-reality overlay showing proposed allocation boundary vs. actual site conditions
                  </p>
                </div>
                <div className="aspect-video bg-neutral-100 relative">
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center">
                      <Eye className="w-12 h-12 text-neutral-300 mx-auto mb-2" />
                      <p className="text-neutral-500 text-sm">Plan-Reality Overlay Canvas</p>
                      <p className="text-xs text-neutral-400 mt-1">Registered site plan with aerial imagery</p>
                    </div>
                  </div>
                  <button className="absolute top-4 right-4 p-2 bg-white rounded shadow hover:bg-neutral-50">
                    <Maximize2 className="w-4 h-4" />
                  </button>
                  
                  {/* Overlay Indicators */}
                  <div className="absolute bottom-4 left-4 space-y-2">
                    <div className="bg-white rounded shadow px-3 py-2 text-xs flex items-center gap-2">
                      <div className="w-3 h-3 bg-blue-500 border-2 border-white rounded" />
                      <span>Proposed allocation boundary</span>
                    </div>
                    <div className="bg-white rounded shadow px-3 py-2 text-xs flex items-center gap-2">
                      <div className="w-3 h-3 bg-green-500 border-2 border-white rounded" />
                      <span>Existing vegetation (retained)</span>
                    </div>
                  </div>
                </div>
                <div className="p-4 bg-amber-50 border-t border-amber-200">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div className="text-sm">
                      <span className="text-amber-800">Transform Uncertainty:</span>
                      <span className="text-neutral-700 ml-1">
                        Registration confidence: Medium. Site plan dated 2022; recent development visible in aerial may not be reflected. 
                        Ground truthing recommended.
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Aerial Context */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
                  <div className="aspect-video bg-neutral-100 relative">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <MapPin className="w-10 h-10 text-neutral-300" />
                    </div>
                  </div>
                  <div className="p-3">
                    <h4 className="text-sm mb-1">Site Context: North</h4>
                    <p className="text-xs text-neutral-600">
                      Established residential to north. Two-storey height datum.
                    </p>
                    <div className="flex items-center gap-2 text-xs text-neutral-500 mt-2">
                      <Camera className="w-3 h-3" />
                      <span>Captured: 12 Nov 2024</span>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
                  <div className="aspect-video bg-neutral-100 relative">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <MapPin className="w-10 h-10 text-neutral-300" />
                    </div>
                  </div>
                  <div className="p-3">
                    <h4 className="text-sm mb-1">Site Access: East</h4>
                    <p className="text-xs text-neutral-600">
                      Existing field access road. Width ~4.5m, suitable for residential.
                    </p>
                    <div className="flex items-center gap-2 text-xs text-neutral-500 mt-2">
                      <Camera className="w-3 h-3" />
                      <span>Captured: 12 Nov 2024</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Visual Features */}
              <div className="bg-white rounded-lg border border-neutral-200 p-4">
                <h3 className="mb-3">Extracted Visual Features</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex items-start gap-3 p-2 hover:bg-neutral-50 rounded">
                    <div className="w-20 h-20 bg-neutral-100 rounded flex-shrink-0" />
                    <div className="flex-1">
                      <h4 className="text-sm mb-1">Scale Bar (Site Plan)</h4>
                      <p className="text-xs text-neutral-600">Extracted: 1:500 scale, 50m bar</p>
                      <p className="text-xs text-[color:var(--color-gov-blue)] mt-1 cursor-pointer hover:underline">
                        Use for overlay calibration →
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 p-2 hover:bg-neutral-50 rounded">
                    <div className="w-20 h-20 bg-neutral-100 rounded flex-shrink-0" />
                    <div className="flex-1">
                      <h4 className="text-sm mb-1">North Arrow</h4>
                      <p className="text-xs text-neutral-600">Orientation: 12° east of grid north</p>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Site Visit Photos */}
              <div className="bg-white rounded-lg border border-neutral-200 p-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="mb-1">Site Visit Evidence</h3>
                    <p className="text-sm text-neutral-600">45 Mill Road, Cambridge - Visit: 12 Dec 2024</p>
                  </div>
                  <span className="text-xs px-2 py-1 bg-[color:var(--color-success-light)] text-[color:var(--color-success)] rounded">
                    Site visit complete
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="border border-neutral-200 rounded overflow-hidden">
                    <div className="aspect-video bg-neutral-100 relative">
                      <div className="absolute inset-0 flex items-center justify-center">
                        <Camera className="w-10 h-10 text-neutral-300" />
                      </div>
                      <div className="absolute top-2 left-2 bg-white px-2 py-1 rounded text-xs">
                        Photo 1
                      </div>
                    </div>
                    <div className="p-3">
                      <h4 className="text-sm mb-1">Street Frontage</h4>
                      <p className="text-xs text-neutral-600 mb-2">
                        Existing shopfront in reasonable condition. Traditional proportions maintained.
                      </p>
                      <div className="text-xs text-neutral-500">
                        View: North from Mill Road
                      </div>
                    </div>
                  </div>

                  <div className="border border-neutral-200 rounded overflow-hidden">
                    <div className="aspect-video bg-neutral-100 relative">
                      <div className="absolute inset-0 flex items-center justify-center">
                        <Camera className="w-10 h-10 text-neutral-300" />
                      </div>
                      <div className="absolute top-2 left-2 bg-white px-2 py-1 rounded text-xs">
                        Photo 2
                      </div>
                    </div>
                    <div className="p-3">
                      <h4 className="text-sm mb-1">Rear Courtyard Access</h4>
                      <p className="text-xs text-neutral-600 mb-2">
                        Shared access to rear courtyard. Width ~3.2m. Suitable for bin/cycle storage.
                      </p>
                      <div className="text-xs text-neutral-500">
                        View: East from rear
                      </div>
                    </div>
                  </div>

                  <div className="border border-neutral-200 rounded overflow-hidden">
                    <div className="aspect-video bg-neutral-100 relative">
                      <div className="absolute inset-0 flex items-center justify-center">
                        <Camera className="w-10 h-10 text-neutral-300" />
                      </div>
                      <div className="absolute top-2 left-2 bg-white px-2 py-1 rounded text-xs">
                        Photo 3
                      </div>
                    </div>
                    <div className="p-3">
                      <h4 className="text-sm mb-1">Ground Floor Interior</h4>
                      <p className="text-xs text-neutral-600 mb-2">
                        Existing retail space. Natural light from front and rear adequate for residential conversion.
                      </p>
                      <div className="text-xs text-neutral-500">
                        View: Interior looking south
                      </div>
                    </div>
                  </div>

                  <div className="border border-neutral-200 rounded overflow-hidden">
                    <div className="aspect-video bg-neutral-100 relative">
                      <div className="absolute inset-0 flex items-center justify-center">
                        <Camera className="w-10 h-10 text-neutral-300" />
                      </div>
                      <div className="absolute top-2 left-2 bg-white px-2 py-1 rounded text-xs">
                        Photo 4
                      </div>
                    </div>
                    <div className="p-3">
                      <h4 className="text-sm mb-1">Street Context</h4>
                      <p className="text-xs text-neutral-600 mb-2">
                        Mixed retail/residential on Mill Road. Other conversions visible within 50m.
                      </p>
                      <div className="text-xs text-neutral-500">
                        View: South along Mill Road
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Officer Observations */}
              <div className="bg-white rounded-lg border border-neutral-200 p-4">
                <h3 className="mb-3">Officer Observations</h3>
                <div className="space-y-3 text-sm">
                  <div className="p-3 bg-neutral-50 rounded">
                    <h4 className="text-sm mb-1">Amenity Assessment</h4>
                    <p className="text-neutral-700">
                      Light levels in proposed ground floor flat appear adequate. Rear courtyard provides 
                      outdoor space/cycle storage. Ceiling height ~3.1m allows good ceiling height for conversion.
                    </p>
                  </div>
                  <div className="p-3 bg-neutral-50 rounded">
                    <h4 className="text-sm mb-1">Character Impact</h4>
                    <p className="text-neutral-700">
                      No external alterations proposed. Shopfront to be retained as per condition. 
                      Conversion would not harm Mill Road character or conservation area.
                    </p>
                  </div>
                  <div className="p-3 bg-blue-50 rounded">
                    <h4 className="text-sm mb-1">Precedent Context</h4>
                    <p className="text-neutral-700">
                      At least 3 similar retail-to-resi conversions approved on Mill Road in past 5 years 
                      (refs: 19/0234/FUL, 20/0891/FUL, 22/0445/FUL). Consistency supports approval.
                    </p>
                  </div>
                </div>
              </div>

              {/* Limitations */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm">
                    <h4 className="text-amber-800 mb-1">Evidence Limitations</h4>
                    <p className="text-neutral-700">
                      Photos taken in December with limited daylight. Summer light levels may differ. 
                      Internal measurements from visual estimation only; detailed survey not available. 
                      Noise levels from adjacent uses not formally assessed.
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
