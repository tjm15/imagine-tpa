from __future__ import annotations

from typing import Any


_POLICY_SPEECH_ACT_NORMATIVE_FORCE = {
    "hard_constraint",
    "presumptive_support",
    "presumptive_resistance",
    "aspirational",
    "procedural",
    "justificatory",
    "defers_to_judgement",
    "unknown",
}

_POLICY_SPEECH_ACT_STRENGTH_HINT = {"strong", "moderate", "weak", "symbolic", "unknown"}
_POLICY_SPEECH_ACT_OFFICER_SPACE = {"narrow", "medium", "wide", "unknown"}


def _normalize_policy_speech_act(
    raw: Any,
    *,
    tool_run_id: str | None,
    method: str,
) -> dict[str, Any]:
    """
    Normalise a PolicySpeechAct payload from an LLM instrument output.

    This clamps values to the ontology set without asserting determinations.
    """
    obj = raw if isinstance(raw, dict) else {}
    normative_force = obj.get("normative_force") if isinstance(obj.get("normative_force"), str) else "unknown"
    if normative_force not in _POLICY_SPEECH_ACT_NORMATIVE_FORCE:
        normative_force = "unknown"

    strength_hint = obj.get("strength_hint") if isinstance(obj.get("strength_hint"), str) else "unknown"
    if strength_hint not in _POLICY_SPEECH_ACT_STRENGTH_HINT:
        strength_hint = "unknown"

    officer_space = (
        obj.get("officer_interpretation_space")
        if isinstance(obj.get("officer_interpretation_space"), str)
        else "unknown"
    )
    if officer_space not in _POLICY_SPEECH_ACT_OFFICER_SPACE:
        officer_space = "unknown"

    ambiguity_flags = obj.get("ambiguity_flags") if isinstance(obj.get("ambiguity_flags"), list) else []
    ambiguity_flags = [a for a in ambiguity_flags if isinstance(a, str)][:20]

    key_terms = obj.get("key_terms") if isinstance(obj.get("key_terms"), list) else []
    key_terms = [t for t in key_terms if isinstance(t, str) and t.strip()][:20]

    limitations_text = obj.get("limitations_text") if isinstance(obj.get("limitations_text"), str) else ""
    if not limitations_text.strip():
        limitations_text = (
            "LLM modality characterisation of policy language; preserves ambiguity and is not a binding test. "
            "Verify clause boundaries and weight/status against the source plan cycle."
        )

    return {
        "normative_force": normative_force,
        "strength_hint": strength_hint,
        "ambiguity_flags": ambiguity_flags,
        "key_terms": key_terms,
        "officer_interpretation_space": officer_space,
        "method": method,
        "tool_run_id": tool_run_id,
        "limitations_text": limitations_text,
    }
