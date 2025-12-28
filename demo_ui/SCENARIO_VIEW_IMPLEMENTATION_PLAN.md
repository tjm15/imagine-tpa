# Scenario Modelling View - Implementation Plan

This plan transforms the current `JudgementView` (Scenarios) into a richer, site-allocation-focused spatial strategy modelling experience, aligned with the reference design from the TPA AI Studio prototype.

---

## Reference Design Analysis

The target UI consists of:

1. **Strategic Scenarios Bar** (top)
   - Horizontal row of scenario cards (e.g., Transit-Oriented Innovation, Heritage-Led Infill, Strategic Urban Extensions)
   - Each card shows: title, short description, site count, total unit capacity
   - Selected card has accent border/highlight
   - "Create Strategy" button to add new scenarios

2. **Two-Column Layout** (main area)
   - **Left Column**: Spatial Strategy Map + Plan Narrative
   - **Right Column**: Allocated Sites list with expandable detail cards

3. **Spatial Strategy Map** (left, ~60% width)
   - Interactive MapLibre map showing allocated vs omitted sites
   - Site markers with tooltips (name, land type, unit count)
   - Legend: Allocated / Omitted distinction
   - Zoom controls

4. **Plan Narrative** (below map, left column)
   - AI-generated narrative summarizing the scenario
   - Bordered card with accent left-border

5. **Allocated Sites Panel** (right column)
   - Header: "Allocated Sites" badge with count + "Total Capacity: X units"
   - Expandable site cards, each containing:
     - **Header**: Site name + unit count badge + land type tag (Brownfield/Greenfield/Urban Extension)
     - **AI Summary**: Short AI-generated description
     - **SAAD Indicators**: Suitability, Availability, Achievability, Deliverability status chips (green/amber/red)
     - **Accessibility & Sustainability scores**: progress bars + numeric score
     - **Key Constraints**: clickable chips that expand to show "Implications & Mitigation" panel
     - **View Inspector's Trace**: button to open trace overlay

---

## Step-by-Step Implementation

### Phase 1: Data Model & Fixtures

| Step | Description | Files |
|------|-------------|-------|
| 1.1 | Extend `siteAllocations` in `extendedMockData.ts` to include richer properties: `landType`, `aiSummary`, `saad` (Suitability/Availability/Achievability/Deliverability), `accessibilityScore`, `sustainabilityScore`, `constraints` (array with `{id, name, implications, mitigation}`). | `src/fixtures/extendedMockData.ts` |
| 1.2 | Create `strategicScenarios` fixture: array of scenario objects with `id`, `name`, `description`, `siteIds[]`, `totalCapacity`, `narrative`. | `src/fixtures/extendedMockData.ts` |
| 1.3 | Add helper functions: `getSitesForScenario(scenarioId)`, `getScenarioById(id)`. | `src/fixtures/extendedMockData.ts` |

### Phase 2: Component Structure

| Step | Description | Files |
|------|-------------|-------|
| 2.1 | Create `ScenarioCard` component: displays a single scenario in the top bar (title, description, site count, capacity). Accepts `selected` prop for highlight styling. | `src/components/scenarios/ScenarioCard.tsx` |
| 2.2 | Create `ScenarioBar` component: horizontal row of `ScenarioCard` + "Create Strategy" button. Manages selection state. | `src/components/scenarios/ScenarioBar.tsx` |
| 2.3 | Create `SiteAllocationCard` component: expandable card showing site details, SAAD indicators, constraints chips, scores. | `src/components/scenarios/SiteAllocationCard.tsx` |
| 2.4 | Create `ConstraintChip` component: clickable chip that expands to show "Implications & Mitigation" popover/inline panel. | `src/components/scenarios/ConstraintChip.tsx` |
| 2.5 | Create `SAADIndicator` component: small status chip with color (green/amber/red) + label. | `src/components/scenarios/SAADIndicator.tsx` |
| 2.6 | Create `ScoreBar` component: horizontal progress bar with icon + label + numeric score. | `src/components/scenarios/ScoreBar.tsx` |
| 2.7 | Create `PlanNarrative` component: bordered card with accent left-border displaying AI narrative. | `src/components/scenarios/PlanNarrative.tsx` |
| 2.8 | Create `AllocatedSitesPanel` component: scrollable list of `SiteAllocationCard` with header showing count + total capacity. | `src/components/scenarios/AllocatedSitesPanel.tsx` |

### Phase 3: Map Integration

| Step | Description | Files |
|------|-------------|-------|
| 3.1 | Extend `MapViewInteractive` to accept `scenarioId` prop and filter site markers based on scenario allocation. | `src/components/views/MapViewInteractive.tsx` |
| 3.2 | Add site marker layer with popup tooltips (site name, land type, units). Distinguish allocated (solid) vs omitted (hollow/grey) markers. | `src/components/views/MapViewInteractive.tsx` |
| 3.3 | Add click handler to select a site, syncing with `AllocatedSitesPanel` scroll/expansion. | `src/components/views/MapViewInteractive.tsx` |

### Phase 4: Refactor JudgementView → ScenarioModellingView

