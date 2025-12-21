# Knowledge Graph Schema

## Node Types
* `Document`, `Page`, `Chunk`
* `Policy`, `PolicyClause`, `PolicyMapZone`
* `Site`, `Area`
* `VisualAsset`, `VisualFeature`, `SegmentationMask`
* `Scope`
* `StandardMatrix`
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
* `CITES`: Chunk -> PolicyClause
* `APPLIES_IN`: PolicyClause -> PolicyMapZone
* `MENTIONS`: Chunk -> Site
* `INTERSECTS`: Site -> SpatialFeature
* `HAS_VISUAL_EVIDENCE`: Site -> VisualAsset
* `SUPPORTED_BY`: Policy -> JustificationBlock
* `ENFORCES`: Policy -> StandardMatrix
* `HAS_VISUAL_CONSTRAINT`: Policy -> VisualConstraint
* `ILLUSTRATED_BY`: Policy -> DesignExemplar
* `IMPLEMENTS`: Policy -> ConformityHook
* `APPLIES_IN`: Policy -> Scope
* `DEFINED_BY`: Scope -> DesignationInstance
* `INSTANCE_OF`: DesignationInstance -> DesignationType
* `REPRESENTED_BY`: DesignationInstance -> GeoLayerRef
* `VISUALISED_ON`: SpatialStrategyElement -> VisualAsset
* `BOUNDED_BY`: AllocationSite -> SpatialFeature
* `GOVERNED_BY`: AllocationSite -> Policy
* `REQUIRES`: AllocationSite -> InfrastructureItem
* `OVERLAPS`: AllocationSite -> DesignationInstance
* `REGISTERED_TO`: VisualAsset -> Transform
* `DERIVES_OVERLAY`: Transform -> ProjectionArtifact
* `HAS_MASK`: VisualAsset -> SegmentationMask
* `IN_FRAME`: VisualAsset -> Frame
* `EVIDENCE_FOR`: EvidenceRef -> Interpretation
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
* `BASELINED_AT`: Policy/Area -> AdoptionBaseline (Monitoring)

## Geographical Linkages (Enrichment)
These edges are *pre-calculated* during ingestion by the Spatial Processor.
*   `CONTAINS`: Area A -> Area B (Topology: B is inside A).
*   `ADJACENT_TO`: Site -> Site (Topology: Shares boundary).
*   `NEAR`: Site -> Feature (Topology: Within X meters).
*   `CONNECTED_TO`: Site -> TransportNode (Network analysis).
*   `VISUALLY_AFFECTS`: VisualAsset -> Site (Viewshed analysis).
