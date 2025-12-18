# Dashboard Information Architecture (DCO Edition)

## Core Principle
The dashboard is a **Digital Case Officer**. It functions like a familiar document editor ("Smart Word") where the primary focus is always the deliverable.

## Global Layout (The 70/30 Split)

### 1. The Workspace (70% - Left)
*   **The Living Document**:
    *   This is the singular focus. It displays the active artefact (e.g., *Officer Report*, *Local Plan Chapter 4*).
    *   **WYSIWYG**: It looks exactly like the PDF that will be published.
    *   **Capabilities**: Rich text editing, inline images, tables.
    *   **Ghost Text**: AI suggestions appear as grey "ghost" text inline.

### 2. The Context Sidebar (30% - Right)
*   **Smart Feed**:
    *   Dynamic cards that change based on what paragraph is active in the document.
    *   *Example*: If cursor is in "Highways", show "Local Plan Policy T1" and "Transport Assessment Key Data".
*   **Evidence Shelf**:
    *   Draggable facts/citations. "Drag this 5YHLS figure into your report".
*   **Map Reference**:
    *   A mini-map card appearing at the top of the sidebar. Expandable if needed, but not the primary distinct view.

### 2. Strategic Home (CULP)
*   **The Dependency Chart (Main View)**:
    *   **Visual**: A horizontal Gantt/Dependency graph spanning the 30-month CULP timeline.
    *   **Nodes**: Represent Evidence (e.g., "Flood Risk Assessment") or Gateways (e.g., "Reg 18 Consultation").
    *   **Edges**: Show blocking relationships (e.g., "Housing Numbers" blocks "Green Belt Review").
    *   **Status Colors**: Green (Complete), Amber (In Progress), Red (Blocked/Late), Grey (Future).
*   **Monitoring Dashboard (AMR Tab)**:
    *   **Visual**: Key Performance Indicators (KPIs) for the existing plan.
    *   **Metrics**: Housing Delivery (5YHLS), S106/CIL Contributions collected, Affordable Housing %.
    *   **Data Source**: Live link to the *Ledger*.
*   **Action Plan (Sidebar)**:
    *   **"Next Steps"**: An ordered list of immediate tasks based on the critical path (e.g., "Commission Transport Study", "Finalize Site Options").
    *   **Interaction**: Clicking a task opens the relevant Document in the **Digital Case Officer** view.

### 3. Casework Home (DM)
*   **The Inbox (Main View)**:
    *   **Style**: Outlook / Email Client interface.
    *   **Columns**: "New", "Validating", "Consultation", "Determination", "Issued".
    *   **Cards**: Each application is a card showing: Ref No, Site Address, Days Remaining (Statutory Deadline).
    *   **Alerts**: "Red Dot" badges for applications requiring urgent attention (e.g., "Expiring in 2 days").
*   **Application Workspace**:
    *   Clicking a card opens the **Digital Case Officer** view for that specific application.

### 3. View Switcher (The "Mode" Toggle)
*   **Document Mode**: (Default) The writing environment.
*   **Map Mode**: replaces the Document pane with the **Map Canvas**.
    *   *Metaphor*: Google Maps.
    *   *Tools*: Simple "Marker" and "Lasso".
    *   *Sidebar*: Shows "Map Layers" (Themes) instead of Smart Feed.
*   **Judgement Mode**: replaces the Document pane with the **Infographic Sheet**.
    *   *Metaphor*: Tabbed Dashboard (Non-editable).
    *   *Feature*: Tabs = Scenarios. Visualizes the logic chain for comparison (e.g., Option A vs B). Reviewers use this to "Sign Off" on the reasoning.
*   **Reality Mode**:
    *   *Metaphor*: Augmented Reality View.
    *   *Feature*: Projects plan vectors (wireframes) onto site photos/street view ("Slice B").

### 4. Navigation (Minimalist Header)
*   **Project Breadcrumbs**: `Projects > TPA/2024/001 > Officer Report`.
*   **Stage Indicator**: Simple status pill ("Drafting", "Review", "Published").
*   **No complex "Tree Views"**: File navigation is handled via a simple "Open File" modal or dropdown, not a persistent IDE sidebar.

## Interaction Rules
*   **Point and Click**: Primary interaction model. Buttons for "Insert", "Draft", "Review".
*   **Draw to Ask**: In Map Mode, drawing a shape triggers an AI query ("What is here?").
*   **Snapshot**: Map views are always one click away from being an image in the Document.
*   **Nudges**: The system communicates via "Comment Bubbles" in the margin (like Word Comments) or "Gold Underlines" (Reasoning Gaps).
*   **Drag & Drop**: Evidence -> Document.

## Mobile/Tablet Friendly
*   The simplified layout allows usage on iPads for site visits (referencing the map/doc split).
