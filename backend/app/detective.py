"""
Detective Tools - Sherlock Analysis Endpoints

This module provides crime investigation analysis capabilities:
1. Shortest path finding between entities
2. Key suspects identification using centrality analysis
3. Natural language to Cypher query conversion
4. Advanced NetworkX-based graph analysis (betweenness centrality, community detection)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
from langchain_groq import ChatGroq
from langchain_neo4j import GraphCypherQAChain
import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities, modularity
from collections import defaultdict

from app.config import get_settings
from app.database import get_neo4j_graph


# Create router for detective endpoints
router = APIRouter(prefix="/detective", tags=["Detective Tools"])


# ============================================================================
# Pydantic Models
# ============================================================================

class PathNode(BaseModel):
    """Represents a node in a path."""
    id: str
    labels: List[str]
    properties: Dict[str, Any]


class PathEdge(BaseModel):
    """Represents an edge/relationship in a path."""
    type: str
    source: str
    target: str
    properties: Dict[str, Any] = {}


class ShortestPathResponse(BaseModel):
    """Response model for shortest path query."""
    found: bool
    path_length: int = 0
    nodes: List[PathNode] = []
    edges: List[PathEdge] = []
    message: str = ""


class SuspectInfo(BaseModel):
    """Information about a key suspect."""
    name: str
    connections: int
    connected_to: List[str] = []


class KeySuspectsResponse(BaseModel):
    """Response model for key suspects query."""
    suspects: List[SuspectInfo]
    analysis_method: str
    message: str


class NaturalLanguageQuery(BaseModel):
    """Request model for natural language queries."""
    question: str = Field(..., description="Natural language question about the crime data")


class QueryResponse(BaseModel):
    """Response model for natural language query."""
    question: str
    cypher_query: str
    answer: str
    success: bool
    message: str = ""


# ============================================================================
# NetworkX Analysis Models
# ============================================================================

class InfluencerInfo(BaseModel):
    """Information about a key influencer (betweenness centrality)."""
    name: str
    node_type: str
    betweenness_score: float
    degree: int
    description: str = ""
    bridges_between: List[str] = []


class MostImportantResponse(BaseModel):
    """Response for most important nodes analysis."""
    influencers: List[InfluencerInfo]
    analysis_method: str
    total_nodes_analyzed: int
    total_edges_analyzed: int
    message: str


class CommunityMember(BaseModel):
    """A member of a community/faction."""
    name: str
    node_type: str
    connections_in_community: int


class Community(BaseModel):
    """A detected community/faction."""
    community_id: int
    size: int
    members: List[CommunityMember]
    label: str = ""  # Auto-generated label like "Faction A" or based on key member


class CommunitiesResponse(BaseModel):
    """Response for community detection analysis."""
    communities: List[Community]
    analysis_method: str
    modularity_score: float
    total_communities: int
    message: str


class PathStep(BaseModel):
    """A single step in a path."""
    from_node: str
    relationship: str
    to_node: str
    from_type: str = ""
    to_type: str = ""


class DetailedPathResponse(BaseModel):
    """Response for detailed path analysis."""
    found: bool
    start_node: str
    end_node: str
    path_length: int = 0
    steps: List[PathStep] = []
    path_description: str = ""
    all_nodes: List[str] = []
    message: str = ""


# ============================================================================
# Helper Functions
# ============================================================================

def get_llm() -> ChatGroq:
    """
    Initialize ChatGroq with Llama 3.3 70B via Groq for natural language queries.
    """
    settings = get_settings()
    return ChatGroq(
        api_key=settings.groq_api_key,
        model="llama-3.3-70b-versatile",
        temperature=0,
    )


def load_graph_to_networkx(investigation_id: Optional[str] = None) -> Tuple[nx.Graph, Dict[str, Dict]]:
    """
    Load Neo4j graph into a NetworkX graph for advanced analysis.
    
    Returns:
        Tuple of (networkx graph, node_data dict mapping node names to their properties)
    """
    graph = get_neo4j_graph()
    G = nx.Graph()  # Undirected for centrality/community analysis
    node_data: Dict[str, Dict] = {}
    
    # Build query based on investigation_id
    if investigation_id:
        nodes_query = """
        MATCH (n {investigation_id: $investigation_id})
        RETURN n.name AS name, labels(n) AS labels, properties(n) AS props
        """
        rels_query = """
        MATCH (a {investigation_id: $investigation_id})-[r]-(b {investigation_id: $investigation_id})
        RETURN DISTINCT a.name AS source, b.name AS target, type(r) AS rel_type
        """
        params = {"investigation_id": investigation_id}
    else:
        nodes_query = """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN n.name AS name, labels(n) AS labels, properties(n) AS props
        """
        rels_query = """
        MATCH (a)-[r]-(b)
        WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN DISTINCT a.name AS source, b.name AS target, type(r) AS rel_type
        """
        params = {}
    
    # Load nodes
    nodes_result = graph.query(nodes_query, params)
    for row in nodes_result:
        name = row["name"]
        if name:
            node_type = row["labels"][0] if row["labels"] else "Entity"
            G.add_node(name)
            node_data[name] = {
                "type": node_type,
                "properties": row.get("props", {})
            }
    
    # Load edges (with relationship type as edge attribute)
    rels_result = graph.query(rels_query, params)
    for row in rels_result:
        source, target = row["source"], row["target"]
        if source and target and source in G.nodes and target in G.nodes:
            # Store relationship type; if multiple, we just keep last one for simplicity
            G.add_edge(source, target, rel_type=row["rel_type"])
    
    return G, node_data


def get_neighbors_by_type(G: nx.Graph, node: str, node_data: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Get neighbors of a node grouped by their type."""
    neighbors_by_type: Dict[str, List[str]] = defaultdict(list)
    for neighbor in G.neighbors(node):
        ntype = node_data.get(neighbor, {}).get("type", "Entity")
        neighbors_by_type[ntype].append(neighbor)
    return dict(neighbors_by_type)


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/shortest-path", response_model=ShortestPathResponse)
async def find_shortest_path(
    start_node: str = Query(..., description="Name of the starting node"),
    end_node: str = Query(..., description="Name of the ending node")
):
    """
    Find the shortest path between two nodes in the knowledge graph.
    
    Uses Neo4j's shortestPath algorithm to find how two entities are connected.
    Returns the list of nodes and edges that form the path.
    
    Example:
        /detective/shortest-path?start_node=John Smith&end_node=The Syndicate
    """
    graph = get_neo4j_graph()
    
    # Cypher query to find shortest path between any two nodes by name
    query = """
    MATCH (start {name: $start_name})
    MATCH (end {name: $end_name})
    MATCH path = shortestPath((start)-[*..15]-(end))
    RETURN path,
           [node IN nodes(path) | {
               id: node.name,
               labels: labels(node),
               properties: properties(node)
           }] AS path_nodes,
           [rel IN relationships(path) | {
               type: type(rel),
               source: startNode(rel).name,
               target: endNode(rel).name,
               properties: properties(rel)
           }] AS path_edges,
           length(path) AS path_length
    LIMIT 1
    """
    
    try:
        result = graph.query(query, {"start_name": start_node, "end_name": end_node})
        
        if not result:
            return ShortestPathResponse(
                found=False,
                message=f"No path found between '{start_node}' and '{end_node}'. They may not be connected or one/both nodes don't exist."
            )
        
        path_data = result[0]
        
        # Parse nodes
        nodes = [
            PathNode(
                id=n["id"],
                labels=n["labels"],
                properties={k: v for k, v in n["properties"].items() if k != "name"}
            )
            for n in path_data["path_nodes"]
        ]
        
        # Parse edges
        edges = [
            PathEdge(
                type=e["type"],
                source=e["source"],
                target=e["target"],
                properties=e.get("properties", {})
            )
            for e in path_data["path_edges"]
        ]
        
        return ShortestPathResponse(
            found=True,
            path_length=path_data["path_length"],
            nodes=nodes,
            edges=edges,
            message=f"Found path with {path_data['path_length']} hop(s) between '{start_node}' and '{end_node}'"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error finding shortest path: {str(e)}"
        )


