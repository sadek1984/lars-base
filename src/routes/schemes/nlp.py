from pydantic import BaseModel, Field
from typing import Optional

class PushRequest(BaseModel):
    do_reset: Optional[int] = 0

class SearchRequest(BaseModel):
    text: str
    limit: Optional[int] = 5

class PostLocalIndex(BaseModel):
    """
    Pydantic model for the local data indexing request.
    """
    do_reset: bool = Field(
        default=False, 
        description="If true, deletes the existing collection before indexing."
    )

class PostLocalQuery(BaseModel):
    """
    Pydantic model for querying local data.
    """
    query: str = Field(..., description="The natural language question to ask the model.")
    n_results: int = Field(default=10, description="The number of documents to retrieve for context.")

class PostDocQuery(BaseModel):
    """
    Placeholder model for querying a single document.
    (To be implemented based on feature requirements)
    """
    query: str
    doc_id: str

class PostDocIndex(BaseModel):
    """
    Placeholder model for indexing a single document.
    (To be implemented based on feature requirements)
    """
    content: str
    metadata: dict

class NLPQuery(BaseModel):
    """
    Pydantic model for the intelligent ISO query request.
    """
    question: str = Field(
        ..., 
        description="The natural language question to ask about ISO documents."
    )
    project_id: str = Field(
        ..., 
        description="The ID of the project to search within."
    )