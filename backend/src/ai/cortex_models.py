"""
cortex_models.py — CORTEX Memory Architecture ORM Models

The CORTEX (Cognitive Orchestrated Recursive Tree EXecution) system
provides a persistent, navigable, writable cognitive tree that serves
as the agent's memory, working scratchpad, knowledge base, and
output canvas during long-running tasks.

Two core tables:
  cortex_trees  — Root container for a cognitive tree (one per long-running task)
  cortex_nodes  — Individual nodes in the tree (knowledge, findings, tasks, outputs, checkpoints)

Design references:
  - PageIndex: Hierarchical tree index for reasoning-based RAG
  - RLM: Recursive Language Model execution with bounded context
  - Anthropic: Context engineering (compaction, structured note-taking, sub-agents)
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Boolean, ForeignKey, DateTime, Text,
    Integer, Enum as SAEnum, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

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
    ROOT = "root"
    KNOWLEDGE = "knowledge"       # Ingested from a document (PageIndex-derived)
    FINDING = "finding"           # Written by the agent during execution
    TASK = "task"                 # A sub-task to be executed
    OUTPUT = "output"            # A section of the output document
    CHECKPOINT = "checkpoint"    # A compacted state snapshot


class CortexNodeStatus(str, enum.Enum):
    PENDING = "pending"          # Not yet worked on
    ACTIVE = "active"            # Currently being processed
    COMPLETE = "complete"        # Fully resolved
    SUMMARISED = "summarised"    # Content replaced by summary (compacted)


# ---------------------------------------------------------------------------
# CortexTree — Root container for a cognitive tree
# ---------------------------------------------------------------------------

class CortexTree(Base):
    """
    A persistent cognitive tree owned by an entity (agent) for a specific task.
    
    The tree IS the agent's complete cognitive state. The agent's context window
    is just a viewport onto the tree — never the tree itself.
    
    Key field: resume_cursor_id — always points to the last node the agent was
    actively working on. Enables deterministic resumption after interruption.
    """
    __tablename__ = "cortex_trees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    task_description = Column(Text, nullable=True)
    status = Column(
        SAEnum(CortexTreeStatus, name="cortex_tree_status", create_constraint=True),
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

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    entity = relationship("HierarchicalEntity")
    company = relationship("Company")
    nodes = relationship("CortexNode", back_populates="tree", cascade="all, delete-orphan",
                         foreign_keys="CortexNode.tree_id")

    __table_args__ = (
        Index("ix_cortex_trees_entity_id", "entity_id"),
        Index("ix_cortex_trees_company_id", "company_id"),
        Index("ix_cortex_trees_status", "status"),
    )


# ---------------------------------------------------------------------------
# CortexNode — A single node in the cognitive tree
# ---------------------------------------------------------------------------

class CortexNode(Base):
    """
    Every piece of information in CORTEX — whether it is a section of an input
    document, an intermediate finding, a sub-task, or a section of the output
    being written — is a CortexNode.
    
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
        SAEnum(CortexNodeType, name="cortex_node_type", create_constraint=True),
        nullable=False,
    )
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)       # ~200 tokens, shown in parent's viewport
    content = Column(Text, nullable=True)        # Full content, only loaded on explicit read
    content_tokens = Column(Integer, default=0)  # Size of content in tokens

    status = Column(
        SAEnum(CortexNodeStatus, name="cortex_node_status", create_constraint=True),
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

    # Relationships
    tree = relationship("CortexTree", back_populates="nodes", foreign_keys=[tree_id])
    parent = relationship("CortexNode", remote_side=[id], backref="children",
                          foreign_keys=[parent_id])
    execution_run = relationship("ExecutionRun")

    __table_args__ = (
        Index("ix_cortex_nodes_tree_id", "tree_id"),
        Index("ix_cortex_nodes_parent_id", "parent_id"),
        Index("ix_cortex_nodes_tree_parent", "tree_id", "parent_id"),
        Index("ix_cortex_nodes_tree_type", "tree_id", "node_type"),
        Index("ix_cortex_nodes_status", "status"),
    )
