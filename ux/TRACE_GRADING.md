# Progressive Traceability Grading

To satisfy the requirement of "beautiful for juniors, forensic for inspectors", we define three tiers of traceability UI.

## Level 1: Inline Hints (The "Magic" Layer)
**Audience**: Junior Planners, Quick Review
**Visual**: Subtle underlines or margin icons next to AI-generated text.
**Interaction**: Hover to glimpse the source.
**Content**: "Verified against 3 documents", "Consistent with Policy P3".

## Level 2: Evidence Cards (The "Working" Layer)
**Audience**: Standard Planners
**Visual**: Expandable cards below paragraphs or in a side panel.
**Interaction**: Click "Review Evidence".
**Content**:
-   **Policy Atom**: The exact text of the policy clause.
-   **Map Snippet**: A small static map showing the constraint.
-   **Quote**: The relevant excerpt from the inspection report.

## Level 3: The Trace Graph (The "Forensic" Layer)
**Audience**: Senior Planners, Inspectors, Legal Challenge
**Visual**: A node-link diagram (ReactFlow) covering the full screen.
**Interaction**: Deep dive into the decision history.
**Content**:
-   **MoveEvent Nodes**: "Issue Surfacing (Move 2)".
-   **Edges**: "Derived From", "Contradicts", "Supports".
-   **Raw Source**: Clicking a node opens the original PDF at the exact line number or the raw GIS attribute table.
