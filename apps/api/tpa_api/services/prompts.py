from __future__ import annotations

from typing import Any
from tpa_api.db import _db_execute, _db_fetch_one
from tpa_api.time_utils import _utc_now


class PromptService:
    """
    Manages prompt versions and retrieval from the canonical DB.
    """

    def register_prompt(
        self,
        prompt_id: str,
        version: int,
        name: str,
        purpose: str,
        template: str,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> None:
        """
        Upserts a prompt definition and version.
        This is typically called at startup or by the prompt registry to ensure
        the DB knows about the prompts we are using.
        """
        now = _utc_now()
        _db_execute(
            """
            INSERT INTO prompts (prompt_id, name, purpose, created_at, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (prompt_id) DO NOTHING
            """,
            (prompt_id, name, purpose, now, created_by),
        )
        
        # We don't store schemas as JSONB in this table version, just refs?
        # The spec says "input_schema_ref" (string).
        # We'll assume for now we just pass None or string refs.
        
        _db_execute(
            """
            INSERT INTO prompt_versions (
              prompt_id, prompt_version, template, input_schema_ref, output_schema_ref,
              created_at, created_by, diff_from_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (prompt_id, prompt_version) DO NOTHING
            """,
            (prompt_id, version, template, None, None, now, created_by),
        )

    def get_template(self, prompt_id: str, version: int | None = None) -> str:
        """
        Retrieves a prompt template. If version is None, gets latest.
        """
        if version:
            row = _db_fetch_one(
                "SELECT template FROM prompt_versions WHERE prompt_id = %s AND prompt_version = %s",
                (prompt_id, version),
            )
        else:
            row = _db_fetch_one(
                "SELECT template FROM prompt_versions WHERE prompt_id = %s ORDER BY prompt_version DESC LIMIT 1",
                (prompt_id,),
            )
            
        if not row:
            raise ValueError(f"Prompt not found: {prompt_id} v{version}")
            
        return str(row["template"])