@router.get("/key-suspects", response_model=KeySuspectsResponse)
async def find_key_suspects(
    limit: int = Query(default=5, ge=1, le=20, description="Number of suspects to return")
):
    """
    Find the most connected Person nodes using degree centrality.
    
    This identifies key suspects by analyzing who has the most connections
    in the crime network. Uses degree centrality (total incoming + outgoing relationships).
    
    Returns the top N persons with the most connections, along with who they're connected to.
    """
    graph = get_neo4j_graph()
    
    # Cypher query to find most connected Person nodes using degree centrality
    query = """
    MATCH (p:Person)
    OPTIONAL MATCH (p)-[r]-()
    WITH p, count(DISTINCT r) AS connection_count
    ORDER BY connection_count DESC
    LIMIT $limit
    
    // Get the names of connected entities
    CALL {
        WITH p
        MATCH (p)-[]->(other)
        RETURN collect(DISTINCT other.name) AS outgoing
    }
    CALL {
        WITH p
        MATCH (p)<-[]-(other)
        RETURN collect(DISTINCT other.name) AS incoming
    }
    
    RETURN p.name AS name, 
           connection_count AS connections,
           outgoing + incoming AS connected_to
    """
    
    # Simpler fallback query if the above fails
    simple_query = """
    MATCH (p:Person)
    OPTIONAL MATCH (p)-[r]-()
    WITH p, count(DISTINCT r) AS connection_count
    ORDER BY connection_count DESC
    LIMIT $limit
    OPTIONAL MATCH (p)-[]-(other)
    WITH p, connection_count, collect(DISTINCT other.name) AS connected_names
    RETURN p.name AS name, 
           connection_count AS connections,
           connected_names AS connected_to
    """
    
    try:
        # Try the detailed query first
        try:
            result = graph.query(query, {"limit": limit})
        except:
            # Fall back to simpler query
            result = graph.query(simple_query, {"limit": limit})
        
        if not result:
            return KeySuspectsResponse(
                suspects=[],
                analysis_method="Degree Centrality",
                message="No Person nodes found in the database."
            )
        
        suspects = [
            SuspectInfo(
                name=row["name"],
                connections=row["connections"],
                connected_to=[n for n in row.get("connected_to", []) if n is not None]
            )
            for row in result
        ]
        
        return KeySuspectsResponse(
            suspects=suspects,
            analysis_method="Degree Centrality",
            message=f"Found top {len(suspects)} most connected persons in the crime network."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error finding key suspects: {str(e)}"
        )


