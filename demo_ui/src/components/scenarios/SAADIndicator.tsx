/**
 * SAAD Indicator Component
 * 
 * Displays Suitability, Availability, Achievability, Deliverability status
 * with traffic-light coloring (green/amber/red)
 */

import { CheckCircle, AlertCircle, XCircle, Info } from 'lucide-react';
import { SAADStatus } from '../../fixtures/extendedMockData';
import { cn } from '../ui/utils';

interface SAADIndicatorProps {
  status: SAADStatus;
  label: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
  tooltip?: string;
}

const statusConfig: Record<SAADStatus, { icon: typeof CheckCircle; bg: string; text: string; border: string }> = {
  green: {
    icon: CheckCircle,
    bg: 'bg-emerald-100',
    text: 'text-emerald-700',
    border: 'border-emerald-300',
  },
  amber: {
    icon: AlertCircle,
    bg: 'bg-amber-100',
    text: 'text-amber-700',
    border: 'border-amber-300',
  },
  red: {
    icon: XCircle,
    bg: 'bg-red-100',
    text: 'text-red-700',
    border: 'border-red-300',
  },
};

export function SAADIndicator({ status, label, showLabel = true, size = 'sm', tooltip }: SAADIndicatorProps) {
  const config = statusConfig[status];
  const Icon = config.icon;
  
  const sizeClasses = size === 'sm' 
    ? 'px-2 py-0.5 text-[10px] gap-1' 
    : 'px-2.5 py-1 text-xs gap-1.5';
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full border font-medium',
        config.bg,
        config.text,
        config.border,
        sizeClasses
      )}
      title={tooltip}
    >
      <Icon className={iconSize} />
      {showLabel && <span>{label}</span>}
    </div>
  );
}

interface SAADIndicatorRowProps {
  saad: {
    suitability: SAADStatus;
    availability: SAADStatus;
    achievability: SAADStatus;
    deliverability: SAADStatus;
  };
  size?: 'sm' | 'md';
}

const saadDescriptions = {
  suitability: 'Site characteristics support proposed use (access, topography, contamination, flood risk)',
  availability: 'Site can be developed now - ownership resolved, no legal impediments',
  achievability: 'Development is economically viable and attractive to the market',
  deliverability: 'Site can deliver homes within 5 years with realistic lead-in times',
};

export function SAADIndicatorRow({ saad, size = 'sm' }: SAADIndicatorRowProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <SAADIndicator 
        status={saad.suitability} 
        label="Suitability" 
        size={size}
        tooltip={saadDescriptions.suitability}
      />
      <SAADIndicator 
        status={saad.availability} 
        label="Availability" 
        size={size}
        tooltip={saadDescriptions.availability}
      />
      <SAADIndicator 
        status={saad.achievability} 
        label="Achievability" 
        size={size}
        tooltip={saadDescriptions.achievability}
      />
      <SAADIndicator 
        status={saad.deliverability} 
        label="Deliverability" 
        size={size}
        tooltip={saadDescriptions.deliverability}
      />
    </div>
  );
}
