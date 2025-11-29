from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class NodeType(BaseModel):
    """Represents a node type (label) in the Neo4j database."""
    label: str = Field(..., description="The name of the node label")
    count: int = Field(default=0, description="Number of nodes with this label")
    properties: List[str] = Field(default_factory=list, description="List of property keys for this node type")


class RelationshipType(BaseModel):
    """Represents a relationship type in the Neo4j database."""
    type: str = Field(..., description="The relationship type name")
    count: int = Field(default=0, description="Number of relationships of this type")


class GraphSchema(BaseModel):
    """
    Schema representation of the Neo4j graph database.
    Shows all node types, relationship types, and their properties.
    """
    node_types: List[NodeType] = Field(default_factory=list, description="List of node types in the database")
    relationship_types: List[RelationshipType] = Field(default_factory=list, description="List of relationship types")
    total_nodes: int = Field(default=0, description="Total number of nodes in the database")
    total_relationships: int = Field(default=0, description="Total number of relationships")


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Overall health status")
    neo4j_connected: bool = Field(..., description="Whether Neo4j connection is active")
    neo4j_message: str = Field(..., description="Neo4j connection status message")
    database: Optional[str] = Field(None, description="Connected database name")


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
