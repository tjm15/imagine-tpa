import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { Site, LocationContext } from '../types';

interface SpatialMapProps {
  allSites: Site[];
  includedSiteIds: string[];
  locationContext: LocationContext;
}

const SpatialMap: React.FC<SpatialMapProps> = ({ allSites, includedSiteIds, locationContext }) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const markersLayer = useRef<L.LayerGroup | null>(null);

  // Helper to project abstract 0-100 coords to Lat/Lng within the dynamic location bounds
  const projectCoordinates = (x: number, y: number) => {
    const { minLng, maxLng, minLat, maxLat } = locationContext.bounds;
    const lng = minLng + (x / 100) * (maxLng - minLng);
    const lat = minLat + (y / 100) * (maxLat - minLat);
    return [lat, lng] as [number, number]; // Leaflet uses [lat, lng]
  };

  // Initialize Map
  useEffect(() => {
    if (mapInstance.current || !mapContainer.current) return;

    const map = L.map(mapContainer.current, {
      zoomControl: false,
      attributionControl: false
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    L.control.zoom({ position: 'topright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

    mapInstance.current = map;
    markersLayer.current = L.layerGroup().addTo(map);

    // Initial view
    map.setView(
      [locationContext.coordinates.lat, locationContext.coordinates.lng], 
      13
    );

    // Add resize observer to handle container size changes which can cause rendering glitches
    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });
    resizeObserver.observe(mapContainer.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapInstance.current = null;
    };
  }, []); // Init once

  // Update View on Context Change
  useEffect(() => {
    if (!mapInstance.current) return;
    mapInstance.current.flyTo(
      [locationContext.coordinates.lat, locationContext.coordinates.lng], 
      13,
      { animate: true, duration: 1.5 }
    );
  }, [locationContext]);

  // Update Markers
  useEffect(() => {
    if (!mapInstance.current || !markersLayer.current) return;

    // Clear existing markers
    markersLayer.current.clearLayers();

    allSites.forEach(site => {
      const isIncluded = includedSiteIds.includes(site.id);
      const [lat, lng] = projectCoordinates(site.coordinates.x, site.coordinates.y);

      // Create Circle Marker
      const marker = L.circleMarker([lat, lng], {
        radius: isIncluded ? 10 : 6,
        fillColor: isIncluded ? '#4f46e5' : '#cbd5e1', // Indigo-600 vs Slate-300
        color: '#ffffff',
        weight: 2,
        opacity: isIncluded ? 1 : 0.6,
        fillOpacity: isIncluded ? 1 : 0.6
      });

      // Popup Content
      const popupContent = `
        <div class="min-w-[160px]">
          <h4 class="font-bold text-slate-800 text-sm mb-1">${site.name}</h4>
          <div class="text-xs text-slate-500 mb-2">${site.category}</div>
          <div class="flex items-center gap-2">
            <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
              isIncluded ? 'bg-indigo-50 text-indigo-700 border-indigo-100' : 'bg-slate-100 text-slate-500 border-slate-200'
            }">
              ${isIncluded ? 'Allocated' : 'Not Allocated'}
            </span>
            <span class="text-xs font-medium text-slate-700">${site.capacity} units</span>
          </div>
        </div>
      `;

      marker.bindPopup(popupContent, {
        closeButton: false,
        offset: [0, -4]
      });

      // Hover Effects
      marker.on('mouseover', function (e) {
        this.openPopup();
        this.setStyle({ 
          radius: isIncluded ? 12 : 8,
          weight: 3
        });
      });

      marker.on('mouseout', function (e) {
        this.closePopup();
        this.setStyle({ 
          radius: isIncluded ? 10 : 6,
          weight: 2
        });
      });

      // Add to layer group
      markersLayer.current?.addLayer(marker);
    });

  }, [allSites, includedSiteIds, locationContext]);

  return (
    <div className="w-full h-full bg-slate-100 rounded-xl overflow-hidden relative border border-slate-200 z-0">
      <div ref={mapContainer} className="w-full h-full z-0" />
      <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur px-3 py-1.5 rounded-md text-xs border border-slate-200 shadow-sm text-slate-500 z-[1000] pointer-events-none">
        <span className="inline-block w-2 h-2 rounded-full bg-indigo-600 mr-2"></span>
        Allocated
        <span className="inline-block w-2 h-2 rounded-full bg-slate-300 ml-3 mr-2"></span>
        Omitted
      </div>
    </div>
  );
};

export default SpatialMap;