# Fixtures Specification

## The "Golden Plan"
A synthetic but realistic Local Plan fixture ("Borsetshire Plan").

## Components
* `fixtures/documents/borsetshire_local_plan.pdf` (Document)
* `fixtures/spatial/borsetshire_boundary.geojson` (Spatial)
* `fixtures/sites/site_allocation_A1.geojson` (Site)
* `fixtures/policy/policy_H1.txt` (Policy Text)
* `fixtures/visuals/site_plan_A1.png` (Plan image for Slice B)
* `fixtures/spatial/constraints_floodzones.geojson` (Constraint layer for Slice C)
* `fixtures/instruments/flood_stub.json` (Instrument output stub for Slice D when offline)
* `fixtures/dm/application_A.json` (Application state vector for DM slices)
* `fixtures/monitoring/monitoring_timeseries_stub.json` (Monitoring timeseries for trend/trigger slices)
* `fixtures/monitoring/adoption_baseline_stub.json` (Adoption baseline snapshot for monitoring)

## Usage
All integration tests must run against this stable fixture set.
