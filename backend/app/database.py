from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase
from app.config import get_settings
from typing import Optional

# Global Neo4j graph connection
_graph: Optional[Neo4jGraph] = None
_driver = None


def get_neo4j_driver():
    """Get or create the Neo4j driver for direct queries."""
    global _driver
    
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password)
        )
    
    return _driver


def get_neo4j_graph() -> Neo4jGraph:
    """
    Get or create the global Neo4jGraph connection.
    Uses singleton pattern to maintain a single connection.
    """
    global _graph
    
    if _graph is None:
        settings = get_settings()
        _graph = Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            refresh_schema=False,  # Don't refresh schema on init for empty DBs
        )
    
    return _graph


def close_neo4j_connection() -> None:
    """Close the Neo4j connection gracefully."""
    global _graph, _driver
    
    if _driver is not None:
        _driver.close()
        _driver = None
    
    if _graph is not None:
        _graph = None


def verify_neo4j_connection() -> dict:
    """
    Verify the Neo4j connection is active using the native driver.
    Returns connection status and basic info.
    """
    try:
        driver = get_neo4j_driver()
        # Verify connectivity
        driver.verify_connectivity()
        
        # Execute a simple query to verify connection
        with driver.session(database=get_settings().neo4j_database) as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            
            if record:
                return {
                    "connected": True,
                    "message": "Neo4j connection is active",
                    "database": get_settings().neo4j_database
                }
            else:
                return {
                    "connected": False,
                    "message": "Neo4j query returned no results"
                }
    except Exception as e:
        error_msg = str(e)
        # Check for common Neo4j Aura issues
        if "routing information" in error_msg.lower():
            error_msg = (
                "Unable to connect to Neo4j Aura. This may happen if: "
                "1) The instance is paused (free instances auto-pause after inactivity), "
                "2) The instance ID is incorrect, or "
                "3) There are network/firewall issues. "
                f"Original error: {str(e)}"
            )
        return {
            "connected": False,
            "message": f"Neo4j connection failed: {error_msg}"
        }
