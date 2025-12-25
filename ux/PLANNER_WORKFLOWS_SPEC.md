# Planner-First Workflows (UI Spec)
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.

This document defines the UI around **how planners actually work**, not around internal architecture.
It complements:
* `ux/DASHBOARD_IA.md` (information architecture)
* `ux/UI_SYSTEM_SPEC.md` (implementable UI contracts)
* `culp/PROCESS_MODEL.yaml` (GOV.UK 30‑month plan-making alignment)

The goal is that a planner can do the job faster, with less risk, and with a defensible audit trail.

---

## 1) Experience principles (planner-shaped, not engineer-shaped)

1. **The deliverable is the product**
   - The primary object is always a publishable artefact: plan chapter, policy wording, officer report, consultation summary, evidence schedule.
   - Everything else exists to support producing and signing off that artefact.

1.1 **Draft-first, then defend**
   - Planners need a first draft fast to react to meetings, member steer, and consultation timelines.
   - The system must make it trivial to “Get a draft”, then make it safe to refine by forcing citations, surfacing gaps, and logging human sign-off.

2. **Evidence lives in the margin**
   - Evidence is not a separate “research mode”; it is continuously present as cards, citations, and source previews.
   - Planners can answer “where does that come from?” in one click.

3. **Map is a verb**
   - The map is for doing: draw, ask, test, snapshot, cite.
   - No GIS specialist workflow is required to get value.

4. **AI behaves like a careful colleague**
   - AI suggests, drafts, and checks; it does not “apply changes”.
   - Every suggestion is inspectable, caveated, and attributable.

5. **Risk is continuously visible**
   - If something will fail at Gateway / consultation / examination, the system should surface it early as a gap, not late as a surprise.

6. **From glanceable to forensic**
   - Everyday mode is fast and uncluttered.
   - “Inspect/Forensic” modes exist for managers, inspectors, complaints, JR/FOI packs.

6.1 **Traceability is visual**
   - The default traceability surface is a flowchart-like Trace Canvas, not JSON.
   - Planners can click any sentence and see the upstream evidence and tests that support it.

7. **It remembers the file**
   - The system behaves like a planning file: what was known when, what changed, who accepted what, and why.

---

## 2) What a planner is trying to do (jobs-to-be-done)

### 2.1 Spatial Strategy (plan-making)
Core jobs:
* Build a defensible **place portrait** (baseline) quickly.
* Form and compare **spatial strategy options** (reasonable alternatives) without drowning in spreadsheets.
* Move from strategy → sites → policies with a visible “golden thread”.
* Run consultation and produce usable summaries.
* Stress-test for gateway/examination and close evidence gaps early.
* Publish with confidence (and produce audit bundles if challenged).

### 2.2 Development Management (casework)
Core jobs:
* Validate quickly, extract key facts, and reduce admin burden.
* Understand policy + constraints + precedent fast.
* Track negotiations and what changed between iterations.
* Produce defensible officer reporting with citations.

### 2.3 Monitoring & Delivery
Core jobs:
* Keep a live “reality check” loop between plan intent and delivery.
* Detect divergence early and propose interventions.
* Draft AMR-style reporting with traceable numbers.

---

## 3) Planner-first workflow: Spatial Strategy (the upstream priority)

This is the first implementation focus. Everything else is downstream.

### 3.1 Getting Ready (pre‑30‑month clock)
Planner intent:
* “What do we have, what’s missing, and what will block us?”

UI must provide:
* Timeline stage list (from `culp/PROCESS_MODEL.yaml`) with a **blocking graph** (critical path).
* One-click: “Create timetable”, “Generate notice pack”, “Confirm SEA requirement”.
* A “readiness view” that feels like a checklist + risks, not an analyst dashboard.

### 3.2 Baselining & place portrait
Planner intent:
* “Give me a coherent baseline I can trust, and show me where it’s weak.”

UI must provide:
* Place portrait sheet (document-like) with:
  - a small number of headline indicators (not dozens),
  - maps + snapshots embedded as evidence,
  - explicit limitations/gaps.
* A one-click “Get a draft place portrait” action:
  - produces an editable draft in the Living Document,
  - highlights uncited claims and gaps,
  - links every figure/map to evidence cards and tool runs.
