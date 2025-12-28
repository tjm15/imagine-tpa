/**
 * ScoreBar Component
 * 
 * Displays a progress bar with icon, label, and numeric score (0-10)
 */

import { LucideIcon, Bus, Leaf, Info } from 'lucide-react';
import { cn } from '../ui/utils';

interface ScoreBarProps {
  label: string;
  score: number; // 0-10
  icon: LucideIcon;
  colorClass?: string;
  tooltip?: string;
}

function getScoreColor(score: number): string {
  if (score >= 8) return 'bg-emerald-500';
  if (score >= 6) return 'bg-amber-500';
  return 'bg-red-500';
}

export function ScoreBar({ label, score, icon: Icon, colorClass, tooltip }: ScoreBarProps) {
  const percentage = (score / 10) * 100;
  const color = colorClass || getScoreColor(score);

  return (
    <div className="flex items-center gap-2" title={tooltip}>
      <Icon className="w-4 h-4 text-neutral-500 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[11px] text-neutral-600 truncate">{label}</span>
          <span className={cn('text-[11px] font-semibold', score >= 8 ? 'text-emerald-700' : score >= 6 ? 'text-amber-700' : 'text-red-700')}>
            {score.toFixed(1)}/10
          </span>
        </div>
        <div className="h-1.5 bg-neutral-200 rounded-full overflow-hidden">
          <div 
            className={cn('h-full rounded-full transition-all duration-300', color)}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    </div>
  );
}

interface AccessibilitySustainabilityScoresProps {
  accessibilityScore: number;
  sustainabilityScore: number;
}

export function AccessibilitySustainabilityScores({ 
  accessibilityScore, 
  sustainabilityScore 
}: AccessibilitySustainabilityScoresProps) {
  return (
    <div className="space-y-2">
      <ScoreBar 
        label="Accessibility" 
        score={accessibilityScore} 
        icon={Bus}
        tooltip="Public transport accessibility level (PTAL equivalent) - measures ease of access by public transport"
      />
      <ScoreBar 
        label="Sustainability" 
        score={sustainabilityScore} 
        icon={Leaf}
        tooltip="Composite sustainability score based on SA objectives (climate, biodiversity, resources)"
      />
    </div>
  );
}
