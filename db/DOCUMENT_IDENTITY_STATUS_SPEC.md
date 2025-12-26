# Document Identity + Status Specification (tpa_document_identity_status_v1)

## Purpose
Classify a planning-related document into a planner-recognisable hierarchy (development plan / emerging / SPD / material / illustrative) without asserting legal status unless evidenced.

This spec defines the canonical bundle and the rule-based weight classification used across ingestion, connectors, and UI display.

## Objects (canonical bundle)
```json
{
  "spec_name": "tpa_document_identity_status_v1",
  "purpose": "Classify a planning-related document into a planner-recognisable hierarchy (development plan / emerging / SPD / material / illustrative) without asserting legal status unless evidenced.",
  "objects": {
    "EvidenceRef": {
      "type": "object",
      "required": ["document_id", "locator_type", "locator_value"],
      "properties": {
        "document_id": { "type": "string" },
        "locator_type": {
          "type": "string",
          "enum": ["page", "section", "paragraph", "figure", "table", "drawing", "appendix", "url"]
        },
        "locator_value": { "type": "string" },
        "excerpt": { "type": "string" }
      }
    },
    "DocumentIdentityCard": {
      "type": "object",
      "required": ["document_id", "title", "document_family", "source_kind", "identity_evidence"],
      "properties": {
        "document_id": { "type": "string" },
        "title": { "type": "string" },
        "author": { "type": "string" },
        "publisher": { "type": "string" },
        "jurisdiction": { "type": "string", "enum": ["UK-England", "UK-Scotland", "UK-Wales", "UK-NI", "Unknown"] },
        "lpa_name": { "type": "string" },
        "lpa_code": { "type": "string" },
        "document_family": {
          "type": "string",
          "enum": [
            "LOCAL_PLAN_DPD",
            "SPATIAL_DEVELOPMENT_STRATEGY",
            "NEIGHBOURHOOD_PLAN",
            "SPD",
            "NPPF_PPG_NATIONAL_POLICY",
            "EVIDENCE_BASE",
            "TECHNICAL_REPORT",
            "DESIGN_CODE",
            "APPLICANT_STATEMENT",
            "DRAWING_SET",
            "CONSULTEE_RESPONSE",
            "PUBLIC_REPRESENTATION",
            "OFFICER_REPORT",
            "DECISION_NOTICE",
            "COMMITTEE_MINUTES",
            "APPEAL_DECISION",
            "S106_HEADS_OR_AGREEMENT",
            "MARKETING_OR_ILLUSTRATIVE",
            "UNKNOWN"
          ]
        },
        "source_kind": {
          "type": "string",
          "enum": ["PDF", "DOCX", "HTML", "EMAIL", "GIS", "IMAGE", "OTHER"]
        },
        "version_label": { "type": "string" },
        "publication_date": { "type": "string", "format": "date" },
        "revision_date": { "type": "string", "format": "date" },
        "identity_evidence": {
          "type": "array",
          "items": { "$ref": "#/objects/EvidenceRef" }
        },
        "notes": { "type": "string" }
      }
    },
    "DocumentStatusStatement": {
      "type": "object",
      "required": ["document_id", "status_claim", "status_confidence", "status_evidence"],
      "properties": {
        "document_id": { "type": "string" },
        "status_claim": {
          "type": "string",
          "enum": [
            "ADOPTED",
            "MADE",
            "APPROVED",
            "PUBLICATION_DRAFT",
            "REGULATION_18",
            "REGULATION_19",
            "SUBMISSION",
            "EXAMINATION",
            "PROPOSED_MODIFICATIONS",
            "CONSULTATION_DRAFT",
            "WITHDRAWN",
            "SUPERSEDED",
            "NOT_STATED"
          ]
        },
        "status_confidence": { "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"] },
        "status_evidence": {
          "type": "array",
          "items": { "$ref": "#/objects/EvidenceRef" }
        },
        "checked_at": { "type": "string", "format": "date-time" },
        "status_note": { "type": "string" }
      }
    },
    "PlanningWeightClass": {
      "type": "string",
      "enum": ["DEVELOPMENT_PLAN", "EMERGING_POLICY", "SPD_GUIDANCE", "MATERIAL_CONSIDERATION", "ILLUSTRATIVE_LOW_WEIGHT", "UNKNOWN"]
    },
    "WeightClassification": {
      "type": "object",
      "required": ["document_id", "weight_class", "classification_basis", "legal_assertion_level"],
      "properties": {
        "document_id": { "type": "string" },
        "weight_class": { "$ref": "#/objects/PlanningWeightClass" },
        "classification_basis": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["basis_type"],
            "properties": {
              "basis_type": {
                "type": "string",
                "enum": ["EXPLICIT_IN_DOCUMENT", "DOCUMENT_FAMILY_ONLY", "EXTERNAL_REGISTER", "DERIVED_RULE"]
              },
              "evidence": {
                "type": "array",
                "items": { "$ref": "#/objects/EvidenceRef" }
              },
              "rule_id": { "type": "string" },
              "note": { "type": "string" }
            }
          }
        },
        "legal_assertion_level": {
          "type": "string",
          "description": "Controls whether the system is allowed to phrase this as a legal fact.",
          "enum": ["ASSERT_NONE", "ASSERT_CLAIMED_BY_DOCUMENT", "ASSERT_VERIFIED_EXTERNALLY"]
        },
        "phrasing_guidance": {
          "type": "string",
          "enum": [
            "SAY_DOCUMENT_PRESENTS_ITSELF_AS",
            "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY",
            "SAY_VERIFIED_STATUS"
          ]
        },
        "warnings": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": ["NO_STATUS_EVIDENCE", "CONFLICTING_STATUS_SIGNALS", "TIME_SENSITIVE_STATUS", "LOW_PROVENANCE", "ILLUSTRATIVE_MARKERS_PRESENT"]
          }
        }
      }
    },
    "DocumentIdentityStatusBundle": {
      "type": "object",
      "required": ["identity", "status", "weight"],
      "properties": {
        "identity": { "$ref": "#/objects/DocumentIdentityCard" },
        "status": { "$ref": "#/objects/DocumentStatusStatement" },
        "weight": { "$ref": "#/objects/WeightClassification" }
      }
    }
  },
  "rules": [
    {
      "rule_id": "R1_DEV_PLAN_EXPLICIT",
      "if": {
        "document_family_in": ["LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"],
        "status_claim_in": ["ADOPTED", "MADE", "APPROVED"],
        "status_confidence_min": "MEDIUM",
        "status_evidence_required": true
      },
      "then": {
        "weight_class": "DEVELOPMENT_PLAN",
        "legal_assertion_level": "ASSERT_CLAIMED_BY_DOCUMENT",
        "phrasing_guidance": "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
      }
    },
    {
      "rule_id": "R2_EMERGING_POLICY_EXPLICIT",
      "if": {
        "document_family_in": ["LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"],
        "status_claim_in": [
          "REGULATION_18",
          "REGULATION_19",
          "PUBLICATION_DRAFT",
          "SUBMISSION",
          "EXAMINATION",
          "PROPOSED_MODIFICATIONS",
          "CONSULTATION_DRAFT"
        ],
        "status_evidence_required": true
      },
      "then": {
        "weight_class": "EMERGING_POLICY",
        "legal_assertion_level": "ASSERT_CLAIMED_BY_DOCUMENT",
        "phrasing_guidance": "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
      }
    },
    {
      "rule_id": "R3_SPD_EXPLICIT",
      "if": {
        "document_family_in": ["SPD", "DESIGN_CODE"],
        "status_claim_in": ["ADOPTED", "APPROVED"],
        "status_evidence_required": true
      },
      "then": {
        "weight_class": "SPD_GUIDANCE",
        "legal_assertion_level": "ASSERT_CLAIMED_BY_DOCUMENT",
        "phrasing_guidance": "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
      }
    },
    {
      "rule_id": "R4_NATIONAL_POLICY",
      "if": { "document_family_in": ["NPPF_PPG_NATIONAL_POLICY"] },
      "then": {
        "weight_class": "MATERIAL_CONSIDERATION",
        "legal_assertion_level": "ASSERT_NONE",
        "phrasing_guidance": "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
      }
    },
    {
      "rule_id": "R5_MATERIAL_CONSIDERATION_DEFAULT",
      "if": {
        "document_family_in": [
          "EVIDENCE_BASE",
          "TECHNICAL_REPORT",
          "CONSULTEE_RESPONSE",
          "PUBLIC_REPRESENTATION",
          "OFFICER_REPORT",
          "DECISION_NOTICE",
          "COMMITTEE_MINUTES",
          "APPEAL_DECISION",
          "S106_HEADS_OR_AGREEMENT",
          "APPLICANT_STATEMENT",
          "DRAWING_SET"
        ]
      },
      "then": {
        "weight_class": "MATERIAL_CONSIDERATION",
        "legal_assertion_level": "ASSERT_NONE",
        "phrasing_guidance": "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
      }
    },
    {
      "rule_id": "R6_ILLUSTRATIVE_LOW_WEIGHT",
      "if": { "document_family_in": ["MARKETING_OR_ILLUSTRATIVE"] },
      "then": {
        "weight_class": "ILLUSTRATIVE_LOW_WEIGHT",
        "legal_assertion_level": "ASSERT_NONE",
        "phrasing_guidance": "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
      }
    },
    {
      "rule_id": "R7_SUPERSEDED_OR_WITHDRAWN_WARNING",
      "if": { "status_claim_in": ["SUPERSEDED", "WITHDRAWN"] },
      "then": {
        "weight_class_override": null,
        "add_warnings": ["TIME_SENSITIVE_STATUS"]
      }
    },
    {
      "rule_id": "R8_NO_EVIDENCE_DEGRADE",
      "if": { "status_claim_in": ["ADOPTED", "MADE", "APPROVED"], "status_evidence_missing": true },
      "then": {
        "set_status_claim": "NOT_STATED",
        "set_status_confidence": "LOW",
        "add_warnings": ["NO_STATUS_EVIDENCE"],
        "set_legal_assertion_level": "ASSERT_NONE",
        "set_phrasing_guidance": "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
      }
    },
    {
      "rule_id": "R9_EXTERNAL_REGISTER_VERIFICATION_OPTIONAL",
      "if": { "external_register_checked": true, "external_register_confirms": true },
      "then": {
        "set_legal_assertion_level": "ASSERT_VERIFIED_EXTERNALLY",
        "set_phrasing_guidance": "SAY_VERIFIED_STATUS",
        "append_classification_basis": { "basis_type": "EXTERNAL_REGISTER" }
      }
    }
  ],
  "output_templates": {
    "phrasing": {
      "SAY_DOCUMENT_PRESENTS_ITSELF_AS": "This document presents itself as {status_claim} {document_family_label} (see {evidence_refs}).",
      "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY": "Classified as {weight_class} for navigation; treat weight as case-specific unless verified (see {basis}).",
      "SAY_VERIFIED_STATUS": "Status verified externally as {status_claim} (see {external_basis})."
    }
  }
}
```

## Storage
- Canonical bundle stored in `document_identity_status` (see `db/DDL_CONTRACT.md`).
- Use `identity_jsonb`, `status_jsonb`, `weight_jsonb` for the full object; optional query columns mirror key fields.
- `EvidenceRef` entries must be present when legal status is asserted.

## Phrasing rules
- Use `legal_assertion_level` and `phrasing_guidance` to control UI language.
- Never state legal status as fact unless backed by explicit evidence or external verification.
