"""
Long-term memory system using Chroma vector store.
Stores and retrieves user experiences, conversation embeddings, and preferences.
"""

from typing import List, Optional
from uuid import UUID

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings

from app.config import settings


class LongTermMemoryStore:
    """
    Vector-based long-term memory for semantic retrieval of user experiences
    and conversation history.
    """

    def __init__(self):
        self.client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.embeddings = OpenAIEmbeddings(
            model=settings.DEFAULT_EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )

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
        vectors = await self.embeddings.aembed_documents(texts)

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

        query_vector = await self.embeddings.aembed_query(query)

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

        vector = await self.embeddings.aembed_query(text)
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

        query_vector = await self.embeddings.aembed_query(query)
        results = collection.query(query_embeddings=[query_vector], n_results=top_k)

        formatted = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
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
