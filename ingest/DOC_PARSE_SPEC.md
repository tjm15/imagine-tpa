# Document Parsing Specification

## Strategy
* **Azure Profile**: Use Azure Document Intelligence (Foundry).
* **OSS Profile**: Use `Docling` (IBM).

## Schema Standardization
Output must be normalized to:
```json
{
  "provider": "docling|azure_document_intelligence|...",
  "pages": [{ "page_number": 1, "text": "..." }],
  "page_texts": ["..."],
  "markdown": "...",
  "chunks": [
    {
      "text": "...",
      "type": "heading|paragraph|bullets|table|image|other",
      "section_path": "Chapter 4 > Policy H1",
      "page_number": 1,
      "bbox": { "...": "..." }
    }
  ],
  "tables": [ "markdown_representation" ]
}
```
Regardless of the provider, the system digests this format.

Notes:
* `markdown` is optional but preferred when available; it is used as an additional structure signal for chunking.
* `bbox` and `page_number` are best-effort and may be omitted/null depending on provider/version/config.
