from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from .orchestrator import MoveType, MoveEvent

class GrammarContext(BaseModel):
    """
    The accumulating context passed between moves.
    """
    framing: Optional[Dict[str, Any]] = None
    issues: List[Dict[str, Any]] = []
    evidence_set: Dict[str, Any] = {}
    interpretations: List[Dict[str, Any]] = []
    ledger: List[Dict[str, Any]] = []
    weighing: Optional[Dict[str, Any]] = None
    negotiations: List[Dict[str, Any]] = []
    positioning: Optional[Dict[str, Any]] = None
    
    def update_from_event(self, event: MoveEvent):
        """
        Updates the context based on the output of a move.
        """
        # This is where the strict "Type Safety" of the grammar comes in.
        # We would validate that IssueSurfacing produced Issue objects, etc.
        pass