@router.post("/query", response_model=QueryResponse)
async def natural_language_query(request: NaturalLanguageQuery):
    """
    Answer natural language questions about the crime data using GraphCypherQAChain.
    
    This endpoint converts natural language questions to Cypher queries,
    executes them against the Neo4j database, and returns human-readable answers.
    
    Examples:
        - "Who was murdered?"
        - "What organizations are in the database?"
        - "How is John Smith connected to The Syndicate?"
        - "Who is investigating the crime?"
    """
    graph = get_neo4j_graph()
    
    try:
        # Refresh schema to ensure LLM has latest graph structure
        graph.refresh_schema()
        
        # Initialize LLM
        llm = get_llm()
        
        # Create GraphCypherQAChain
        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            verbose=False,
            return_intermediate_steps=True,
            validate_cypher=True,
            allow_dangerous_requests=True,  # Required for Neo4j queries
        )
        
        # Execute the query
        result = chain.invoke({"query": request.question})
        
        # Extract Cypher query from intermediate steps
        cypher_query = ""
        if "intermediate_steps" in result:
            for step in result["intermediate_steps"]:
                if isinstance(step, dict) and "query" in step:
                    cypher_query = step["query"]
                    break
                elif isinstance(step, str) and step.strip().upper().startswith(("MATCH", "RETURN", "WITH", "CALL")):
                    cypher_query = step
                    break
        
        return QueryResponse(
            question=request.question,
            cypher_query=cypher_query,
            answer=result.get("result", "No answer found."),
            success=True,
            message="Query executed successfully."
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # Provide helpful error messages
        if "no procedure" in error_msg.lower():
            error_msg = "Database procedure not available. Please ensure APOC is installed."
        elif "syntax" in error_msg.lower():
            error_msg = f"Query syntax error: {error_msg}"
        
        return QueryResponse(
            question=request.question,
            cypher_query="",
            answer=f"I encountered an error processing your question: {error_msg}",
            success=False,
            message=f"Failed to process query: {error_msg}"
        )


@router.get("/graph-summary")
async def get_graph_summary():
    """
    Get a summary of the crime investigation graph.
    
    Returns counts of different node types and relationships,
    useful for understanding the scope of the investigation data.
    """
    graph = get_neo4j_graph()
    
    query = """
    CALL {
        MATCH (n)
        RETURN count(n) AS total_nodes
    }
    CALL {
        MATCH ()-[r]->()
        RETURN count(r) AS total_relationships
    }
    CALL {
        MATCH (p:Person) RETURN count(p) AS persons
    }
    CALL {
        MATCH (o:Organization) RETURN count(o) AS organizations
    }
    CALL {
        MATCH (l:Location) RETURN count(l) AS locations
    }
    CALL {
        MATCH (c:Crime) RETURN count(c) AS crimes
    }
    CALL {
        MATCH (e:Event) RETURN count(e) AS events
    }
    RETURN total_nodes, total_relationships, persons, organizations, locations, crimes, events
    """
    
    try:
        result = graph.query(query)
        
        if result:
            data = result[0]
            return {
                "summary": {
                    "total_nodes": data["total_nodes"],
                    "total_relationships": data["total_relationships"],
                    "node_breakdown": {
                        "persons": data["persons"],
                        "organizations": data["organizations"],
                        "locations": data["locations"],
                        "crimes": data["crimes"],
                        "events": data["events"]
                    }
                },
                "message": "Graph summary retrieved successfully."
            }
        
        return {
            "summary": {
                "total_nodes": 0,
                "total_relationships": 0,
                "node_breakdown": {}
            },
            "message": "No data in the graph."
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting graph summary: {str(e)}"
        )


@router.get("/full-graph")
async def get_full_graph(
    investigation_id: Optional[str] = Query(None, description="Filter graph by investigation ID")
):
    """
    Fetch the graph data (nodes and relationships) for a specific investigation.
    
    If investigation_id is provided, returns only nodes and relationships
    belonging to that investigation. Otherwise returns all data.
    This allows each investigation to have isolated graph data.
    """
    graph = get_neo4j_graph()
    
    # Build queries based on whether investigation_id is provided
    if investigation_id:
        # Get nodes for specific investigation
        nodes_query = """
        MATCH (n {investigation_id: $investigation_id})
        RETURN 
            elementId(n) AS id,
            n.name AS name,
            labels(n) AS labels,
            properties(n) AS properties
        """
        
        # Get relationships for specific investigation
        rels_query = """
        MATCH (a {investigation_id: $investigation_id})-[r]->(b {investigation_id: $investigation_id})
        RETURN 
            elementId(r) AS id,
            a.name AS source,
            b.name AS target,
            type(r) AS type,
            properties(r) AS properties
        """
        params = {"investigation_id": investigation_id}
    else:
        # Get all nodes
        nodes_query = """
        MATCH (n)
        RETURN 
            elementId(n) AS id,
            n.name AS name,
            labels(n) AS labels,
            properties(n) AS properties
        """
        
        # Get all relationships
        rels_query = """
        MATCH (a)-[r]->(b)
        RETURN 
            elementId(r) AS id,
            a.name AS source,
            b.name AS target,
            type(r) AS type,
            properties(r) AS properties
        """
        params = {}
    
    try:
        nodes_result = graph.query(nodes_query, params)
        rels_result = graph.query(rels_query, params)
        
        # Transform nodes
        nodes = []
        for n in nodes_result:
            label = n.get("name") or n.get("id", "Unknown")
            node_type = n["labels"][0] if n["labels"] else "Entity"
            nodes.append({
                "id": str(n["id"]),
                "label": label,
                "type": node_type,
                "properties": n.get("properties", {})
            })
        
        # Transform relationships
        relationships = []
        for r in rels_result:
            relationships.append({
                "id": str(r["id"]),
                "source": r["source"],
                "target": r["target"],
                "type": r["type"],
                "properties": r.get("properties", {})
            })
        
        return {
            "nodes": nodes,
            "relationships": relationships,
            "total_nodes": len(nodes),
            "total_relationships": len(relationships),
            "message": "Full graph data retrieved successfully."
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching full graph: {str(e)}"
        )


# ============================================================================
# NetworkX Analysis Endpoints
# ============================================================================

@router.get("/analyze/most-important", response_model=MostImportantResponse)
async def analyze_most_important(
    investigation_id: Optional[str] = Query(None, description="Filter by investigation ID"),
    top_n: int = Query(10, ge=1, le=50, description="Number of top influencers to return"),
    node_type: Optional[str] = Query(None, description="Filter by node type (e.g., Person, Organization)")
):
    """
    Find the most important/influential nodes using betweenness centrality.
    
    Betweenness centrality identifies nodes that act as bridges between different
    parts of the network. High betweenness = important connector/broker.
    
    In a crime investigation context:
    - High betweenness Person = key intermediary, potential informant or mastermind
    - High betweenness Organization = central hub connecting different groups
    - High betweenness Location = meeting point, crime scene, or strategic location
    """
    try:
        G, node_data = load_graph_to_networkx(investigation_id)
        
        if G.number_of_nodes() == 0:
            return MostImportantResponse(
                influencers=[],
                analysis_method="betweenness_centrality",
                total_nodes_analyzed=0,
                total_edges_analyzed=0,
                message="No nodes found in the graph to analyze."
            )
        
        # Calculate betweenness centrality
        betweenness = nx.betweenness_centrality(G)
        
        # Filter by node type if specified
        if node_type:
            betweenness = {
                k: v for k, v in betweenness.items()
                if node_data.get(k, {}).get("type", "").lower() == node_type.lower()
            }
        
        # Sort by centrality score
        sorted_nodes = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]
        
        influencers = []
        for name, score in sorted_nodes:
            ndata = node_data.get(name, {})
            ntype = ndata.get("type", "Entity")
            degree = G.degree(name)
            
            # Find what communities/groups this node bridges between
            neighbors_by_type = get_neighbors_by_type(G, name, node_data)
            bridges = []
            for t, members in neighbors_by_type.items():
                if len(members) > 0:
                    bridges.append(f"{t}s: {', '.join(members[:3])}" + ("..." if len(members) > 3 else ""))
            
            # Generate description based on metrics
            if score > 0.3:
                desc = f"Critical connector - bridges multiple network clusters"
            elif score > 0.1:
                desc = f"Important intermediary with {degree} direct connections"
            elif score > 0.01:
                desc = f"Moderate influence with connections to {len(neighbors_by_type)} different entity types"
            else:
                desc = f"Peripheral node with {degree} connection(s)"
            
            influencers.append(InfluencerInfo(
                name=name,
                node_type=ntype,
                betweenness_score=round(score, 4),
                degree=degree,
                description=desc,
                bridges_between=bridges
            ))
        
        return MostImportantResponse(
            influencers=influencers,
            analysis_method="betweenness_centrality",
            total_nodes_analyzed=G.number_of_nodes(),
            total_edges_analyzed=G.number_of_edges(),
            message=f"Found {len(influencers)} influential nodes using betweenness centrality analysis."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing graph importance: {str(e)}"
        )


