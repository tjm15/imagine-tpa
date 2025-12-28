/**
 * CreateStrategyModal Component
 * 
 * Modal wizard for creating a new strategic scenario
 */

import { useState } from 'react';
import { 
  X, MapPin, Home, ChevronRight, ChevronLeft, Check, 
  Sparkles, Target, Layers, FileText, AlertCircle
} from 'lucide-react';
import { siteAllocations, EnrichedSiteProperties } from '../../fixtures/extendedMockData';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { cn } from '../ui/utils';

interface CreateStrategyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateScenario: (scenario: NewScenarioData) => void;
}

export interface NewScenarioData {
  name: string;
  description: string;
  allocatedSiteIds: string[];
  color: 'blue' | 'amber' | 'emerald' | 'purple';
}

type WizardStep = 'basics' | 'sites' | 'review';

const colorOptions = [
  { id: 'blue', label: 'Blue', class: 'bg-blue-500' },
  { id: 'amber', label: 'Amber', class: 'bg-amber-500' },
  { id: 'emerald', label: 'Emerald', class: 'bg-emerald-500' },
  { id: 'purple', label: 'Purple', class: 'bg-purple-500' },
] as const;

export function CreateStrategyModal({ isOpen, onClose, onCreateScenario }: CreateStrategyModalProps) {
  const [step, setStep] = useState<WizardStep>('basics');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState<NewScenarioData['color']>('blue');
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);

  const allSites = siteAllocations.features;
  const totalCapacity = allSites
    .filter(s => selectedSiteIds.includes(s.properties.id))
    .reduce((sum, s) => sum + s.properties.capacity, 0);

  const toggleSite = (id: string) => {
    setSelectedSiteIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const canProceedFromBasics = name.trim().length > 0;
  const canProceedFromSites = selectedSiteIds.length > 0;

  const handleCreate = () => {
    onCreateScenario({
      name: name.trim(),
      description: description.trim(),
      allocatedSiteIds: selectedSiteIds,
      color,
    });
    // Reset form
    setStep('basics');
    setName('');
    setDescription('');
    setColor('blue');
    setSelectedSiteIds([]);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b border-neutral-200">
          <div>
            <h2 className="text-lg font-semibold">Create New Strategy</h2>
            <p className="text-sm text-neutral-500">
              Define a spatial strategy scenario for plan-making
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-neutral-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress Steps */}
        <div className="px-6 py-3 border-b border-neutral-100 bg-neutral-50">
          <div className="flex items-center justify-between">
            {[
              { id: 'basics', label: 'Basics', icon: FileText },
              { id: 'sites', label: 'Select Sites', icon: MapPin },
              { id: 'review', label: 'Review', icon: Check },
            ].map((s, idx) => (
              <div key={s.id} className="flex items-center">
                <div className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors',
                  step === s.id 
                    ? 'bg-[color:var(--color-gov-blue)] text-white' 
                    : idx < ['basics', 'sites', 'review'].indexOf(step)
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-neutral-200 text-neutral-500'
                )}>
                  <s.icon className="w-4 h-4" />
                  <span className="font-medium">{s.label}</span>
                </div>
                {idx < 2 && (
                  <ChevronRight className="w-5 h-5 text-neutral-300 mx-2" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === 'basics' && (
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-2">
                  Strategy Name
                </label>
                <Input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g., Transit-Oriented Growth"
                  className="text-base"
                />
                <p className="mt-1.5 text-xs text-neutral-500">
                  A clear name that describes the strategic approach
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-2">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Briefly describe the priorities and rationale for this scenario..."
                  rows={3}
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm resize-none focus:ring-2 focus:ring-[color:var(--color-gov-blue)] focus:border-transparent"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-2">
                  Theme Color
                </label>
                <div className="flex items-center gap-3">
                  {colorOptions.map(c => (
                    <button
                      key={c.id}
                      onClick={() => setColor(c.id)}
                      className={cn(
                        'w-10 h-10 rounded-full transition-all',
                        c.class,
                        color === c.id 
                          ? 'ring-2 ring-offset-2 ring-neutral-900 scale-110' 
                          : 'hover:scale-105'
                      )}
                      title={c.label}
                    />
                  ))}
                </div>
              </div>

              <div className="bg-blue-50 rounded-lg p-4 flex gap-3">
                <Sparkles className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-blue-900 font-medium mb-1">
                    AI will generate a narrative
                  </p>
                  <p className="text-xs text-blue-700">
                    Once you select sites, the system will generate a strategic narrative 
                    explaining the rationale and trade-offs of your scenario.
                  </p>
                </div>
              </div>
            </div>
          )}

          {step === 'sites' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-neutral-900">Available Sites</h3>
                  <p className="text-xs text-neutral-500">
                    Select sites to include in this strategy
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold text-neutral-900">
                    {selectedSiteIds.length} sites
                  </div>
                  <div className="text-xs text-neutral-500">
                    {totalCapacity.toLocaleString()} units capacity
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                {allSites.map(site => {
                  const s = site.properties;
                  const selected = selectedSiteIds.includes(s.id);
                  
                  return (
                    <button
                      key={s.id}
                      onClick={() => toggleSite(s.id)}
                      className={cn(
                        'w-full p-3 rounded-lg border-2 text-left transition-all',
                        selected 
                          ? 'border-emerald-500 bg-emerald-50'
                          : 'border-neutral-200 bg-white hover:border-neutral-300'
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            'w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                            selected 
                              ? 'border-emerald-500 bg-emerald-500' 
                              : 'border-neutral-300'
                          )}>
                            {selected && <Check className="w-3 h-3 text-white" />}
                          </div>
                          <div>
                            <div className="font-medium text-sm text-neutral-900">{s.name}</div>
                            <div className="text-xs text-neutral-500 flex items-center gap-2">
                              <span>{s.id}</span>
                              <span>·</span>
                              <span className="capitalize">{s.landType.replace('-', ' ')}</span>
                              {s.greenBelt && (
                                <>
                                  <span>·</span>
                                  <span className="text-green-600">Green Belt</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          <Home className="w-3 h-3 mr-1" />
                          {s.capacity.toLocaleString()}
                        </Badge>
                      </div>
                      {s.constraints.length > 0 && (
                        <div className="mt-2 pl-8 flex items-center gap-1 text-[11px] text-amber-600">
                          <AlertCircle className="w-3 h-3" />
                          <span>{s.constraints.length} constraint{s.constraints.length > 1 ? 's' : ''}</span>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {step === 'review' && (
            <div className="space-y-6">
              <div className="bg-neutral-50 rounded-lg p-4">
                <h3 className="text-lg font-semibold text-neutral-900 mb-1">{name}</h3>
                <p className="text-sm text-neutral-600 mb-3">{description || 'No description provided'}</p>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <div className={cn('w-4 h-4 rounded-full', colorOptions.find(c => c.id === color)?.class)} />
                    <span className="text-sm text-neutral-600 capitalize">{color} theme</span>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-neutral-900 mb-2">
                  Allocated Sites ({selectedSiteIds.length})
                </h4>
                <div className="space-y-2">
                  {allSites
                    .filter(s => selectedSiteIds.includes(s.properties.id))
                    .map(site => (
                      <div 
                        key={site.properties.id}
                        className="flex items-center justify-between p-2 bg-white border border-neutral-200 rounded-lg"
                      >
                        <div className="flex items-center gap-2">
                          <MapPin className="w-4 h-4 text-emerald-600" />
                          <span className="text-sm font-medium">{site.properties.name}</span>
                        </div>
                        <span className="text-xs text-neutral-500">
                          {site.properties.capacity.toLocaleString()} units
                        </span>
                      </div>
                    ))}
                </div>
                <div className="mt-3 p-2 bg-emerald-50 rounded-lg flex items-center justify-between">
                  <span className="text-sm font-medium text-emerald-700">Total Capacity</span>
                  <span className="text-sm font-semibold text-emerald-900">
                    {totalCapacity.toLocaleString()} units
                  </span>
                </div>
              </div>

              <div className="bg-violet-50 rounded-lg p-4 flex gap-3">
                <Sparkles className="w-5 h-5 text-violet-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-violet-900 font-medium mb-1">
                    Ready to generate
                  </p>
                  <p className="text-xs text-violet-700">
                    A plan narrative will be generated based on the selected sites, 
                    their constraints, and sustainability characteristics.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-neutral-200 flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={() => {
              if (step === 'basics') {
                onClose();
              } else if (step === 'sites') {
                setStep('basics');
              } else {
                setStep('sites');
              }
            }}
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            {step === 'basics' ? 'Cancel' : 'Back'}
          </Button>

          <Button
            onClick={() => {
              if (step === 'basics') {
                setStep('sites');
              } else if (step === 'sites') {
                setStep('review');
              } else {
                handleCreate();
              }
            }}
            disabled={
              (step === 'basics' && !canProceedFromBasics) ||
              (step === 'sites' && !canProceedFromSites)
            }
          >
            {step === 'review' ? (
              <>
                <Sparkles className="w-4 h-4 mr-1" />
                Create Strategy
              </>
            ) : (
              <>
                Next
                <ChevronRight className="w-4 h-4 ml-1" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
