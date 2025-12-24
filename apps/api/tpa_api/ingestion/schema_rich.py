from typing import List, Literal, Optional, Dict, Union, Any
from pydantic import BaseModel, Field
from datetime import date

# =============================================================================
# 1. DOCUMENT IDENTITY & GOVERNANCE (The "Legal Container")
# =============================================================================

class DocumentLegalStatus(BaseModel):
    """
    Precise legal standing of the document in the UK planning system.
    """
    functional_role: Literal[
        "local_plan_dpd", 
        "neighbourhood_plan",
        "spatial_development_strategy",
        "supplementary_planning_document", 
        "design_code",
        "statement_of_community_involvement",
        "authority_monitoring_report",
        "brownfield_register",
        "evidence_base_technical", 
        "sustainability_appraisal",
        "consultation_statement",
        "committee_report",
        "appeal_decision",
        "unknown"
    ] = "unknown"
    
    legal_weight: Literal[
        "statutory_development_plan",  # Section 38(6) priority
        "material_consideration_strong", # Adopted SPD / NPPF
        "material_consideration_moderate", # Emerging policy / Evidence
        "material_consideration_weak", # Withdrawn / Superseded / Old evidence
        "procedural_administrative", 
        "informative_only"
    ] = "material_consideration_moderate"

    stage: Literal[
        "regulation_18_draft",
        "regulation_19_publication",
        "submission",
        "examination_modifications",
        "adopted_made",
        "withdrawn",
        "superseded"
    ] = "adopted_made"

    dates: Dict[str, Optional[date]] = Field(
        default_factory=dict, 
        description="Key dates: 'adopted', 'published', 'period_start', 'period_end'."
    )
    
    relevant_jurisdiction_codes: List[str] = Field(
        default_factory=list, 
        description="ONS/GSS codes for the area this legally covers (e.g. 'E07000012')."
    )

class DocumentAffordances(BaseModel):
    """
    UX/Agent hints: 'What can I do with this document?'
    """
    contains_site_allocations: bool = False
    contains_design_codes: bool = False
    contains_monitoring_indicators: bool = False
    contains_policies_map: bool = False
    
    primary_topics: List[str] = Field(default_factory=list, description="Top 5 dominant themes.")
    
    # Q&A Seeds for the Agent
    canonical_questions: List[str] = Field(
        default_factory=list,
        description="Examples: 'What is the affordable housing target?', 'List all strategic sites'."
    )

# =============================================================================
# 2. POLICY ATOMS (The "Reasoning Core")
# =============================================================================

class PolicyTrigger(BaseModel):
    """
    The 'IF' or 'WHERE' condition of a policy.
    """
    trigger_type: Literal[
        "spatial_zone",       # "In the Green Belt"
        "development_scale",  # "Development > 10 units"
        "development_use",    # "Retail uses (Class E)"
        "temporal_event",     # "Prior to occupation"
        "feature_presence"    # "Where trees are present"
    ]
    raw_text: str
    normalized_value: Optional[Any] = None # e.g. 10 (units), "E(a)" (use class)
    spatial_layer_ref: Optional[str] = None # e.g. "layer_green_belt"

class PolicyRequirement(BaseModel):
    """
    The 'THEN' or 'MUST' of a policy.
    """
    modality: Literal["must", "should", "support", "resist", "prohibit", "require_contribution"]
    requirement_type: Literal[
        "performance_standard", # "BREEAM Excellent"
        "submission_item",      # "Flood Risk Assessment"
        "financial_contribution", # "CIL / S106"
        "physical_provision",   # "Cycle parking"
        "design_principle"      # "Active frontage"
    ]
    raw_text: str
    
    # Structured Target (if applicable)
    target_metric: Optional[str] = None # "affordable_housing_pct"
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    target_operator: Literal["min", "max", "exact", "approx"] = "min"

class PolicyException(BaseModel):
    """
    The 'UNLESS' - critical for reasoning.
    """
    exception_type: Literal["viability", "technical_feasibility", "better_alternative", "temporary_use"]
    description: str

class RichPolicyClause(BaseModel):
    """
    A fully semanticized policy clause.
    """
    policy_code: str
    clause_ref: str
    intent: Literal["strategic_objective", "development_management", "site_allocation", "implementation"]
    
    triggers: List[PolicyTrigger] = Field(default_factory=list)
    requirements: List[PolicyRequirement] = Field(default_factory=list)
    exceptions: List[PolicyException] = Field(default_factory=list)
    
    # Entity Linking
    defined_terms: List[str] = Field(default_factory=list, description="Terms defined in Glossary")
    legislation_refs: List[str] = Field(default_factory=list, description="NPPF paragraphs, Acts")
    related_policies: List[str] = Field(default_factory=list, description="Cross-references")

# =============================================================================
# 3. VISUAL INTELLIGENCE (The "Map Brain")
# =============================================================================

class MapLayerDetection(BaseModel):
    """
    A specific semantic layer identified in a map.
    """
    layer_name: str # e.g. "Conservation Area", "Settlement Boundary"
    layer_type: Literal["constraint", "allocation", "administrative", "context", "infrastructure"]
    representation_style: Literal["polygon_fill", "hatching", "boundary_line", "point_symbol"]
    color_hex_guess: Optional[str] = None
    is_legend_item: bool = False

class VisualDeepMetadata(BaseModel):
    """
    Comprehensive visual understanding.
    """
    asset_category: Literal["proposals_map", "constraints_map", "masterplan", "technical_diagram", "illustrative_render", "photo", "other"]
    
    # Map Specifics
    map_scale_declared: Optional[str] = None # e.g. "1:1250"
    orientation: Literal["north_up", "rotated", "unknown"] = "north_up"
    
    # Content Inventory
    detected_layers: List[MapLayerDetection] = Field(default_factory=list)
    
    # Spatial Specifics
    extracted_toponyms: List[str] = Field(default_factory=list, description="Place names found in image")
    
    # Linkage
    linked_policy_codes: List[str] = Field(default_factory=list, description="Policies this map visualizes")
    
    # Agent Findings (Summary)
    legibility_score: float = Field(..., description="0-1 score of how readable this map is for automation")
    interpretation_notes: str = Field(..., description="VLM commentary on ambiguities or key features")

# =============================================================================
# 4. CROSS-MODAL & RETRIEVAL (The "Glue")
# =============================================================================

class RetrievalFingerprint(BaseModel):
    """
    Precomputed vector-ready descriptors.
    """
    semantic_intent_vector: List[float] = Field(default_factory=list, description="Small embedding of policy intent")
    keyword_bag: List[str] = Field(default_factory=list, description="High-value search keywords")
    spatial_hashes: List[str] = Field(default_factory=list, description="Geohashes or Quadkeys if spatial")

class IngestionArtifact(BaseModel):
    """
    The master container for extraction.
    """
    document_id: str
    legal: DocumentLegalStatus
    affordances: DocumentAffordances
    policies: List[RichPolicyClause]
    visuals: List[VisualDeepMetadata]