@router.get("/analyze/communities", response_model=CommunitiesResponse)
async def analyze_communities(
    investigation_id: Optional[str] = Query(None, description="Filter by investigation ID"),
    min_community_size: int = Query(2, ge=1, description="Minimum members to include community")
):
    """
    Detect communities/factions in the network using Greedy Modularity algorithm.
    
    Community detection reveals groups of nodes that are more densely connected
    to each other than to the rest of the network.
    
    In a crime investigation context:
    - Separate criminal organizations or gangs
    - Family/social groups
    - Business networks
    - Victim clusters
    """
    try:
        G, node_data = load_graph_to_networkx(investigation_id)
        
        if G.number_of_nodes() == 0:
            return CommunitiesResponse(
                communities=[],
                analysis_method="greedy_modularity",
                modularity_score=0.0,
                total_communities=0,
                message="No nodes found in the graph to analyze."
            )
        
        # Remove isolated nodes for community detection
        connected_nodes = [n for n in G.nodes() if G.degree(n) > 0]
        G_connected = G.subgraph(connected_nodes).copy()
        
        if G_connected.number_of_nodes() < 2:
            return CommunitiesResponse(
                communities=[],
                analysis_method="greedy_modularity",
                modularity_score=0.0,
                total_communities=0,
                message="Not enough connected nodes for community detection."
            )
        
        # Use Greedy Modularity community detection
        communities_gen = greedy_modularity_communities(G_connected)
        communities_list = [set(c) for c in communities_gen]
        
        # Calculate modularity score
        mod_score = modularity(G_connected, communities_list)
        
        # Build response
        communities = []
        for idx, community_nodes in enumerate(communities_list):
            if len(community_nodes) < min_community_size:
                continue
            
            # Build member list with connection counts
            members = []
            subgraph = G_connected.subgraph(community_nodes)
            
            for node in community_nodes:
                ndata = node_data.get(node, {})
                internal_connections = subgraph.degree(node)
                members.append(CommunityMember(
                    name=node,
                    node_type=ndata.get("type", "Entity"),
                    connections_in_community=internal_connections
                ))
            
            # Sort members by connections (most connected first)
            members.sort(key=lambda x: x.connections_in_community, reverse=True)
            
            # Generate label based on most connected member or dominant type
            type_counts: Dict[str, int] = defaultdict(int)
            for m in members:
                type_counts[m.node_type] += 1
            dominant_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else "Entity"
            
            leader = members[0].name if members else "Unknown"
            label = f"{dominant_type} cluster centered on {leader}"
            
            communities.append(Community(
                community_id=idx + 1,
                size=len(members),
                members=members,
                label=label
            ))
        
        # Sort communities by size
        communities.sort(key=lambda x: x.size, reverse=True)
        
        return CommunitiesResponse(
            communities=communities,
            analysis_method="greedy_modularity",
            modularity_score=round(mod_score, 4),
            total_communities=len(communities),
            message=f"Detected {len(communities)} communities with modularity score {mod_score:.4f}."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error detecting communities: {str(e)}"
        )


