"""
memory_service.py — S1: Three-tier MemoryRouter

Memory tiers:
  WORKING   — Current ExecutionRun context_state (in-process, no persistence cost)
  EPISODIC  — Short-term interaction records persisted in EpisodicMemory table
              (last N interactions per entity, queryable by entity/user/channel)
  SEMANTIC  — Long-term vectorised knowledge in DocumentChunk table
              (retrieved via cosine similarity using pgvector)

Usage (from worker.py):
    memory = MemoryRouter(db)

    # Retrieve relevant context before a run
    ctx = await memory.retrieve(
        entity_id=..., user_id=..., query="last purchase amount"
    )

    # Write on run completion (called by S2 hook in worker.py)
    await memory.write_episodic(run)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy import select, desc
from sqlalchemy.dialects.postgresql import UUID as PGUUID
# ---------------------------------------------------------------------------
# ORM Model imported from models.py
# ---------------------------------------------------------------------------
from src.ai.models import EpisodicMemory
from src.ai.constants import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MemoryRouter
# ---------------------------------------------------------------------------

class MemoryRouter:
    """
    Routes memory reads/writes across three tiers: WORKING → EPISODIC → SEMANTIC.

    retrieve()    — Returns combined context from episodic + semantic tiers.
    write_episodic() — Persists a completed run's summary to EpisodicMemory.
    search_semantic() — Vector similarity search in DocumentChunk (if embeddings available).
    """

    MAX_EPISODES = 10    # Keep last N episodic memories per entity/user pair
    MAX_SEMANTIC = 5     # Max semantic chunks to inject
    EPISODIC_CHARS = 300 # Max chars per episode in the injected context block

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cortex_viewport = None  # Cached viewport for long_running mode

    # ------------------------------------------------------------------
    # Retrieve (called before run to inject context)
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        entity_id: UUID,
        user_id: Optional[UUID] = None,
        query: Optional[str] = None,
        channel: Optional[str] = None,
        long_running: bool = True,
        tree_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Merge episodic + semantic search results into a single context dict.

        When long_running=True and tree_id is provided, loads CORTEX viewport
        instead of flat episodic/semantic results.

        Returns:
            {
                "episodic": [{"input": ..., "output": ..., "at": ...}, ...],
                "semantic":  [{"content": ..., "score": ...}, ...],
                "cortex_viewport": {...} | None
            }
        """
        episodic = await self._load_episodic(entity_id, user_id)
        semantic: List[Dict] = []
        if query:
            semantic = await self.search_semantic(entity_id=entity_id, query=query)

        result = {"episodic": episodic, "semantic": semantic, "cortex_viewport": None}

        # Load CORTEX viewport if long_running mode is active
        if long_running and tree_id:
            try:
                from src.ai.cortex_service import CortexRouter as CortexService
                company_id = await self._get_company_id(entity_id)
                if company_id:
                    cortex = CortexService(self.db, company_id)
                    tree, viewport, checkpoint = await cortex.resume_tree(tree_id)
                    self._cortex_viewport = viewport
                    result["cortex_viewport"] = viewport.to_dict()
                    if checkpoint:
                        result["cortex_checkpoint"] = checkpoint
            except Exception as e:
                logger.warning(f"CORTEX viewport load failed: {e}")

        return result

    # ------------------------------------------------------------------
    # Write Episodic (S2 — called on ExecutionRun completion)
    # ------------------------------------------------------------------

    async def write_episodic(self, run: Any) -> Optional[EpisodicMemory]:
        """
        Persist the completed run as an episodic memory record.

        Only top-level runs are written (parent_run_id is None).
        Sub-runs (child steps) are dropped to keep the episodic store lean.

        Args:
            run: ExecutionRun ORM instance
        Returns:
            EpisodicMemory row, or None if skipped (sub-run or error)
        """
        # Only top-level runs get episodic entries
        if getattr(run, "parent_run_id", None) is not None:
            return None

        try:
            input_summary = _summarize(run.input_data)
            output_summary = _summarize(run.result_data)

            # Collect metadata from context_state
            ctx = run.context_state or {}
            tools_used = list({
                tr["tool"]
                for step_key, step_val in ctx.items()
                if isinstance(step_val, dict)
                for tr in step_val.get("tool_results", [])
                if isinstance(tr, dict) and "tool" in tr
            })

            episode = EpisodicMemory(
                entity_id=run.entity_id,
                company_id=run.company_id,
                user_id=run.user_id,
                run_id=run.id,
                input_summary=input_summary,
                output_summary=output_summary,
                status=str(run.status),
                total_cost_usd=str(run.total_cost_usd) if run.total_cost_usd else None,
                total_tokens=run.total_tokens,
                execution_time_ms=run.execution_time_ms,
                metadata_info={
                    "tools_used": tools_used,
                    "step_count": len([k for k in ctx if k.startswith("step_")]),
                },
            )
            self.db.add(episode)
            await self.db.flush()   # Get the ID without full commit (caller commits)

            # Prune old episodes beyond MAX_EPISODES
            await self._prune_old_episodes(run.entity_id, run.user_id)

            logger.debug(f"Episodic memory written for run {run.id}")
            return episode

        except Exception as e:
            logger.warning(f"EpisodicMemory write failed for run {run.id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Semantic Search (pgvector)
    # ------------------------------------------------------------------

    async def search_semantic(
        self,
        entity_id: UUID,
        query: str,
        top_k: int = 5,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search across DocumentChunk records for this entity.
        Uses Vertex AI for embedding (no direct API key calls).

        Returns empty list gracefully if embeddings or config unavailable.
        """
        try:
            from google import genai as _genai
            from google.genai import types as _types

            # Build Vertex AI client from company integration
            company_id = await self._get_company_id(entity_id)
            if not company_id:
                return []

            from src.common.genai_factory import build_vertex_genai_client
            try:
                _client = await build_vertex_genai_client(
                    self.db, company_id,
                    http_options={"api_version": "v1beta"}
                )
            except (RuntimeError, ValueError) as _cfg_err:
                logger.debug(f"Vertex AI client not available for semantic search: {_cfg_err}")
                return []

            # Embed the query
            embed_resp = _client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=query,
                config=_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )
            query_vector = embed_resp.embeddings[0].values

            # pgvector cosine distance query
            from src.ai.models import DocumentChunk, Document
            from sqlalchemy import text

            stmt = text("""
                SELECT dc.content,
                       1 - (dc.embedding <=> CAST(:vec AS vector)) AS score
                FROM   document_chunks dc
                JOIN   documents d ON d.id = dc.document_id
                WHERE  d.entity_id = :entity_id
                ORDER  BY dc.embedding <=> CAST(:vec AS vector)
                LIMIT  :top_k
            """)
            result = await self.db.execute(stmt, {
                "vec": json.dumps(list(query_vector)),
                "entity_id": str(entity_id),
                "top_k": top_k,
            })
            rows = result.fetchall()
            return [{"content": r[0], "score": float(r[1])} for r in rows]

        except Exception as e:
            logger.debug(f"Semantic search skipped: {e}")
            return []

    # ------------------------------------------------------------------
    # Format for injection into system/user prompt
    # ------------------------------------------------------------------

    def format_for_prompt(self, memory: Dict[str, Any]) -> str:
        """
        Render the retrieved memory dict as a text block for prompt injection.

        Gap #13: When CORTEX viewport is available, renders the spec §4.3 format:
          [CORTEX VIEWPORT] — primary context (task + breadcrumb + children)
          [EPISODIC MEMORY]  — brief recent interaction history
          [LAST CHECKPOINT]  — compressed context from previous compaction

        Returns an empty string if all tiers are empty.
        """
        viewport = memory.get("cortex_viewport")

        # ── CORTEX mode: structured spec-compliant prompt ──────────────
        if viewport and self._cortex_viewport:
            parts = []

            # Task description (from tree)
            task_desc = memory.get("task_description")
            if task_desc:
                parts.append(f"## Task\n{task_desc}")

            # Episodic memory (brief, subordinated)
            episodes = memory.get("episodic", [])
            if episodes:
                ep_lines = []
                for ep in episodes[-5:]:  # Only last 5 in CORTEX mode
                    inp = (ep.get("input") or "")[:200]
                    out = (ep.get("output") or "")[:200]
                    at = ep.get("at", "")
                    ep_lines.append(f"  [{at}] {inp!r} → {out!r}")
                parts.append("## Recent Episodes\n" + "\n".join(ep_lines))

            # CORTEX viewport (primary context — includes available operations)
            parts.append(self._cortex_viewport.to_prompt_text())

            # Last checkpoint
            checkpoint = memory.get("cortex_checkpoint")
            if checkpoint:
                ckpt_summary = checkpoint.get("progress_summary", "")
                key_facts = checkpoint.get("key_facts", [])
                next_steps = checkpoint.get("next_steps", [])
                ckpt_lines = [f"## Last Checkpoint\n{ckpt_summary}"]
                if key_facts:
                    ckpt_lines.append("Key facts: " + "; ".join(key_facts))
                if next_steps:
                    ckpt_lines.append("Next steps: " + "; ".join(next_steps))
                parts.append("\n".join(ckpt_lines))

            return "\n\n".join(parts)

        # ── Standard mode (non-CORTEX) ─────────────────────────────────
        parts = []

        episodes = memory.get("episodic", [])
        if episodes:
            ep_lines = []
            for ep in episodes[-self.MAX_EPISODES:]:
                inp = (ep.get("input") or "")[:self.EPISODIC_CHARS]
                out = (ep.get("output") or "")[:self.EPISODIC_CHARS]
                at = ep.get("at", "")
                ep_lines.append(f"  [{at}] User asked: {inp!r} → Agent replied: {out!r}")
            parts.append("## Recent Interaction History\n" + "\n".join(ep_lines))

        chunks = memory.get("semantic", [])
        if chunks:
            chunk_lines = [f"  (score {c['score']:.2f}) {c['content'][:300]}" for c in chunks]
            parts.append("## Relevant Knowledge\n" + "\n".join(chunk_lines))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_episodic(
        self,
        entity_id: UUID,
        user_id: Optional[UUID],
    ) -> List[Dict[str, Any]]:
        """Load last N episodic records for this entity/user pair."""
        try:
            stmt = (
                select(EpisodicMemory)
                .where(EpisodicMemory.entity_id == entity_id)
                .order_by(desc(EpisodicMemory.created_at))
                .limit(self.MAX_EPISODES)
            )
            if user_id:
                stmt = stmt.where(EpisodicMemory.user_id == user_id)
            result = await self.db.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "input": r.input_summary,
                    "output": r.output_summary,
                    "status": r.status,
                    "at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in reversed(rows)   # oldest-first for chronological reading
            ]
        except Exception as e:
            logger.debug(f"Episodic load failed: {e}")
            return []

    async def _prune_old_episodes(self, entity_id: UUID, user_id: Optional[UUID]) -> None:
        """Delete records beyond MAX_EPISODES for this entity/user pair."""
        try:
            stmt = (
                select(EpisodicMemory.id)
                .where(EpisodicMemory.entity_id == entity_id)
                .order_by(desc(EpisodicMemory.created_at))
                .offset(self.MAX_EPISODES)
            )
            if user_id:
                stmt = stmt.where(EpisodicMemory.user_id == user_id)
            result = await self.db.execute(stmt)
            stale_ids = [r[0] for r in result.fetchall()]
            if stale_ids:
                from sqlalchemy import delete
                await self.db.execute(
                    delete(EpisodicMemory).where(EpisodicMemory.id.in_(stale_ids))
                )
        except Exception as e:
            logger.debug(f"Episode pruning failed: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize(data: Any, max_chars: int = 400) -> str:
    """Convert any value to a short readable string for episodic storage."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data[:max_chars]
    try:
        s = json.dumps(data, default=str)
    except Exception:
        s = str(data)
    return s[:max_chars]


# Needed for retrieve() when tree_id is provided
async def _get_company_id_from_entity(db, entity_id: UUID) -> Optional[UUID]:
    """Lookup company_id for an entity."""
    try:
        from src.ai.models import HierarchicalEntity
        result = await db.execute(
            select(HierarchicalEntity.company_id)
            .where(HierarchicalEntity.id == entity_id)
        )
        row = result.scalar_one_or_none()
        return row
    except Exception:
        return None


# Add helper to MemoryRouter
MemoryRouter._get_company_id = _get_company_id_from_entity
