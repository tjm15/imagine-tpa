# CULP Artefacts (Stage Gating) Specification


CULP stages in `culp/PROCESS_MODEL.yaml` declare **required artefacts**. These are hard requirements: the dashboard must treat them as first-class deliverables, not as optional outputs.

This spec makes that implementable by defining:
1. a canonical artefact registry (what each artefact is),
2. a per-project artefact ledger (what exists, what’s missing),
3. how the UI uses both to drive the Strategic Home timeline and stage gate panel.

## 1) Artefact registry (the catalogue)
Registry file:
* `culp/ARTEFACT_REGISTRY.yaml`

Rules:
* Every string listed in `culp/PROCESS_MODEL.yaml:stages[].required_artefacts[]` MUST appear in the registry as `artefact_key`.
* Registry entries define how artefacts are stored and surfaced (authored document vs map overlay vs dataset/bundle).

## 1.1 Alignment outputs (primary deliverables)
Alignment outputs in `culp/ALIGNMENT_OUTPUTS_2025_11.yaml` are a primary deliverable set
and must be surfaced alongside stage gating. These outputs map GOV.UK and Planning Data
hooks to artefacts and validators, and should be treated as “what the plan must publish”
in addition to “what each stage requires.”

## 2) Artefact ledger (per plan project)
Each `PlanProject` maintains a ledger of artefacts per stage.

Canonical record:
* `schemas/CulpArtefactRecord.schema.json`

Persistence contract:
* `culp_artefacts` table in `db/DDL_CONTRACT.md`

The ledger is what allows the dashboard to show:
* what is missing (blocking),
* what is draft/in review/published,
* what evidence/run/tool output supports it (traceability),
* and what changed since last publish (diff/snapshot integration).

## 3) UI behaviour (Strategic Home + stage gate panel)
The UI uses:
* `culp/PROCESS_MODEL.yaml` for stage ordering and the list of required artefacts
* `culp/ARTEFACT_REGISTRY.yaml` to interpret each artefact key (type, format, publish target)
* the project ledger (`culp_artefacts`) to render status and links

Required affordances:
* Stage gate panel shows required artefacts with status pills.
* Clicking an artefact opens the relevant surface:
  - authored documents → Living Document
  - map overlays/geometries → Map Mode
  - bundles/datasets → Evidence view with provenance + download controls
* “Create” buttons are contextual:
  - drafts open templates in the Living Document
  - map artefacts open Map Mode with guided steps (draw/export/snapshot)

## 4) Interaction with agents
Agents can propose drafts, figures, maps, and schedules, but:
* every output must be linked to an artefact ledger entry,
* every suggestion must be auditable (`AuditEvent`),
* and every evidence-generating action must be logged (`ToolRun`).

This keeps CULP requirements satisfied without collapsing into a rigid workflow engine.
