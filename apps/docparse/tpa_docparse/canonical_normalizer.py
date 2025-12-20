from typing import List, Dict, Any
from pydantic import BaseModel

class CanonicalDocument(BaseModel):
    """
    The rigid schema expected by the rest of the system.
    """
    source_url: str
    title: str
    content_markdown: str
    tables: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class CanonicalNormalizer:
    """
    Uses Docling to parse generic disparate inputs into CanonicalDocument objects.
    """
    
    async def normalize(self, file_path: str) -> CanonicalDocument:
        """
        Runs Docling pipeline on a local file.
        """
        # TODO: Import and use docling
        # from docling.document_converter import DocumentConverter
        # converter = DocumentConverter()
        # result = converter.convert(file_path)
        
        return CanonicalDocument(
            source_url="file://" + file_path,
            title="Extracted Document",
            content_markdown="# Mock Content\n\nThis is a placeholder.",
            tables=[],
            images=[],
            metadata={}
        )
