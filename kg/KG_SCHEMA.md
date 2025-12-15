# Knowledge Graph Schema

## Node Types
* `Document`, `Page`, `Chunk`
* `Policy`, `PolicyClause`, `PolicyMapZone`
* `Site`, `Area`
* `VisualAsset`, `VisualFeature`
* `MoveEvent`, `Assumption`, `Issue`
* `Interpretation`, `Consideration`, `Trajectoy`

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
