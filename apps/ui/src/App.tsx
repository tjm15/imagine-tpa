import { useEffect, useMemo, useState } from "react";

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

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

function StageGate({
  stage,
  artefactsByKey,
}: {
  stage: CulpStage | null;
  artefactsByKey: Map<string, ArtefactRegistryEntry>;
}) {
  if (!stage) return <div className="card">Select a stage.</div>;

  const required = stage.required_artefacts || [];

  return (
    <div className="card">
      <div className="kicker">Selected stage</div>
      <div className="big">{stage.title || stage.id}</div>
      <div className="muted" style={{ marginTop: 6 }}>
        Phase: <strong>{stage.phase || "—"}</strong>
        {stage.gov_uk_ref ? (
          <>
            {" "}
            · GOV.UK:{" "}
            <a href={stage.gov_uk_ref} target="_blank" rel="noreferrer">
              link
            </a>
          </>
        ) : null}
      </div>

      <div className="kicker" style={{ marginTop: 12 }}>
        Required artefacts (stage gate)
      </div>
      <div className="chips">
        {required.length === 0 ? (
          <span className="muted">No required artefacts listed.</span>
        ) : (
          required.map((key) => {
            const a = artefactsByKey.get(key);
            const title = a?.title || key;
            return (
              <span key={key} className="chip chip--required" title={a?.notes || ""}>
                {title}
              </span>
            );
          })
        )}
      </div>

      <div className="muted" style={{ marginTop: 12 }}>
        This UI slice demonstrates stage gating semantics. Next steps are to persist per-project artefact
        status via the `culp_artefacts` ledger and to attach runs/snapshots to published artefacts.
      </div>
    </div>
  );
}

export default function App() {
  const [processModel, setProcessModel] = useState<CulpProcessModel | null>(null);
  const [registry, setRegistry] = useState<ArtefactRegistry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        setError(null);
        const [pm, reg] = await Promise.all([
          getJson<CulpProcessModel>("/api/spec/culp/process-model"),
          getJson<ArtefactRegistry>("/api/spec/culp/artefact-registry"),
        ]);
        if (cancelled) return;
        setProcessModel(pm);
        setRegistry(reg);
        const first = (pm.stages || [])[0]?.id || null;
        setSelectedStageId(first);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const artefactsByKey = useMemo(() => {
    const map = new Map<string, ArtefactRegistryEntry>();
    for (const a of registry?.artefacts || []) map.set(a.artefact_key, a);
    return map;
  }, [registry]);

  const stages = processModel?.stages || [];
  const selectedStage = stages.find((s) => s.id === selectedStageId) || null;

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <div className="brand__title">The Planner’s Assistant</div>
          <div className="brand__subtitle">React/Vite workbench scaffold · Strategic Home stage gating</div>
        </div>
        <div className="pill">UI: vite</div>
      </header>

      <main className="layout">
        <section className="panel">
          <div className="panel__title">Strategic Home (CULP)</div>
          <div className="muted">
            {error
              ? `Failed to load specs: ${error}`
              : processModel
                ? `Loaded ${stages.length} stages from ${processModel.source_of_truth || "CULP model"}.`
                : "Loading CULP process model…"}
          </div>

          <div className="grid">
            <div>
              <div className="label">Stages</div>
              <div className="list">
                {stages.map((stage) => (
                  <button
                    key={stage.id}
                    className="stage"
                    onClick={() => setSelectedStageId(stage.id)}
                    aria-pressed={stage.id === selectedStageId}
                    type="button"
                  >
                    <div className="stage__title">{stage.title || stage.id}</div>
                    <div className="stage__meta">{stage.phase || ""}</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="label">Stage Gate</div>
              <StageGate stage={selectedStage} artefactsByKey={artefactsByKey} />
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel__title">Next actions (scaffold)</div>
          <div className="card">
            <ol className="muted">
              <li>Implement `PlanProject` creation + `culp_artefacts` ledger persistence.</li>
              <li>Wire sidebar: Live Policy Surface + Evidence Shelf.</li>
              <li>Add Scenario×Framing tabs and judgement sheet renderer.</li>
              <li>Render Trace Canvas from MoveEvents/ToolRuns/AuditEvents.</li>
            </ol>
          </div>
        </section>
      </main>
    </>
  );
}

