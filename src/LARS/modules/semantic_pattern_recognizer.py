"""
Semantic Pattern Recognizer for LARS
Uses sentence-transformers for Arabic/multilingual embeddings
and ChromaDB for vector similarity search.
"""

import os
import json
import logging
from typing import Tuple, Optional, Dict, List
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    import chromadb
    from chromadb.config import Settings
    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False

logger = logging.getLogger(__name__)


class SemanticPatternRecognizer:
    """
    Semantic pattern recognition using embeddings.
    Replaces fixed keyword matching with semantic understanding.
    """
    
    # Pattern types that map to handler functions
    PATTERN_HANDLERS = {
        'count_above_limit': '_handle_count_samples_limit',
        'count_below_limit': '_handle_count_samples_limit',
        'comprehensive_analysis': '_handle_comprehensive_analysis',
        'pesticide_specific': '_handle_find_pesticide_in_sample',
        'pesticide_limit_specific': '_handle_sample_pesticide_limit',
        'list_pesticides': '_handle_list_pesticides',
        'neighborhood_pesticides': '_handle_neighborhood_pesticides',
        'samples_with_n_pesticides': '_handle_n_pesticides',
        'simple_count': '_handle_count_samples_limit',
        'statistics': '_handle_statistics',
    }
    
    def __init__(self, 
                 model_name: str = "intfloat/multilingual-e5-base",
                 knowledge_path: str = None,
                 db_path: str = None,
                 similarity_threshold: float = 0.65):
        """
        Initialize the semantic pattern recognizer.
        
        Args:
            model_name: Sentence transformer model for embeddings
            knowledge_path: Path to pattern_knowledge.json
            db_path: Path to store ChromaDB data
            similarity_threshold: Minimum similarity score to accept a match
        """
        self.similarity_threshold = similarity_threshold
        self.initialized = False
        
        if not HAS_DEPENDENCIES:
            logger.warning("sentence-transformers or chromadb not installed. Semantic recognition disabled.")
            return
        
        try:
            # Set up paths
            base_path = Path(__file__).parent.parent
            self.knowledge_path = knowledge_path or str(base_path / "data" / "pattern_knowledge.json")
            self.db_path = db_path or str(base_path / "data" / "chroma_patterns")
            
            # Load embedding model
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)
            
            # Initialize ChromaDB
            self.chroma_client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get or create collection
            self.collection = self.chroma_client.get_or_create_collection(
                name="pattern_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Load patterns if collection is empty
            if self.collection.count() == 0:
                self._load_patterns()
            
            self.initialized = True
            logger.info(f"✅ SemanticPatternRecognizer initialized with {self.collection.count()} patterns")
            
        except Exception as e:
            logger.error(f"Failed to initialize SemanticPatternRecognizer: {e}")
            self.initialized = False
    
    def _load_patterns(self):
        """Load patterns from JSON and embed them into ChromaDB."""
        if not os.path.exists(self.knowledge_path):
            logger.warning(f"Pattern knowledge file not found: {self.knowledge_path}")
            return
        
        with open(self.knowledge_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
        
        documents = []
        metadatas = []
        ids = []
        
        for pattern_type, examples in patterns.items():
            for i, example in enumerate(examples):
                documents.append(example)
                metadatas.append({"pattern_type": pattern_type})
                ids.append(f"{pattern_type}_{i}")
        
        if documents:
            # Generate embeddings
            embeddings = self.model.encode(documents).tolist()
            
            # Add to collection
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Loaded {len(documents)} pattern examples into ChromaDB")
    
    def recognize(self, query: str) -> Optional[Dict]:
        """
        Recognize the pattern type for a query.
        
        Args:
            query: User query text
            
        Returns:
            Dict with 'pattern_type', 'confidence', 'handler' if recognized,
            None otherwise
        """
        if not self.initialized:
            return None
        
        try:
            # Encode query
            query_embedding = self.model.encode([query]).tolist()
            
            # Search for similar patterns
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=3,
                include=["documents", "metadatas", "distances"]
            )
            
            if not results['ids'][0]:
                return None
            
            # ChromaDB returns distances (lower = more similar for cosine)
            # Convert to similarity score
            distance = results['distances'][0][0]
            similarity = 1 - distance  # For cosine distance
            
            if similarity < self.similarity_threshold:
                logger.debug(f"Query similarity {similarity:.3f} below threshold {self.similarity_threshold}")
                return None
            
            pattern_type = results['metadatas'][0][0]['pattern_type']
            matched_example = results['documents'][0][0]
            
            return {
                'pattern_type': pattern_type,
                'confidence': similarity,
                'handler': self.PATTERN_HANDLERS.get(pattern_type),
                'matched_example': matched_example
            }
            
        except Exception as e:
            logger.error(f"Error in pattern recognition: {e}")
            return None
    
    def add_pattern(self, query: str, pattern_type: str):
        """
        Add a new pattern example (for learning from corrections).
        
        Args:
            query: The query text
            pattern_type: The pattern type it should map to
        """
        if not self.initialized:
            return False
        
        try:
            new_id = f"{pattern_type}_{self.collection.count()}"
            embedding = self.model.encode([query]).tolist()
            
            self.collection.add(
                documents=[query],
                embeddings=embedding,
                metadatas=[{"pattern_type": pattern_type}],
                ids=[new_id]
            )
            logger.info(f"Added new pattern: '{query}' -> {pattern_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding pattern: {e}")
            return False
    
    def reload_patterns(self):
        """Reload patterns from JSON file (useful after updates)."""
        if not self.initialized:
            return False
        
        try:
            # Delete existing collection
            self.chroma_client.delete_collection("pattern_knowledge")
            
            # Recreate collection
            self.collection = self.chroma_client.create_collection(
                name="pattern_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Reload patterns
            self._load_patterns()
            logger.info("Patterns reloaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error reloading patterns: {e}")
            return False


# Singleton instance for reuse
_recognizer_instance = None

def get_semantic_recognizer() -> Optional[SemanticPatternRecognizer]:
    """Get or create the singleton SemanticPatternRecognizer instance."""
    global _recognizer_instance
    
    if _recognizer_instance is None:
        _recognizer_instance = SemanticPatternRecognizer()
    
    return _recognizer_instance if _recognizer_instance.initialized else None
