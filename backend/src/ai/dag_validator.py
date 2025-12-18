"""DAG validation and topological sorting for workflow execution."""

from typing import Dict, List, Set
from fastapi import HTTPException


class DAGValidator:
    """Validates DAG structure and provides topological sorting for execution."""
    
    @staticmethod
    def validate_dag(nodes: List[Dict], edges: List[Dict]) -> None:
        """
        Validate DAG structure and check for circular dependencies.
        
        Args:
            nodes: List of workflow nodes
            edges: List of edges connecting nodes
            
        Raises:
            HTTPException: If DAG is invalid or contains cycles
        """
        if not nodes:
            raise HTTPException(status_code=400, detail="Workflow must have at least one node")
        
        # Build adjacency list
        graph = {node["id"]: [] for node in nodes}
        for edge in edges:
            if edge["source"] not in graph:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid source node: {edge['source']}"
                )
            if edge["target"] not in graph:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid target node: {edge['target']}"
                )
            graph[edge["source"]].append(edge["target"])
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            """DFS-based cycle detection."""
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    raise HTTPException(
                        status_code=400, 
                        detail="Circular dependency detected in workflow"
                    )
    
    @staticmethod
    def topological_sort(nodes: List[Dict], edges: List[Dict]) -> List[str]:
        """
        Return nodes in topological order for execution using Kahn's algorithm.
        
        Args:
            nodes: List of workflow nodes
            edges: List of edges connecting nodes
            
        Returns:
            List of node IDs in topological order
            
        Raises:
            HTTPException: If circular dependency is detected
        """
        if not nodes:
            return []
        
        # Build adjacency list and in-degree count
        graph = {node["id"]: [] for node in nodes}
        in_degree = {node["id"]: 0 for node in nodes}
        
        for edge in edges:
            graph[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1
        
        # Find all nodes with no incoming edges (starting nodes)
        queue = [node for node in in_degree if in_degree[node] == 0]
        result = []
        
        while queue:
            # Sort queue for deterministic ordering
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            
            # Reduce in-degree for neighbors
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # If not all nodes are processed, there's a cycle
        if len(result) != len(nodes):
            raise HTTPException(
                status_code=400, 
                detail="Circular dependency detected in workflow"
            )
        
        return result
    
    @staticmethod
    def get_node_dependencies(node_id: str, edges: List[Dict]) -> List[str]:
        """
        Get all direct dependencies (incoming edges) for a node.
        
        Args:
            node_id: ID of the node
            edges: List of edges
            
        Returns:
            List of node IDs that this node depends on
        """
        return [edge["source"] for edge in edges if edge["target"] == node_id]
