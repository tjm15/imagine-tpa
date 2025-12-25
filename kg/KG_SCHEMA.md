# Knowledge Graph Schema


The KG is a **join fabric** for planner-legible objects. Canonical truth lives in the relational
tables (e.g., `policy_clauses.conditions_jsonb`, `policy_clause_mentions`). The KG materializes only
stable, planner-meaningful nodes and explicit links. Derived nodes are allowed, but must be rebuildable
from canonical fields and always carry provenance.

## Canonical vs Derived
* **Canonical**: PolicySection, PolicyClause, PolicyMatrix, PolicyScope, VisualAsset, Site, DesignationInstance.
* **Derived (optional)**: ClauseQualifier (from `policy_clauses.conditions_jsonb`), GroundedReference
  (from `policy_clause_mentions` where `resolved_entity_id` is present), PolicyMapZone (if produced by
  map interpretation).

## Canonical metadata (not KG nodes)
These stay in canonical tables and are not represented as KG nodes unless explicitly required later:
* Document identity/status/weight classification (`document_identity_status`).

## Node Types
* `Document`, `Page`, `Chunk`
* `PolicySection`, `PolicyClause`, `PolicyDefinition`, `PolicyTarget`, `PolicyMonitoringHook`
* `PolicyMapZone` (derived)
* `Site`, `Area`, `SpatialFeature`
* `VisualAsset`, `VisualFeature`, `SegmentationMask`
* `PolicyScope`, `PolicyMatrix`
* `VisualConstraint`
* `DesignExemplar`
* `GeoLayerRef`
* `DesignationType`
* `DesignationInstance`
* `SpatialStrategyElement`
* `AllocationSite`
* `AllocationRequirement`
* `AllocationConstraint`
* `InfrastructureItem`
* `Target`
* `MonitoringIndicator`
* `ConformityHook`
* `Frame`, `Transform`, `ControlPoint`, `ProjectionArtifact`
* `EvidenceRef`
* `ClauseQualifier` (derived)
* `GroundedReference` (derived)
* `MoveEvent`, `Assumption`, `Issue`
* `Interpretation`, `ConsiderationLedgerEntry`, `Trajectory`
* `Application` (DM)
* `ConsultationResponse` (DM)
* `Condition` (DM)
* `Decision` (DM)
* `MonitoringEvent` (Monitoring)
* `MonitoringMetric` (Monitoring)
* `AdoptionBaseline` (Monitoring)

## Edge Types
* `CITES`: PolicyClause -> PolicyClause (explicit cross-refs)
* `CITES`: Chunk -> PolicyClause (evidence linkage)
* `MENTIONS`: PolicyClause -> DesignationInstance/Site/Area (only when mention is resolved)
* `INTERSECTS`: Site -> SpatialFeature
* `HAS_VISUAL_EVIDENCE`: Site -> VisualAsset
* `SUPPORTED_BY`: PolicySection -> Chunk (justification/explanatory text)
* `ENFORCES`: PolicySection -> PolicyMatrix
* `HAS_VISUAL_CONSTRAINT`: PolicySection -> VisualConstraint
* `ILLUSTRATED_BY`: PolicySection -> DesignExemplar
* `IMPLEMENTS`: PolicySection -> ConformityHook
* `APPLIES_IN`: PolicySection -> PolicyScope
* `DEFINED_BY`: PolicyScope -> DesignationInstance
* `CONTAINS_MATRIX`: PolicySection -> PolicyMatrix
* `DEFINES_SCOPE`: PolicySection -> PolicyScope
* `HAS_DEFINITION`: PolicyClause -> PolicyDefinition
* `HAS_TARGET`: PolicyClause -> PolicyTarget
* `HAS_MONITORING_HOOK`: PolicyClause -> PolicyMonitoringHook
* `HAS_QUALIFIER`: PolicyClause -> ClauseQualifier (derived)
* `INSTANCE_OF`: DesignationInstance -> DesignationType
* `REPRESENTED_BY`: DesignationInstance -> GeoLayerRef
* `VISUALISED_ON`: SpatialStrategyElement -> VisualAsset
* `BOUNDED_BY`: AllocationSite -> SpatialFeature
* `GOVERNED_BY`: AllocationSite -> PolicySection
* `REQUIRES`: AllocationSite -> InfrastructureItem
* `OVERLAPS`: AllocationSite -> DesignationInstance
* `REGISTERED_TO`: VisualAsset -> Transform
* `DERIVES_OVERLAY`: Transform -> ProjectionArtifact
* `HAS_MASK`: VisualAsset -> SegmentationMask
* `IN_FRAME`: VisualAsset -> Frame
* `EVIDENCE_FOR`: EvidenceRef -> any derived node
* `SUPPORTS`: Interpretation -> ConsiderationLedgerEntry
* `CONTRADICTS`: Interpretation -> ConsiderationLedgerEntry
* `PART_OF_MOVE`: * -> MoveEvent
* `RELIES_ON`: Application -> Document (DM)
* `OBJECTS_TO` / `SUPPORTS`: ConsultationResponse -> Application (DM)
* `MITIGATES`: Condition -> Issue (DM)
* `BREACHES`: Application -> PolicyClause (DM)
* `HAS_DECISION`: Application -> Decision (DM)
* `HAS_MONITORING_EVENT`: Area/Site/PolicyClause -> MonitoringEvent (Monitoring)
* `MEASURED_BY`: PolicyClause/Site/Area -> MonitoringMetric (Monitoring)
* `BASELINED_AT`: PolicySection/Area -> AdoptionBaseline (Monitoring)

## Geographical Linkages (Enrichment)
These edges are *pre-calculated* during ingestion by the Spatial Processor.
*   `CONTAINS`: Area A -> Area B (Topology: B is inside A).
*   `ADJACENT_TO`: Site -> Site (Topology: Shares boundary).
*   `NEAR`: Site -> Feature (Topology: Within X meters).
*   `CONNECTED_TO`: Site -> TransportNode (Network analysis).
*   `VISUALLY_AFFECTS`: VisualAsset -> Site (Viewshed analysis).
