"""
embedding_service.py — Centralized Embedding Generation Service

Provides a unified interface for generating embedding vectors, with:
- Admin-configurable embedding model (via IntegrationRegistry)
- Batch embedding with error handling
- Automatic cost tracking
- Single-node and multi-text embedding methods

Used by: knowledge_tree_service, episodic_tree_service, dreaming_engine,
         memory_service (semantic search), graph_service (auto-edges)
"""
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.constants import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Centralized embedding generation with admin-configurable model,
    batching, and error handling.
    """

    BATCH_SIZE = 100  # Max texts per API call (Vertex AI limit)

    def __init__(self, db: AsyncSession, company_id: UUID):
        self.db = db
        self.company_id = company_id
        self._client = None
        self._model_name = None

    async def _get_client_and_model(self):
        """
        Resolve the embedding model and Vertex AI client.

        Priority:
        1. Admin-configured embedding integration (IntegrationRegistry)
        2. Fallback to EMBEDDING_MODEL constant
        """
        if self._client and self._model_name:
            return self._client, self._model_name

        # Try to resolve admin-configured embedding model
        model_name = await self._resolve_embedding_model()

        # Build Vertex AI client (embeddings use v1 stable endpoint)
        from src.common.genai_factory import build_vertex_genai_client
        client = await build_vertex_genai_client(
            self.db, self.company_id,
        )

        self._client = client
        self._model_name = model_name
        return client, model_name

    async def _resolve_embedding_model(self) -> str:
        """
        Resolve embedding model from admin configuration.

        Priority:
        1. ModelTaskDefault for task_type 'embedding' (AI Config page)
        2. IntegrationRegistry with service_category 'EMBEDDING'
        3. IntegrationRegistry with provider 'google' and model matching 'embed'
        4. Fallback to EMBEDDING_MODEL constant
        """
        try:
            # Priority 1: Check AI Config task defaults for 'embedding'
            from src.config.models import ModelTaskDefault as _MTD
            mtd_result = await self.db.execute(
                select(_MTD).where(
                    _MTD.company_id == self.company_id,
                    _MTD.task_type == "embedding",
                )
            )
            mtd = mtd_result.scalar_one_or_none()
            if mtd and mtd.integration_id:
                from src.config.models import IntegrationRegistry as _IR
                ir_result = await self.db.execute(
                    select(_IR).where(
                        _IR.id == mtd.integration_id,
                        _IR.status == "active",
                    )
                )
                ir = ir_result.scalar_one_or_none()
                if ir and ir.model_name:
                    logger.debug(f"Using AI Config task default embedding model: {ir.model_name}")
                    return ir.model_name
        except Exception as e:
            logger.debug(f"ModelTaskDefault lookup for embedding failed: {e}")

        try:
            from src.config.models import IntegrationRegistry

            # Priority 2: Explicit EMBEDDING category
            result = await self.db.execute(
                select(IntegrationRegistry).where(
                    IntegrationRegistry.company_id == self.company_id,
                    IntegrationRegistry.service_category == "EMBEDDING",
                    IntegrationRegistry.status == "active",
                )
            )
            integration = result.scalar_one_or_none()
            if integration and integration.model_name:
                logger.debug(f"Using admin-configured embedding model: {integration.model_name}")
                return integration.model_name

            # Priority 3: Google integration with embed in model name
            result = await self.db.execute(
                select(IntegrationRegistry).where(
                    IntegrationRegistry.company_id == self.company_id,
                    IntegrationRegistry.provider_name.in_(["google", "gemini"]),
                    IntegrationRegistry.model_name.ilike("%embed%"),
                    IntegrationRegistry.status == "active",
                )
            )
            integration = result.scalar_one_or_none()
            if integration and integration.model_name:
                logger.debug(f"Using google embedding model: {integration.model_name}")
                return integration.model_name

        except Exception as e:
            logger.debug(f"Failed to resolve embedding model from registry: {e}")

        logger.debug(f"Using fallback embedding model: {EMBEDDING_MODEL}")
        return EMBEDDING_MODEL

    async def embed_text(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> Optional[List[float]]:
        """
        Embed a single text string.

        Returns embedding vector or None on failure.
        """
        results = await self.embed_batch([text], task_type=task_type)
        return results[0] if results else None

    async def embed_query(self, query: str) -> Optional[List[float]]:
        """Embed a query for search (uses RETRIEVAL_QUERY task type)."""
        return await self.embed_text(query, task_type="RETRIEVAL_QUERY")

    async def embed_batch(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[Optional[List[float]]]:
        """
        Embed a batch of texts. Returns list of embedding vectors.
        None entries indicate failures (logged, not raised).

        Handles batching internally if texts exceed BATCH_SIZE.
        """
        if not texts:
            return []

        try:
            from google.genai import types as _types
            client, model_name = await self._get_client_and_model()
        except Exception as e:
            logger.warning(f"Embedding service unavailable: {e}")
            return [None] * len(texts)

        results: List[Optional[List[float]]] = []

        # Process in batches
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_results = await self._embed_batch_internal(
                client, model_name, batch, task_type
            )
            results.extend(batch_results)

        return results

    async def _embed_batch_internal(
        self,
        client,
        model_name: str,
        texts: List[str],
        task_type: str,
    ) -> List[Optional[List[float]]]:
        """Internal: embed a single batch (≤ BATCH_SIZE texts)."""
        from google.genai import types as _types

        results: List[Optional[List[float]]] = []

        for text in texts:
            if not text or not text.strip():
                results.append(None)
                continue

            try:
                # Truncate very long texts (embedding models have limits)
                truncated = text[:8000] if len(text) > 8000 else text

                embed_response = client.models.embed_content(
                    model=model_name,
                    contents=truncated,
                    config=_types.EmbedContentConfig(task_type=task_type),
                )
                embedding = embed_response.embeddings[0].values
                results.append(list(embedding))
            except Exception as e:
                logger.warning(f"Embedding failed for text (first 100 chars: {text[:100]!r}): {e}")
                results.append(None)

        return results

    async def embed_node(self, node) -> bool:
        """
        Generate and store embedding for a CortexNode.

        Uses node.summary if available, then node.title, then node.content (truncated).
        Sets node.embedding and node.embedding_model.

        Returns True if embedding was generated, False otherwise.
        """
        text_to_embed = node.summary or node.title
        if not text_to_embed and node.content:
            text_to_embed = node.content[:2000]

        if not text_to_embed:
            return False

        embedding = await self.embed_text(text_to_embed)
        if embedding:
            node.embedding = embedding
            node.embedding_model = self._model_name or EMBEDDING_MODEL
            return True

        return False

    async def embed_nodes_batch(self, nodes: list) -> int:
        """
        Embed multiple CortexNodes in batch.

        Returns count of successfully embedded nodes.
        """
        texts = []
        valid_nodes = []
        for node in nodes:
            text = node.summary or node.title
            if not text and node.content:
                text = node.content[:2000]
            if text:
                texts.append(text)
                valid_nodes.append(node)

        if not texts:
            return 0

        embeddings = await self.embed_batch(texts)
        model_name = self._model_name or EMBEDDING_MODEL
        count = 0
        for node, embedding in zip(valid_nodes, embeddings):
            if embedding:
                node.embedding = embedding
                node.embedding_model = model_name
                count += 1

        return count

    def get_model_name(self) -> str:
        """Return the resolved embedding model name."""
        return self._model_name or EMBEDDING_MODEL

    async def embed_node_with_edges(self, node) -> bool:
        """
        Embed a node and automatically create similarity edges (Phase E).

        Combines embed_node() with SemanticGraphService.create_similarity_edges()
        for nodes that should be discoverable via the associative graph.
        """
        embedded = await self.embed_node(node)
        if not embedded:
            return False

        try:
            from src.ai.memory.graph_service import SemanticGraphService
            graph = SemanticGraphService(self.db, self.company_id)
            await graph.create_similarity_edges(node.id)
        except Exception as e:
            logger.debug(f"Auto-edge creation failed for node {node.id}: {e}")

        return True

