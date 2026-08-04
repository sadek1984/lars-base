import chromadb
from typing import List, Dict, Any, Optional

from models import ChunkModel
from stores.VectorDB.VectorDBInterface import VectorDBInterface


class ChromaDBProvider(VectorDBInterface):
    def __init__(self, config):
        self.client = chromadb.HttpClient(
            host=config.CHROMA_HOST,
            port=config.CHROMA_PORT
        )
        self.collection_name = config.CHROMA_COLLECTION

    async def add_documents(self, documents: List[ChunkModel.ChunkModel]):
        collection = self.client.get_or_create_collection(self.collection_name)
        collection.add(
            ids=[doc.id for doc in documents],
            documents=[doc.content for doc in documents],
            metadatas=[doc.metadata for doc in documents]
        )

    # --- UPDATED SEARCH METHOD ---
    async def search_by_vector(
        self,
        project_id: str,
        embedding: List[float],
        limit: int,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[dict]:
        collection = self.client.get_or_create_collection(self.collection_name)
        
        # Build the 'where' clause for ChromaDB
        # Start with the mandatory project_id filter
        where_clause = {"project_id": project_id}
        
        # If an additional metadata_filter is provided, merge it in
        if metadata_filter:
            where_clause.update(metadata_filter)

        results = collection.query(
            query_embeddings=[embedding],
            n_results=limit,
            where=where_clause # <-- Apply the combined filter here
        )

        # Format the results to match what the controller expects
        formatted_results = []
        if results and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                formatted_results.append({
                    "id": doc_id,
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i]
                })
        return formatted_results

    async def delete_by_project_id(self, project_id: str):
        collection = self.client.get_collection(self.collection_name)
        # ChromaDB requires a bit more work to delete by metadata,
        # but this is the general idea.
        collection.delete(where={"project_id": project_id})
