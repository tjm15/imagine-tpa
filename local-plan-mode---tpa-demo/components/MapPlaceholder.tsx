import React from 'react';
import { Site } from '../types';

interface MapPlaceholderProps {
  allSites: Site[];
  includedSiteIds: string[];
}

const MapPlaceholder: React.FC<MapPlaceholderProps> = ({ allSites, includedSiteIds }) => {
  return (
    <div className="w-full h-full bg-slate-100 rounded-xl overflow-hidden relative flex items-center justify-center border border-slate-200">
      {/* Background pattern */}
      <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(#94a3b8 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
      
      <svg viewBox="0 0 100 100" className="w-full h-full max-w-md max-h-md drop-shadow-xl" preserveAspectRatio="xMidYMid meet">
        {/* Mock Borough Shape */}
        <path 
          d="M20,20 Q40,5 60,20 T90,40 Q95,60 80,80 T40,90 Q10,80 10,50 T20,20 Z" 
          fill="#e2e8f0" 
          stroke="#94a3b8" 
          strokeWidth="1.5"
        />
        
        {/* Sites */}
        {allSites.map(site => {
          const isIncluded = includedSiteIds.includes(site.id);
          // Clamp coordinates to ensure they stay within visual bounds (5-95)
          // This handles cases where generated coordinates might be slightly out of expected 0-100 range
          const safeX = Math.max(5, Math.min(95, site.coordinates.x));
          const safeY = Math.max(5, Math.min(95, site.coordinates.y));
          
          return (
            <g key={site.id} className="cursor-pointer group">
              {/* Site Marker */}
              <circle 
                cx={safeX} 
                cy={safeY} 
                r={isIncluded ? 4 : 2}
                fill={isIncluded ? "#4f46e5" : "#cbd5e1"} 
                stroke={isIncluded ? "#ffffff" : "#94a3b8"}
                strokeWidth={isIncluded ? 1.5 : 0.5}
                className={`transition-all duration-300 ${isIncluded ? 'opacity-100' : 'opacity-40'}`}
              />
              
              {/* Label on hover or if important */}
              {isIncluded && (
                <text 
                  x={safeX} 
                  y={safeY - 6} 
                  textAnchor="middle" 
                  className="text-[3px] font-bold fill-indigo-900 bg-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none select-none"
                  style={{ textShadow: '0 0 2px white' }}
                >
                  {site.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      
      <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur px-3 py-1.5 rounded-md text-xs border border-slate-200 shadow-sm text-slate-500">
        <span className="inline-block w-2 h-2 rounded-full bg-indigo-600 mr-2"></span>
        Allocated Site
      </div>
    </div>
  );
};

export default MapPlaceholder;