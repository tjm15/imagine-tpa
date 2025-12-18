import { useEffect, useMemo, useState } from "react";

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

type DmCase = {
  id: string;
  authority_id: string;
  reference: string;
  address: string;
  description: string;
  status: "new" | "validating" | "consultation" | "assessment" | "determination" | "issued";
  days_remaining: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
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
}: {
  open: boolean;
  onClose: () => void;
}) {
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

function JudgementView({
  mode,
  framings,
}: {
  mode: Mode;
  framings: PoliticalFraming[];
}) {
  const scenarios =
    mode === "plan"
      ? [
          { id: "dispersed_growth", title: "Dispersed Growth" },
          { id: "transit_corridors", title: "Transit Corridors" },
          { id: "urban_intensification", title: "Urban Intensification" },
        ]
      : [
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
        <div className="kicker">Scenario × Political framing (scaffold)</div>
        <div className="big">
          Under framing <strong>{active?.framing.title || "—"}</strong>, a reasonable position is:
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          <strong>{active?.scenario.title || "—"}</strong> (sheet rendering + evidence drill-down comes next).
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
  const [showTrace, setShowTrace] = useState(false);

  const [processModel, setProcessModel] = useState<CulpProcessModel | null>(null);
  const [registry, setRegistry] = useState<ArtefactRegistry | null>(null);
  const [authoritiesPack, setAuthoritiesPack] = useState<SelectedAuthoritiesPack | null>(null);
  const [framingsPack, setFramingsPack] = useState<PoliticalFramingsPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedAuthorityId, setSelectedAuthorityId] = useState<string | null>(null);
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

  const authorities = authoritiesPack?.selected_authorities || [];
  const selectedAuthority = authorities.find((a) => a.authority_id === selectedAuthorityId) || null;

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
  const crumbs =
    mode === "plan"
      ? [
          "Projects",
          selectedAuthority?.name || selectedAuthorityId || "—",
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
            { value: "plan", label: "Local Plan" },
            { value: "dm", label: "DM Casework" },
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
                              {demoArtefactStatuses[`${selectedAuthorityId || "unknown"}::${key}`] ||
                                "not_started"}
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
                onClick={() => setDocBody((b) => `${b}\n\n[DRAFT] Inserted placeholder draft block.`)}
              >
                Draft
              </button>
              <button className="btn btn--ghost" type="button" onClick={() => setShowTrace(true)}>
                Trace
              </button>
              <Toggle
                value={view}
                onChange={(v) => setView(v as View)}
                options={[
                  { value: "document", label: "Document" },
                  { value: "map", label: "Map/Plan" },
                  { value: "judgement", label: "Judgement" },
                  { value: "reality", label: "Reality" },
                ]}
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
              <JudgementView mode={mode} framings={framings} />
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

      <TraceOverlay open={showTrace} onClose={() => setShowTrace(false)} />
    </div>
  );
}
