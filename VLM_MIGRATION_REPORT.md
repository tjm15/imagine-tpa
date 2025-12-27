# VLM & Synthesis Migration Report (Dec 25, 2025)

## Overview
The Visual Pipeline and Synthesis stages have been refactored to align with the Provider Architecture and "no shortcuts" philosophy.

## Key Changes

### 1. `VLMProvider` Interface
*   **Defined**: `tpa_api.providers.vlm.VLMProvider` (interface).
*   **Implemented**: `tpa_api.providers.vlm_openai.OpenAIVLMProvider` (OSS profile).
*   **Provenance**: Automatically logs image counts, sizes, and model usage to `tool_runs`.

### 2. Visual Extraction Module (`visual_extraction.py`)
Centralized all visual reasoning logic:
*   `vlm_enrich_visual_asset`: High-level classification/metadata.
*   `extract_visual_asset_facts`: Detailed structured extraction.
*   `extract_visual_text_snippets`: OCR/text extraction.
*   `extract_visual_region_assertions`: Semantic reasoning on image crops.
*   `extract_visual_agent_findings`: Expert agent review (LLM-based review of VLM outputs).

### 3. Synthesis Module (`synthesis.py`)
*   `imagination_synthesis`: Cross-modal reasoning (linking policies to visuals) now uses `LLMProvider` and `PromptService`.

### 4. Georeferencing (`georef.py`)
*   Migrated `auto_georef_visual_assets` and related logic to a clean module.
*   Uses `VLMProvider` for redline boundary detection.

## Impact
*   **Traceability**: Every VLM call is now a logged ToolRun with a registered Prompt Version.
*   **Modularity**: Visual logic is decoupled from the worker and the graph.
*   **Stability**: Removed reliance on ad-hoc functions in `prompts_rich.py` and the legacy worker monolith.

The Ingestion Pipeline is now fully provider-backed.
