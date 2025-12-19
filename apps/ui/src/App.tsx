import { useEffect, useMemo, useRef, useState } from "react";

type Mode = "plan" | "dm";
type View = "document" | "map" | "judgement" | "reality";
type ArtefactStatus = "not_started" | "drafting" | "ready" | "published";

type CulpStage = {
  id: string;
  phase?: string;
  title?: string;
  required_artefacts?: string[];
  gov_uk_ref?: string;
};

type CulpProcessModel = {
  process_id?: string;
  source_of_truth?: string;
  phases?: Array<{ id: string; title?: string; description?: string }>;
  stages?: CulpStage[];
};

type ArtefactRegistryEntry = {
  artefact_key: string;
  title?: string;
  notes?: string;
};

type ArtefactRegistry = {
  artefacts?: ArtefactRegistryEntry[];
};

type PoliticalFraming = {
  political_framing_id: string;
  title?: string;
  description?: string;
};

type PoliticalFramingsPack = {
  political_framings?: PoliticalFraming[];
};

type SelectedAuthority = {
  authority_id: string;
  name?: string;
  codes?: Record<string, string>;
  website?: string;
};

type SelectedAuthoritiesPack = {
  selected_authorities?: SelectedAuthority[];
};

type PlanCycle = {
  plan_cycle_id: string;
  authority_id: string;
  plan_name: string;
  status: string;
  weight_hint?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
};

type PlanCyclesResponse = {
  plan_cycles: PlanCycle[];
};

type PlanProject = {
  plan_project_id: string;
  authority_id: string;
  process_model_id: string;
  title: string;
  status: string;
  current_stage_id?: string | null;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
};

type PlanProjectsResponse = {
  plan_projects: PlanProject[];
};

type Scenario = {
  scenario_id: string;
  plan_project_id: string;
  culp_stage_id: string;
  title: string;
  summary: string;
  state_vector: Record<string, unknown>;
  parent_scenario_id?: string | null;
  status: string;
  created_by: string;
  created_at?: string;
  updated_at?: string;
};

type ScenariosResponse = {
  scenarios: Scenario[];
};

type ScenarioSetListItem = {
  scenario_set_id: string;
  plan_project_id: string;
  culp_stage_id: string;
  tab_count: number;
  selected_tab_id?: string | null;
  selected_at?: string | null;
};

type ScenarioSetListResponse = {
  scenario_sets: ScenarioSetListItem[];
};

type ScenarioSetDetail = {
  scenario_set: {
    scenario_set_id: string;
    plan_project_id: string;
    culp_stage_id: string;
    political_framing_ids: string[];
    scenario_ids: string[];
    tab_ids: string[];
    selected_tab_id?: string | null;
    selection_rationale?: string | null;
    selected_at?: string | null;
  };
  tabs: Array<{
    tab_id: string;
    scenario_set_id: string;
    scenario_id: string;
    political_framing_id: string;
    framing_id?: string | null;
    run_id?: string | null;
    status: string;
    trajectory_id?: string | null;
    judgement_sheet_ref?: string | null;
    last_updated_at?: string;
  }>;
};

type ActiveScenarioTab = {
  tab_id: string;
  run_id: string | null;
  scenario_id: string;
  political_framing_id: string;
  trajectory_id: string | null;
  status: string;
};

type DmCase = {
  id: string;
  authority_id: string;
  reference: string;
  address: string;
  description: string;
  status: "new" | "validating" | "consultation" | "assessment" | "determination" | "issued";
  days_remaining: number;
};

type DraftArtefactType =
  | "policy_clause"
  | "plan_chapter"
  | "place_portrait"
  | "consultation_summary"
  | "site_assessment"
  | "officer_report_section"
  | "other";

type DraftRequest = {
  draft_request_id: string;
  requested_at: string;
  requested_by: "user" | "agent" | "system";
  artefact_type: DraftArtefactType;
  audience?: string | null;
  style_guide?: string | null;
  time_budget_seconds: number;
  context?: {
    plan_project_id?: string | null;
    culp_stage_id?: string | null;
    scenario_id?: string | null;
    framing_id?: string | null;
    application_id?: string | null;
    site_id?: string | null;
  };
  user_prompt?: string | null;
  constraints?: Record<string, unknown>;
};

type DraftBlockSuggestion = {
  suggestion_id: string;
  block_type: "heading" | "paragraph" | "bullets" | "table" | "figure" | "callout" | "other";
  content: string;
  evidence_refs: string[];
  assumption_ids?: string[];
  limitations_text?: string | null;
  requires_judgement_run: boolean;
  insertion_hint?: Record<string, unknown>;
};

type DraftPack = {
  draft_pack_id: string;
  draft_request_id: string;
  status: "complete" | "partial" | "failed";
  suggestions: DraftBlockSuggestion[];
  tool_run_ids?: string[];
  created_at: string;
};

type EvidenceCard = {
  card_id: string;
  card_type: string;
  title: string;
  summary?: string;
  evidence_refs: string[];
  limitations_text?: string;
  artifact_ref?: string;
};

type ScenarioJudgementSheet = {
  title: string;
  sections: {
    framing_summary: string;
    scenario_summary?: string;
    key_issues: string[];
    evidence_cards: EvidenceCard[];
    planning_balance: string;
    conditional_position: string;
    uncertainty_summary?: string[];
  };
};

type Trajectory = {
  trajectory_id: string;
  scenario_id?: string | null;
  framing_id: string;
  position_statement: string;
  explicit_assumptions?: string[];
  key_evidence_refs?: string[];
  judgement_sheet_data: ScenarioJudgementSheet;
};

type ScenarioTabRunResponse = {
  tab_id: string;
  run_id: string;
  status: string;
  trajectory_id: string;
  sheet: ScenarioJudgementSheet;
  move_event_ids: string[];
};

type ScenarioTabSheetResponse = {
  tab_id: string;
  status: string;
  run_id?: string | null;
  trajectory: Trajectory | null;
  sheet: ScenarioJudgementSheet | null;
};

type TraceGraphNode = {
  node_id: string;
  node_type:
    | "run"
    | "move"
    | "tool_run"
    | "evidence"
    | "interpretation"
    | "assumption"
    | "ledger"
    | "weighing"
    | "negotiation"
    | "output"
    | "audit_event";
  label: string;
  ref?: Record<string, unknown>;
  layout?: { x?: number; y?: number; group?: string | null };
  severity?: "info" | "warning" | "error" | null;
};

type TraceGraphEdge = {
  edge_id: string;
  src_id: string;
  dst_id: string;
  edge_type: "TRIGGERS" | "USES" | "PRODUCES" | "CITES" | "ASSUMES" | "SUPPORTS" | "CONTRADICTS" | "SUPERSEDES";
  label?: string | null;
};

