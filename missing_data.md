# Missing Data Report

This document enumerates precisely the data that could not be automatically retrieved during the last data acquisition phase.

## 1. Greater Manchester Combined Authority

*   **Places for Everyone (PfE) Joint Development Plan Document PDF**:
    *   **Issue**: Direct PDF download attempts resulted in 404 errors or HTML responses. Automated scraping of the adoption page did not yield a direct link to the final PDF document.
    *   **Current Status**: The `greater_manchester/manifest.json` links to the main adoption portal: `https://www.greatermanchester-ca.gov.uk/what-we-do/planning-and-housing/places-for-everyone/adoption/adoption-documentation`. Users will need to manually navigate this page to locate and download the final adopted PDF.
    *   **Note**: GIS data for PfE Allocations, Housing Land Supply, and Office Land Supply were successfully downloaded as ZIP archives.

## 2. South Cambridgeshire District Council

*   **Specific Supplementary Planning Documents (SPDs) and Area Action Plans (AAPs)**:
    *   **Issue**: Several PDFs listed in `ADDITIONAL.md` for Northstowe AAP, Cambridge East AAP, and District Design Guide SPD could not be downloaded via direct links. These URLs either returned 0-byte files or HTTP errors, suggesting they might be dynamic, moved, or embedded within other web content.
    *   **Affected Files (expected names)**:
        *   `northstowe_aap.pdf`
        *   `cambridge_east_aap.pdf`
        *   `district_design_guide_spd.pdf`
    *   **Current Status**: Manual browsing of the respective council planning policy pages (e.g., `https://www.greatercambridgeplanning.org/local-and-neighbourhood-planning/area-action-plans/`) is required to locate these documents.

## 3. Milton Keynes City Council

*   **GIS Vector Data**:
    *   **Issue**: The interactive mapping portal (`https://mapping.milton-keynes.gov.uk/`) was unresponsive during automated investigation (connection timeout). This prevented the discovery and extraction of ArcGIS FeatureServer URLs for downloading vector data layers.
    *   **Current Status**: Manual investigation of the Milton Keynes GIS portal is required to identify accessible FeatureService or WFS/WMS endpoints from which vector data can be downloaded.

## 4. South Oxfordshire District Council

*   **GIS Vector Data**:
    *   **Issue**: Automated attempts to download GIS layers from `maps.southoxon.gov.uk` consistently resulted in `ConnectTimeoutError`. This indicates that the server is either unresponsive, heavily loaded, or actively blocking automated requests from outside its network.
    *   **Current Status**: Manual investigation or a proxy might be necessary to access and download GIS vector data from this authority.

## 5. Original Authorities (GIS Retries)

*   **Westminster City Council**: All GIS layers (`City Plan New`, `Westminster Boundary Mask`, `Ward Boundaries`, `City of Westminster`) returned HTTP 500 errors, indicating server-side issues or inaccessible services.
*   **Royal Borough of Kensington and Chelsea**: All GIS layers (`Planning layers`, `RBKC Borough Boundary Mask`, `RBKC Ward Boundaries`, `RBKC Borough Boundary`) returned HTTP 500 errors, similar to Westminster.
*   **Brighton & Hove City Council**: GIS layers (`Flood Zone 2 and 3 - CP11`, `Adopted City Plan`) returned HTTP 400 errors, suggesting malformed requests or strict access controls.

*   **Current Status for Original Authorities GIS**: 
    *   **Local Sources**: Westminster, RBKC, and Brighton & Hove have secured/broken ArcGIS endpoints (HTTP 500/400).
    *   **National Sources**: Bulk downloads from `planning.data.gov.uk` for `conservation-area` and `listed-building-outline` were successful but **contained 0 features** for these specific authorities. This indicates they have not submitted their spatial data to the central platform or use non-standard referencing.
    *   **Unavailable**: `article-4-direction` and `tree-preservation-order` bulk datasets returned 403 Forbidden, confirming they are not publicly accessible via the bulk API.
    *   **Conclusion**: Machine-readable vector data for these authorities is currently inaccessible via standard open methods.

## 6. Milton Keynes & South Oxfordshire GIS

*   **Milton Keynes**: Local portal is unresponsive; National dataset contained 0 features.
*   **South Oxfordshire**: Local portal blocks connections; National dataset contained 0 features.
*   **Conclusion**: No vector data could be retrieved.

---
**Note**: This report focuses on data that was attempted but failed to be retrieved. It does not list documents or data that were explicitly noted as requiring manual lookup or not being available in a machine-readable format.
