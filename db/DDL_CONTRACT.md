# DDL Contract

All state must exist in these tables.

## 1. Canonical Tables
* `documents` (id, metadata, blob_path)
* `policies` (id, text, overarching_policy_id)
* `sites` (id, geometry_polygon, metadata)
* `spatial_features` (id, type, geometry, properties)

## 2. Knowledge Graph Tables (The "Join Fabric")
* `kg_node` (node_id [PK], node_type, props_jsonb, canonical_fk [nullable])
* `kg_edge` (edge_id [PK], src_id [FK], dst_id [FK], edge_type, props_jsonb, evidence_ref_id, tool_run_id)

## 3. Provenance Tables
* `artifacts` (id, type, path)
* `tool_runs` (id, tool_name, inputs, outputs, timestamp)
* `evidence_refs` (id, source_type, source_id, fragment_id)

## Invariants
* Every `kg_edge` must have a valid `evidence_ref_id` OR `tool_run_id` (provenance is mandatory).
* `kg_node.canonical_fk` links strict graph nodes to rich canonical table rows.
