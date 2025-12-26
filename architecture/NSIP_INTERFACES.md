# NSIP Interface Stubs (TODO)

This file provides non-binding placeholders for NSIP interfaces and jobs.
It is an anchor for future implementation work, not a committed contract.

---

## API endpoints (TODO)
* POST /nsip/case
* PATCH /nsip/case/{id}
* POST /nsip/case/{id}/harvest
* POST /nsip/case/{id}/signals
* POST /nsip/case/{id}/hypotheses
* POST /nsip/case/{id}/action-slate
* POST /nsip/case/{id}/backtest

## Background jobs (TODO)
* nsip.harvest.scheduler
* nsip.harvest.scout_proposal
* nsip.signal.extract
* nsip.hypothesis.generate
* nsip.backtest.run

## Data objects (stubs)
* `schemas/NSIPCase.schema.json`
* `schemas/NSIPTimelineEntry.schema.json`
* `schemas/NSIPSignal.schema.json`
* `schemas/NSIPHypothesis.schema.json`
* `schemas/NSIPManifestation.schema.json`
* `schemas/NSIPActionCard.schema.json`
* `schemas/NSIPLatentTemplate.schema.json`
* `schemas/NSIPBacktestRun.schema.json`
