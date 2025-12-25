# Planner-First UX Concept: The Planner's Assistant Testbed
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.

## 1. Conceptual Analysis: What's Missing

### Current State Assessment

The existing UI (both the canonical dockerized version and the "Improve Project UI" testbed) provides:
- ✅ Two distinct workspaces (Plan Studio / Casework)
- ✅ Four views (Document, Map, Judgement, Reality)
- ✅ Context margin with evidence shelf and policy chips
- ✅ Process rail showing stages/cases
- ✅ Audit ribbon with run tracking and explainability modes
- ✅ Attractive visual polish (animations, transitions, warmth)

### What's Missing from a Planner Mental Model

1. **Orientation & Wayfinding**
   - Planners ask: "Where am I in my thinking, not just the process?"
   - Missing: Clear indication of which reasoning stage is active (framing → issues → evidence → interpretation → considerations → balance → negotiation → positioning)
   - Missing: Visual "you are here" that connects process stage to reasoning state

2. **Traceability as a Primary Surface**
   - The Trace Canvas exists as an overlay, but planners need to *live* with provenance
   - Missing: Inline provenance that doesn't require opening a separate view
   - Missing: "Why is this here?" as a first-class interaction everywhere, not a hidden feature

3. **Confidence & Uncertainty**
   - Planners work with provisional judgements, contested evidence, and evolving positions
   - Missing: Visual language for "settled" vs "provisional" vs "contested" 
   - Missing: Uncertainty indicators that are glanceable, not buried

4. **Narrative Flow**
   - Planning judgement is storytelling: "here's what we're doing, why, what we found, what it means, what we recommend"
   - Missing: The document view is WYSIWYG but doesn't scaffold the narrative structure
   - Missing: Clear progression from evidence → considerations → balance → position

5. **Control Over AI**
   - Planners want AI as a careful colleague, not a black box
   - Missing: Clear boundaries between "AI suggested this" and "I decided this"
   - Missing: Easy way to see what the AI *didn't* consider (deliberate omissions)

6. **The Ledger as a Thinking Tool**
   - Material considerations are the "bricks" of planning argument
   - Missing: A dedicated considerations ledger that planners can build incrementally
   - Missing: Visual representation of tensions, trade-offs, and weights

---

## 2. Planner-First Interaction Model

### Primary Workspace Layout