@router.get("/analyze/path", response_model=DetailedPathResponse)
async def analyze_path(
    start_node: str = Query(..., description="Name of the starting node"),
    end_node: str = Query(..., description="Name of the ending node"),
    investigation_id: Optional[str] = Query(None, description="Filter by investigation ID")
):
    """
    Find and describe the shortest path between two nodes with natural language description.
    
    Enhanced version of shortest-path that:
    1. Uses NetworkX for path finding
    2. Includes relationship types in the path
    3. Generates a human-readable narrative of the connection
    """
    try:
        G, node_data = load_graph_to_networkx(investigation_id)
        
        if start_node not in G.nodes:
            return DetailedPathResponse(
                found=False,
                start_node=start_node,
                end_node=end_node,
                message=f"Start node '{start_node}' not found in the graph."
            )
        
        if end_node not in G.nodes:
            return DetailedPathResponse(
                found=False,
                start_node=start_node,
                end_node=end_node,
                message=f"End node '{end_node}' not found in the graph."
            )
        
        # Check if path exists
        if not nx.has_path(G, start_node, end_node):
            return DetailedPathResponse(
                found=False,
                start_node=start_node,
                end_node=end_node,
                message=f"No path exists between '{start_node}' and '{end_node}'. They are in disconnected parts of the network."
            )
        
        # Find shortest path
        path = nx.shortest_path(G, start_node, end_node)
        
        # Build detailed steps
        steps = []
        for i in range(len(path) - 1):
            from_node = path[i]
            to_node = path[i + 1]
            
            # Get relationship type from edge data
            edge_data = G.get_edge_data(from_node, to_node, {})
            rel_type = edge_data.get("rel_type", "CONNECTED_TO")
            
            from_type = node_data.get(from_node, {}).get("type", "Entity")
            to_type = node_data.get(to_node, {}).get("type", "Entity")
            
            steps.append(PathStep(
                from_node=from_node,
                relationship=rel_type,
                to_node=to_node,
                from_type=from_type,
                to_type=to_type
            ))
        
        # Generate natural language description
        description_parts = []
        description_parts.append(f"Connection path from {start_node} to {end_node}:")
        
        for i, step in enumerate(steps, 1):
            rel_readable = step.relationship.replace("_", " ").lower()
            description_parts.append(
                f"  {i}. {step.from_node} ({step.from_type}) --[{rel_readable}]--> {step.to_node} ({step.to_type})"
            )
        
        # Add summary
        if len(steps) == 1:
            description_parts.append(f"\nDirect connection: {start_node} and {end_node} are directly linked.")
        elif len(steps) == 2:
            middle = steps[0].to_node
            description_parts.append(f"\nOne degree of separation through {middle}.")
        else:
            intermediaries = [s.to_node for s in steps[:-1]]
            description_parts.append(f"\n{len(steps)-1} intermediaries: {' → '.join(intermediaries)}")
        
        return DetailedPathResponse(
            found=True,
            start_node=start_node,
            end_node=end_node,
            path_length=len(steps),
            steps=steps,
            path_description="\n".join(description_parts),
            all_nodes=path,
            message=f"Found path with {len(steps)} hop(s)."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing path: {str(e)}"
        )
