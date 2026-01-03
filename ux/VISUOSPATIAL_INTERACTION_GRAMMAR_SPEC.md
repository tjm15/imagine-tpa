# Visuospatial Interaction Grammar — UI Behaviour Spec (#2)
> v1 target: implementable in `demo_ui` and verifiable via screenshots (Given/When/Then).

## 0) Purpose (planner framing)
Visuospatial work is not a “map tab”. It is the **plan ↔ reality surface** where allocations, constraints, and assumptions become inspectable.

This spec defines the non‑negotiable, map‑first interaction grammar that keeps the UI planner‑grade and contestable.

## 1) Map-first surfaces (v1)
In v1, the primary map surface is `Map & Plans` and the secondary map surface is the right sidebar `Map` panel.

### 1.1 Layer toggles are explicit and stable
- Boundary, Sites, Green Belt, Flood Zones, Conservation Areas are independently toggleable.
- Layer toggles do not reflow the rest of the UI; they only change map overlays.

### 1.2 Cross-highlighting (map ↔ list)
- Selecting a site in the Candidate Sites list focuses the map and highlights that site.
- Selecting a site on the map updates the popup and marks it as selected in the list.

### 1.3 Spatial “Why?”
- Any spatial feature with accountability requirements exposes a `Why?` affordance that opens Trace Overlay anchored to that feature.

### 1.4 Highlight vs adjustment semantics (v1)
- **Highlight** = temporary focus (blue outline).
- **Adjusted** = plan-state change marker (amber outline).

These are distinct. Highlight can be cleared; adjustment persists until undone/reverted.

### 1.5 Patch-bundle → map choreography
- A patch item of type `allocation_geometry` must provide a `Show on map` affordance.
- Clicking `Show on map` highlights the site (blue outline).
- If not currently in `Map & Plans`, the right sidebar `Map` panel opens to show the highlight without forcing navigation.

## 2) Acceptance tests (Given/When/Then)

### Scenario: Site list selection focuses the map
Given I am in `Map & Plans`
When I click a Candidate Site list item (e.g., “Northern Fringe”)
Then the map zoom/extent updates to the site area
And the site polygon is visually emphasized

### Scenario: Map click produces a contestable identification
Given I am in `Map & Plans`
When I click a site polygon
Then a popup shows site reference, capacity, and status
And a “Trace selection” or equivalent control is available

### Scenario: Adjustment marker is visible
Given a patch bundle has been applied that affects `SHLAA/045`
When I view `Map & Plans`
Then the adjusted site renders with the “Adjusted” outline styling

### Scenario: Highlight is invoked from a patch review
Given I am reviewing a patch bundle item of type `allocation_geometry`
When I click `Show on map`
Then the map highlights the referenced site boundary (blue outline)
And a toast confirms “Highlighted on map: {site_id}”

### Scenario: “Why?” for a spatial item opens trace
Given a spatial item is highlighted/selected
When I click its `Why?` affordance
Then Trace Overlay opens and the header identifies the site (site id + label)

