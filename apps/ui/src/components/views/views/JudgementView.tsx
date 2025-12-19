import { WorkspaceMode } from '../../App';
import { Scale, TrendingUp, AlertTriangle, CheckCircle, FileText } from 'lucide-react';
import { useState } from 'react';

interface JudgementViewProps {
  workspace: WorkspaceMode;
}

interface ScenarioTab {
  id: string;
  scenario: string;
  framing: string;
  color: string;
}

export function JudgementView({ workspace }: JudgementViewProps) {
  const planTabs: ScenarioTab[] = [
    { id: '1', scenario: 'Urban Intensification', framing: 'Growth-focused', color: 'blue' },
    { id: '2', scenario: 'Urban Intensification', framing: 'Heritage-balanced', color: 'amber' },
    { id: '3', scenario: 'Edge Expansion', framing: 'Growth-focused', color: 'blue' },
    { id: '4', scenario: 'Edge Expansion', framing: 'Environment-first', color: 'green' },
  ];

  const caseworkTabs: ScenarioTab[] = [
    { id: '1', scenario: 'Approve', framing: 'Economic vitality', color: 'green' },
    { id: '2', scenario: 'Approve', framing: 'Precedent-cautious', color: 'amber' },
    { id: '3', scenario: 'Refuse', framing: 'Retail protection', color: 'red' },
  ];

  const tabs = workspace === 'plan' ? planTabs : caseworkTabs;
  const [activeTab, setActiveTab] = useState(tabs[0].id);

  const activeTabData = tabs.find(t => t.id === activeTab)!;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-neutral-200 p-4 flex-shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <Scale className="w-5 h-5 text-[color:var(--color-gov-blue)]" />
          <h2 className="text-lg">
            {workspace === 'plan' ? 'Scenario × Political Framing' : 'Position Packages'}
          </h2>
        </div>
        <p className="text-sm text-neutral-600">
          {workspace === 'plan' 
            ? 'Compare spatial strategy options under different political framings'
            : 'Explore decision positions with explicit assumptions and trade-offs'}
        </p>
      </div>

      {/* Scenario Tabs */}
      <div className="bg-white border-b border-neutral-200 overflow-x-auto flex-shrink-0">
        <div className="flex items-center gap-2 px-4 py-2 min-w-max">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-t border transition-colors ${
                activeTab === tab.id
                  ? `border-${tab.color}-500 bg-${tab.color}-50 border-b-2`
                  : 'border-transparent hover:bg-neutral-50'
              }`}
            >
              <div className="text-sm">
                <div className={activeTab === tab.id ? `text-${tab.color}-700` : 'text-neutral-900'}>
                  {tab.scenario}
                </div>
                <div className="text-xs text-neutral-600 mt-0.5">
                  {tab.framing}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Sheet Content */}
      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Tab Context Banner */}
          <div className={`bg-${activeTabData.color}-50 border border-${activeTabData.color}-200 rounded-lg p-4`}>
            <h3 className="mb-2">{activeTabData.scenario}</h3>
            <p className="text-sm text-neutral-700 mb-2">
              Under <strong>{activeTabData.framing}</strong> framing, a reasonable position would be...
            </p>
            <p className="text-xs text-neutral-600 italic">
              This judgement sheet is conditional on the selected political framing. 
              All assumptions and uncertainties are explicitly stated below.
            </p>
          </div>

          {workspace === 'plan' ? (
            <>
              {/* Framing Section */}
              <section>
                <h3 className="mb-3">1. What This Is About</h3>
                <p className="text-sm mb-2">
                  This scenario explores {activeTabData.scenario.toLowerCase()} as the primary spatial strategy 
                  for Cambridge's growth to 2040. It is assessed under a {activeTabData.framing.toLowerCase()} 
                  political framing.
                </p>
                <div className="bg-neutral-50 rounded p-3 text-sm">
                  <div className="text-neutral-700 mb-1">Scope:</div>
                  <ul className="list-disc list-inside space-y-1 text-neutral-600">
                    <li>Growth target: 1,800 dwellings per annum</li>
                    <li>Plan period: 2025-2040</li>
                    <li>Geographic scope: Cambridge authority area</li>
                  </ul>
                </div>
              </section>

              {/* Issues & Considerations */}
              <section>
                <h3 className="mb-3">2. What Matters Here</h3>
                <div className="space-y-3">
                  <div className="border border-neutral-200 rounded-lg p-4">
                    <div className="flex items-start gap-3 mb-2">
                      <TrendingUp className="w-5 h-5 text-[color:var(--color-gov-blue)] flex-shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-sm mb-1">Housing Delivery Capacity</h4>
                        <p className="text-sm text-neutral-600">
                          {activeTabData.scenario === 'Urban Intensification' 
                            ? 'Can achieve ~1,400 dpa through brownfield and intensification alone, leaving 400 dpa shortfall.'
                            : 'Edge expansion sites can deliver additional 800 dpa, meeting and exceeding target.'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-neutral-500 mt-2">
                      <FileText className="w-3 h-3" />
                      <span>Evidence: SHLAA 2024, Urban Capacity Study</span>
                    </div>
                  </div>

                  <div className="border border-neutral-200 rounded-lg p-4">
                    <div className="flex items-start gap-3 mb-2">
                      <Scale className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-sm mb-1">Heritage & Character Impact</h4>
                        <p className="text-sm text-neutral-600">
                          {activeTabData.framing === 'Heritage-balanced'
                            ? 'Intensification must respect conservation area character and historic skyline. This constrains height and density in central areas.'
                            : 'Heritage considerations are material but balanced against acute housing need. Some character change is acceptable.'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="border border-neutral-200 rounded-lg p-4">
                    <div className="flex items-start gap-3 mb-2">
                      <AlertTriangle className="w-5 h-5 text-[color:var(--color-warning)] flex-shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-sm mb-1">Transport Capacity</h4>
                        <p className="text-sm text-neutral-600">
                          {activeTabData.scenario === 'Urban Intensification'
                            ? 'Strong public transport and cycling infrastructure can accommodate intensification without strategic road upgrades.'
                            : 'Edge expansion requires A14 junction improvements and new cycleways. DfT funding uncertain.'}
                        </p>
                      </div>
                    </div>
                    <div className="bg-amber-50 border border-amber-200 rounded p-2 mt-2 text-xs">
                      <span className="text-amber-800">Limitation:</span>
                      <span className="text-neutral-700 ml-1">
                        DfT Connectivity Tool does not model future capacity constraints.
                      </span>
                    </div>
                  </div>
                </div>
              </section>

              {/* Planning Balance */}
              <section>
                <h3 className="mb-3">3. Planning Balance</h3>
                <div className="bg-neutral-50 rounded-lg p-4">
                  <p className="text-sm mb-3">
                    Under {activeTabData.framing.toLowerCase()} framing:
                  </p>
                  {activeTabData.framing === 'Growth-focused' ? (
                    <p className="text-sm text-neutral-700">
                      The acute housing need (12.8x affordability) carries decisive weight. 
                      {activeTabData.scenario === 'Urban Intensification'
                        ? ' Intensification maximizes brownfield use and sustainable transport, though shortfall remains.'
                        : ' Edge expansion delivers full need and provides family housing with gardens, though consuming greenfield land.'}
                      Heritage and landscape considerations are material but do not outweigh need.
                    </p>
                  ) : (
                    <p className="text-sm text-neutral-700">
                      Housing need is significant, but heritage protection and environmental quality are equally weighted. 
                      {activeTabData.scenario === 'Urban Intensification'
                        ? ' Intensification approach protects Green Belt but requires careful design controls to safeguard conservation areas.'
                        : ' Green Belt harm is substantial and requires exceptional circumstances justification.'}
                    </p>
                  )}
                </div>
              </section>

              {/* Position & Uncertainties */}
              <section>
                <h3 className="mb-3">4. Conditional Position</h3>
                <div className={`bg-${activeTabData.color}-50 border-l-4 border-${activeTabData.color}-500 p-4 mb-4`}>
                  <p className="text-sm">
                    {activeTabData.id === '1' && 
                      'This strategy is reasonable IF the authority accepts a modest housing shortfall in exchange for brownfield prioritization and character protection measures can be secured.'}
                    {activeTabData.id === '2' && 
                      'This strategy is reasonable IF intensification is carefully designed to respect conservation areas AND the shortfall can be addressed through Duty to Cooperate.'}
                    {activeTabData.id === '3' && 
                      'This strategy is reasonable IF exceptional circumstances for Green Belt release can be demonstrated AND transport infrastructure can be funded.'}
                    {activeTabData.id === '4' && 
                      'This strategy requires very strong exceptional circumstances for Green Belt harm, which may be difficult to demonstrate given intensification alternatives.'}
                  </p>
                </div>

                <div className="bg-amber-50 rounded p-3">
                  <h4 className="text-sm text-amber-800 mb-2">Key Uncertainties:</h4>
                  <ul className="text-sm space-y-1 text-neutral-700">
                    <li>• DfT funding timeline for transport upgrades (edge expansion)</li>
                    <li>• Deliverability of high-density schemes in conservation areas (intensification)</li>
                    <li>• Neighboring authorities' capacity for Duty to Cooperate discussions</li>
                  </ul>
                </div>
              </section>
            </>
          ) : (
            <>
              {/* Casework Position */}
              <section>
                <h3 className="mb-3">1. Recommended Position</h3>
                <div className={`${
                  activeTabData.scenario === 'Approve' 
                    ? 'bg-[color:var(--color-success-light)] border-[color:var(--color-success)]' 
                    : 'bg-[color:var(--color-warning-light)] border-[color:var(--color-warning)]'
                } border-l-4 p-4 mb-4`}>
                  <div className={`${
                    activeTabData.scenario === 'Approve' 
                      ? 'text-[color:var(--color-success)]' 
                      : 'text-[color:var(--color-warning)]'
                  } mb-2`}>
                    {activeTabData.scenario.toUpperCase()}
                  </div>
                  <p className="text-sm text-neutral-700">
                    {activeTabData.id === '1' && 
                      'Under economic vitality framing, the loss of ground floor retail is acceptable given 15-month marketing period and decline in Mill Road footfall. Residential use contributes to housing need.'}
                    {activeTabData.id === '2' && 
                      'Marketing evidence just satisfies Policy DM12. Approval recommended but with careful consideration of cumulative retail loss in the District Centre.'}
                    {activeTabData.id === '3' && 
                      'Under retail protection framing, the marketing period is not sufficient to demonstrate that retail use is unviable. District Centre vitality should be prioritized.'}
                  </p>
                </div>
              </section>

              <section>
                <h3 className="mb-3">2. Material Considerations</h3>
                <div className="space-y-3">
                  <div className="border border-neutral-200 rounded p-3">
                    <div className="flex items-center gap-2 mb-2">
                      {activeTabData.scenario === 'Approve' ? (
                        <CheckCircle className="w-4 h-4 text-[color:var(--color-success)]" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-[color:var(--color-warning)]" />
                      )}
                      <h4 className="text-sm">Policy DM12 Compliance</h4>
                    </div>
                    <p className="text-sm text-neutral-600">
                      {activeTabData.scenario === 'Approve'
                        ? '15 months marketing at market rates satisfies the 12-month policy requirement.'
                        : 'Marketing evidence is borderline. Policy requires genuine attempt, not just nominal listing.'}
                    </p>
                  </div>

                  <div className="border border-neutral-200 rounded p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="w-4 h-4 text-[color:var(--color-success)]" />
                      <h4 className="text-sm">Residential Standards</h4>
                    </div>
                    <p className="text-sm text-neutral-600">
                      Both proposed flats meet minimum space standards and have adequate amenity.
                    </p>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="mb-3">3. Conditions / Reasons</h3>
                {activeTabData.scenario === 'Approve' ? (
                  <div className="space-y-2 text-sm">
                    <div className="p-3 bg-neutral-50 rounded">
                      <strong>Condition 1:</strong> Secure cycle storage for 2 bikes per flat to be provided prior to occupation.
                    </div>
                    <div className="p-3 bg-neutral-50 rounded">
                      <strong>Condition 2:</strong> Removal of permitted development rights to prevent future subdivision.
                    </div>
                    <div className="p-3 bg-neutral-50 rounded">
                      <strong>Condition 3:</strong> Retention of existing shopfront for heritage reasons.
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-[color:var(--color-warning-light)] rounded text-sm">
                    <strong>Reason for Refusal:</strong> The proposal fails to demonstrate that the retail use is unviable, 
                    contrary to Policy DM12. The loss of ground floor retail would harm the vitality and viability of 
                    the Mill Road District Centre.
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
