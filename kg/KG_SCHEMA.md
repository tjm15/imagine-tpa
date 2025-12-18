# Knowledge Graph Schema

## Node Types
* `Document`, `Page`, `Chunk`
* `Policy`, `PolicyClause`, `PolicyMapZone`
* `Site`, `Area`
* `VisualAsset`, `VisualFeature`
* `MoveEvent`, `Assumption`, `Issue`
* `Interpretation`, `Consideration`, `Trajectoy`
* `Application` (DM)
* `ConsultationResponse` (DM)
* `Condition` (DM)

## Edge Types
* `CITES`: Chunk -> PolicyClause
* `APPLIES_IN`: PolicyClause -> PolicyMapZone
* `MENTIONS`: Chunk -> Site
* `INTERSECTS`: Site -> SpatialFeature
* `HAS_VISUAL_EVIDENCE`: Site -> VisualAsset
* `REGISTERED_TO`: VisualAsset -> Transform
* `EVIDENCE_FOR`: EvidenceRef -> Interpretation
* `SUPPORTS`: Interpretation -> Consideration
* `CONTRADICTS`: Interpretation -> Consideration
* `PART_OF_MOVE`: * -> MoveEvent
* `RELIES_ON`: Application -> Document (DM)
* `OBJECTS_TO` / `SUPPORTS`: ConsultationResponse -> Application (DM)
* `MITIGATES`: Condition -> Issue (DM)
* `BREACHES`: Application -> PolicyClause (DM)

## Geographical Linkages (Enrichment)
These edges are *pre-calculated* during ingestion by the Spatial Processor.
*   `CONTAINS`: Area A -> Area B (Topology: B is inside A).
*   `ADJACENT_TO`: Site -> Site (Topology: Shares boundary).
*   `NEAR`: Site -> Feature (Topology: Within X meters).
*   `CONNECTED_TO`: Site -> TransportNode (Network analysis).
*   `VISUALLY_AFFECTS`: VisualAsset -> Site (Viewshed analysis).

