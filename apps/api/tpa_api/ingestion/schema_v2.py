from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, Field

# --- 1. Document Routing (documents.metadata) ---

class DocumentRoutingMetadata(BaseModel):
    """
    High-level classification to guide downstream processing and UI.
    """
    functional_role: Literal[
        "local_plan", 
        "spd", 
        "evidence_base", 
        "design_code", 
        "committee_report", 
        "appeal_decision", 
        "consultation", 
        "technical_appendix",
        "unknown"
    ] = "unknown"
    
    decision_criticality: Literal["binding", "guidance", "evidence", "context"] = "context"
    
    planning_stage: Literal[
        "plan_making", 
        "development_management", 
        "monitoring", 
        "unknown"
    ] = "unknown"
    
    spatial_intensity_score: float = Field(0.0, ge=0.0, le=1.0, description="Likelihood of map-based rules.")
    quant_density_score: float = Field(0.0, ge=0.0, le=1.0, description="Likelihood of heavy tabular data.")
    
    update_likelihood: Literal["static", "periodic", "living"] = "static"

    # UX Affordances
    suggested_task_cards: List[str] = Field(default_factory=list, description="IDs of UI cards to show, e.g. 'site_allocations_table'")
    hotspot_pages: List[int] = Field(default_factory=list, description="Pages with high decision relevance.")

# --- 2. Structure Signatures (policy_sections.metadata_jsonb) ---

class SectionTaxonomy(BaseModel):
    section_role: Literal[
        "policy", 
        "justification", 
        "implementation", 
        "monitoring", 
        "glossary", 
        "appendix", 
        "front_matter",
        "unknown"
    ] = "unknown"
    
    contains_tables: bool = False
    contains_maps: bool = False

# --- 3. Policy Semantics (policy_clauses.speech_act_jsonb enriched) ---

class ClauseSemantics(BaseModel):
    """
    Planner-legible semantics for a single policy clause.
    """
    intent_label: Literal[
        "protect", 
        "allocate", 
        "require", 
        "support", 
        "restrict", 
        "encourage", 
        "mitigate", 
        "define",
        "procedure"
    ] = "define"
    
    topic_tags: List[str] = Field(default_factory=list) # Controlled vocabulary (Heritage, Flood, etc.)
    
    modality: Literal["must", "should", "may", "will"] = "should"
    
    trigger_conditions: List[str] = Field(default_factory=list, description="When this applies e.g. 'In Conservation Areas'")
    outputs_required: List[str] = Field(default_factory=list, description="What must be submitted e.g. 'Flood Risk Assessment'")
    
    spatial_referents: List[str] = Field(default_factory=list, description="Named places or zones.")

# --- 4. Numeric Targets (policy_targets) ---
# (Existing table covers this, but we enforce normalization)

class NumericTarget(BaseModel):
    metric_normalized: str # Canonical name e.g. "affordable_housing_percentage"
    value_normalized: float
    unit_canonical: str # "percentage", "dwellings_per_ha"
    tolerance: Literal["exact", "min", "max", "approx", "indicative"] = "exact"

# --- 5. Visual Metadata (visual_semantic_outputs.canonical_facts_jsonb) ---

class VisualRoutingMetadata(BaseModel):
    """
    Fast-pass metadata to decide if deep VLM/Segmentation is needed.
    """
    asset_category: Literal[
        "map", 
        "diagram", 
        "photo", 
        "render", 
        "table_image", 
        "other"
    ] = "other"
    
    map_role: Optional[Literal["proposals", "constraints", "allocation", "context", "inset"]] = None
    
    # Presence Flags
    has_legend: bool = False
    has_scale_bar: bool = False
    has_north_arrow: bool = False
    has_site_boundary: bool = False
    
    text_summary: str = Field("", description="Short OCR summary of title/legend.")
    
    # Geometry Confidence
    geometry_style: Literal["vector_like", "raster_scan", "sketch", "unknown"] = "unknown"

# --- 6. Region Proposals (visual_asset_regions) ---
# (Existing table covers this, but we formalize region_type)

class RegionProposal(BaseModel):
    region_type: Literal["legend", "key", "title_block", "boundary_area", "annotation_cluster"]
    confidence: float
