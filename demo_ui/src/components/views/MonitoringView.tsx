import { BarChart3, ShieldAlert, Timer, TriangleAlert } from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Separator } from '../ui/separator';
import type { TraceTarget } from '../../lib/trace';

export type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

interface MonitoringViewProps {
  workspace: WorkspaceMode;
  explainabilityMode?: ExplainabilityMode;
  onOpenTrace?: (target?: TraceTarget) => void;
}

type IndicatorStatus = 'settled' | 'provisional' | 'attention';

const statusStyles: Record<IndicatorStatus, { badge: string; label: string }> = {
  settled: { badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Settled' },
  provisional: { badge: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Provisional' },
  attention: { badge: 'bg-slate-100 text-slate-700 border-slate-200', label: 'Review' },
};

export function MonitoringView({ explainabilityMode = 'summary' }: MonitoringViewProps) {
  const indicators = [
    { id: 'housing-delivery', name: 'Housing completions (YTD)', value: '612', target: '≥ 1,800 dpa', status: 'provisional' as const, note: 'Monitoring return draft; QA pending.' },
    { id: 'affordability', name: 'Affordability ratio', value: '12.8×', target: '↓ trend', status: 'settled' as const, note: 'Census 2021 + ONS update (3 sources).' },
    { id: 'modal-share', name: 'Active travel mode share', value: '28%', target: '≥ 25%', status: 'attention' as const, note: 'DfT tool limitations; peak-hour sampling.' },
    { id: 'gb-release', name: 'Green Belt release risk', value: 'High', target: 'Exceptional circumstances', status: 'attention' as const, note: 'Case not yet consolidated for Gateway 2.' },
  ];

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="max-w-7xl mx-auto p-8 font-sans">
      <div className="mb-6 pb-4 border-b border-slate-200">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium mb-2" style={{ color: 'var(--color-accent)' }}>
              <BarChart3 className="w-4 h-4" />
              <span className="uppercase tracking-wider text-xs">Monitoring & Governance</span>
            </div>
            <h1 className="text-3xl font-bold text-slate-900 tracking-tight truncate">Plan Soundness Monitoring</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 mt-2">
              <Badge variant="outline" className="bg-slate-50 border-slate-200 text-slate-600 rounded-sm font-normal">Local Plan 2025</Badge>
              <span>CULP statutory loop · evidence currency · gateways · trajectories</span>
              <Separator orientation="vertical" className="h-4" />
              <Badge variant="secondary" className="text-[11px] bg-blue-50 text-blue-700 border-blue-200">{explainabilityMode} mode</Badge>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <Button variant="outline" size="sm" className="gap-2">
              <Timer className="w-4 h-4" />
              Refresh
            </Button>
            <Button size="sm" className="gap-2" style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}>
              <ShieldAlert className="w-4 h-4" />
              Review Signals
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-600 tracking-wide uppercase mb-1">Programme health</div>
          <div className="text-2xl font-semibold text-slate-900">On track</div>
          <div className="text-xs text-slate-600 mt-1">2 warnings · 0 blockers</div>
        </div>
        <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-600 tracking-wide uppercase mb-1">Evidence gaps</div>
          <div className="text-2xl font-semibold text-slate-900">3</div>
          <div className="text-xs text-slate-600 mt-1">Transport baseline · viability · heritage</div>
        </div>
        <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-600 tracking-wide uppercase mb-1">Next gateway</div>
          <div className="text-2xl font-semibold text-slate-900">G1</div>
          <div className="text-xs text-slate-600 mt-1">Self-assessment due in 14 days</div>
        </div>
        <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-600 tracking-wide uppercase mb-1">Contested items</div>
          <div className="text-2xl font-semibold text-slate-900">2</div>
          <div className="text-xs text-slate-600 mt-1">Uplift vs heritage · parking trade-off</div>
        </div>
      </div>

      <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-neutral-200 flex items-center justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-900">Governance signals</div>
            <div className="text-xs text-slate-600">Evidence currency, delivery divergence, and gateway readiness (demo)</div>
          </div>
          <Badge variant="outline" className="text-[11px]">Demo</Badge>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr className="text-xs text-slate-600">
                <th className="text-left font-semibold px-4 py-2.5">Indicator</th>
                <th className="text-left font-semibold px-4 py-2.5">Latest</th>
                <th className="text-left font-semibold px-4 py-2.5">Target / test</th>
                <th className="text-left font-semibold px-4 py-2.5">Status</th>
                <th className="text-left font-semibold px-4 py-2.5">Note</th>
              </tr>
            </thead>
            <tbody>
              {indicators.map((row) => {
                const status = statusStyles[row.status];
                return (
                  <tr key={row.id} className="border-t border-neutral-200">
                    <td className="px-4 py-3 font-medium text-slate-900">{row.name}</td>
                    <td className="px-4 py-3 text-slate-700">{row.value}</td>
                    <td className="px-4 py-3 text-slate-700">{row.target}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${status.badge}`}>
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{row.note}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-6 bg-white border border-neutral-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <TriangleAlert className="w-4 h-4 text-amber-600" />
          <div className="text-sm font-semibold text-slate-900">Attention this week</div>
        </div>
        <ul className="text-sm text-slate-700 list-disc pl-5 space-y-1">
          <li>Transport baseline: modelling assumptions need audit note before Gateway 1.</li>
          <li>Heritage: town centre sensitivity summary missing from the place portrait.</li>
          <li>Viability: affordable housing threshold needs sensitivity testing against brownfield mix.</li>
        </ul>
      </div>
      </div>
    </div>
  );
}
