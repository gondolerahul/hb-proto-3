"""
cortex_models.py — CORTEX Memory Architecture ORM Models (v2.0)

The CORTEX (Cognitive Orchestrated Recursive Tree EXecution) system
provides a persistent, navigable, writable cognitive tree that serves
as the agent's memory, working scratchpad, knowledge base, and
output canvas during long-running tasks.

v2.0 additions:
  - Four memory domains: Knowledge, Experience, Intelligence, Episodic
  - Six-level hierarchical scoping: App → Partner → Tenant → User → Entity → Runtime
  - Semantic graph layer via CortexEdge
  - Embedding vectors on nodes for semantic search
  - Access tracking and importance scoring

Three core tables:
  cortex_trees  — Root container for a cognitive tree
  cortex_nodes  — Individual nodes in the tree
  cortex_edges  — Weighted directed edges between nodes (semantic graph)

Design references:
  - PageIndex: Hierarchical tree index for reasoning-based RAG
  - RLM: Recursive Language Model execution with bounded context
  - Anthropic: Context engineering (compaction, structured note-taking, sub-agents)
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column, String, Boolean, ForeignKey, DateTime, Text,
    Integer, Numeric, Enum as SAEnum, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import pgvector.sqlalchemy

from src.common.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

import enum


class CortexTreeStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class CortexNodeType(str, enum.Enum):
    # --- v1 types (existing) ---
    ROOT = "root"
    KNOWLEDGE = "knowledge"       # Ingested from a document (PageIndex-derived)
    FINDING = "finding"           # Written by the agent during execution
    TASK = "task"                 # A sub-task to be executed
    OUTPUT = "output"            # A section of the output document
    CHECKPOINT = "checkpoint"    # A compacted state snapshot
    # --- v2 types (new) ---
    GROUP = "group"              # Re-clustering group container
    DOCUMENT = "document"        # Represents an ingested document
    SECTION = "section"          # A section/chapter within a document
    CHUNK = "chunk"              # Leaf-level text chunk with embedding
    OBSERVATION = "observation"  # Experience: specific observation from execution analysis
    PATTERN = "pattern"          # Experience: recurring pattern across observations
    SUGGESTION = "suggestion"    # Experience: suggested approach based on patterns
    INSTRUCTION = "instruction"  # Intelligence: distilled actionable rule
    STRATEGY = "strategy"        # Intelligence: high-level strategic approach
    PREFERENCE = "preference"    # Intelligence: user/entity behavioral preference
    EPISODE = "episode"          # Episodic: single execution episode record
    EPISODE_GROUP = "episode_group"  # Episodic: grouped episodes (by date, topic)
    # --- Phase 11 agent-loop types ---
    SNAPSHOT = "snapshot"        # AgentState snapshot written each loop iteration
    HEALTH_RECORD = "health_record"  # Critic StepHealthRecord
    HEALTH_ROOT = "health_root"  # Container node for a run's health records


class CortexNodeStatus(str, enum.Enum):
    PENDING = "pending"          # Not yet worked on
    ACTIVE = "active"            # Currently being processed
    COMPLETE = "complete"        # Fully resolved
    SUMMARISED = "summarised"    # Content replaced by summary (compacted)


class MemoryDomain(str, enum.Enum):
    """Which memory domain a CORTEX tree belongs to."""
    KNOWLEDGE = "knowledge"         # Persistent knowledge base (documents, facts)
    EXPERIENCE = "experience"       # Learned patterns from execution history
    INTELLIGENCE = "intelligence"   # Distilled rules and strategies
    EPISODIC = "episodic"           # Chronological execution history


class ScopeLevel(str, enum.Enum):
    """Hierarchical scope level for memory inheritance."""
    APP = "app"             # L0: Platform-wide (shared across all partners)
    PARTNER = "partner"     # L1: Partner organization level
    TENANT = "tenant"       # L2: Company/tenant level
    USER = "user"           # L3: End-user level
    ENTITY = "entity"       # L4: Agent/entity level
    RUNTIME = "runtime"     # L5: Single execution run


# ---------------------------------------------------------------------------
# CortexTree — Root container for a cognitive tree
# ---------------------------------------------------------------------------

class CortexTree(Base):
    """
    A persistent cognitive tree owned by an entity (agent) for a specific task.

    The tree IS the agent's complete cognitive state. The agent's context window
    is just a viewport onto the tree — never the tree itself.

    v2.0: Trees are now scoped by memory_domain and scope_level to support
    the four-domain unified memory architecture with hierarchical inheritance.

    Key field: resume_cursor_id — always points to the last node the agent was
    actively working on. Enables deterministic resumption after interruption.
    """
    __tablename__ = "cortex_trees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable: tenant/app/partner-scoped trees (e.g. the Meta-Agent platform
    # intelligence tree) are not tied to a single entity and carry entity_id=NULL.
    # The FK still enforces that any non-NULL value references a real entity.
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    task_description = Column(Text, nullable=True)
    status = Column(
        SAEnum(CortexTreeStatus, name="cortex_tree_status", create_constraint=True,
               values_callable=lambda x: [e.value for e in x]),
        default=CortexTreeStatus.ACTIVE,
        nullable=False,
    )

    total_nodes = Column(Integer, default=0)
    root_node_id = Column(UUID(as_uuid=True), nullable=True)       # Set after root node created
    output_root_id = Column(UUID(as_uuid=True), nullable=True)     # Root of the output subtree
    resume_cursor_id = Column(UUID(as_uuid=True), nullable=True)   # KEY: where to resume

    # Configuration
    max_children = Column(Integer, default=12)       # MAX_CHILDREN invariant
    page_size_tokens = Column(Integer, default=8000) # Max tokens per content page
    context_budget_pct = Column(Integer, default=40)  # Root run budget as % of window

    # Scheduling (Gap #5: multi-day operation)
    resume_schedule = Column(String(100), nullable=True)   # Cron expression for periodic wake-ups
    next_resume_at = Column(DateTime, nullable=True)       # Next scheduled resume timestamp

    # --- v2.0: Memory Domain & Scope ---
    memory_domain = Column(
        SAEnum(MemoryDomain, name="memory_domain", create_constraint=False,
               values_callable=lambda x: [e.value for e in x]),
        default=MemoryDomain.KNOWLEDGE,
        server_default="knowledge",
        nullable=False,
    )
    scope_level = Column(
        SAEnum(ScopeLevel, name="scope_level", create_constraint=False,
               values_callable=lambda x: [e.value for e in x]),
        default=ScopeLevel.RUNTIME,
        server_default="runtime",
        nullable=False,
    )

    # Scope hierarchy keys (nullable — set based on scope_level)
    app_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)

    # Categorization and lifecycle
    tree_category = Column(String(100), nullable=True)      # e.g. "hr_policies", "sales_playbook"
    expires_at = Column(DateTime, nullable=True)             # Expiration time (NULL = never)
    is_persistent = Column(Boolean, default=True, server_default="true")  # Survives archival?

    # Consolidation / Dreaming tracking
    last_consolidated_at = Column(DateTime, nullable=True)   # Last dreaming process timestamp
    consolidation_generation = Column(Integer, default=0, server_default="0")  # Dream cycle count
    source_run_ids = Column(JSONB, nullable=True)            # Which runs contributed

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    entity = relationship("HierarchicalEntity")
    company = relationship("Company", foreign_keys=[company_id])
    nodes = relationship("CortexNode", back_populates="tree", cascade="all, delete-orphan",
                         foreign_keys="CortexNode.tree_id")

    __table_args__ = (
        Index("ix_cortex_trees_entity_id", "entity_id"),
        Index("ix_cortex_trees_company_id", "company_id"),
        Index("ix_cortex_trees_status", "status"),
        Index("ix_cortex_trees_domain_scope", "memory_domain", "scope_level"),
        Index("ix_cortex_trees_scope_company", "scope_level", "company_id"),
    )


# ---------------------------------------------------------------------------
# CortexNode — A single node in the cognitive tree
# ---------------------------------------------------------------------------

class CortexNode(Base):
    """
    Every piece of information in CORTEX — whether it is a section of an input
    document, an intermediate finding, a sub-task, or a section of the output
    being written — is a CortexNode.

    v2.0 additions:
      - embedding: pgvector semantic vector for similarity search
      - cross_refs: JSONB pointers to related nodes in other trees
      - access_count / last_accessed_at: usage tracking for importance decay
      - importance_score: 0.0–1.0, updated by learning algorithm

    Invariants:
      1. Summary Always Exists — every node must have a summary before it can be a parent
      2. No Unbounded Viewports — max MAX_CHILDREN direct children per node
      3. Content is Always Paged — large content is read in sequential pages
      4. Write-Once Content — content is immutable; revisions are child finding nodes
    """
    __tablename__ = "cortex_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tree_id = Column(UUID(as_uuid=True), ForeignKey("cortex_trees.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("cortex_nodes.id", ondelete="SET NULL"), nullable=True)

    node_type = Column(
        SAEnum(CortexNodeType, name="cortex_node_type", create_constraint=False,
               values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)       # ~200 tokens, shown in parent's viewport
    content = Column(Text, nullable=True)        # Full content, only loaded on explicit read
    content_tokens = Column(Integer, default=0)  # Size of content in tokens

    status = Column(
        SAEnum(CortexNodeStatus, name="cortex_node_status", create_constraint=True,
               values_callable=lambda x: [e.value for e in x]),
        default=CortexNodeStatus.PENDING,
        nullable=False,
    )

    # Source reference for knowledge nodes
    source_ref = Column(JSONB, nullable=True)    # {document_id, page_start, page_end}

    # Execution linkage
    execution_run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)

    # Tree structure
    depth = Column(Integer, default=0)           # Depth in tree (root = 0)
    sibling_order = Column(Integer, default=0)   # Order among siblings

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Arbitrary metadata (cost, tokens, tool_used, etc.)
    metadata_extra = Column(JSONB, nullable=True)

    # --- v2.0: Semantic embedding ---
    embedding = Column(pgvector.sqlalchemy.Vector(768), nullable=True)
    embedding_model = Column(String(100), nullable=True)  # Which model generated the embedding

    # --- v2.0: Cross-tree references ---
    cross_refs = Column(JSONB, nullable=True)    # [{tree_id, node_id, relationship}, ...]

    # --- v2.0: Access tracking ---
    access_count = Column(Integer, default=0, server_default="0")
    last_accessed_at = Column(DateTime, nullable=True)

    # --- v2.0: Importance scoring ---
    importance_score = Column(Numeric(5, 3), default=Decimal("0.500"), server_default="0.500")

    # Relationships
    tree = relationship("CortexTree", back_populates="nodes", foreign_keys=[tree_id])
    parent = relationship("CortexNode", remote_side=[id], backref="children",
                          foreign_keys=[parent_id])
    execution_run = relationship("ExecutionRun")

    # Edges where this node is the source
    outgoing_edges = relationship("CortexEdge", foreign_keys="CortexEdge.source_node_id",
                                  back_populates="source_node", cascade="all, delete-orphan")
    # Edges where this node is the target
    incoming_edges = relationship("CortexEdge", foreign_keys="CortexEdge.target_node_id",
                                  back_populates="target_node", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cortex_nodes_tree_id", "tree_id"),
        Index("ix_cortex_nodes_parent_id", "parent_id"),
        Index("ix_cortex_nodes_tree_parent", "tree_id", "parent_id"),
        Index("ix_cortex_nodes_tree_type", "tree_id", "node_type"),
        Index("ix_cortex_nodes_status", "status"),
        Index("ix_cortex_nodes_tree_type_status", "tree_id", "node_type", "status"),
    )


# ---------------------------------------------------------------------------
# CortexEdge — Weighted directed edge in the semantic graph
# ---------------------------------------------------------------------------

class CortexEdge(Base):
    """
    A weighted, typed edge connecting two CortexNodes across any trees.

    The cortex_edges table provides the semantic graph layer that overlays
    the tree structures, enabling associative navigation and hybrid
    semantic-structural search.

    Edge types:
      - references: Document cites or references another
      - derived_from: Experience observation derived from episodic data
      - generalizes: Intelligence rule generalizes an experience pattern
      - semantic_similar: High embedding cosine similarity (auto-created)
      - co_accessed: Nodes accessed together in same execution (runtime tracking)
      - precedes: Temporal sequence in same session
      - contradicts: Conflicting intelligence rules
      - supersedes: Updated rule replaces old one
      - applies_to: Intelligence rule applies to specific knowledge domain
    """
    __tablename__ = "cortex_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(UUID(as_uuid=True),
                            ForeignKey("cortex_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True),
                            ForeignKey("cortex_nodes.id", ondelete="CASCADE"), nullable=False)
    edge_type = Column(String(50), nullable=False)
    weight = Column(Numeric(5, 4), default=Decimal("0.5000"), server_default="0.5000")
    traversal_count = Column(Integer, default=0, server_default="0")
    last_traversed_at = Column(DateTime, nullable=True)
    created_by = Column(String(50), nullable=True)  # "dreaming_engine", "embedding_pipeline", etc.
    edge_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_node = relationship("CortexNode", foreign_keys=[source_node_id],
                               back_populates="outgoing_edges")
    target_node = relationship("CortexNode", foreign_keys=[target_node_id],
                               back_populates="incoming_edges")

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type",
                         name="uq_cortex_edges_src_tgt_type"),
        Index("ix_cortex_edges_source", "source_node_id"),
        Index("ix_cortex_edges_target", "target_node_id"),
        Index("ix_cortex_edges_type_weight", "edge_type", weight.desc()),
    )
