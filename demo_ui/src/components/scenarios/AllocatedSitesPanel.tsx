/**
 * AllocatedSitesPanel Component
 * 
 * Scrollable list of site allocation cards with summary header
 */

import { useState } from 'react';
import { MapPin, Home, ChevronRight } from 'lucide-react';
import { EnrichedSiteProperties } from '../../fixtures/extendedMockData';
import { SiteAllocationCard } from './SiteAllocationCard';
import { Badge } from '../ui/badge';
import { cn } from '../ui/utils';
import type { TraceTarget } from '../../lib/trace';

interface AllocatedSitesPanelProps {
  allocatedSites: { properties: EnrichedSiteProperties }[];
  omittedSites: { properties: EnrichedSiteProperties }[];
  onOpenTrace?: (target?: TraceTarget) => void;
}

export function AllocatedSitesPanel({ allocatedSites, omittedSites, onOpenTrace }: AllocatedSitesPanelProps) {
  // Defensive defaults in case upstream data is missing
  const safeAllocated = Array.isArray(allocatedSites) ? allocatedSites : [];
  const safeOmitted = Array.isArray(omittedSites) ? omittedSites : [];

  // Default first site expanded to show SAAD indicators
  const [expandedSiteId, setExpandedSiteId] = useState<string | null>(
    safeAllocated.length > 0 ? safeAllocated[0].properties.id : null
  );
  const [showOmitted, setShowOmitted] = useState(false);

  const totalCapacity = safeAllocated.reduce((sum, s) => sum + (s?.properties?.capacity ?? 0), 0);
  const omittedCapacity = safeOmitted.reduce((sum, s) => sum + (s?.properties?.capacity ?? 0), 0);

  return (
    <div className="flex flex-col bg-slate-50">
      {/* Header */}
      <div className="px-4 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-indigo-600" />
              Allocated Sites
            </h3>
            <span className="text-xs font-medium text-slate-500">{safeAllocated.length}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-indigo-50 px-2.5 py-1 rounded-md border border-indigo-100">
            <Home className="w-3.5 h-3.5 text-indigo-600" />
            <span className="font-bold text-slate-900">{totalCapacity.toLocaleString()}</span>
            <span className="text-slate-500">units</span>
          </div>
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">
          Total Capacity: <strong className="text-slate-700">{totalCapacity.toLocaleString()} units</strong>
        </p>
      </div>
      
      {/* Allocated Sites List */}
      <div className="p-4 space-y-3">
        {safeAllocated.map(site => (
          <SiteAllocationCard
            key={site.properties.id}
            site={site.properties}
            expanded={expandedSiteId === site.properties.id}
            onToggle={() => setExpandedSiteId(
              expandedSiteId === site.properties.id ? null : site.properties.id
            )}
            onViewTrace={() => onOpenTrace?.({ 
              kind: 'site', 
              id: site.properties.id, 
              label: site.properties.name 
            })}
            isAllocated
          />
        ))}
      </div>
      
      {/* Omitted Sites Section */}
      {safeOmitted.length > 0 && (
        <div className="border-t border-neutral-200 bg-white">
          <button
            onClick={() => setShowOmitted(!showOmitted)}
            className="w-full p-3 flex items-center justify-between text-left hover:bg-neutral-50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[11px] text-neutral-600">
                Omitted Sites
              </Badge>
              <span className="text-xs text-neutral-500">
                {safeOmitted.length} sites · {omittedCapacity.toLocaleString()} units
              </span>
            </div>
            <ChevronRight className={cn(
              'w-4 h-4 text-neutral-400 transition-transform',
              showOmitted && 'rotate-90'
            )} />
          </button>
          
          {showOmitted && (
            <div className="px-3 pb-3 space-y-2 max-h-48 overflow-y-auto">
              {safeOmitted.map(site => (
                <SiteAllocationCard
                  key={site.properties.id}
                  site={site.properties}
                  expanded={expandedSiteId === site.properties.id}
                  onToggle={() => setExpandedSiteId(
                    expandedSiteId === site.properties.id ? null : site.properties.id
                  )}
                  onViewTrace={() => onOpenTrace?.({ 
                    kind: 'site', 
                    id: site.properties.id, 
                    label: site.properties.name 
                  })}
                  isAllocated={false}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
