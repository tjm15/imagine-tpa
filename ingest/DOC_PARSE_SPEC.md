# Document Parsing Specification

## Strategy
* **Azure Profile**: Use Azure Document Intelligence (Foundry).
* **OSS Profile**: Use `Docling` (IBM).

## Schema Standardization
Output must be normalized to:
```json
{
  "pages": [],
  "chunks": [
    { "text": "...", "bbox": [...], "type": "paragraph" }
  ],
  "tables": [ "markdown_representation" ]
}
```
Regardless of the provider, the system digests this format.
