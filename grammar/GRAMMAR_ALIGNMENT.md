# Grammar Alignment (Canonical)

This document is canonical. It aligns the frozen 8-move grammar with the book's
theory of planning judgement. It is not a new grammar and does not add new moves.
It describes how the existing grammar is used in practice: creative, agentic,
traceable trajectories through a contested reasoning space.

---

## 1) Book to grammar crosswalk
The book describes planning judgement as cognitive practice. The grammar provides
a procedural scaffold. They describe the same thing at different resolution.
Moves do not have to occur once or in order.

1. Framing the problem
   - Book: establish what kind of question this is, and which framing applies.
   - Grammar: framing
   - Note: framing is not neutral; different framings create different valid trajectories.

2. Surfacing issues
   - Book: identify what could plausibly make or break the decision.
   - Grammar: issue_surfacing
   - Note: issues are potentially relevant, not yet weighed.

3. Assembling evidence
   - Book: curate a usable subset of the available material.
   - Grammar: evidence_curation
   - Note: this is selective and bounded by bandwidth, not exhaustive.

4. Interpreting evidence
   - Book: turn material into understood facts, constraints, and implications.
   - Grammar: evidence_interpretation
   - Note: interpretation already contains judgement.

5. Forming material considerations
   - Book: crystallize what matters into planning considerations.
   - Grammar: considerations_formation
   - Note: relevance is asserted explicitly here.

6. Weighing and balancing
   - Book: assign salience and recognize trade-offs.
   - Grammar: weighing_and_balance
   - Note: weighting is qualitative, contestable, and must be reasoned.

7. Negotiation and alteration
   - Book: explore mitigation, conditions, amendments, or alternatives.
   - Grammar: negotiation_and_alteration
   - Note: this is a core move, not an afterthought.

8. Positioning and narration
   - Book: select a stance within the corridor and narrate it.
   - Grammar: positioning_and_narration
   - Note: narration is how judgement becomes legitimate and challengeable.

---

## 2) Trajectory semantics (non-linear)
The grammar is a scaffold, not a strict pipeline. The system should:
- explore multiple trajectories where useful,
- loop and backtrack as evidence or pressure changes,
- emit a new MoveEvent for every epistemic correction,
- keep the trace surface legible and contestable.

---

## 3) Backtrack reason vocabulary (canonical)
Backtracking is a visible epistemic correction, not a hidden retry.
Use the controlled vocabulary below for MoveEvent.backtrack_reason_code.

- MISSING_EVIDENCE
- CONFLICT_FOUND
- POLICY_MISAPPLIED
- SITE_FACT_INCORRECT
- CONSULTEE_CONTRADICTION
- UNCERTAINTY_TOO_HIGH
- FRAMING_SHIFT
- DRAFT_CLAIM_UNCITED

---

## 4) Evidence habit anchors (canonical)
These are prompt anchors and test invariants, not new schema fields.

1. No normative claim without evidence.
2. No policy claim without a specific policy hook.
3. Adopted status must be explicit; never assume weight.
4. Fact, interpretation, judgement, and recommendation must not be collapsed.
5. Weight must be justified, not asserted.
6. Material uncertainty must be surfaced.
7. Negotiation changes the balance and must feed back into weighing.
