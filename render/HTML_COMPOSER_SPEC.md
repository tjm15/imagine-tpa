# HTML Composer Specification

## Core Capability
The system generates **Static HTML5** outputs. 
1.  **Single Doc**: Officer Reports / Justification Statements.
2.  **Full Site**: The "Digital Local Plan" website.

## 1. Digital Local Plan (Static Site Export)
The system treats the Local Plan workspace as a Content Management System (CMS) and exports a full static website (e.g., utilizing a mechanism like Hugo/11ty).

*   **Structure**: 
    *   `index.html`: The Plan Landing Page.
    *   `/policies/`: Individual HTML page for *every* policy (e.g., `/policies/h1-housing`).
    *   `/map/`: Interactive Policies Map (Leaflet.js/MapLibre) linking back to policy pages.
*   **Accessibility**:
    *   Strict adherence to **WCAG 2.2 AA**.
    *   Semantic HTML (`<article>`, `<nav>`, `<aside>`).
    *   No "Click here" links (descriptive link text).
*   **Machine Readability**:
    *   Every policy page includes invisible Schema.org metadata or JSON-LD representing the policy constraints.

## 2. Document Rendering (Officer Reports)
*   **Format**: Single-page HTML (Print-friendly CSS).
*   **Style**: GOV.UK Design System (GDS) clone.
    *   Clear typography (GDS Transport).
    *   Simple tables.
    *   Warning callouts for "Departures from Policy".

## 3. Technology Stack
*   **Engine**: Jinja2 (Python) for server-side template rendering.
*   **CSS**: Tachyons or Tailwind (Utility-first) for lightweight styling.
*   **Interactivity**: Progressive enhancement only. The content must work without JS.

