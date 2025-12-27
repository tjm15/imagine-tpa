import { useEffect, useMemo, useState } from 'react';
import { Scale, TrendingUp, AlertTriangle, FileText, RefreshCw, Sparkles } from 'lucide-react';
import { WorkspaceMode } from '../../App';
import { ExplainabilityLevel } from '../../contexts/ExplainabilityContext';
import { useProject } from '../../contexts/AuthorityContext';
import { useRun } from '../../contexts/RunContext';
import { Button } from '../ui/button';

interface JudgementViewProps {
  workspace: WorkspaceMode;
  explainabilityLevel?: ExplainabilityLevel;
}

interface ScenarioTab {
  tab_id: string;
  scenario_id: string;
  political_framing_id: string;
  scenario_title?: string;
  scenario_summary?: string;
  status: string;
  run_id?: string | null;
}

interface ScenarioSetResponse {
  scenario_set: {
    scenario_set_id: string;
    selected_tab_id?: string | null;
  };
  tabs: ScenarioTab[];
}

export function JudgementView({ workspace, explainabilityLevel = 'summary' }: JudgementViewProps) {
  const { planProject } = useProject();
  const { setCurrentRun } = useRun();
  const [scenarioSet, setScenarioSet] = useState<ScenarioSetResponse | null>(null);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [sheet, setSheet] = useState<any | null>(null);
  const [freshness, setFreshness] = useState<any | null>(null);
  const [loadingSheet, setLoadingSheet] = useState(false);
  const [inspector, setInspector] = useState<any | null>(null);
  const [loadingInspector, setLoadingInspector] = useState(false);
  const [artifactUrls, setArtifactUrls] = useState<Record<string, string>>({});

  const fetchJson = async (url: string, options?: RequestInit) => {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      throw new Error(`Request failed: ${resp.status}`);
    }
    return resp.json();
  };

  const loadScenarioSets = async () => {
    if (!planProject?.plan_project_id) return;
    const stageParam = planProject.current_stage_id ? `&culp_stage_id=${planProject.current_stage_id}` : '';
    const data = await fetchJson(`/api/scenario-sets?plan_project_id=${planProject.plan_project_id}${stageParam}`);
    const setId = data.scenario_sets?.[0]?.scenario_set_id;
    if (!setId) {
      setScenarioSet(null);
      return;
    }
    const detail = await fetchJson(`/api/scenario-sets/${setId}`);
    setScenarioSet(detail);
    const selected = detail.scenario_set?.selected_tab_id || detail.tabs?.[0]?.tab_id || null;
    setActiveTabId(selected);
  };

  const loadInspector = async () => {
    if (!planProject?.plan_project_id) return;
    setLoadingInspector(true);
    try {
      const data = await fetchJson('/api/scenario-inspector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_project_id: planProject.plan_project_id, culp_stage_id: planProject.current_stage_id || undefined }),
      });
      setInspector(data.report);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingInspector(false);
    }
  };

  useEffect(() => {
    if (workspace !== 'plan') return;
    loadScenarioSets().catch((err) => console.error(err));
  }, [workspace, planProject?.plan_project_id, planProject?.current_stage_id]);

  useEffect(() => {
    if (workspace !== 'plan') return;
    if (!scenarioSet) {
      loadInspector().catch((err) => console.error(err));
    }
  }, [workspace, scenarioSet]);

  const activeTab = useMemo(() => {
    return scenarioSet?.tabs?.find((tab) => tab.tab_id === activeTabId) || null;
  }, [scenarioSet, activeTabId]);

  useEffect(() => {
    if (!activeTab) {
      setCurrentRun(null, null);
      return;
    }
    setCurrentRun(activeTab.run_id || null, activeTab.status || null);
  }, [activeTab?.run_id, activeTab?.status, setCurrentRun]);

  const selectTab = async (tabId: string) => {
    if (!scenarioSet) return;
    setActiveTabId(tabId);
    try {
      await fetchJson(`/api/scenario-sets/${scenarioSet.scenario_set.scenario_set_id}/select-tab`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab_id: tabId, selection_rationale: 'planner_selection' }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  const loadSheet = async (tabId: string) => {
    setLoadingSheet(true);
    setSheet(null);
    try {
      const data = await fetchJson(`/api/scenario-framing-tabs/${tabId}/sheet?auto_refresh=true&prefer_async=true`);
      setSheet(data.sheet || null);
      setFreshness(data.freshness || null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingSheet(false);
    }
  };

  useEffect(() => {
    if (!activeTabId || workspace !== 'plan') return;
    loadSheet(activeTabId).catch((err) => console.error(err));
  }, [activeTabId, workspace]);

  useEffect(() => {
    if (!activeTabId || workspace !== 'plan') return;
    if (!freshness?.is_stale) return;
    const timer = window.setTimeout(() => {
      loadSheet(activeTabId).catch((err) => console.error(err));
    }, 6000);
    return () => window.clearTimeout(timer);
  }, [activeTabId, workspace, freshness?.is_stale]);

  useEffect(() => {
    if (!sheet?.sections?.evidence_cards) return;
    const cards = sheet.sections.evidence_cards as Array<any>;
    cards.forEach((card) => {
      const ref = Array.isArray(card.evidence_refs) ? card.evidence_refs[0] : null;
      if (!ref || artifactUrls[ref]) return;
      const parts = typeof ref === 'string' ? ref.split('::') : [];
      if (parts[0] === 'visual_asset' && parts[1]) {
        fetchJson(`/api/visual-assets/${parts[1]}/blob`)
          .then((data) => {
            if (data?.data_url) {
              setArtifactUrls((prev) => ({ ...prev, [ref]: data.data_url }));
            }
          })
          .catch((err) => console.error(err));
      }
    });
  }, [sheet, artifactUrls]);

  const createScenarioSet = async () => {
    if (!planProject?.plan_project_id) return;
    try {
      const data = await fetchJson('/api/scenario-sets/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_project_id: planProject.plan_project_id,
          culp_stage_id: planProject.current_stage_id || 'getting_ready_pre_30m',
          scenario_count: 2,
        }),
      });
      setScenarioSet(data);
      const selected = data.scenario_set?.selected_tab_id || data.tabs?.[0]?.tab_id || null;
      setActiveTabId(selected);
    } catch (err) {
      console.error(err);
    }
  };

  const renderEvidenceCards = () => {
    if (!sheet?.sections?.evidence_cards) return null;
    const cards = sheet.sections.evidence_cards as Array<any>;
    return (
      <div className="space-y-3">
        {cards.map((card) => {
          const ref = Array.isArray(card.evidence_refs) ? card.evidence_refs[0] : null;
          const preview = ref && artifactUrls[ref] ? artifactUrls[ref] : null;
          return (
            <div key={card.card_id} className="border border-neutral-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-[color:var(--color-gov-blue)]" />
                <h4 className="text-sm">{card.title || 'Evidence'}</h4>
              </div>
              {preview && (
                <img src={preview} alt="evidence" className="w-full rounded mb-2" />
              )}
              <p className="text-sm text-neutral-600">{card.summary || 'Evidence summary pending.'}</p>
              {explainabilityLevel !== 'summary' && ref && (
                <div className="mt-2 text-xs text-neutral-500">Evidence ref: {ref}</div>
              )}
              {explainabilityLevel === 'forensic' && card.limitations_text && (
                <div className="mt-2 text-xs text-amber-700">Limitations: {card.limitations_text}</div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  if (workspace !== 'plan') {
    return (
      <div className="h-full flex flex-col">
        <div className="bg-white border-b border-neutral-200 p-4 flex-shrink-0">
          <div className="flex items-center gap-2 mb-2">
            <Scale className="w-5 h-5 text-[color:var(--color-gov-blue)]" />
            <h2 className="text-lg">Position Packages</h2>
          </div>
          <p className="text-sm text-neutral-600">Casework balance views will appear here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="bg-white border-b border-neutral-200 p-4 flex-shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <Scale className="w-5 h-5 text-[color:var(--color-gov-blue)]" />
          <h2 className="text-lg">Scenario × Political Framing</h2>
        </div>
        <p className="text-sm text-neutral-600">Compare spatial strategy options under different political framings.</p>
      </div>

      {!scenarioSet && (
        <div className="flex-1 overflow-auto p-8">
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="bg-white rounded-lg border border-neutral-200 p-6">
              <div className="flex items-center gap-2 text-sm text-[color:var(--color-gov-blue)]">
                <Sparkles className="w-4 h-4" />
                AI Inspector report card
              </div>
              {loadingInspector && <div className="text-sm text-neutral-500 mt-3">Evaluating readiness…</div>}
              {!loadingInspector && inspector && (
                <>
                  <div className="mt-3 text-sm text-neutral-700">{inspector.summary}</div>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    {inspector.scorecard?.map((item: any) => (
                      <div key={item.dimension} className="border border-neutral-200 rounded p-3 text-xs">
                        <div className="font-medium text-neutral-700">{item.dimension}</div>
                        <div className="text-neutral-500">{item.rating}</div>
                        <div className="text-neutral-500 mt-1">{item.notes}</div>
                      </div>
                    ))}
                  </div>
                  {inspector.blockers?.length > 0 && (
                    <div className="mt-4 text-sm text-amber-800">
                      {inspector.blockers.map((block: any) => (
                        <div key={block.title} className="flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 mt-0.5" />
                          <div>
                            <div className="font-medium">{block.title}</div>
                            <div className="text-xs text-neutral-600">{block.detail}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-5">
                    <Button
                      onClick={createScenarioSet}
                      disabled={inspector.decision !== 'ready'}
                    >
                      Create Scenarios
                    </Button>
                    {inspector.decision !== 'ready' && (
                      <span className="ml-3 text-xs text-neutral-500">Awaiting evidence readiness</span>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {scenarioSet && (
        <>
          <div className="bg-white border-b border-neutral-200 overflow-x-auto flex-shrink-0">
            <div className="flex items-center gap-2 px-4 py-2 min-w-max">
              {scenarioSet.tabs.map((tab) => (
                <button
                  key={tab.tab_id}
                  onClick={() => selectTab(tab.tab_id)}
                  className={`px-4 py-2 rounded-t border transition-colors ${
                    activeTabId === tab.tab_id
                      ? 'border-[color:var(--color-accent)] bg-emerald-50 border-b-2'
                      : 'border-transparent hover:bg-neutral-50'
                  }`}
                >
                  <div className="text-sm">
                    <div className={activeTabId === tab.tab_id ? 'text-emerald-800' : 'text-neutral-900'}>
                      {tab.scenario_title || 'Scenario'}
                    </div>
                    <div className="text-xs text-neutral-600 mt-0.5">
                      {tab.political_framing_id}
                    </div>
                    {tab.status !== 'complete' && (
                      <div className="text-[10px] text-neutral-400 mt-1">{tab.status}</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-auto p-8">
            <div className="max-w-4xl mx-auto space-y-6">
              {loadingSheet && (
                <div className="text-sm text-neutral-500 flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading scenario sheet…
                </div>
              )}
              {!loadingSheet && sheet && (
                <>
                  <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                    <h3 className="mb-2">{sheet.title}</h3>
                    <p className="text-sm text-neutral-700 mb-2">
                      Under <strong>{sheet.framing?.frame_title || sheet.framing?.political_framing_id}</strong> framing, a reasonable position would be…
                    </p>
                    {freshness?.is_stale && (
                      <div className="text-xs text-amber-700 flex items-center gap-2">
                        <RefreshCw className="w-3 h-3" />
                        Refreshing scenario outputs in the background.
                      </div>
                    )}
                  </div>

                  <section>
                    <h3 className="mb-3">1. What This Is About</h3>
                    <p className="text-sm mb-2">{sheet.sections?.framing_summary}</p>
                    {explainabilityLevel !== 'summary' && (
                      <p className="text-sm text-neutral-600">{sheet.sections?.scenario_summary}</p>
                    )}
                  </section>

                  <section>
                    <h3 className="mb-3">2. What Matters Here</h3>
                    <div className="space-y-3">
                      {(sheet.sections?.key_issues || []).slice(0, explainabilityLevel === 'summary' ? 3 : 8).map((issue: string) => (
                        <div key={issue} className="border border-neutral-200 rounded-lg p-4">
                          <div className="flex items-start gap-3">
                            <TrendingUp className="w-5 h-5 text-[color:var(--color-gov-blue)] flex-shrink-0 mt-0.5" />
                            <div>
                              <h4 className="text-sm mb-1">{issue}</h4>
                              {explainabilityLevel !== 'summary' && (
                                <p className="text-xs text-neutral-500">Issue surfaced in the scenario grammar run.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section>
                    <h3 className="mb-3">3. Evidence Cards</h3>
                    {renderEvidenceCards()}
                  </section>

                  <section>
                    <h3 className="mb-3">4. Planning Balance</h3>
                    <div className="bg-neutral-50 rounded-lg p-4">
                      <p className="text-sm text-neutral-700">{sheet.sections?.planning_balance}</p>
                    </div>
                  </section>

                  <section>
                    <h3 className="mb-3">5. Conditional Position</h3>
                    <div className="bg-emerald-50 border-l-4 border-emerald-400 p-4 mb-4">
                      <p className="text-sm">{sheet.sections?.conditional_position}</p>
                    </div>
                    {sheet.sections?.uncertainty_summary?.length > 0 && (
                      <div className="bg-amber-50 rounded p-3">
                        <h4 className="text-sm text-amber-800 mb-2">Key Uncertainties:</h4>
                        <ul className="text-sm space-y-1 text-neutral-700">
                          {sheet.sections.uncertainty_summary.map((u: string) => (
                            <li key={u}>• {u}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>

                  {explainabilityLevel === 'forensic' && freshness?.dependency_snapshot && (
                    <section>
                      <h3 className="mb-3">Trace Snapshot</h3>
                      <pre className="text-xs text-neutral-500 bg-white border border-neutral-200 rounded p-3 overflow-auto">
                        {JSON.stringify(freshness.dependency_snapshot, null, 2)}
                      </pre>
                    </section>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
