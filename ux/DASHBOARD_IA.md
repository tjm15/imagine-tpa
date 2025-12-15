# Dashboard Information Architecture

## Core Principle
The dashboard is a **Process Navigator**, not a "Cockpit". It guides the user through the linear CULP stages defined in `PROCESS_MODEL.yaml`.

## Navigation Structure

### 1. Global Navigation (Sidebar/Top)
* **Project Switcher** (if multi-project)
* **Stage Timeline** (Vertical list of CULP stages)
    * Status Indicators: Locked, In Progress, Ready for Review, Published.

### 2. Stage View (Main Content)
* **Stage Header**: Title, description, GOV.UK guidance link.
* **Artefact Checklist**: List of required items for this stage.
* **Work Area**:
    * **Tabs**: "Judgement Sheets" (Trajectories).
    * Comparison is done by flipping tabs, not side-by-side.

### 3. Sheet View (Within a Tab)
* **Header**: Framing Summary & Goal.
* **Body**: Infographic layout (Issues -> Evidence -> Balance -> Position).
* **Footer**: Uncertainty & Metadata.

## Rules
* No "Drill Down" into infinite data pits. Click-through on charts opens the "Evidence Card" modal, not raw database tables.
* No "Edit" buttons on the sheet. Editing happens via "Negotiation Moves" in a separate action panel.
