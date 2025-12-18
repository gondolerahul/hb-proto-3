"""Tests for DAG validator module."""

import pytest
from fastapi import HTTPException
from src.ai.dag_validator import DAGValidator


def test_valid_dag():
    """Test validation of a valid DAG."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"},
        {"id": "node3"}
    ]
    edges = [
        {"source": "node1", "target": "node2"},
        {"source": "node2", "target": "node3"}
    ]
    
    # Should not raise exception
    DAGValidator.validate_dag(nodes, edges)


def test_circular_dependency():
    """Test detection of circular dependencies."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"},
        {"id": "node3"}
    ]
    edges = [
        {"source": "node1", "target": "node2"},
        {"source": "node2", "target": "node3"},
        {"source": "node3", "target": "node1"}  # Creates cycle
    ]
    
    with pytest.raises(HTTPException) as exc_info:
        DAGValidator.validate_dag(nodes, edges)
    assert "Circular dependency" in str(exc_info.value.detail)


def test_invalid_source_node():
    """Test detection of invalid source node reference."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"}
    ]
    edges = [
        {"source": "invalid_node", "target": "node2"}
    ]
    
    with pytest.raises(HTTPException) as exc_info:
        DAGValidator.validate_dag(nodes, edges)
    assert "Invalid source node" in str(exc_info.value.detail)


def test_invalid_target_node():
    """Test detection of invalid target node reference."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"}
    ]
    edges = [
        {"source": "node1", "target": "invalid_node"}
    ]
    
    with pytest.raises(HTTPException) as exc_info:
        DAGValidator.validate_dag(nodes, edges)
    assert "Invalid target node" in str(exc_info.value.detail)


def test_topological_sort_linear():
    """Test topological sort on a linear DAG."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"},
        {"id": "node3"}
    ]
    edges = [
        {"source": "node1", "target": "node2"},
        {"source": "node2", "target": "node3"}
    ]
    
    result = DAGValidator.topological_sort(nodes, edges)
    assert result == ["node1", "node2", "node3"]


def test_topological_sort_branching():
    """Test topological sort on a branching DAG."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"},
        {"id": "node3"},
        {"id": "node4"}
    ]
    edges = [
        {"source": "node1", "target": "node2"},
        {"source": "node1", "target": "node3"},
        {"source": "node2", "target": "node4"},
        {"source": "node3", "target": "node4"}
    ]
    
    result = DAGValidator.topological_sort(nodes, edges)
    # node1 must be first, node4 must be last
    assert result[0] == "node1"
    assert result[-1] == "node4"
    # node2 and node3 can be in any order but must be between node1 and node4
    assert "node2" in result[1:3]
    assert "node3" in result[1:3]


def test_topological_sort_with_cycle():
    """Test that topological sort detects cycles."""
    nodes = [
        {"id": "node1"},
        {"id": "node2"},
        {"id": "node3"}
    ]
    edges = [
        {"source": "node1", "target": "node2"},
        {"source": "node2", "target": "node3"},
        {"source": "node3", "target": "node1"}
    ]
    
    with pytest.raises(HTTPException) as exc_info:
        DAGValidator.topological_sort(nodes, edges)
    assert "Circular dependency" in str(exc_info.value.detail)


def test_get_node_dependencies():
    """Test getting dependencies for a node."""
    edges = [
        {"source": "node1", "target": "node3"},
        {"source": "node2", "target": "node3"},
        {"source": "node3", "target": "node4"}
    ]
    
    deps = DAGValidator.get_node_dependencies("node3", edges)
    assert set(deps) == {"node1", "node2"}
    
    deps = DAGValidator.get_node_dependencies("node1", edges)
    assert deps == []


def test_empty_dag():
    """Test handling of empty DAG."""
    with pytest.raises(HTTPException) as exc_info:
        DAGValidator.validate_dag([], [])
    assert "at least one node" in str(exc_info.value.detail)
