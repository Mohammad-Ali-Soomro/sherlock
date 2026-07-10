from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from typing import List, Optional
from pydantic import BaseModel

import os

from app.config import get_settings
from app.database import get_neo4j_graph, get_neo4j_driver, close_neo4j_connection, verify_neo4j_connection
from app.schemas import GraphSchema, HealthStatus, NodeType, RelationshipType
from app.ingest import (
    ingest_document, ingest_multiple_documents, 
    IngestRequest, IngestResponse, 
    RefineGraphRequest, RefineGraphResponse, refine_graph,
    ALLOWED_NODES, ALLOWED_RELATIONSHIPS
)
from app.detective import router as detective_router

# Load environment variables
load_dotenv()

# CORS origins - reads from ALLOWED_ORIGINS env var (comma-separated), defaults to localhost
_default_origins = ["http://localhost:3000"]
_env_origins = os.getenv("ALLOWED_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _env_origins.split(",") if o.strip()] if _env_origins else _default_origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup: Initialize Neo4j connection
    print("Starting up... Initializing Neo4j connection")
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        print(f"Connected to Neo4j database: {get_settings().neo4j_database}")
    except Exception as e:
        print(f"Warning: Could not connect to Neo4j on startup: {e}")
    
    yield
    
    # Shutdown: Close connections
    print("Shutting down... Closing Neo4j connection")
    close_neo4j_connection()


app = FastAPI(
    title="Sherlock Backend API",
    description="A FastAPI backend with Neo4j graph database integration using LangChain",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the detective router for analysis endpoints
app.include_router(detective_router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint returning API information."""
    return {
        "message": "Sherlock Backend API is running",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthStatus, tags=["Health"])
async def health_check():
    """
    Health check endpoint that verifies the Neo4j connection is active.
    Returns detailed status about the database connection.
    """
    neo4j_status = verify_neo4j_connection()
    
    overall_status = "healthy" if neo4j_status["connected"] else "unhealthy"
    
    return HealthStatus(
        status=overall_status,
        neo4j_connected=neo4j_status["connected"],
        neo4j_message=neo4j_status["message"],
        database=neo4j_status.get("database")
    )


@app.get("/schema", response_model=GraphSchema, tags=["Database"])
async def get_graph_schema():
    """
    Get the schema of the Neo4j graph database.
    Returns all node types, relationship types, and their properties.
    """
    graph = get_neo4j_graph()
    
    # Get node labels with counts and properties
    node_labels_query = """
    CALL db.labels() YIELD label
    CALL apoc.cypher.run('MATCH (n:`' + label + '`) RETURN count(n) as count, keys(n) as props LIMIT 1', {})
    YIELD value
    RETURN label, value.count as count, value.props as properties
    """
    
    # Fallback query without APOC
    simple_labels_query = """
    CALL db.labels() YIELD label
    RETURN label
    """
    
    # Get relationship types
    rel_types_query = """
    CALL db.relationshipTypes() YIELD relationshipType
    RETURN relationshipType
    """
    
    # Get total counts
    count_query = """
    MATCH (n) WITH count(n) as nodeCount
    OPTIONAL MATCH ()-[r]->() 
    RETURN nodeCount, count(r) as relCount
    """
    
    node_types = []
    relationship_types = []
    total_nodes = 0
    total_relationships = 0
    
    try:
        # Try to get node labels
        try:
            labels_result = graph.query(node_labels_query)
            for row in labels_result:
                node_types.append(NodeType(
                    label=row["label"],
                    count=row.get("count", 0),
                    properties=row.get("properties", [])
                ))
        except:
            # Fallback without APOC
            labels_result = graph.query(simple_labels_query)
            for row in labels_result:
                # Get count for each label
                count_result = graph.query(f"MATCH (n:`{row['label']}`) RETURN count(n) as count")
                count = count_result[0]["count"] if count_result else 0
                
                # Get properties sample
                props_result = graph.query(f"MATCH (n:`{row['label']}`) RETURN keys(n) as props LIMIT 1")
                props = props_result[0]["props"] if props_result else []
                
                node_types.append(NodeType(
                    label=row["label"],
                    count=count,
                    properties=props
                ))
        
        # Get relationship types
        rel_result = graph.query(rel_types_query)
        for row in rel_result:
            rel_type = row["relationshipType"]
            # Get count for each relationship type
            rel_count_result = graph.query(f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) as count")
            rel_count = rel_count_result[0]["count"] if rel_count_result else 0
            
            relationship_types.append(RelationshipType(
                type=rel_type,
                count=rel_count
            ))
        
        # Get total counts
        counts = graph.query(count_query)
        if counts:
            total_nodes = counts[0].get("nodeCount", 0)
            total_relationships = counts[0].get("relCount", 0)
            
    except Exception as e:
        print(f"Error fetching schema: {e}")
    
    return GraphSchema(
        node_types=node_types,
        relationship_types=relationship_types,
        total_nodes=total_nodes,
        total_relationships=total_relationships
    )


@app.get("/schema/refresh", tags=["Database"])
async def refresh_schema():
    """
    Refresh the Neo4j graph schema cache.
    Useful after adding new node types or relationships.
    """
    try:
        graph = get_neo4j_graph()
        graph.refresh_schema()
        return {
            "success": True,
            "message": "Schema refreshed successfully",
            "schema": graph.schema
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to refresh schema: {str(e)}"
        }


# =============================================================================
# INGESTION ENDPOINTS
# =============================================================================

@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_text(request: IngestRequest):
    """
    Ingest a text document and convert it to a knowledge graph.
    
    This endpoint uses LLMGraphTransformer with Grok 3 Mini to:
    1. Extract entities (Person, Organization, Location, Event, Crime)
    2. Extract relationships (KNOWS, INVOLVED_IN, LOCATED_AT, PERPETRATED, VICTIM_OF)
    3. Store the resulting graph in Neo4j
    
    If investigation_id is provided, the data will be tagged with that ID
    so each investigation can have isolated graph data.
    
    Example request:
    ```json
    {
        "text": "John Smith was seen at the Central Bank on March 15th...",
        "source": "witness_statement_001",
        "investigation_id": "inv-123"
    }
    ```
    """
    return await ingest_document(request.text, request.source, request.investigation_id)


class BatchIngestRequest(BaseModel):
    """Request model for batch document ingestion."""
    texts: List[str]
    source: Optional[str] = None


@app.post("/ingest/batch", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_batch(request: BatchIngestRequest):
    """
    Ingest multiple text documents at once.
    
    This is more efficient than calling /ingest multiple times
    as it processes all documents in a single LLM call.
    """
    return await ingest_multiple_documents(request.texts, request.source)


@app.get("/ingest/config", tags=["Ingestion"])
async def get_ingest_config():
    """
    Get the current ingestion configuration.
    
    Returns the allowed node types and relationship types
    that the LLMGraphTransformer will extract.
    """
    return {
        "allowed_nodes": ALLOWED_NODES,
        "allowed_relationships": ALLOWED_RELATIONSHIPS,
        "model": "x-ai/grok-3-mini",
        "description": "The ingestion pipeline extracts entities and relationships from text using Grok 3 Mini via OpenRouter"
    }


# =============================================================================
# ENTITY RESOLUTION ENDPOINTS
# =============================================================================

@app.post("/refine-graph", response_model=RefineGraphResponse, tags=["Entity Resolution"])
async def refine_graph_endpoint(request: RefineGraphRequest):
    """
    Refine the graph by merging duplicate nodes and removing orphans.
    
    This endpoint performs "Entity Resolution" to clean up the knowledge graph:
    
    1. **Find Duplicates**: Identifies nodes that likely refer to the same entity
       using string similarity (containment, token overlap, honorific variations).
       Example: "Mr. Vane" and "Thomas Vane" would be flagged as duplicates.
    
    2. **Merge Duplicates**: Transfers all relationships from the duplicate node
       to the primary node, adds the duplicate name as an alias, then deletes
       the duplicate.
    
    3. **Remove Orphans**: Optionally removes nodes that have no relationships,
       as they provide no value in a knowledge graph.
    
    **Use Cases:**
    - Run after ingesting multiple documents to consolidate entities
    - Clean up graphs that have accumulated duplicate nodes over time
    - Prepare data for analysis by removing noise
    
    **Dry Run Mode:**
    Set `dry_run: true` to see what would be changed without making changes.
    This returns the list of merge candidates for review.
    
    Example request:
    ```json
    {
        "investigation_id": "inv-123",
        "similarity_threshold": 0.8,
        "remove_orphans": true,
        "dry_run": false
    }
    ```
    """
    return await refine_graph(request)
