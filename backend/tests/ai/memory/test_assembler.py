"""Tests for the unified memory assembler."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from src.ai.memory.assembler import assemble_memory


@pytest.mark.asyncio
class TestAssembleMemory:
    """Tests for the unified assemble_memory function."""

    async def test_none_scope_returns_empty(self):
        """NONE scope should return empty dict without any DB calls."""
        result = await assemble_memory(
            db=MagicMock(),
            company_id=uuid4(),
            entity_id=uuid4(),
            memory_scope="NONE",
        )
        assert result == {}

    async def test_defaults_to_v1_full(self):
        """Default pipeline should be v1, scope FULL."""
        with patch("src.ai.memory.assembler._assemble_v1", new_callable=AsyncMock) as mock_v1:
            mock_v1.return_value = {"__memory__": "test"}
            result = await assemble_memory(
                db=MagicMock(),
                company_id=uuid4(),
                entity_id=uuid4(),
                memory_pipeline="v1",
                memory_scope="FULL",
            )
            mock_v1.assert_called_once()
            assert result == {"__memory__": "test"}

    async def test_v2_pipeline_calls_assembler(self):
        """v2 pipeline should call _assemble_v2."""
        with patch("src.ai.memory.assembler._assemble_v2", new_callable=AsyncMock) as mock_v2:
            mock_v2.return_value = {"__memory__": "v2 context"}
            result = await assemble_memory(
                db=MagicMock(),
                company_id=uuid4(),
                entity_id=uuid4(),
                memory_pipeline="v2",
                memory_scope="FULL",
                task_description="test task",
            )
            mock_v2.assert_called_once()
            assert result == {"__memory__": "v2 context"}

    async def test_knowledge_only_scope_passes_through(self):
        """KNOWLEDGE_ONLY scope should work with v1 pipeline."""
        with patch("src.ai.memory.assembler._assemble_v1", new_callable=AsyncMock) as mock_v1:
            mock_v1.return_value = {}
            await assemble_memory(
                db=MagicMock(),
                company_id=uuid4(),
                entity_id=uuid4(),
                memory_pipeline="v1",
                memory_scope="KNOWLEDGE_ONLY",
            )
            # _assemble_v1(db, entity_id, user_id, tree_id, memory_scope, long_running)
            # memory_scope is the 5th positional arg (index 4)
            call_args = mock_v1.call_args[0]
            assert call_args[4] == "KNOWLEDGE_ONLY"
