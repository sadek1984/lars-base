# src/dependencies.py
from sqlalchemy.orm import Session
from stores.VectorDB.VectorDBInterface import VectorDBInterface
from helper.config import get_settings
from stores.VectorDB.VectorDBProviderFactory import VectorDBProviderFactory
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Global variables to store clients
_db_client = None
_vectordb_client = None

def init_dependencies(db_client, vectordb_client):
    """Initialize dependencies from main app"""
    global _db_client, _vectordb_client
    _db_client = db_client
    _vectordb_client = vectordb_client

def get_db():
    """Get database session"""
    if _db_client is None:
        raise RuntimeError("Database client not initialized")
    return _db_client()

def get_vectordb_client() -> VectorDBInterface:
    """Get vector database client"""
    if _vectordb_client is None:
        raise RuntimeError("VectorDB client not initialized")
    return _vectordb_client