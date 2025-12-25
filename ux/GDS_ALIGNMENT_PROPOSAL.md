# GDS Alignment & Assisted Spatial Workflow Proposal
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.

This document refines the Information Architecture (IA) to align strictly with the **GOV.UK Design System (GDS)** for process navigation, while leveraging the **Visuospatial Workbench** and **AI Assistance** for complex tasks.

## 0. Scope note: “GDS alignment” for a professional workbench
This product is **not** a public-facing GOV.UK transactional service. “GDS alignment” here means:
* use GOV.UK patterns where they improve clarity and accessibility (especially **task lists**, content structure, and plain-language labeling), and
* keep the underlying architecture constraints intact (traceability, provenance, non-deterministic agents).

The workbench will still include specialised spatial/visual tooling that is not “pure GDS UI”, but it should remain:
* accessible (keyboard, contrast, clear focus states),
* predictable (no “magic” state changes),
* auditable (explicit user commits).

## 1. Core Philosophy: Process Guide + Specialized Tools

We distinguish between two modes of interaction:
1.  **The Process Guide (GDS Task List):** The "Home" view. It answers "Where are we?" and "What is next?". It is textual, statutory, and simple.
2.  **The Assisted Workspace (Specialized UI):** The "Doing" view. When a task is complex (e.g., "Assess Sites"), the user enters a rich, AI-assisted environment (Map/Plan canvas) to perform the work.

**Key Shift:** The AI does not just "wait to be asked." It **pre-computes and proposes**. When the planner opens a task, the AI has already prepared a "Draft State" (options, assessments, text) for review.

### 1.1 Non‑negotiables (TPA constraints that must be preserved)
To avoid “uncanny valley” automation and to keep decisions contestable:
* **No silent AI commits**: AI can prepare “draft state”, but only the user can adopt/accept/sign‑off changes (log an `AuditEvent`).
* **Provenance-first**: any proposed boundary, figure, statement, or checklist item must carry `EvidenceRef` and/or `ToolRun` pointers (or be an explicit `Assumption`).
* **Grammar-first judgement**: if a proposed option implies a position/recommendation, it must link to (or trigger) an 8‑move grammar run and store `MoveEvent`s.
* **Traceability is visual**: every “why is this here?” interaction should open the Trace Canvas flowchart view (summary/inspect/forensic).

## 2. The "Task List" Homepage (The Anchor)

The landing page remains a standard **GDS Task List**, mapping directly to `culp/PROCESS_MODEL.yaml`.

*   **Heading:** [Authority Name] Local Plan (2025-2040)
*   **The Task List:**
    *   **Phase 1: Getting Ready**
        *   [Completed] Confirm SEA requirement
        *   [Active] Call for Sites Assessment __— You are here__
    *   **Phase 2: Plan Preparation**
        *   [Cannot Start Yet] Define Spatial Strategy

### 2.1 DM adaptation: “task list” inside the case file
DM does not naturally start with a GOV.UK task list; it starts with an inbox and statutory clock.

However, once a planner opens a case, the **case file** can present an internal “task list” that uses the same GDS patterns:
* Validate
* Consult
* Assess
* Draft report
* Agree conditions/obligations
* Issue decision

This keeps navigation consistent while staying planner-native for casework.

## 3. The "Assisted Workspace" Patterns

When a user clicks a "Task", they enter one of three workspace types, depending on the task's nature.

### Type A: The Form-Based Assistant (Textual Tasks)
*   **Use Case:** `Confirm SEA`, `Vision Statement`, `Timetable`.
*   **Interaction:**
    1.  **AI Pre-fill:** The form opens with fields *already filled* based on previous context/documents.
        *   *Example:* "Vision Statement" is pre-drafted based on the Council's Corporate Plan (ingested previously).
    2.  **Review & Refine:** The planner edits the text.
    3.  **Governance Check:** Real-time "Linter" highlights phrases that might lack evidence or conflict with NPPF.

**Implementation note:** pre-fill must be stored as suggestions (e.g. a `DraftPack`) until the user accepts; accept/reject is always explicit and logged.

### Type B: The Spatial Option Selector (Site/Strategy Tasks)
*   **Use Case:** `Site Assessment`, `Boundary Review`, `Route Selection`.
*   **Interaction:**
    1.  **Launch:** User clicks "Assess Site REF-123".
    2.  **The Workspace:** A split-screen view (Map Left / Options Right).
    3.  **AI Proposal:** The AI doesn't just show a map. It presents **Visual Options**.
        *   *Option A:* "Standard Boundary" (matches Land Registry).
        *   *Option B:* "Extended Boundary" (includes adjacent wasteland, flagged as opportunity).
        *   *Option C:* "Constrained" (excludes flood zone).
    4.  **User Action:** Planner clicks an Option card. The Map updates instantly to reflect that boundary/layout.
    5.  **Confirm:** Planner clicks "Adopt Option B". The system records the decision and the reasoning.

**Implementation note:** option cards should expose “why this option exists”:
* inputs used (layers, constraints, tools),
* what was deliberately omitted (and why),
* limitations/uncertainty (especially plan↔reality registration).

