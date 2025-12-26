# TPA-NSIP Module Specification

TPA-NSIP is a Procedural Foresight and Assistance module for Nationally Significant
Infrastructure Projects (NSIP). It is a planner-facing workbench that turns a
multi-source NSIP corpus into actionable assistance loops, with traceable,
contestable reasoning.

This module is not "chat with PDF". It treats a project as a changing pressure
field of hypotheses and surfaces concrete work items, drafts, and warnings while
preserving institutional nuance. It never collapses uncertainty into a single
risk score.

---

## 1) North star
* Maintain a live procedural understanding of a NSIP across DCOs, s106, SoCGs,
  consultation logs, and discharge portals.
* Provide planner-legible assistance loops (tasks, drafts, warnings) that are
  grounded in evidence and logged procedures.
* Learn without expert labels using time as the supervisor.

---

## 2) Product architecture (NSIP mode)
NSIP adds a dedicated mode to the TPA workbench with four primary panels.

### 2.1 Action Slate (what next)
* Ranked, work-focused agenda: This week, Next month, Sleeping risks.
* Action cards generated from hypotheses and evidence deltas.
* Each card has a "why" chain and an evidence checklist.

### 2.2 Issue Register (coordination loop)
* Persistent threads by topic (e.g. construction traffic, night noise, BNG).
* Friction map showing where promoter and authorities diverge.
* "Boomerang" detection for issues that appear resolved but remain brittle.

### 2.3 Evidence Pack Builder (drafting loop)
* Auto-assembles a context pack per task (graph slice, deltas, excerpts).
* Gap analysis for missing artifacts before drafting starts.
* Citation gating: no draft output without specific document IDs.

### 2.4 Watchlist (foresight loop)
* No probability score; instead, specific observables to monitor.
* Example: "If a non-material change is filed for Work No. 3, expect
  Hypothesis H3 (budget stress) to dominate."

---

## 3) Core intelligence: the Pressure Field Engine
The engine maintains high-dimensional state and multiple hypotheses at once.

### 3.1 Pressure field state
Internal state tensor:
P[time, actor, topic, location, phase] -> posterior distributions over latent
variables such as:
* discretion deferral
* enforcement ambiguity
* consultation debt
* delivery brittleness

### 3.2 Abductive inference
* Generates hypotheses that best explain observed signals.
* Maintains a posterior band of competing hypotheses until disproved.
* Emits manifestations: expected future observables if a hypothesis holds.

### 3.3 Latent templates (cold start)
* Bootstraps with a library of latent templates (e.g. blame displacement,
  consultation debt) rather than expert labels.
* Templates are instantiated and adapted by observed evidence.

---

## 4) Technical architecture (stack)

### Layer A: Multi-source harvester (evidence substrate)
* Scheduler: deterministic sync from stable sources (PINS, GOV.UK).
* Scout: agent that proposes retrieval targets for missing artifacts.
* Safety: Scout proposes; Scheduler executes; all runs are logged.
* Maintains a version graph with supersession and diffs.

### Layer B: Signal extraction (neural)
* LLMs extract signals, not conclusions:
  - conditionality density
  - "to be agreed" clustering
  - draft churn rate
  - SoCG asymmetry
  - responsibility diffusion

### Layer C: Constraint geometry (symbolic)
* Graph of institutional invariants constraining procedural moves.
* Nodes: artifacts, actors, assets, phases.
* Edges: obliges, approves, consults, supersedes, triggers.
* Prevents invalid procedural inferences (e.g. LPA approves DCO amendment).

### Layer D: Scenario and intervention generator
* Perturbation tests: "If schedule pressure increases, which hypothesis wins?"
* Intervention levers: suggested actions tied to hypotheses (e.g. tighten
  definition of commencement to reduce ambiguity risk).

---

## 5) Data strategy: learning without experts

### 5.1 Self-supervised temporal backtesting
1. Snapshot a historical project state at time t.
2. Forecast hypotheses and manifestations for time t + delta.
3. Roll forward and verify whether manifestations occurred.
4. Calibrate weights based on outcomes.

### 5.2 Adversarial ensembles
* Model A proposes hypotheses.
* Model B (critic) seeks disconfirming evidence.
* Model C checks feasibility against the constraint geometry.
* Only robust hypotheses reach the user.

---

## 6) Implementation roadmap

### Phase 1 (Weeks 1-6): foundation
* Harvester (PINS + basic scraping), casefile timeline.
* Action Slate (heuristic-based), Evidence Pack Builder.
* Value: centralized view and smart librarian.

### Phase 2 (Weeks 7-12): signal store and gaps
* Neural signal extraction, missing artifact detection (Scout).
* Constraint graph v1.
* Value: drafting acceleration and missing artifact warnings.

### Phase 3 (Weeks 13-18): abductive core
* Hypothesis engine, backtesting harness, risk-based Action Slate.
* Value: sleeping risk detection and foresight.

### Phase 4 (Weeks 19+): scenarios and levers
* Scenario workbench and intervention levers.
* Value: strategic guidance tied to procedural risks.

---

## 7) Alignment with TPA invariants
* All outputs are logged as AuditEvents with evidence and provenance.
* External model calls are ToolRuns with inputs, outputs, and limitations.
* Uses frozen 8-move grammar for judgement where positions are stated.
* Must run in both OSS and Azure profiles without hybrid runtime.

---

## 8) Required schema and service additions (planned)
* NSIP case record and timeline entries.
* Hypothesis, Manifestation, Signal, Template, and ActionCard objects.
* Constraint geometry graph extensions in the KG schema.
* Backtesting harness persistence for temporal calibration.