type TraceGraph = {
  trace_graph_id: string;
  run_id: string;
  mode: "summary" | "inspect" | "forensic";
  nodes: TraceGraphNode[];
  edges: TraceGraphEdge[];
  created_at: string;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

function newUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `tpa_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;
}

function loadDemoArtefactStatuses(): Record<string, ArtefactStatus> {
  try {
    const raw = localStorage.getItem("tpa_demo_artefact_status_v1");
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, ArtefactStatus>;
  } catch {
    return {};
  }
}

function saveDemoArtefactStatuses(next: Record<string, ArtefactStatus>): void {
  try {
    localStorage.setItem("tpa_demo_artefact_status_v1", JSON.stringify(next));
  } catch {
    // ignore
  }
}

function Toggle({
  value,
  options,
  onChange,
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="toggle" role="group">
      {options.map((opt) => (
        <button
          key={opt.value}
          className="toggle__btn"
          aria-pressed={opt.value === value}
          type="button"
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function ArtefactStatusPill({ status }: { status: ArtefactStatus }) {
  const label =
    status === "not_started"
      ? "Not started"
      : status === "drafting"
        ? "Drafting"
        : status === "ready"
          ? "Ready"
          : "Published";
  return <span className={`status status--${status}`}>{label}</span>;
}

function TraceOverlay({
  open,
  onClose,
  runId,
}: {
  open: boolean;
  onClose: () => void;
  runId: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<TraceGraph | null>(null);
  const [activeMoveNodeId, setActiveMoveNodeId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(false);
    setError(null);
    setGraph(null);
    setActiveMoveNodeId(null);
  }, [open, runId]);

  useEffect(() => {
    if (!open) return;
    if (!runId) return;
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const g = await getJson<TraceGraph>(`/api/trace/runs/${runId}?mode=summary`);
        if (cancelled) return;
        setGraph(g);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, runId]);

  const nodesById = useMemo(() => {
    const m = new Map<string, TraceGraphNode>();
    for (const n of graph?.nodes || []) m.set(n.node_id, n);
    return m;
  }, [graph]);

  const outEdgesBySrc = useMemo(() => {
    const m = new Map<string, TraceGraphEdge[]>();
    for (const e of graph?.edges || []) {
      const list = m.get(e.src_id) || [];
      list.push(e);
      m.set(e.src_id, list);
    }
    return m;
  }, [graph]);

  const moveNodes = useMemo(() => {
    const moves = (graph?.nodes || []).filter((n) => n.node_type === "move");
    moves.sort((a, b) => a.label.localeCompare(b.label));
    return moves;
  }, [graph]);

  const renderNodeSeverity = (severity: TraceGraphNode["severity"]) => {
    if (!severity) return null;
    const label = severity === "error" ? "Error" : severity === "warning" ? "Warning" : "Info";
    return <span className="pill pill--small">{label}</span>;
  };

  if (!open) return null;
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="overlay__card">
        <div className="overlay__head">
          <div>
            <div className="overlay__title">Trace Canvas (scaffold)</div>
            <div className="muted">Flowchart-style traceability (MoveEvents/ToolRuns/AuditEvents) goes here.</div>
          </div>
          <button className="btn btn--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="card" style={{ marginTop: 12 }}>
          <div className="kicker">Active run</div>
          <div className="muted" style={{ marginTop: 8 }}>
            {runId ? (
              <>
                Run id: <strong>{runId}</strong>
              </>
            ) : (
              "No run selected yet. Run a Scenario × Political Framing tab to generate a trace."
            )}
          </div>
        </div>

        {runId ? (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="kicker">Trace graph</div>
            {loading ? (
              <div className="muted" style={{ marginTop: 8 }}>
                Loading trace…
              </div>
            ) : null}
            {error ? (
              <div className="callout callout--warn" style={{ marginTop: 10 }}>
                {error}
              </div>
            ) : null}
            {graph ? (
              <>
                <div className="muted" style={{ marginTop: 8 }}>
                  Nodes: <strong>{graph.nodes.length}</strong> · Edges: <strong>{graph.edges.length}</strong>
                </div>

                <div className="list" style={{ marginTop: 12 }}>
                  {moveNodes.map((m) => {
                    const edges = outEdgesBySrc.get(m.node_id) || [];
                    const toolEdges = edges.filter((e) => e.edge_type === "USES");
                    const citeEdges = edges.filter((e) => e.edge_type === "CITES");
                    const selected = m.node_id === activeMoveNodeId;
                    return (
                      <div key={m.node_id} className="card" style={{ padding: 10 }}>
                        <div className="actions" style={{ justifyContent: "space-between" }}>
                          <button
                            className="btn btn--ghost btn--small"
                            type="button"
                            onClick={() => setActiveMoveNodeId(selected ? null : m.node_id)}
                            title={m.label}
                          >
                            {m.label}
                          </button>
                          <div className="actions">
                            {renderNodeSeverity(m.severity)}
                            <span className="pill pill--small">Tools: {toolEdges.length}</span>
                            <span className="pill pill--small">Evidence: {citeEdges.length}</span>
                          </div>
                        </div>

                        {selected ? (
                          <>
                            {toolEdges.length ? (
                              <div style={{ marginTop: 10 }}>
                                <div className="kicker">Tool runs</div>
                                <div className="chips">
                                  {toolEdges.slice(0, 10).map((e) => {
                                    const n = nodesById.get(e.dst_id);
                                    return (
                                      <span key={e.edge_id} className="chip">
                                        {n?.label || e.dst_id}
                                      </span>
                                    );
                                  })}
                                  {toolEdges.length > 10 ? <span className="chip">+{toolEdges.length - 10}</span> : null}
                                </div>
                              </div>
                            ) : null}

                            {citeEdges.length ? (
                              <div style={{ marginTop: 10 }}>
                                <div className="kicker">Evidence</div>
                                <div className="chips">
                                  {citeEdges.slice(0, 8).map((e) => {
                                    const n = nodesById.get(e.dst_id);
                                    const ref = (n?.ref as any)?.evidence_ref;
                                    return (
                                      <span key={e.edge_id} className="chip" title={e.label || ""}>
                                        {typeof ref === "string" ? ref : n?.label || e.dst_id}
                                      </span>
                                    );
                                  })}
                                  {citeEdges.length > 8 ? <span className="chip">+{citeEdges.length - 8}</span> : null}
                                </div>
                              </div>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <div className="muted" style={{ marginTop: 8 }}>
                Run a judgement to generate MoveEvents/ToolRuns, then reopen Trace.
              </div>
            )}
          </div>
        ) : null}

        <div className="card" style={{ marginTop: 12 }}>
          <div className="kicker">8-move spine (preview)</div>
          <ol className="muted" style={{ marginTop: 8 }}>
            <li>Framing</li>
            <li>Issue surfacing</li>
            <li>Evidence curation</li>
            <li>Evidence interpretation</li>
            <li>Considerations formation</li>
            <li>Weighing &amp; balance</li>
            <li>Negotiation &amp; alteration</li>
            <li>Positioning &amp; narration</li>
          </ol>
        </div>
      </div>
    </div>
  );
}

function DraftOverlay({
  open,
  onClose,
  mode,
  authorityId,
  planCycleId,
  defaultContext,
  onInsert,
}: {
  open: boolean;
  onClose: () => void;
  mode: Mode;
  authorityId: string | null;
  planCycleId: string | null;
  defaultContext: DraftRequest["context"];
  onInsert: (suggestion: DraftBlockSuggestion) => void;
}) {
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const [artefactType, setArtefactType] = useState<DraftArtefactType>(
    mode === "dm" ? "officer_report_section" : "plan_chapter",
  );
  const [audience, setAudience] = useState<string>("planner");
  const [styleGuide, setStyleGuide] = useState<string>("Plain English; officer tone; cite evidence cards where possible.");
  const [timeBudget, setTimeBudget] = useState<number>(10);
  const [prompt, setPrompt] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pack, setPack] = useState<DraftPack | null>(null);

  useEffect(() => {
    if (!open) return;
    setArtefactType(mode === "dm" ? "officer_report_section" : "plan_chapter");
    setError(null);
    setPack(null);
    setLoading(false);
    setPrompt("");
    setAudience("planner");
    setStyleGuide("Plain English; officer tone; cite evidence cards where possible.");
    setTimeBudget(10);
    requestAnimationFrame(() => promptRef.current?.focus());
  }, [open, mode]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const submit = async () => {
    const req: DraftRequest = {
      draft_request_id: newUuid(),
      requested_at: new Date().toISOString(),
      requested_by: "user",
      artefact_type: artefactType,
      audience: audience.trim() ? audience.trim() : null,
      style_guide: styleGuide.trim() ? styleGuide.trim() : null,
      time_budget_seconds: Math.max(1, timeBudget),
      context: defaultContext,
      user_prompt: prompt.trim() ? prompt.trim() : null,
      constraints: authorityId
        ? {
            authority_id: authorityId,
            plan_cycle_id: planCycleId,
          }
        : {},
    };

    try {
      setLoading(true);
      setError(null);
      setPack(null);
      const result = await postJson<DraftPack>("/api/draft", req);
      setPack(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const formatForInsert = (s: DraftBlockSuggestion): string => {
    const text = s.content.trim();
    if (!text) return "";
    if (s.block_type === "heading") return `\n\n## ${text}\n`;
    if (s.block_type === "bullets") {
      const lines = text
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("-") || l.startsWith("•") ? l : `- ${l}`));
      return `\n\n${lines.join("\n")}\n`;
    }
    if (s.block_type === "callout") return `\n\n> ${text.replace(/\n/g, "\n> ")}\n`;
    return `\n\n${text}\n`;
  };

  if (!open) return null;
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="overlay__card">
        <div className="overlay__head">
          <div>
            <div className="overlay__title">Draft launcher</div>
            <div className="muted">
              Get a quick draft, then turn it into a defensible position via evidence cards and a full judgement run.
            </div>
          </div>
          <button className="btn btn--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="draftGrid">
          <div className="card">
            <div className="kicker">Request</div>

            <div className="field">
              <div className="field__label">Artefact</div>
              <select
                className="select"
                value={artefactType}
                onChange={(e) => setArtefactType(e.target.value as DraftArtefactType)}
              >
                <option value="plan_chapter">Plan chapter</option>
                <option value="policy_clause">Policy clause</option>
                <option value="place_portrait">Place portrait</option>
                <option value="consultation_summary">Consultation summary</option>
                <option value="site_assessment">Site assessment</option>
                <option value="officer_report_section">Officer report section</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="field">
              <div className="field__label">Audience</div>
              <input className="input" value={audience} onChange={(e) => setAudience(e.target.value)} />
            </div>

            <div className="field">
              <div className="field__label">Style</div>
              <input className="input" value={styleGuide} onChange={(e) => setStyleGuide(e.target.value)} />
            </div>

            <div className="field">
              <div className="field__label">Time budget</div>
              <select className="select" value={timeBudget} onChange={(e) => setTimeBudget(Number(e.target.value))}>
                <option value={5}>5s (fast)</option>
                <option value={10}>10s</option>
                <option value={20}>20s (better)</option>
              </select>
            </div>

            <div className="field">
              <div className="field__label">Prompt</div>
              <textarea
                ref={promptRef}
                className="textarea"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="What do you want drafted? Include scope, site, policies, or what to avoid."
              />
            </div>

            <div className="actions" style={{ marginTop: 12 }}>
              <button className="btn" type="button" disabled={loading} onClick={submit}>
                {loading ? "Drafting…" : "Generate draft"}
              </button>
              <button
                className="btn btn--ghost"
                type="button"
                disabled={loading}
                onClick={() => {
                  setPrompt("");
                  setPack(null);
                  setError(null);
                }}
              >
                Reset
              </button>
            </div>

            {error ? (
              <div className="card" style={{ marginTop: 12, borderColor: "rgba(245, 195, 21, 0.55)" }}>
                <div className="kicker">Draft failed</div>
                <div className="muted" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
                  {error}
                </div>
              </div>
            ) : null}
          </div>

          <div className="card">
            <div className="kicker">Draft pack</div>
            {!pack && !loading ? (
              <div className="muted" style={{ marginTop: 10 }}>
                Generate a draft to see insertable blocks. Later: evidence cards + accept/reject + tracked changes.
              </div>
            ) : null}

            {loading ? (
              <div className="muted" style={{ marginTop: 10 }}>
                Drafting with the configured LLM (or scaffold fallback)…
              </div>
            ) : null}

            {pack ? (
              <>
                <div className="draftPackMeta">
                  <span className="pill pill--small">Status: {pack.status}</span>
                  <span className="pill pill--small">Blocks: {pack.suggestions.length}</span>
                  <span className="pill pill--small">Created: {new Date(pack.created_at).toLocaleString()}</span>
                </div>

                <div className="draftSuggestions">
                  {pack.suggestions.map((s) => (
                    <div key={s.suggestion_id} className="draftSuggestion">
                      <div className="draftSuggestion__head">
                        <div className="draftSuggestion__meta">
                          <span className="pill pill--small">{s.block_type}</span>
                          {s.requires_judgement_run ? (
                            <span className="pill pill--small pill--attention">Judgement run required</span>
                          ) : null}
                          {s.evidence_refs?.length ? (
                            <span className="pill pill--small">Evidence refs: {s.evidence_refs.length}</span>
                          ) : null}
                        </div>
                        <div className="draftSuggestion__actions">
                          <button
                            className="btn btn--small"
                            type="button"
                            onClick={() => {
                              onInsert({ ...s, content: formatForInsert(s) });
                            }}
                          >
                            Insert
                          </button>
                          <button
                            className="btn btn--ghost btn--small"
                            type="button"
                            onClick={() => {
                              const text = formatForInsert(s).trim();
                              const p = navigator.clipboard?.writeText(text);
                              if (p) p.catch(() => {});
                            }}
                          >
                            Copy
                          </button>
                        </div>
                      </div>
                      {s.limitations_text ? (
                        <div className="muted" style={{ marginTop: 8 }}>
                          {s.limitations_text}
                        </div>
                      ) : null}
                      <div className="draftSuggestion__content">{s.content}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function PlanCycleOverlay({
  open,
  onClose,
  authorityId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  authorityId: string | null;
  onCreated: (cycle: PlanCycle) => void;
}) {
  const [planName, setPlanName] = useState<string>("Authority pack snapshot");
  const [status, setStatus] = useState<string>("unknown");
  const [weightHint, setWeightHint] = useState<string>("unknown");
  const [supersedeExisting, setSupersedeExisting] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPlanName("Authority pack snapshot");
    setStatus("unknown");
    setWeightHint("unknown");
    setSupersedeExisting(false);
    setLoading(false);
    setError(null);
  }, [open]);

  const submit = async () => {
    if (!authorityId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await postJson<PlanCycle>("/api/plan-cycles", {
        authority_id: authorityId,
        plan_name: planName.trim() ? planName.trim() : "Plan cycle",
        status,
        weight_hint: weightHint.trim() ? weightHint.trim() : null,
        supersede_existing: supersedeExisting,
      });
      onCreated(res);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="overlay__card">
        <div className="overlay__head">
          <div>
            <div className="overlay__title">New plan cycle</div>
            <div className="muted">Make authority versioning explicit (adopted/emerging/draft).</div>
          </div>
          <button className="btn btn--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="card" style={{ marginTop: 12 }}>
          <div className="field">
            <div className="field__label">Name</div>
            <input className="input" value={planName} onChange={(e) => setPlanName(e.target.value)} />
          </div>

          <div className="grid2" style={{ marginTop: 12 }}>
            <div className="field">
              <div className="field__label">Status</div>
              <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="adopted">Adopted</option>
                <option value="emerging">Emerging</option>
                <option value="draft">Draft</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
            <div className="field">
              <div className="field__label">Weight</div>
              <select className="select" value={weightHint} onChange={(e) => setWeightHint(e.target.value)}>
                <option value="full">Full</option>
                <option value="reduced">Reduced</option>
                <option value="emerging">Emerging</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
          </div>

          <div className="field" style={{ marginTop: 12 }}>
            <label style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={supersedeExisting}
                onChange={(e) => setSupersedeExisting(e.target.checked)}
              />
              <span>Supersede any conflicting active cycle (deactivate previous)</span>
            </label>
            <div className="muted" style={{ marginTop: 6 }}>
              Prevents two active “draft/emerging” cycles (or two active adopted cycles) for the same authority.
            </div>
          </div>

          {error ? (
            <div className="callout callout--warn" style={{ marginTop: 12 }}>
              {error}
            </div>
          ) : null}

          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn" type="button" disabled={!authorityId || loading} onClick={submit}>
              {loading ? "Creating…" : "Create cycle"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlanProjectOverlay({
  open,
  onClose,
  authorityId,
  processModelId,
  currentStageId,
  planCycleId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  authorityId: string | null;
  processModelId: string | null;
  currentStageId: string | null;
  planCycleId: string | null;
  onCreated: (project: PlanProject) => void;
}) {
  const [title, setTitle] = useState<string>("New plan project");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle("New plan project");
    setLoading(false);
    setError(null);
  }, [open]);

  const submit = async () => {
    if (!authorityId || !processModelId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await postJson<PlanProject>("/api/plan-projects", {
        authority_id: authorityId,
        process_model_id: processModelId,
        title: title.trim() ? title.trim() : "Plan project",
        status: "draft",
        current_stage_id: currentStageId,
        metadata: { plan_cycle_id: planCycleId },
      });
      onCreated(res);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="overlay__card">
        <div className="overlay__head">
          <div>
            <div className="overlay__title">New plan project</div>
            <div className="muted">A workspace that will hold deliverables, scenarios, and runs.</div>
          </div>
          <button className="btn btn--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="card" style={{ marginTop: 12 }}>
          <div className="field">
            <div className="field__label">Title</div>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          <div className="muted" style={{ marginTop: 10 }}>
            Process model: <strong>{processModelId || "—"}</strong> · Stage:{" "}
            <strong>{currentStageId || "—"}</strong>
          </div>

          {error ? (
            <div className="callout callout--warn" style={{ marginTop: 12 }}>
              {error}
            </div>
          ) : null}

          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn" type="button" disabled={!authorityId || !processModelId || loading} onClick={submit}>
              {loading ? "Creating…" : "Create project"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StrategicHome({
  processModel,
  selectedStage,
  artefactsByKey,
  selectedAuthorityId,
  artefactStatuses,
  setArtefactStatus,
  openArtefactKey,
  onOpenArtefact,
}: {
  processModel: CulpProcessModel | null;
  selectedStage: CulpStage | null;
  artefactsByKey: Map<string, ArtefactRegistryEntry>;
  selectedAuthorityId: string | null;
  artefactStatuses: Record<string, ArtefactStatus>;
  setArtefactStatus: (key: string, status: ArtefactStatus) => void;
  openArtefactKey: string | null;
  onOpenArtefact: (key: string) => void;
}) {
  const required = selectedStage?.required_artefacts || [];

  const statusKeyPrefix = selectedAuthorityId ? `${selectedAuthorityId}::` : "unknown::";
  const completeCount = required.filter((k) => {
    const s = artefactStatuses[`${statusKeyPrefix}${k}`] || "not_started";
    return s === "ready" || s === "published";
  }).length;
  const readiness = required.length === 0 ? 0 : Math.round((completeCount / required.length) * 100);

  return (
    <div className="panel">
      <div className="panel__title">Strategic Home (CULP programme board)</div>
      <div className="muted">
        {processModel?.source_of_truth ? (
          <>
            Source:{" "}
            <a href={processModel.source_of_truth} target="_blank" rel="noreferrer">
              GOV.UK overview
            </a>
          </>
        ) : (
          "CULP model loaded."
        )}
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <div className="kicker">Selected stage</div>
          <div className="big">{selectedStage?.title || selectedStage?.id || "Select a stage"}</div>
          <div className="muted" style={{ marginTop: 8 }}>
            Phase: <strong>{selectedStage?.phase || "—"}</strong>
            {selectedStage?.gov_uk_ref ? (
              <>
                {" "}
                ·{" "}
                <a href={selectedStage.gov_uk_ref} target="_blank" rel="noreferrer">
                  Guidance
                </a>
              </>
            ) : null}
          </div>
          <div className="muted" style={{ marginTop: 10 }}>
            Stage gate readiness: <strong>{readiness}%</strong> (demo: stored locally in this browser)
          </div>
        </div>

        <div className="card">
          <div className="kicker">Required deliverables (stage gate)</div>
          {required.length === 0 ? (
            <div className="muted" style={{ marginTop: 8 }}>
              No required artefacts listed for this stage.
            </div>
          ) : (
            <div className="artefactGrid" style={{ marginTop: 10 }}>
              {required.map((key) => {
                const meta = artefactsByKey.get(key);
                const statusKey = `${statusKeyPrefix}${key}`;
                const status = artefactStatuses[statusKey] || "not_started";
                return (
                  <div key={key} className="artefactRow">
                    <button
                      className="artefact artefact--row"
                      aria-pressed={openArtefactKey === key}
                      type="button"
                      onClick={() => onOpenArtefact(key)}
                      title={meta?.notes || ""}
                    >
                      <div className="artefact__title">{meta?.title || key}</div>
                      <div className="artefact__meta">{key}</div>
                    </button>
                    <div className="artefactRow__status">
                      <ArtefactStatusPill status={status} />
                      <select
                        className="select select--compact"
                        value={status}
                        onChange={(e) => setArtefactStatus(key, e.target.value as ArtefactStatus)}
                        aria-label={`Set status for ${key}`}
                      >
                        <option value="not_started">Not started</option>
                        <option value="drafting">Drafting</option>
                        <option value="ready">Ready</option>
                        <option value="published">Published</option>
                      </select>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DocumentEditor({
  title,
  body,
  onChangeBody,
}: {
  title: string;
  body: string;
  onChangeBody: (next: string) => void;
}) {
  return (
    <div className="doc">
      <div className="doc__title">{title}</div>
      <textarea
        className="doc__editor"
        value={body}
        onChange={(e) => onChangeBody(e.target.value)}
        spellCheck
      />
      <div className="muted" style={{ marginTop: 10 }}>
        Editor v0: replace with a Word-like WYSIWYG (citations, tables, tracked accept/reject) per `ux/UI_SYSTEM_SPEC.md`.
      </div>
    </div>
  );
}

function ScenarioWorkspace({
  planProjectId,
  culpStageId,
  framings,
  onActiveTabChange,
}: {
  planProjectId: string | null;
  culpStageId: string | null;
  framings: PoliticalFraming[];
  onActiveTabChange?: (tab: ActiveScenarioTab | null) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioSet, setScenarioSet] = useState<ScenarioSetDetail | null>(null);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [tabSheet, setTabSheet] = useState<ScenarioTabSheetResponse | null>(null);

  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [selectedFramingIds, setSelectedFramingIds] = useState<string[]>(() =>
    framings.map((f) => f.political_framing_id),
  );

  useEffect(() => {
    setSelectedFramingIds(framings.map((f) => f.political_framing_id));
  }, [framings]);

  const load = async () => {
    if (!planProjectId || !culpStageId) return;
    setLoading(true);
    setError(null);
    try {
      const [scRes, ssRes] = await Promise.all([
        getJson<ScenariosResponse>(`/api/scenarios?plan_project_id=${planProjectId}&culp_stage_id=${culpStageId}`),
        getJson<ScenarioSetListResponse>(`/api/scenario-sets?plan_project_id=${planProjectId}&culp_stage_id=${culpStageId}&limit=1`),
      ]);
      setScenarios(scRes.scenarios || []);
      const latest = (ssRes.scenario_sets || [])[0];
      if (latest?.scenario_set_id) {
        const detail = await getJson<ScenarioSetDetail>(`/api/scenario-sets/${latest.scenario_set_id}`);
        setScenarioSet(detail);
        const nextTabId = detail.scenario_set.selected_tab_id || detail.tabs[0]?.tab_id || null;
        setActiveTabId(nextTabId);
        if (nextTabId) {
          try {
            const sheet = await getJson<ScenarioTabSheetResponse>(`/api/scenario-framing-tabs/${nextTabId}/sheet`);
            setTabSheet(sheet);
          } catch {
            setTabSheet(null);
          }
        } else {
          setTabSheet(null);
        }
      } else {
        setScenarioSet(null);
        setActiveTabId(null);
        setTabSheet(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planProjectId, culpStageId]);

  useEffect(() => {
    if (!onActiveTabChange) return;
    if (!scenarioSet || !activeTabId) {
      onActiveTabChange(null);
      return;
    }
    const tab = scenarioSet.tabs.find((t) => t.tab_id === activeTabId);
    if (!tab) {
      onActiveTabChange(null);
      return;
    }
    onActiveTabChange({
      tab_id: tab.tab_id,
      run_id: tab.run_id || null,
      scenario_id: tab.scenario_id,
      political_framing_id: tab.political_framing_id,
      trajectory_id: tab.trajectory_id || null,
      status: tab.status,
    });
  }, [activeTabId, onActiveTabChange, scenarioSet]);

  const seedDefaults = async () => {
    if (!planProjectId || !culpStageId) return;
    try {
      setLoading(true);
      setError(null);
      const defaults = [
        { title: "Dispersed Growth", summary: "Distribute growth across settlements; manage change at multiple nodes." },
        { title: "Transit Corridors", summary: "Focus growth along high-capacity transit corridors and hubs." },
        { title: "Urban Intensification", summary: "Prioritise densification and regeneration in existing urban areas." },
      ];
      for (const d of defaults) {
        await postJson<Scenario>("/api/scenarios", {
          plan_project_id: planProjectId,
          culp_stage_id: culpStageId,
          title: d.title,
          summary: d.summary,
          state_vector: { template: d.title },
          status: "draft",
          created_by: "user",
        });
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const createSet = async () => {
    if (!planProjectId || !culpStageId) return;
    if (selectedScenarioIds.length === 0) {
      setError("Select at least one scenario.");
      return;
    }
    if (selectedFramingIds.length === 0) {
      setError("Select at least one political framing.");
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const detail = await postJson<ScenarioSetDetail>("/api/scenario-sets", {
        plan_project_id: planProjectId,
        culp_stage_id: culpStageId,
        scenario_ids: selectedScenarioIds,
        political_framing_ids: selectedFramingIds,
      });
      setScenarioSet(detail);
      setActiveTabId(detail.tabs[0]?.tab_id || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const selectTab = async (tabId: string) => {
    if (!scenarioSet) return;
    setActiveTabId(tabId);
    try {
      await postJson(`/api/scenario-sets/${scenarioSet.scenario_set.scenario_set_id}/select-tab`, {
        tab_id: tabId,
        selection_rationale: null,
      });
    } catch {
      // non-blocking for UI; audit logging can fail without breaking navigation
    }
    try {
      const sheet = await getJson<ScenarioTabSheetResponse>(`/api/scenario-framing-tabs/${tabId}/sheet`);
      setTabSheet(sheet);
    } catch {
      setTabSheet(null);
    }
  };

  const runActiveTab = async () => {
    if (!activeTabId) return;
    try {
      setLoading(true);
      setError(null);
      await postJson<ScenarioTabRunResponse>(`/api/scenario-framing-tabs/${activeTabId}/run`, {
        time_budget_seconds: 120,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const scenarioTitleById = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of scenarios) m.set(s.scenario_id, s.title);
    return m;
  }, [scenarios]);

  const framingTitleById = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of framings) m.set(f.political_framing_id, f.title || f.political_framing_id);
    return m;
  }, [framings]);

  if (!planProjectId || !culpStageId) {
    return (
      <div className="card">
        <div className="kicker">Scenario workspace</div>
        <div className="muted" style={{ marginTop: 8 }}>
          Create/select a plan project and a CULP stage to build Scenario × Political Framing tabs.
        </div>
      </div>
    );
  }

  return (
    <div className="judgement">
      <div className="actions">
        <button className="btn btn--ghost" type="button" disabled={loading} onClick={load}>
          Refresh
        </button>
      </div>

      {error ? (
        <div className="callout callout--warn" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}

      {!scenarioSet ? (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="kicker">Build scenario set</div>
          <div className="muted" style={{ marginTop: 8 }}>
            Tabs represent Scenario × Political Framing combinations for comparison.
          </div>

          <div className="grid2" style={{ marginTop: 12 }}>
            <div className="card">
              <div className="kicker">Scenarios</div>
              {scenarios.length === 0 ? (
                <>
                  <div className="muted" style={{ marginTop: 8 }}>
                    No scenarios yet.
                  </div>
                  <div className="actions" style={{ marginTop: 10 }}>
                    <button className="btn" type="button" disabled={loading} onClick={seedDefaults}>
                      Seed 3 defaults
                    </button>
                  </div>
                </>
              ) : (
                <div className="list" style={{ marginTop: 8 }}>
                  {scenarios.map((s) => {
                    const checked = selectedScenarioIds.includes(s.scenario_id);
                    return (
                      <label key={s.scenario_id} className="chip" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...selectedScenarioIds, s.scenario_id]
                              : selectedScenarioIds.filter((id) => id !== s.scenario_id);
                            setSelectedScenarioIds(next);
                          }}
                        />
                        <span>{s.title}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="card">
              <div className="kicker">Political framings</div>
              <div className="list" style={{ marginTop: 8 }}>
                {framings.map((f) => {
                  const checked = selectedFramingIds.includes(f.political_framing_id);
                  return (
                    <label key={f.political_framing_id} className="chip" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...selectedFramingIds, f.political_framing_id]
                            : selectedFramingIds.filter((id) => id !== f.political_framing_id);
                          setSelectedFramingIds(next);
                        }}
                      />
                      <span>{f.title || f.political_framing_id}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn" type="button" disabled={loading} onClick={createSet}>
              Create scenario set
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="tabs">
            {scenarioSet.tabs.map((t) => {
              const scenarioTitle = scenarioTitleById.get(t.scenario_id) || t.scenario_id;
              const framingTitle = framingTitleById.get(t.political_framing_id) || t.political_framing_id;
              return (
                <button
                  key={t.tab_id}
                  className="tab"
                  aria-pressed={t.tab_id === activeTabId}
                  type="button"
                  onClick={() => selectTab(t.tab_id)}
                  title={`Status: ${t.status}`}
                >
                  {scenarioTitle} × {framingTitle}
                </button>
              );
            })}
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <div className="kicker">Selected tab</div>
            <div className="big">{activeTabId ? "Run the 8-move judgement." : "Select a tab."}</div>
            {activeTabId ? (
              <div className="muted" style={{ marginTop: 8 }}>
                Status:{" "}
                <strong>{scenarioSet.tabs.find((t) => t.tab_id === activeTabId)?.status || "—"}</strong>{" "}
                {scenarioSet.tabs.find((t) => t.tab_id === activeTabId)?.run_id ? (
                  <>
                    · Run:{" "}
                    <strong>{scenarioSet.tabs.find((t) => t.tab_id === activeTabId)?.run_id}</strong>
                  </>
                ) : null}
              </div>
            ) : null}
            <div className="actions" style={{ marginTop: 12 }}>
              <button className="btn" type="button" disabled={!activeTabId || loading} onClick={runActiveTab}>
                {loading ? "Running…" : "Run judgement"}
              </button>
              <button className="btn btn--ghost" type="button" disabled={loading} onClick={load}>
                Refresh
              </button>
            </div>
          </div>

          {tabSheet?.sheet ? (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="kicker">Scenario judgement sheet</div>
              <div className="big">{tabSheet.sheet.title}</div>

              <div className="card" style={{ marginTop: 12 }}>
                <div className="kicker">Conditional position</div>
                <div className="muted" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                  {tabSheet.sheet.sections.conditional_position}
                </div>
              </div>

              <div className="card" style={{ marginTop: 12 }}>
                <div className="kicker">Planning balance</div>
                <div className="muted" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                  {tabSheet.sheet.sections.planning_balance}
                </div>
              </div>

              <div className="grid2" style={{ marginTop: 12 }}>
                <div className="card">
                  <div className="kicker">Key issues</div>
                  <div className="muted" style={{ marginTop: 8 }}>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {tabSheet.sheet.sections.key_issues.map((i) => (
                        <li key={i}>{i}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="card">
                  <div className="kicker">Evidence cards</div>
                  <div className="list" style={{ marginTop: 8 }}>
                    {tabSheet.sheet.sections.evidence_cards.map((c) => (
                      <div key={c.card_id} className="card" style={{ padding: 10 }}>
                        <div className="kicker">{c.card_type}</div>
                        <div className="big" style={{ fontSize: 14, marginTop: 6 }}>
                          {c.title}
                        </div>
                        {c.summary ? (
                          <div className="muted" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                            {c.summary}
                          </div>
                        ) : null}
                        <div className="chips">
                          {c.evidence_refs.slice(0, 2).map((r) => (
                            <span key={r} className="chip">
                              {r}
                            </span>
                          ))}
                          {c.evidence_refs.length > 2 ? <span className="chip">+{c.evidence_refs.length - 2}</span> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {tabSheet.sheet.sections.uncertainty_summary?.length ? (
                <div className="card" style={{ marginTop: 12 }}>
                  <div className="kicker">Uncertainty</div>
                  <div className="muted" style={{ marginTop: 8 }}>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {tabSheet.sheet.sections.uncertainty_summary.map((u) => (
                        <li key={u}>{u}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
            </div>
          ) : activeTabId ? (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="kicker">Scenario judgement sheet</div>
              <div className="muted" style={{ marginTop: 8 }}>
                No sheet yet for this tab. Run a judgement to generate one.
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function DmBalanceView({ framings }: { framings: PoliticalFraming[] }) {
  const scenarios = [
    { id: "approve", title: "Approve (conditions)" },
    { id: "approve_s106", title: "Approve (S106 package)" },
    { id: "refuse", title: "Refuse" },
  ];

  const tabs = scenarios.flatMap((s) =>
    framings.map((f) => ({
      id: `${s.id}__${f.political_framing_id}`,
      scenario: s,
      framing: f,
    })),
  );

  const [activeTabId, setActiveTabId] = useState<string>(() => tabs[0]?.id || "none");
  const active = tabs.find((t) => t.id === activeTabId) || tabs[0];

  return (
    <div className="judgement">
      <div className="tabs">
        {tabs.slice(0, 8).map((t) => (
          <button
            key={t.id}
            className="tab"
            aria-pressed={t.id === activeTabId}
            type="button"
            onClick={() => setActiveTabId(t.id)}
            title={t.framing.description || ""}
          >
            {t.scenario.title} × {t.framing.title || t.framing.political_framing_id}
          </button>
        ))}
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <div className="kicker">Balance (scaffold)</div>
        <div className="big">
          Under framing <strong>{active?.framing.title || "—"}</strong>, a reasonable position is:
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          <strong>{active?.scenario.title || "—"}</strong>
        </div>
      </div>
    </div>
  );
}

function CaseBoard({
  cases,
  onOpenCase,
}: {
  cases: DmCase[];
  onOpenCase: (id: string) => void;
}) {
  const columns: Array<{ key: DmCase["status"]; title: string }> = [
    { key: "new", title: "New" },
    { key: "validating", title: "Validating" },
    { key: "consultation", title: "Consultation" },
    { key: "assessment", title: "Assessment" },
    { key: "determination", title: "Determination" },
    { key: "issued", title: "Issued" },
  ];

  return (
    <div className="board">
      {columns.map((col) => (
        <div key={col.key} className="board__col">
          <div className="board__head">
            <div className="board__title">{col.title}</div>
            <div className="pill pill--small">{cases.filter((c) => c.status === col.key).length}</div>
          </div>
          <div className="board__cards">
            {cases
              .filter((c) => c.status === col.key)
              .map((c) => (
                <button key={c.id} type="button" className="case" onClick={() => onOpenCase(c.id)}>
                  <div className="case__ref">{c.reference}</div>
                  <div className="case__addr">{c.address}</div>
                  <div className="case__meta">
                    <span className="case__days">{c.days_remaining}d</span>
                    <span className="muted">· {c.description}</span>
                  </div>
                </button>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>("plan");
  const [view, setView] = useState<View>("document");
  const [showDraft, setShowDraft] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const [activeScenarioTab, setActiveScenarioTab] = useState<ActiveScenarioTab | null>(null);

  const [processModel, setProcessModel] = useState<CulpProcessModel | null>(null);
  const [registry, setRegistry] = useState<ArtefactRegistry | null>(null);
  const [authoritiesPack, setAuthoritiesPack] = useState<SelectedAuthoritiesPack | null>(null);
  const [framingsPack, setFramingsPack] = useState<PoliticalFramingsPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedAuthorityId, setSelectedAuthorityId] = useState<string | null>(null);
  const [planCycles, setPlanCycles] = useState<PlanCycle[]>([]);
  const [selectedPlanCycleId, setSelectedPlanCycleId] = useState<string | null>(null);
  const [showNewPlanCycle, setShowNewPlanCycle] = useState(false);
  const [lastIngestSummary, setLastIngestSummary] = useState<string | null>(null);

  const [planProjects, setPlanProjects] = useState<PlanProject[]>([]);
  const [selectedPlanProjectId, setSelectedPlanProjectId] = useState<string | null>(null);
  const [showNewPlanProject, setShowNewPlanProject] = useState(false);

  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [openArtefactKey, setOpenArtefactKey] = useState<string | null>(null);
  const [docBody, setDocBody] = useState<string>(
    "Get a draft fast, then make it defensible.\n\nThis is a scaffold document surface. Next: citations, evidence insertion, and suggestion accept/reject.",
  );
  const [demoArtefactStatuses, setDemoArtefactStatuses] = useState<Record<string, ArtefactStatus>>(() =>
    loadDemoArtefactStatuses(),
  );

  const [dmCases] = useState<DmCase[]>([
    {
      id: "dm1",
      authority_id: "cornwall",
      reference: "PA25/00001",
      address: "Land west of Example Road, Truro",
      description: "Outline housing (120 dwellings)",
      status: "new",
      days_remaining: 36,
    },
    {
      id: "dm2",
      authority_id: "croydon",
      reference: "25/01234/FUL",
      address: "12 High Street, Croydon",
      description: "Change of use to HMO",
      status: "consultation",
      days_remaining: 14,
    },
    {
      id: "dm3",
      authority_id: "brighton_and_hove",
      reference: "BH2025/0007",
      address: "Seafront Parade, Hove",
      description: "Shopfront alterations",
      status: "assessment",
      days_remaining: 9,
    },
  ]);
  const [openCaseId, setOpenCaseId] = useState<string | null>(null);

  useEffect(() => {
    saveDemoArtefactStatuses(demoArtefactStatuses);
  }, [demoArtefactStatuses]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setError(null);
        const [pm, reg, auths, framings] = await Promise.all([
          getJson<CulpProcessModel>("/api/spec/culp/process-model"),
          getJson<ArtefactRegistry>("/api/spec/culp/artefact-registry"),
          getJson<SelectedAuthoritiesPack>("/api/spec/authorities/selected"),
          getJson<PoliticalFramingsPack>("/api/spec/framing/political-framings"),
        ]);
        if (cancelled) return;
        setProcessModel(pm);
        setRegistry(reg);
        setAuthoritiesPack(auths);
        setFramingsPack(framings);
        setSelectedAuthorityId((auths.selected_authorities || [])[0]?.authority_id || null);
        setSelectedStageId((pm.stages || [])[0]?.id || null);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedAuthorityId) {
      setPlanCycles([]);
      setSelectedPlanCycleId(null);
      setPlanProjects([]);
      setSelectedPlanProjectId(null);
      setLastIngestSummary(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const [cyclesRes, projectsRes] = await Promise.all([
          getJson<PlanCyclesResponse>(`/api/plan-cycles?authority_id=${selectedAuthorityId}`),
          getJson<PlanProjectsResponse>(`/api/plan-projects?authority_id=${selectedAuthorityId}`),
        ]);
        if (cancelled) return;

        const cycles = cyclesRes.plan_cycles || [];
        setPlanCycles(cycles);
        setSelectedPlanCycleId((prev) => {
          if (prev && cycles.some((c) => c.plan_cycle_id === prev)) return prev;
          return cycles[0]?.plan_cycle_id || null;
        });

        const projects = projectsRes.plan_projects || [];
        setPlanProjects(projects);
        setSelectedPlanProjectId((prev) => {
          if (prev && projects.some((p) => p.plan_project_id === prev)) return prev;
          return projects[0]?.plan_project_id || null;
        });
        setLastIngestSummary(null);
      } catch (e) {
        if (cancelled) return;
        setLastIngestSummary(e instanceof Error ? e.message : String(e));
        setPlanCycles([]);
        setSelectedPlanCycleId(null);
        setPlanProjects([]);
        setSelectedPlanProjectId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedAuthorityId]);

  const authorities = authoritiesPack?.selected_authorities || [];
  const selectedAuthority = authorities.find((a) => a.authority_id === selectedAuthorityId) || null;
  const selectedPlanCycle = planCycles.find((c) => c.plan_cycle_id === selectedPlanCycleId) || null;
  const selectedPlanProject = planProjects.find((p) => p.plan_project_id === selectedPlanProjectId) || null;

  const artefactsByKey = useMemo(() => {
    const map = new Map<string, ArtefactRegistryEntry>();
    for (const a of registry?.artefacts || []) map.set(a.artefact_key, a);
    return map;
  }, [registry]);

  const stages = processModel?.stages || [];
  const selectedStage = stages.find((s) => s.id === selectedStageId) || null;
  const requiredArtefacts = selectedStage?.required_artefacts || [];

  const framings = framingsPack?.political_framings || [];

  const dmOpenCase = dmCases.find((c) => c.id === openCaseId) || null;
  const auditSummary =
    mode === "dm" && dmOpenCase
      ? `Clock: ${dmOpenCase.days_remaining}d · ${dmOpenCase.status}`
      : mode === "plan" && selectedStage
        ? `Stage: ${selectedStage.title || selectedStage.id}`
        : "No active file";

  const ingestAuthorityPack = async () => {
    if (!selectedAuthorityId || !selectedPlanCycleId) {
      setLastIngestSummary("Select a plan cycle first.");
      return;
    }
    try {
      setLastIngestSummary("Starting ingest…");
      const start = await postJson<any>(`/api/ingest/authority-packs/${selectedAuthorityId}/start`, {
        plan_cycle_id: selectedPlanCycleId,
      });
      const ingestBatchId = start?.ingest_batch_id;
      if (!ingestBatchId) {
        setLastIngestSummary("Ingest started but no ingest_batch_id was returned.");
        return;
      }

      setLastIngestSummary(`Ingest running · batch ${String(ingestBatchId).slice(0, 8)}…`);

      const pollStartedAt = Date.now();
      const pollDeadlineMs = pollStartedAt + 10 * 60 * 1000; // 10 minutes
      while (Date.now() < pollDeadlineMs) {
        await new Promise((r) => setTimeout(r, 2000));
        const batchRes = await getJson<any>(`/api/ingest/batches/${ingestBatchId}`);
        const batch = batchRes?.ingest_batch;
        const status = batch?.status;
        const outputs = batch?.outputs || {};
        const counts = outputs?.counts || {};
        const progress = outputs?.progress || {};
        const currentDoc = progress?.current_document;

        if (status === "running") {
          setLastIngestSummary(
            `Ingest running · docs ${counts?.documents_seen ?? "?"} · chunks ${counts?.chunks ?? "?"} · policies ${counts?.policies_created ?? "?"}${currentDoc ? ` · ${currentDoc}` : ""}`,
          );
          continue;
        }

        setLastIngestSummary(
          `Ingest ${status || "done"} · docs ${counts?.documents_created ?? "?"} · chunks ${counts?.chunks ?? "?"} · policies ${counts?.policies_created ?? "?"} · chunk_emb ${counts?.chunk_embeddings_inserted ?? "?"} · clause_emb ${counts?.policy_clause_embeddings_inserted ?? "?"}`,
        );
        return;
      }

      setLastIngestSummary(`Ingest still running · batch ${String(ingestBatchId).slice(0, 8)}… (check /ingest/batches)`);
    } catch (e) {
      setLastIngestSummary(e instanceof Error ? e.message : String(e));
    }
  };
  const crumbs =
    mode === "plan"
      ? [
          "Plan Studio",
          selectedAuthority?.name || selectedAuthorityId || "—",
          selectedPlanProject?.title || "No project",
          selectedStage?.title || selectedStageId || "Strategic Home",
          openArtefactKey ? artefactsByKey.get(openArtefactKey)?.title || openArtefactKey : "—",
        ]
      : [
          "Casework",
          selectedAuthority?.name || selectedAuthorityId || "—",
          dmOpenCase ? dmOpenCase.reference : "Inbox",
          dmOpenCase ? "Officer report" : "—",
        ];

  const activeDeliverableTitle =
    mode === "plan"
      ? openArtefactKey
        ? artefactsByKey.get(openArtefactKey)?.title || openArtefactKey
        : "Strategic Home"
      : dmOpenCase
        ? `Officer report · ${dmOpenCase.reference}`
        : "Casework inbox";

  const setArtefactStatus = (key: string, status: ArtefactStatus) => {
    const authorityPrefix = selectedAuthorityId ? `${selectedAuthorityId}::` : "unknown::";
    setDemoArtefactStatuses((prev) => ({ ...prev, [`${authorityPrefix}${key}`]: status }));
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand__mark">
            <svg
              width="40"
              height="34"
              viewBox="0 0 100 85"
              xmlns="http://www.w3.org/2000/svg"
              aria-label="The Planner's Assistant Logo"
            >
              <title>Shorter Map Pin Icon with 8-Point Compass Rose</title>
              <desc>
                A deep navy, flat-style map pin with a proportionally reduced height below the compass
                rose. Features smooth curves and an obtuse point. Contains a detailed golden yellow
                8-point compass rose with significantly shorter, wider-based intercardinal points.
              </desc>
              <path
                id="pin-background"
                d="M 50 80 C 35 70, 15 55, 15 35 A 35 35 0 1 1 85 35 C 85 55, 65 70, 50 80 Z"
                fill="var(--ink)"
                stroke="none"
              />
              <g id="compass-rose" transform="translate(0, -15)">
                <path d="M 37.3 37.3 A 18 18 0 0 1 62.7 37.3" stroke="var(--brand)" strokeWidth="4" fill="none" />
                <path d="M 62.7 37.3 A 18 18 0 0 1 62.7 62.7" stroke="var(--brand)" strokeWidth="4" fill="none" />
                <path d="M 62.7 62.7 A 18 18 0 0 1 37.3 62.7" stroke="var(--brand)" strokeWidth="4" fill="none" />
                <path d="M 37.3 62.7 A 18 18 0 0 1 37.3 37.3" stroke="var(--brand)" strokeWidth="4" fill="none" />
                <polygon points="50,22 53,50 47,50" fill="var(--brand)" />
                <polygon points="50,78 53,50 47,50" fill="var(--brand)" />
                <polygon points="76,50 50,52.5 50,47.5" fill="var(--brand)" />
                <polygon points="24,50 50,52.5 50,47.5" fill="var(--brand)" />
                <polygon points="56.4,43.6 54,50 50,46" fill="var(--brand)" />
                <polygon points="56.4,56.4 50,54 54,50" fill="var(--brand)" />
                <polygon points="43.6,56.4 46,50 50,54" fill="var(--brand)" />
                <polygon points="43.6,43.6 50,46 46,50" fill="var(--brand)" />
                <circle cx="50" cy="50" r="3" fill="var(--ink)" />
              </g>
            </svg>
          </div>
          <div>
            <div className="brand__title">The Planner&apos;s Assistant</div>
            <div className="brand__subtitle">AI-augmented planning workbench</div>
          </div>
        </div>

        <Toggle
          value={mode}
          onChange={(v) => {
            const next = v as Mode;
            setMode(next);
            setView("document");
            setOpenArtefactKey(null);
            setOpenCaseId(null);
          }}
          options={[
            { value: "plan", label: "Plan Studio" },
            { value: "dm", label: "Casework" },
          ]}
        />

        <div className="pill">Audit: {auditSummary} · flags 0</div>
      </header>

      <div className="shell">
        <aside className="rail">
          <div className="rail__section">
            <div className="label">Authority</div>
            <select
              className="select"
              value={selectedAuthorityId || ""}
              onChange={(e) => setSelectedAuthorityId(e.target.value || null)}
            >
              {authorities.map((a) => (
                <option key={a.authority_id} value={a.authority_id}>
                  {a.name || a.authority_id}
                </option>
              ))}
            </select>
            {selectedAuthority?.website ? (
              <div className="muted" style={{ marginTop: 8 }}>
                <a href={selectedAuthority.website} target="_blank" rel="noreferrer">
                  {selectedAuthority.website}
                </a>
              </div>
            ) : null}
          </div>

          {mode === "plan" ? (
            <>
              <div className="rail__section">
                <div className="label">Plan Cycle</div>
                <div className="actions" style={{ justifyContent: "space-between" }}>
                  <select
                    className="select select--compact"
                    value={selectedPlanCycleId || ""}
                    onChange={(e) => setSelectedPlanCycleId(e.target.value || null)}
                    disabled={planCycles.length === 0}
                    title={selectedPlanCycle?.plan_name || ""}
                  >
                    {planCycles.length === 0 ? <option value="">No plan cycles</option> : null}
                    {planCycles.map((cycle) => (
                      <option key={cycle.plan_cycle_id} value={cycle.plan_cycle_id}>
                        {cycle.plan_name}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={!selectedAuthorityId}
                    onClick={() => setShowNewPlanCycle(true)}
                  >
                    New
                  </button>
                </div>

                {selectedPlanCycle ? (
                  <div className="muted" style={{ marginTop: 8 }}>
                    Status: <strong>{selectedPlanCycle.status}</strong>
                    {selectedPlanCycle.weight_hint ? (
                      <>
                        {" "}
                        · Weight: <strong>{selectedPlanCycle.weight_hint}</strong>
                      </>
                    ) : null}
                  </div>
                ) : (
                  <div className="muted" style={{ marginTop: 8 }}>
                    Create a plan cycle to make authority versioning explicit (adopted/emerging/draft).
                  </div>
                )}

                <div className="actions" style={{ marginTop: 10 }}>
                  <button
                    className="btn"
                    type="button"
                    disabled={!selectedAuthorityId || !selectedPlanCycleId}
                    onClick={() => void ingestAuthorityPack()}
                  >
                    Ingest authority pack
                  </button>
                </div>
                {lastIngestSummary ? (
                  <div className="muted" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                    {lastIngestSummary}
                  </div>
                ) : null}
              </div>

              <div className="rail__section">
                <div className="label">Plan Project</div>
                <div className="actions" style={{ justifyContent: "space-between" }}>
                  <select
                    className="select select--compact"
                    value={selectedPlanProjectId || ""}
                    onChange={(e) => setSelectedPlanProjectId(e.target.value || null)}
                    disabled={planProjects.length === 0}
                    title={selectedPlanProject?.title || ""}
                  >
                    {planProjects.length === 0 ? <option value="">No projects</option> : null}
                    {planProjects.map((project) => (
                      <option key={project.plan_project_id} value={project.plan_project_id}>
                        {project.title}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={!selectedAuthorityId || !processModel}
                    onClick={() => setShowNewPlanProject(true)}
                  >
                    New
                  </button>
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  {selectedPlanProject ? (
                    <>
                      Status: <strong>{selectedPlanProject.status}</strong>
                    </>
                  ) : (
                    "Create/select a plan project to hold deliverables, scenarios, and runs."
                  )}
                </div>
              </div>

              <div className="rail__section">
                <div className="label">Programme (CULP)</div>
                <div className="list">
                  {stages.map((stage) => (
                    <button
                      key={stage.id}
                      className="stage"
                      aria-pressed={stage.id === selectedStageId}
                      type="button"
                      onClick={() => {
                        setSelectedStageId(stage.id);
                        setOpenArtefactKey(null);
                      }}
                    >
                      <div className="stage__title">{stage.title || stage.id}</div>
                      <div className="stage__meta">{stage.phase || ""}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rail__section">
                <div className="label">Deliverables (stage gate)</div>
                <div className="list">
                  {requiredArtefacts.length === 0 ? (
                    <div className="muted">No required artefacts listed.</div>
                  ) : (
                    requiredArtefacts.map((key) => (
                      <button
                        key={key}
                        className="artefact"
                        aria-pressed={key === openArtefactKey}
                        type="button"
                        onClick={() => {
                          setOpenArtefactKey(key);
                          setView("document");
                        }}
                        title={artefactsByKey.get(key)?.notes || ""}
                      >
                        <div className="artefact__title">{artefactsByKey.get(key)?.title || key}</div>
                        <div className="artefact__meta">
                          Status:{" "}
                          <strong>
                            {demoArtefactStatuses[`${selectedAuthorityId || "unknown"}::${key}`] || "not_started"}
                          </strong>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="rail__section">
                <div className="label">Inbox</div>
                <div className="list">
                  {dmCases
                    .filter((c) => (selectedAuthorityId ? c.authority_id === selectedAuthorityId : true))
                    .map((c) => (
                      <button
                        key={c.id}
                        className="artefact"
                        aria-pressed={c.id === openCaseId}
                        type="button"
                        onClick={() => {
                          setOpenCaseId(c.id);
                          setView("document");
                        }}
                      >
                        <div className="artefact__title">{c.reference}</div>
                        <div className="artefact__meta">
                          {c.days_remaining}d · {c.status}
                        </div>
                      </button>
                    ))}
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  PlanIt sync comes next (`integration/PLANIT_CONNECTOR_SPEC.md`).
                </div>
              </div>
            </>
          )}
        </aside>

        <main className="workspace">
          <div className="crumbs">
            {crumbs.map((c, idx) => (
              <span key={`${idx}-${c}`} className="crumb">
                {c}
              </span>
            ))}
          </div>

          <div className="workspace__head">
            <div>
              <div className="workspace__title">{activeDeliverableTitle}</div>
              <div className="muted">
                {error
                  ? `Spec load failed: ${error}`
                  : processModel
                    ? `Specs loaded · ${processModel.source_of_truth || "CULP model"}`
                    : "Loading specs…"}
              </div>
            </div>

            <div className="actions">
              <button
                className="btn"
                type="button"
                onClick={() => setShowDraft(true)}
              >
                Draft
              </button>
              <button className="btn btn--ghost" type="button" onClick={() => setShowTrace(true)}>
                Trace
              </button>
              <Toggle
                value={view}
                onChange={(v) => setView(v as View)}
                options={
                  mode === "plan"
                    ? [
                        { value: "document", label: "Deliverable" },
                        { value: "map", label: "Map & plans" },
                        { value: "judgement", label: "Scenarios" },
                        { value: "reality", label: "Visuals" },
                      ]
                    : [
                        { value: "document", label: "Officer report" },
                        { value: "map", label: "Site & plans" },
                        { value: "judgement", label: "Balance" },
                        { value: "reality", label: "Photos" },
                      ]
                }
              />
            </div>
          </div>

          <div className="workspace__body">
            {mode === "dm" && !dmOpenCase ? (
              <CaseBoard cases={dmCases} onOpenCase={(id) => setOpenCaseId(id)} />
            ) : mode === "plan" && !openArtefactKey && view === "document" ? (
              <StrategicHome
                processModel={processModel}
                selectedStage={selectedStage}
                artefactsByKey={artefactsByKey}
                selectedAuthorityId={selectedAuthorityId}
                artefactStatuses={demoArtefactStatuses}
                setArtefactStatus={setArtefactStatus}
                openArtefactKey={openArtefactKey}
                onOpenArtefact={(key) => {
                  setOpenArtefactKey(key);
                  setView("document");
                }}
              />
            ) : view === "document" ? (
              <DocumentEditor
                title={activeDeliverableTitle}
                body={docBody}
                onChangeBody={setDocBody}
              />
            ) : view === "judgement" ? (
              mode === "plan" ? (
                <ScenarioWorkspace
                  planProjectId={selectedPlanProjectId}
                  culpStageId={selectedStageId}
                  framings={framings}
                  onActiveTabChange={setActiveScenarioTab}
                />
              ) : (
                <DmBalanceView framings={framings} />
              )
            ) : (
              <div className="card">
                <div className="kicker">View scaffold</div>
                <div className="big">
                  {view === "map"
                    ? "Map/Plan canvases"
                    : view === "reality"
                      ? "Reality / photomontage canvas"
                      : "—"}
                </div>
                <div className="muted" style={{ marginTop: 8 }}>
                  Implement per `ux/VISUOSPATIAL_WORKBENCH_SPEC.md` (draw-to-ask, overlays, snapshot-to-evidence).
                </div>
              </div>
            )}
          </div>
        </main>

        <aside className="sidebar">
          <div className="panel">
            <div className="panel__title">Context margin</div>
            <div className="muted">
              Smart Feed · Live Policy Surface · Evidence Shelf (scaffold; wired to KG/retrieval next)
            </div>
          </div>

          <div className="panel">
            <div className="panel__title">Smart feed</div>
            <div className="card">
              <div className="kicker">Cursor-aware cards</div>
              <div className="muted" style={{ marginTop: 8 }}>
                Example: “Highways” → Policy T1, DfT connectivity run, TA extract.
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel__title">Evidence shelf</div>
            <div className="chips">
              <span className="chip">EvidenceCard: policy excerpt</span>
              <span className="chip">EvidenceCard: map snapshot</span>
              <span className="chip">EvidenceCard: instrument output</span>
            </div>
            <div className="muted" style={{ marginTop: 10 }}>
              Drag/drop into the document becomes “insert citation / embed card” (next).
            </div>
          </div>
        </aside>
      </div>

      <DraftOverlay
        open={showDraft}
        onClose={() => setShowDraft(false)}
        mode={mode}
        authorityId={selectedAuthorityId}
        planCycleId={selectedPlanCycleId}
        defaultContext={{
          culp_stage_id: mode === "plan" ? selectedStageId : null,
          plan_project_id: mode === "plan" ? selectedPlanProjectId : null,
          scenario_id: mode === "plan" ? activeScenarioTab?.scenario_id || null : null,
          framing_id: mode === "plan" ? activeScenarioTab?.political_framing_id || null : null,
          application_id: null,
          site_id: null,
        }}
        onInsert={(s) => setDocBody((b) => `${b}${s.content}`)}
      />
      <TraceOverlay open={showTrace} onClose={() => setShowTrace(false)} runId={activeScenarioTab?.run_id || null} />

      <PlanCycleOverlay
        open={showNewPlanCycle}
        onClose={() => setShowNewPlanCycle(false)}
        authorityId={selectedAuthorityId}
        onCreated={(cycle) => {
          setPlanCycles((prev) => [cycle, ...prev]);
          setSelectedPlanCycleId(cycle.plan_cycle_id);
        }}
      />
      <PlanProjectOverlay
        open={showNewPlanProject}
        onClose={() => setShowNewPlanProject(false)}
        authorityId={selectedAuthorityId}
        processModelId={processModel?.process_id || null}
        currentStageId={selectedStageId}
        planCycleId={selectedPlanCycleId}
        onCreated={(project) => {
          setPlanProjects((prev) => [project, ...prev]);
          setSelectedPlanProjectId(project.plan_project_id);
        }}
      />
    </div>
  );
}
