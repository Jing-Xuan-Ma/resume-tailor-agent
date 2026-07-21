"""
Long-term memory system using Chroma vector store.
Stores and retrieves user experiences, conversation embeddings, and preferences.

Falls back to local persistent Chroma + default embedding function when
Docker/HTTP Chroma is unavailable or API keys are missing.
"""

import asyncio
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from app.config import settings

# Determine Chroma storage path
_CHROMA_DB_PATH = Path("C:/Users/HP/resume-agent/data/chroma")
_CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)


class _SimpleEmbeddingFunction:
    """
    Lightweight deterministic embedding function.
    No model download required — uses SHA-256 hashing.
    Sufficient for MVP validation; replace with a real model in production.
    """

    def __call__(self, input: list[str]) -> list[list[float]]:
        import hashlib
        import struct

        embeddings = []
        for text in input:
            # Deterministic 384-dim vector from text hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = []
            for i in range(0, len(h), 4):
                val = struct.unpack("<f", h[i : i + 4] + b"\x00" * (4 - len(h) + i))[0]
                vec.append(val)
            # Pad / truncate to 384 dims
            while len(vec) < 384:
                vec.extend(vec)
            embeddings.append(vec[:384])
        return embeddings


def _get_embedding_fn():
    """Return an embedding function.

    Uses OpenAI only when it's the official endpoint (no custom base URL).
    Custom providers typically don't support the /embeddings endpoint.
    """
    if (
        settings.OPENAI_API_KEY
        and settings.OPENAI_API_KEY.startswith("sk-")
        and not settings.OPENAI_BASE_URL
    ):
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.DEFAULT_EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
    # Fallback: simple hash-based embedding (no download, works offline)
    return _SimpleEmbeddingFunction()


class LongTermMemoryStore:
    """
    Vector-based long-term memory for semantic retrieval of user experiences
    and conversation history.
    """

    def __init__(self):
        # Prefer local persistent client when Docker is unavailable
        try:
            self.client = chromadb.PersistentClient(
                path=str(_CHROMA_DB_PATH),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception:
            # Ultimate fallback: ephemeral in-memory client
            self.client = chromadb.EphemeralClient(
                settings=ChromaSettings(anonymized_telemetry=False),
            )

        self._embedding_fn = _get_embedding_fn()

    async def _embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper for document embedding."""
        if hasattr(self._embedding_fn, "aembed_documents"):
            return await self._embedding_fn.aembed_documents(texts)
        # Run sync embedding in thread pool to avoid blocking
        return await asyncio.to_thread(self._embedding_fn, texts)

    async def _embed_query(self, text: str) -> list[float]:
        """Async wrapper for query embedding."""
        if hasattr(self._embedding_fn, "aembed_query"):
            return await self._embedding_fn.aembed_query(text)
        # Run sync embedding in thread pool to avoid blocking
        result = await asyncio.to_thread(self._embedding_fn, [text])
        return result[0]

    def _collection_name(self, user_id: str, data_type: str) -> str:
        """Generate a unique collection name per user and data type."""
        return f"{settings.CHROMA_COLLECTION_PREFIX}{data_type}_{str(user_id)}"

    async def add_experiences(self, user_id: str, documents: list[dict]):
        """
        Add user experience documents to vector store.
        documents: list of {"text": str, "metadata": dict}
        """
        collection_name = self._collection_name(user_id, "experiences")
        collection = self.client.get_or_create_collection(collection_name)

        texts = [doc["text"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]
        ids = [f"{user_id}_exp_{i}" for i in range(len(documents))]

        # Generate embeddings
        vectors = await self._embed_documents(texts)

        collection.add(
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

    async def search_experiences(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        filters: Optional[dict] = None,
    ) -> List[dict]:
        """
        Semantic search over user's experiences.
        """
        collection_name = self._collection_name(user_id, "experiences")
        collection = self.client.get_or_create_collection(collection_name)

        query_vector = await self._embed_query(query)

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=filters,
        )

        # Format results
        formatted = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return formatted

    async def add_conversation_turn(self, user_id: str, session_id: str, text: str, role: str):
        """Store a conversation turn for semantic retrieval."""
        collection_name = self._collection_name(user_id, "conversations")
        collection = self.client.get_or_create_collection(collection_name)

        vector = await self._embed_query(text)
        doc_id = f"{user_id}_conv_{session_id}_{hash(text) & 0xFFFFFFFF}"

        collection.add(
            embeddings=[vector],
            documents=[text],
            metadatas=[{"role": role, "session_id": session_id}],
            ids=[doc_id],
        )

    async def search_conversations(
        self, user_id: str, query: str, top_k: int = 3
    ) -> List[dict]:
        """Search relevant past conversation turns."""
        collection_name = self._collection_name(user_id, "conversations")
        collection = self.client.get_or_create_collection(collection_name)

        query_vector = await self._embed_query(query)
        results = collection.query(query_embeddings=[query_vector], n_results=top_k)

        formatted = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
            })
        return formatted

    def get_all_experiences(self, user_id: str) -> List[dict]:
        """Retrieve all embedded experience documents for a user."""
        collection_name = self._collection_name(user_id, "experiences")
        try:
            collection = self.client.get_or_create_collection(collection_name)
        except Exception:
            return []
        results = collection.get()
        if not results or not results["ids"]:
            return []
        formatted = []
        for i in range(len(results["ids"])):
            formatted.append({
                "id": results["ids"][i],
                "text": results["documents"][i],
                "metadata": results["metadatas"][i],
            })
        return formatted

    async def jd_skill_match(
        self,
        user_id: str,
        jd_text: str,
        top_k: int = 3,
    ) -> List[dict]:
        """
        Find user's most relevant experiences for a given JD.
        """
        return await self.search_experiences(
            user_id=user_id,
            query=jd_text,
            top_k=top_k,
        )