### Type C: The Visual Reasoning Workbench (Deep Analysis)
*   **Use Case:** `Constraints Analysis`, `Viewpoint Assessment`.
*   **Interaction:**
    1.  **Launch:** User clicks "Analyze Constraints".
    2.  **The Workspace:** Full-screen Map Canvas.
    3.  **AI Layers:** The AI has *already* toggled the relevant layers (Flood, Green Belt, Heritage) and highlighted conflict zones in Red.
    4.  **Auto-Drafting:** A side panel contains a pre-written "Constraints Summary" text: *"The site is heavily constrained by Flood Zone 3 to the north..."*
    5.  **User Action:**
        *   Planner corrects the map (draws a new buffer).
        *   Planner edits the summary text.
        *   **Snapshot:** Planner clicks "Snapshot to Evidence". The system saves the *exact* view settings and the text as a citation.

**Implementation note:** “AI-chosen layers” must be explainable:
* show which layers are on/off and why,
* allow the planner to pin/dismiss layers (logged),
* record a limitations statement when layers are incomplete/out-of-date.

## 4. UI Structure for Assisted Workspaces

To maintain GDS alignment even in rich views:

*   **Header:** Standard GDS Header with "Save & Return" button.
*   **Layout:**
    *   **Left (Visual):** Map / Plan / Image Canvas. Interactive, layer-aware.
    *   **Right (Decision):** The "Control Panel".
        *   **Top:** AI Proposals (Cards/Options).
        *   **Middle:** Reasoning/Text Editor (The "Draft").
        *   **Bottom:** Evidence References (Citations).

### 4.1 Mapping to the Workbench “views”
These workspace types map cleanly to the workbench views:
* Type A → **Document view** (form/drafting with citations)
* Type B/C → **Map/Plan view** (option selector + deep analysis)
* Scenario comparison across options/priorities → **Judgement view** (tabs)
* Visual impact / photomontage workflows → **Reality view**

## 5. Terminology Updates (Planner-Centric)

| Internal Concept | User-Facing Term |
| :--- | :--- |
| `ToolRun` | **Analysis Check** |
| `Scenario` | **Option** |
| `Snapshot` | **Evidence Record** |
| `Political Framing` | **Strategic Priority (framing)** |
| `VisualAsset` | **Map Layer / Site Photo** |

**Note:** “Strategic Priority (framing)” must remain explicit and selectable by the user (it is the political lens for weighing and narration, not an internal model setting).

## 6. Implementation Strategy (Refined)

1.  **Task List Engine:** Build the `Home` view driven by `culp/PROCESS_MODEL.yaml`.
2.  **Workspace Router:** A mechanism to route specific Tasks to specific Workspace layouts (Form vs. Spatial).
3.  **AI "Pre-Flight" Hooks:** Define a hook system where entering a task triggers an agent job to prepare the "Draft State" (options/text) *without blocking the UI*.
    * show a loading skeleton immediately
    * stream proposals as they arrive
    * cache the prepared draft state and timestamp it (“prepared at 10:42”)
    * never auto-apply proposals to canonical state without user confirmation
4.  **Spatial Components:**
    *   **OptionCard:** A UI component showing a mini-map thumbnail + text summary + "Select" button.
    *   **LiveMap:** A wrapper around the Map Canvas that accepts `StateVector` inputs to render options instantly.
    *   **DraftEditor:** A rich text editor that accepts AI streams and allows citation insertion.

## 7. Scenario Walkthrough: "Assess Site Capacity"

1.  **Home:** Planner sees "[Active] Assess Site Capacities (34 remaining)".
2.  **Click:** Opens list of sites. Selects "Land at North Farm".
3.  **Loading:** "Analysing constraints and capacity models..." (AI is working).
4.  **Workspace Opens:**
    *   **Left:** 3D Map of the site.
    *   **Right Panel:** "Capacity Options".
        *   **Option 1 (Low Density):** "30 dwellings (detached). Reflects local character."
        *   **Option 2 (Med Density):** "55 dwellings. Optimizes for transit hub proximity."
        *   **Option 3 (Max):** "80 dwellings. Requires 4-storey flats (High visual impact risk)."
5.  **Interaction:** Planner clicks "Option 2".
    *   Map updates to show massing blocks for 55 units.
    *   "Draft Assessment" text box updates: *"Site is suitable for approximately 55 dwellings..."*
6.  **Refinement:** Planner toggles "Flood Layer" on map. Notices a clash.
    *   Manually draws a "No Build Zone" on the map.
    *   AI updates Option 2 text: *"Capacity reduced to 48 dwellings due to surface water risk."*
7.  **Completion:** Planner clicks "Save Assessment". Returns to Task List.

**Note:** default should be 2D-first with an optional 3D toggle; 3D is valuable but can be slow and harder to verify/accessibly navigate.

---
**Summary:**
This proposal balances the **clarity** of the statutory process (GDS Task List) with the **power** of AI-assisted spatial reasoning. The complexity is hidden inside the "Task" workspaces, which present **choices** rather than blank canvases.