* A “baseline builder” action:
  - choose public sources to pull,
  - show licensing notes,
  - show confidence/coverage gaps as plain language.

### 3.3 Vision & outcomes (≤10)
Planner intent:
* “Translate political intent into testable outcomes.”

UI must provide:
* A structured “outcomes editor” (≤10) that links each outcome to:
  - supporting evidence,
  - candidate indicators (monitoring-ready),
  - candidate spatial implications (what it means on the ground).

### 3.4 Spatial strategy options (reasonable alternatives)
Planner intent:
* “Generate and iterate strategy options, then compare them in a way that feels like planning judgement.”

UI must provide:
* A **Scenario Workspace**:
  - scenario cards (human-readable),
  - scenario state vector under the hood,
  - “mutate scenario” controls (prompt + guided sliders).
* **Tabs = Scenario × Political Framing**:
  - “Under framing X, option S looks like…”
  - explicit trade-offs, not fake precision.
* Three comparison tools that feel like planning:
  - a “tensions” matrix (policy/constraint conflicts),
  - a “benefits” matrix (opportunity signatures),
  - a “delta explainer” (what changed, why it matters).
* A “Get a draft strategy narrative” action:
  - drafts the narrative of why a strategy is reasonable under a given framing,
  - inserts citations automatically where evidence exists,
  - flags assumptions explicitly where evidence does not exist.

### 3.5 Sites stage (identify → assess → allocate)
Planner intent:
* “Do site selection at scale, but keep the reasoning traceable.”

UI must provide:
* Bulk site ingestion + mapping.
* Site assessment pages that look like:
  - a mini officer report for allocation,
  - with a site fingerprint summary,
  - with a small number of decisive tests (constraints, accessibility, deliverability signals),
  - with evidence cards and limitations.
* A “shortlist board” that shows:
  - why sites are in/out,
  - what would change the answer,
  - which gaps are blocking.
* A “Get a draft allocation assessment” action per site:
  - creates a draft assessment block the planner can edit,
  - links to decisive tests (constraints/accessibility/deliverability),
  - flags what evidence is missing to make it defensible.

### 3.6 Consultation
Planner intent:
* “Summarise what people actually said and what it means for the plan.”

UI must provide:
* Theme clusters with representative quotes and traceability to source submissions.
* “Change log” view:
  - what the plan changed in response to consultation,
  - what was not changed and why (deliberate omissions).
* A “Get a draft consultation summary” action:
  - produces a summary in plain officer language,
  - preserves representative quotes and traceability,
  - highlights contested issues and uncertainty.

### 3.7 Gateway / examination readiness
Planner intent:
* “Tell me where an inspector will hit us, with receipts.”

UI must provide:
* “Inspector simulation” outputs as:
  - evidence gaps,
  - strained interpretations,
  - policy conflicts,
  - unreasonable alternatives coverage warnings.
* A remediation workflow:
  - commission evidence,
  - rerun tests,
  - regenerate sheets,
  - record changes as traceable deltas.

At every stage, planners must be able to:
* “Get a draft” (fast) to start work, then
* “Make it defensible” (trace + citations + governance checks) before sign-off.

---

## 4) The WYSIWYG editor: what makes it planner-grade (not a generic editor)

The editor must feel like Word (familiar), but behave like a planning file (traceable).

Required planner-grade features:
* **Citations that work like planners work**:
  - clickable footnote-style citations,
  - evidence preview on hover,
  - one-click “insert policy clause” with proper reference.
* **Drafting with friction in the right places**:
  - AI can propose, but cannot silently overwrite.
  - accept/reject is explicit and logged.
* **Reasoning gap highlights**:
  - uncited claims,
  - missing tests,
  - missing qualifications/limitations for instruments.
* **Publishing outputs**:
  - PDF-like preview and export,
  - inspector/FOI pack export (evidence bundle + trace).

---

## 5) How “clever architecture” becomes felt value in the UI

Planners should experience the underlying system as:
* “I can find the right policy in seconds.”
* “I can explain why we chose this option without rewriting the world.”
* “I can see what will block the timetable before it blocks us.”
* “I can take a map snapshot and it’s instantly citeable.”
* “I can accept an AI draft and I know exactly what it relied on.”

If a feature does not improve one of those felt outcomes, it is not part of v1.
