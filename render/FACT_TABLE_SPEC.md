# Fact Table Specification
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.


## Principle
Rendering is deterministic. It reads from "Fact Tables", not raw text.

## Structure
* A Fact Table is a JSON array of objects.
* Each object has a `_provenance` field containing `EvidenceRef`s for every cell.

## Usage
* Agents produce `FigureSpec` (Chart def).
* `FigureSpec` references `FactTable`.
* Renderer joins them => SVG/PNG.
