# PESE Interface Stubs (TODO)

This file provides non-binding placeholders for PESE interfaces and events.
It is an anchor for future implementation work, not a committed contract.

---

## API endpoints (TODO)
* POST /preapp
* PATCH /preapp/{id}
* POST /preapp/{id}/scenario
* POST /preapp/{id}/negotiation-entry

## Realtime channels (TODO)
* preapp:{id}:updates

## Event types (TODO)
* PreAppCaseCreated
* PreAppCaseUpdated
* PreAppScenarioUpdated
* PreAppNegotiationEntryAdded

## Data objects (stubs)
* `schemas/PreAppCase.schema.json`
* `schemas/PreAppNegotiationEntry.schema.json`