The workspace is organised around the **file being worked** (deliverable), with reasoning surfaces as lenses:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Mode · Authority · Project · Stage/Case · Deadline/Gate Status      │
│         [Audit Ribbon: run_id · trace toggle · explainability · export]     │
├──────────────┬──────────────────────────────────────────┬───────────────────┤
│              │                                          │                   │
│   PROCESS    │           MAIN WORKSPACE                 │    CONTEXT        │
│   RAIL       │                                          │    MARGIN         │
│              │   ┌────────────────────────────────┐     │                   │
│  Where am I  │   │  View Tabs:                    │     │   Evidence        │
│  in the      │   │  Deliverable | Map | Balance | │     │   Shelf           │
│  programme?  │   │  Visuals                       │     │                   │
│              │   └────────────────────────────────┘     │   Policy          │
│  What's      │                                          │   Surface         │
│  blocking?   │   ┌────────────────────────────────┐     │                   │
│              │   │                                │     │   Smart           │
│  What's      │   │   ACTIVE VIEW CONTENT          │     │   Feed            │
│  next?       │   │                                │     │                   │
│              │   │   with inline provenance       │     │   Site            │
│              │   │   and "why?" affordances       │     │   Preview         │
│              │   │                                │     │                   │
│              │   └────────────────────────────────┘     │                   │
│              │                                          │                   │
│              │   ┌────────────────────────────────┐     │                   │
│              │   │  REASONING TRAY (collapsible)  │     │                   │
│              │   │  Current move · Considerations │     │                   │
│              │   │  ledger · Trace summary        │     │                   │
│              │   └────────────────────────────────┘     │                   │
│              │                                          │                   │
└──────────────┴──────────────────────────────────────────┴───────────────────┘
```

### Key Innovations

1. **Reasoning Tray** (bottom of main workspace)
   - A collapsible panel that shows the current "move" in the 8-move grammar
   - Quick access to the considerations ledger
   - Trace summary showing the "spine" of reasoning

2. **Inline Provenance**
   - Every claim/figure/policy chip has a subtle provenance indicator
   - Clicking reveals the upstream evidence without leaving context

3. **Settled/Provisional Visual Language**
   - Settled: solid borders, full opacity
   - Provisional: dashed borders, slightly reduced opacity
   - Contested: amber accent, visible tension indicator

4. **Progress Through Reasoning**
   - A subtle "reasoning stage" indicator in the audit ribbon
   - Shows: Framing ○ → Issues ● → Evidence ● → Interpretation ○ → ...
   - Filled circles = work done; hollow = not yet addressed

---

## 3. The Planning Process in the UI

### The 8-Move Grammar as UX Scaffolding

The system's judgement engine follows 8 moves. The UI doesn't force linearity, but makes the moves *discoverable* and *navigable*:

| Move | UI Surface | Planner Question |
|------|-----------|-----------------|
| 1. Framing | Header + Reasoning Tray | "What lens am I using? What are my goals?" |
| 2. Issues | Reasoning Tray → Issue List | "What matters here?" |
| 3. Evidence | Context Margin + Evidence Shelf | "What do I know? What's missing?" |
| 4. Interpretation | Document View (inline) + Reality View | "What does the evidence mean here?" |
| 5. Considerations | Ledger View (in Reasoning Tray) | "What are my building blocks?" |
| 6. Balance | Judgement View tabs | "How do I weigh competing concerns?" |
| 7. Negotiation | Document View (redlines/conditions) | "What would make this work?" |
| 8. Positioning | Document View (narrative) | "What's my story, under this framing?" |

### Non-Linear Navigation

- Planners can jump to any move
- The UI shows what's "done" vs "pending" vs "needs revisiting"
- Changes to upstream moves (e.g., new evidence) flag downstream as "stale"

### First-Class Uncertainty

Every AI output and interpretation carries:
- **Confidence level**: High / Medium / Low (never hidden)
- **Limitations**: What the tool/model *couldn't* assess
- **Assumptions**: What was taken as given (explicitly stated)

Visual treatment:
- High confidence: normal presentation
- Medium: subtle amber underline
- Low: dashed border + explicit caveat

---

## 4. Core UI Surfaces

### 4.1 Deliverable View (Document)

**Purpose**: Draft, edit, and cite the primary output (plan chapter, officer report, policy wording).

**Planner thinking supported**: Narrative formation, evidence citation, structured argumentation.

**Objects**:
- Text blocks with provenance indicators
- Embedded evidence cards (dragged from shelf)
- AI suggestion blocks (accept/reject/edit)
- Evidence gap warnings
- Inline policy citations (chips)

**Key interactions**:
- "Insert citation" drops an evidence link inline
- "Why is this here?" on any paragraph reveals upstream trace
- "Get a draft" produces suggestions in a side panel, not inline (until accepted)

### 4.2 Map & Plans View

**Purpose**: Geospatial reasoning, constraint checking, "draw to ask", plan-reality comparison.

**Planner thinking supported**: Spatial judgement, site context, overlay analysis.

**Objects**:
- Base map with toggleable constraint layers
- Drawing tools (point/area/buffer queries)
- Plan overlay canvas (registered plans/policy maps)
- Site markers with linked evidence
- Snapshot tool (export current view as citable evidence)

**Key interactions**:
- Draw a polygon → system surfaces relevant constraints, policies, evidence
- Toggle between "plan" (what the policy says) and "reality" (what's actually there)
- Export snapshot creates an `EvidenceCard` with provenance

### 4.3 Balance View (Judgement)

**Purpose**: Weigh considerations under explicit political framings.

**Planner thinking supported**: Trade-off reasoning, scenario comparison, conditional positioning.

**Objects**:
- Scenario × Framing tabs (each tab is a complete judgement path)
- Considerations ledger (in/out, weight, tensions)
- Balance summary (what tips the scales)
- Position statement (conditional recommendation)
- Assumptions & uncertainties box

**Key interactions**:
- Select a tab = explicit user choice (audited)
- Each tab shows the same evidence/considerations but different weights/conclusions
- "What would change this?" reveals sensitivity

### 4.4 Visuals View (Reality)

**Purpose**: Site photos, photomontages, visual impact assessment with caveated interpretations.

**Planner thinking supported**: Visual judgement, character assessment, "what you'd see" reasoning.

**Objects**:
- Site photo gallery (with metadata)
- Plan-reality overlays (registered plans on aerial/photo)
- Photomontage comparisons (baseline vs proposed, where available)
- Visual interpretation blocks (AI-generated with limitations)

**Key interactions**:
- "Quote what's visible" = select region, get structured description with caveats
- Scenario toggle (compare before/after)
- Export photo + interpretation as citable evidence

### 4.5 Considerations Ledger (in Reasoning Tray)

**Purpose**: Build and manage the "bricks" of the planning argument.

**Planner thinking supported**: Systematic consideration formation, tension identification, completeness checking.

**Objects**:
- Consideration cards (issue → evidence → interpretation → policy link)
- Weight indicators (under current framing)
- Tension markers (which considerations conflict)
- Completeness indicators (which issues lack considerations)

**Key interactions**:
- Add consideration from evidence interpretation
- Link consideration to policy clause
- Mark as "decisive" or "material but not decisive"
- Flag tension between considerations

### 4.6 Trace Canvas (Overlay)

**Purpose**: Visual provenance for any claim or output.

**Planner thinking supported**: "How did we get here?", audit, challenge, defensibility.

**Objects**:
- Flowchart nodes (moves, tool runs, evidence, interpretations, outputs)
- Edge types (uses, produces, cites, assumes, supersedes)
- Explainability mode toggle (summary / inspect / forensic)

**Key interactions**:
- Triggered by "Why is this here?" on any element
- Shows upstream path to the selected element
- Drill down to see tool inputs/outputs, model calls, human decisions
- Diff mode: compare two runs or snapshots

---

## 5. Interaction Principles

### Inspecting AI Outputs

Every AI-generated element has:
1. **Subtle indicator**: A small sparkle icon or "AI" chip
2. **Hover state**: Shows confidence + "See why" link
3. **"See why" click**: Opens inline or side panel with:
   - What evidence was used
   - What tool/model produced it
   - What assumptions were made
   - What limitations apply

### Provenance & Inputs

- Policy chips show source (local plan ref, NPPF para, case law)
- Evidence cards show source, date, licensing, confidence
- Interpretations show which evidence they draw on

### Challenge & Override

- Any AI suggestion can be:
  - **Accepted** (becomes part of deliverable, logged as user decision)
  - **Edited** (user modifies before accepting, logged as user override)
  - **Rejected** (removed, logged as rejection)
- Users can add manual considerations not generated by AI
- Manual overrides are visually distinct (human badge)

### Settled vs Provisional

| State | Visual Treatment | Meaning |
|-------|-----------------|---------|
| **Draft** | Dashed border, muted text | Not yet reviewed |
| **Provisional** | Solid border, amber accent | Reviewed but not final |
| **Settled** | Solid border, green checkmark | Signed off for this stage |
| **Contested** | Red/amber border, tension icon | Conflicting views present |
| **Stale** | Grey overlay, refresh icon | Upstream changed, needs revisiting |

---

## 6. Accessibility & Trust

### Calm, Non-Overwhelming

- Default view is clean, focused on the deliverable
- Reasoning Tray is collapsible (hidden by default for light users)
- Context Margin can be collapsed
- No autoplay, no pop-ups, no surprise changes

### AI Visibility Without Dominance

- AI suggestions appear in a dedicated panel or tray, not inline until accepted
- The "Draft" button is prominent but not intrusive
- Preflight results appear as proposals in the Smart Feed, not automatic edits

### Inspectable Without Clutter

- Provenance indicators are subtle (small icons, hover states)
- Full trace is one click away but not always visible
- Limitations and caveats appear on demand, not by default
- "Forensic" mode exists for deep inspection, not for everyday use

### GDS Alignment

- Typography, spacing, and colour follow GOV.UK Design System principles
- Crown branding where appropriate
- Accessible contrast ratios, keyboard navigation, screen reader support

---

## 7. Front-End Testbed Implementation

### Approach: UX Laboratory

The "Improve Project UI" project is a **standalone UX laboratory**:
- ✅ No backend dependencies - fully client-side
- ✅ Seeded with realistic mock data (South Cambridgeshire/Cambridge context)
- ✅ Suitable for demos, user testing, and rapid iteration
- ✅ Preserves existing UI sugar (animations, transitions, visual warmth)

### Implementation Stack

| Technology | Purpose | Status |
|------------|---------|--------|
| React 18.3 + Vite 6.4 | Build framework | ✅ Configured |
| Tailwind CSS v4 | Styling | ✅ Configured |
| MapLibre GL + react-map-gl | Interactive maps | ✅ Integrated |
| @dnd-kit/core + sortable | Drag-drop interactions | ✅ Integrated |
| @tiptap/react | Rich text editing | ✅ Integrated |
| sonner | Toast notifications | ✅ Integrated |
| yet-another-react-lightbox | Photo gallery | ✅ Integrated |

### Core Infrastructure Created

#### State Management (`src/lib/appState.tsx`)
- ✅ React Context with useReducer pattern
- ✅ Actions use consistent `{ type, payload }` pattern
- ✅ Tracks: current stage, document state, considerations, reasoning moves, AI state, modals
- ✅ Undo/redo stack (50 levels)
- ✅ Convenience hooks: `useAppState()`, `useAppDispatch()`

#### AI Simulation (`src/lib/aiSimulation.ts`)
- ✅ `simulateDraft()` - streaming text generation with stage-specific responses
- ✅ `simulateGatewayCheck()` - gateway checkpoint analysis
- ✅ `simulateBalance()` - planning balance synthesis
- ✅ `getStageSuggestions()` - context-aware suggestions
- ✅ Configurable delay and chunk size for realistic streaming

#### Mock Data Fixtures (`src/fixtures/`)

| Data Type | File | Status |
|-----------|------|--------|
| CULP Stages | `extendedMockData.ts` | ✅ 10 stages with deliverables, prompts, checklists |
| Evidence Cards | `extendedMockData.ts` | ✅ 8 evidence items with sources, dates, confidence |
| Policies | `extendedMockData.ts` | ✅ PolicyDetail with full text, case refs |
| Site Allocations | `extendedMockData.ts` | ✅ GeoJSON with 4 sites, constraints |
| Constraints | `extendedMockData.ts` | ✅ Green Belt, Flood Zone, Conservation layers |
| Consultee Responses | `extendedMockData.ts` | ✅ 3 statutory/internal responses |
| Site Photos | `extendedMockData.ts` | ✅ 4 photos with metadata |
| Political Framings | `extendedMockData.ts` | ✅ 4 framings (Growth, Protect, Retrofit, Balance) |
| Considerations | `mockData.ts` | ✅ Extended interface with UI aliases |
| Authority Boundary | `extendedMockData.ts` | ✅ Cambridge boundary GeoJSON |

### Components Created

#### Interactive Views

| Component | Location | Features |
|-----------|----------|----------|
| `MapViewInteractive` | `src/components/views/` | MapLibre GL, Carto Voyager tiles, site/constraint layers, popups, layer toggles, drawing tools, export snapshot |
| `DocumentEditor` | `src/components/editor/` | TipTap rich text, formatting toolbar, citation marks, comment threads, AI suggestion panel, droppable for evidence |

#### Layout Components

| Component | Location | Features |
|-----------|----------|----------|
| `ProcessRail` | `src/components/layout/` | CULP stage navigation, phase grouping, status indicators, gateway check simulation, deliverables list |
| `ContextMarginInteractive` | `src/components/layout/` | Draggable evidence cards, photo grid with lightbox, policy panels, consultee responses, search/filter |

#### Reasoning Components

| Component | Location | Features |
|-----------|----------|----------|
| `ReasoningTrayInteractive` | `src/components/` | 8-move progress dots (clickable), sortable considerations (drag-reorder), move completion, trace summary, balance synthesis trigger |

#### Modal System

| Modal | Purpose | Status |
|-------|---------|--------|
| `EvidenceDetailModal` | View evidence with full metadata | ✅ |
| `SiteAssessmentModal` | Site details with constraints, capacity | ✅ |
| `ConsiderationFormModal` | Add/edit consideration with valence/weight | ✅ |
| `ExportDialog` | Export document in multiple formats | ✅ |
| `BalanceSynthesisModal` | AI-generated planning balance | ✅ |
| `ModalManager` | Centralized modal rendering | ✅ |

### Integration Points

| Integration | Location | Status |
|-------------|----------|--------|
| AppStateProvider wrapping | `App.tsx` | ✅ |
| DndContext for drag-drop | `App.tsx` | ✅ |
| ModalManager rendering | `App.tsx` | ✅ |
| Toast notifications (Toaster) | `App.tsx` | ✅ |
| WorkbenchShell wiring | `WorkbenchShell.tsx` | ✅ Draft button, Export button, interactive components |

---

## 8. Implementation Status

### Phase 1: Foundation ✅ COMPLETE

1. **Mock data fixtures** ✅
   - Authority: South Cambridgeshire / Cambridge context
   - Evidence cards: 8 items with sources, dates, confidence levels
   - Policy chips: PolicyDetail with full text, case references
   - Considerations: Extended interface with issue/title, direction/valence aliases
   - Site allocations: 4 GeoJSON sites with capacity, status, constraints
   - CULP stages: 10 stages across 3 phases with deliverables

2. **Reasoning Tray component** ✅
   - Collapsible bottom panel with expand/collapse animation
   - 8-move progress indicator (clickable dots showing complete/in-progress/pending)
   - Considerations ledger with drag-reorder (using @dnd-kit/sortable)
   - Trace summary tab (move events timeline)
   - Add consideration button → opens modal

3. **Provenance indicators** ✅
   - AI/human badges via sparkle icon on AI-generated content
   - Confidence indicators in evidence cards
   - Source attribution on all evidence and policy items

### Phase 2: Interactive Features ✅ COMPLETE

4. **Interactive Map View** ✅
   - MapLibre GL with Carto Voyager tiles
   - Layer toggles: boundary, sites, green belt, flood zone, conservation
   - Click-to-identify popups with site details
   - Drawing tools (point/polygon/buffer) - UI present
   - Export snapshot functionality

5. **Document Editor** ✅
   - TipTap integration with StarterKit, Highlight, Placeholder
   - Formatting toolbar (bold, italic, lists, headings, quotes)
   - Citation marks (highlight selected text)
   - Comment thread support
   - AI suggestion panel with streaming preview
   - Droppable zone for evidence (drag from context margin)

6. **Process Rail** ✅
   - CULP stage navigation with phase grouping
   - Status indicators (complete, in-progress, blocked, pending)
   - Gateway checkpoint simulation
   - Deliverables list per stage
   - Mark complete / Reset demo buttons

7. **Context Margin** ✅
   - Evidence cards with draggable handles (using @dnd-kit)
   - Photo grid with lightbox (yet-another-react-lightbox)
   - Policy expansion panels with cite button
   - Consultee response cards
   - Search and category filter

### Phase 3: AI Simulation & Modals ✅ COMPLETE

8. **AI Simulation** ✅
   - Streaming draft generation with stage-specific content
   - Gateway check simulation with gaps, strengths, inspector questions
   - Balance synthesis with for/against considerations
   - Configurable delays for realistic demo feel

9. **Modal System** ✅
   - Evidence detail sheet
   - Site assessment modal
   - Consideration form (add with title, valence, weight)
   - Export dialog (multiple formats)
   - Balance synthesis modal with framing selector

10. **State Management** ✅
    - Global AppState with React Context + useReducer
    - Consistent action payload pattern
    - Undo/redo support (50 levels)
    - Toast notifications via sonner

### Remaining Work (Future Phases)

| Feature | Priority | Notes |
|---------|----------|-------|
| Trace Canvas overlay | Medium | 3D/2D graph visualization of reasoning chain |
| Settled/provisional visual states | Medium | State indicators with animations |
| Stale detection | Low | Visual cue when upstream changes |
| Inline "Why is this here?" | Medium | Click handler opening trace panel |
| BubbleMenu for text selection | Low | Requires @tiptap/extension-bubble-menu |
| Accessibility audit | High | Keyboard navigation, screen reader labels |
| Mobile responsiveness | Low | Planner tool is desktop-focused |

### Build Status

```
✓ TypeScript: No errors
✓ Vite build: 580KB bundle (1.03s)
✓ Dev server: Running on port 3001
```

### File Structure Created

```
src/
├── lib/
│   ├── appState.tsx          # Global state management
│   └── aiSimulation.ts       # AI response simulation
├── fixtures/
│   ├── mockData.ts           # Core types and base data
│   └── extendedMockData.ts   # CULP stages, GeoJSON, photos
├── components/
│   ├── views/
│   │   └── MapViewInteractive.tsx
│   ├── editor/
│   │   └── DocumentEditor.tsx
│   ├── layout/
│   │   ├── ProcessRail.tsx
│   │   └── ContextMarginInteractive.tsx
│   ├── modals/
│   │   └── ModalDialogs.tsx
│   └── ReasoningTrayInteractive.tsx
└── App.tsx                   # Provider wiring
```

---

## Appendix: Planner Vocabulary

| Term | Meaning |
|------|---------|
| **Deliverable** | The document/artefact being produced (plan chapter, officer report, policy) |
| **Consideration** | A discrete point that is material to the decision |
| **Framing** | The political/strategic lens through which options are assessed |
| **Balance** | The weighing of considerations to reach a position |
| **Position** | The conditional recommendation under a specific framing |
| **Trace** | The chain of evidence, reasoning, and decisions that led to an output |
| **Settled** | A claim or position that has been reviewed and accepted |
| **Provisional** | A claim or position that is working but not final |
| **Contested** | A point where there are conflicting views or evidence |

---

## Appendix: Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.3.1 | UI framework |
| vite | 6.4.1 | Build tool |
| tailwindcss | 4.x | Styling |
| maplibre-gl | ^5.5.0 | Map rendering |
| react-map-gl | ^8.1.0 | React wrapper for MapLibre |
| @dnd-kit/core | ^6.3.1 | Drag-drop core |
| @dnd-kit/sortable | ^10.0.0 | Sortable lists |
| @tiptap/react | ^3.14.0 | Rich text editor |
| sonner | ^2.0.3 | Toast notifications |
| yet-another-react-lightbox | ^3.26.2 | Photo lightbox |
| lucide-react | ^0.511.0 | Icons |

---

*Last updated: December 2024. This testbed prioritises judgement quality and confidence over speed. It treats planners as professionals who work with ambiguity, not consumers who want magic answers.*
