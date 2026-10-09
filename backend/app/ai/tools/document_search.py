"""Document search tool schema. Executed by the document_researcher node via DocumentRetriever.

Note what is *not* in the schema: owner id and document filters. Those come from the session,
never from the model, so a prompt-injected model cannot read another user's documents.
"""

from pydantic import BaseModel, Field


class DocumentSearch(BaseModel):
    """Semantic search over the documents the user uploaded for this research."""

    query: str = Field(max_length=300, description="What to look for in the documents.")
    task_id: str = Field(description="Id of the research task this search serves.")