| Step | Description | Files |
|------|-------------|-------|
| 4.1 | Rename/replace `JudgementView` with `ScenarioModellingView` for plan workspace. Keep existing casework logic as a branch or separate component. | `src/components/views/ScenarioModellingView.tsx` |
| 4.2 | Compose the new view: `ScenarioBar` at top, two-column layout below (Map + Narrative left, Sites right). | `src/components/views/ScenarioModellingView.tsx` |
| 4.3 | Wire scenario selection: changing scenario updates map markers + sites list + narrative. | `src/components/views/ScenarioModellingView.tsx` |
| 4.4 | Update `WorkbenchShell` to render `ScenarioModellingView` for the "Scenarios" tab when in plan workspace. | `src/components/WorkbenchShell.tsx` |

### Phase 5: State & Interaction

| Step | Description | Files |
|------|-------------|-------|
| 5.1 | Add `selectedScenarioId` to component state (local) or global app state. | `src/components/views/ScenarioModellingView.tsx` or `src/lib/appState.tsx` |
| 5.2 | Add `expandedSiteId` state for accordion behavior in sites list. | `src/components/scenarios/AllocatedSitesPanel.tsx` |
| 5.3 | Add `expandedConstraintId` state for constraint detail popover. | `src/components/scenarios/SiteAllocationCard.tsx` |
| 5.4 | Wire "View Inspector's Trace" to `onOpenTrace` prop. | `src/components/scenarios/SiteAllocationCard.tsx` |

### Phase 6: Styling & Polish

| Step | Description | Files |
|------|-------------|-------|
| 6.1 | Apply consistent padding/margins across new components (align with existing design system: 4px grid, `px-4 py-3` rhythm). | All new components |
| 6.2 | Use existing color tokens: `--color-accent`, `--color-brand`, semantic status colors (emerald for green, amber for caution, red for issues). | All new components |
| 6.3 | Ensure responsive behavior: stack columns on narrow viewports. | `src/components/views/ScenarioModellingView.tsx` |
| 6.4 | Add loading/skeleton states for AI-generated content (narrative, summaries). | Various |

### Phase 7: Testing & Screenshots

| Step | Description | Files |
|------|-------------|-------|
| 7.1 | Add Playwright test for scenario modelling flow: select scenario → verify map + sites + narrative update. | `tests/scenario-modelling.spec.ts` |
| 7.2 | Capture screenshots: scenario bar, expanded site card, constraint popover. | `tests/scenario-modelling.spec.ts` |
| 7.3 | Manual QA: verify all interactions, check for whitespace/alignment issues. | — |

---

## File Summary

| New Files | Purpose |
|-----------|---------|
| `src/components/scenarios/ScenarioCard.tsx` | Individual scenario card in top bar |
| `src/components/scenarios/ScenarioBar.tsx` | Horizontal scenario selector |
| `src/components/scenarios/SiteAllocationCard.tsx` | Expandable site detail card |
| `src/components/scenarios/ConstraintChip.tsx` | Clickable constraint with popover |
| `src/components/scenarios/SAADIndicator.tsx` | Status indicator chip |
| `src/components/scenarios/ScoreBar.tsx` | Score progress bar |
| `src/components/scenarios/PlanNarrative.tsx` | AI narrative card |
| `src/components/scenarios/AllocatedSitesPanel.tsx` | Sites list container |
| `src/components/views/ScenarioModellingView.tsx` | Main composed view |
| `tests/scenario-modelling.spec.ts` | E2E test |

| Modified Files | Changes |
|----------------|---------|
| `src/fixtures/extendedMockData.ts` | Extended site data + scenarios fixture |
| `src/components/WorkbenchShell.tsx` | Swap JudgementView for ScenarioModellingView |
| `src/components/views/MapViewInteractive.tsx` | Scenario-aware site markers |

---

## Estimated Effort

| Phase | Complexity | Estimate |
|-------|------------|----------|
| Phase 1: Data Model | Low | 1 hour |
| Phase 2: Components | Medium | 3-4 hours |
| Phase 3: Map Integration | Medium | 2 hours |
| Phase 4: View Composition | Medium | 2 hours |
| Phase 5: State & Interaction | Low-Medium | 1-2 hours |
| Phase 6: Styling | Low | 1-2 hours |
| Phase 7: Testing | Low | 1 hour |

**Total: ~12-14 hours**

---

## Questions / Decisions Needed

1. **Create Strategy button**: Should this open a modal/wizard, or just add a placeholder scenario?
2. **Narrative generation**: Use static mock text, or wire to AI simulation endpoint?
3. **Constraint detail panel**: Inline expansion (like screenshot 2) or popover/modal?
4. **Map base tiles**: Keep existing MapLibre OSM tiles or switch to a cleaner/lighter style?
5. **SAAD scoring logic**: Where do these values come from? Static fixture or derived from constraint analysis?

---

## Next Steps

1. Review and approve this plan
2. Begin Phase 1: extend fixtures with richer site/scenario data
3. Create component scaffolds (Phase 2) in parallel
4. Integrate and test incrementally

Let me know if you'd like me to start implementing any phase!
