"""
Robust Data Ingestion Pipeline for Sherlock

This module provides a custom extraction pipeline that:
1. Uses Pydantic schemas with structured output for consistent entity extraction
2. Filters out pronouns, generic terms, and junk nodes
3. Normalizes entity names to prevent duplicates
4. Uses MERGE operations in Neo4j to handle duplicates gracefully
"""

from langchain_openai import ChatOpenAI
from typing import List, Optional, Set
from pydantic import BaseModel, Field
from enum import Enum
import re

from app.config import get_settings
from app.database import get_neo4j_graph


# =============================================================================
# Enums for Strict Type Checking
# =============================================================================

class NodeType(str, Enum):
    """Allowed node types in the crime investigation graph."""
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    EVENT = "Event"
    CRIME = "Crime"
    EVIDENCE = "Evidence"
    VEHICLE = "Vehicle"
    WEAPON = "Weapon"


class RelationshipType(str, Enum):
    """Allowed relationship types in the crime investigation graph."""
    KNOWS = "KNOWS"
    INVOLVED_IN = "INVOLVED_IN"
    LOCATED_AT = "LOCATED_AT"
    PERPETRATED = "PERPETRATED"
    VICTIM_OF = "VICTIM_OF"
    WITNESSED = "WITNESSED"
    OWNS = "OWNS"
    WORKS_FOR = "WORKS_FOR"
    RELATED_TO = "RELATED_TO"
    MEMBER_OF = "MEMBER_OF"
    CONNECTED_TO = "CONNECTED_TO"
    FOUND_AT = "FOUND_AT"
    USED_IN = "USED_IN"


# =============================================================================
# Pydantic Schemas for Structured Extraction
# =============================================================================

class ExtractedNode(BaseModel):
    """A single extracted entity node."""
    id: str = Field(
        ..., 
        description="The full proper noun name of the entity (e.g., 'Thomas Vane', not 'Thomas'). Must be specific and complete."
    )
    type: str = Field(
        ..., 
        description="The type/category: Person, Organization, Location, Event, Crime, Evidence, Vehicle, or Weapon"
    )
    description: Optional[str] = Field(
        None, 
        description="A brief description of this entity based on the text context"
    )
    date: Optional[str] = Field(
        None,
        description="For Event or Crime nodes: The date/time when this occurred in ISO format (YYYY-MM-DD) or relative description. Extract any temporal information mentioned."
    )
    date_order: Optional[int] = Field(
        None,
        description="A numeric order for sequencing events (1=first, 2=second, etc.) based on the narrative timeline"
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence score from 0.0 to 1.0 indicating extraction certainty"
    )
    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names or references to this entity found in the text"
    )


class ExtractedRelationship(BaseModel):
    """A single extracted relationship between entities."""
    source: str = Field(
        ..., 
        description="The ID (full proper noun) of the source entity"
    )
    target: str = Field(
        ..., 
        description="The ID (full proper noun) of the target entity"
    )
    type: str = Field(
        ..., 
        description="The relationship type: KNOWS, INVOLVED_IN, LOCATED_AT, PERPETRATED, VICTIM_OF, WITNESSED, OWNS, WORKS_FOR, RELATED_TO, MEMBER_OF, CONNECTED_TO, FOUND_AT, or USED_IN"
    )
    evidence: Optional[str] = Field(
        None, 
        description="The text snippet that supports this relationship"
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence score for this relationship"
    )


class GraphExtraction(BaseModel):
    """Complete graph extraction result from a document."""
    nodes: List[ExtractedNode] = Field(
        default_factory=list,
        description="List of extracted entity nodes"
    )
    relationships: List[ExtractedRelationship] = Field(
        default_factory=list,
        description="List of extracted relationships between entities"
    )


# =============================================================================
# Request/Response Models
# =============================================================================

class IngestRequest(BaseModel):
    """Request model for document ingestion."""
    text: str = Field(..., description="The text content to ingest and convert to graph")
    source: Optional[str] = Field(None, description="Optional source identifier for the document")
    investigation_id: Optional[str] = Field(None, description="Investigation ID to tag data with for isolation")


class IngestResponse(BaseModel):
    """Response model for document ingestion."""
    success: bool
    message: str
    nodes_created: int = 0
    relationships_created: int = 0
    nodes_filtered: int = 0
    node_types: List[str] = []
    relationship_types: List[str] = []


# =============================================================================
# Constants for Filtering
# =============================================================================

# Pronouns and generic terms to filter out
BLOCKED_TERMS: Set[str] = {
    # Pronouns
    "he", "she", "it", "they", "them", "him", "her", "his", "hers", "its",
    "we", "us", "our", "ours", "you", "your", "yours", "i", "me", "my", "mine",
    "this", "that", "these", "those", "who", "whom", "whose", "which", "what",
    "someone", "somebody", "anyone", "anybody", "everyone", "everybody",
    "no one", "nobody", "something", "anything", "everything", "nothing",
    
    # Generic terms
    "the company", "the organization", "the driver", "the victim", "the suspect",
    "the witness", "the detective", "the officer", "the man", "the woman",
    "the person", "the building", "the place", "the location", "the event",
    "the crime", "a man", "a woman", "a person", "unknown", "unidentified",
    "the group", "the team", "the agency", "the department", "the police",
    "the car", "the vehicle", "an individual", "the individual",
    "suspect", "victim", "witness", "perpetrator", "criminal",
    
    # Single letters and numbers
    "a", "b", "c", "x", "y", "z", "1", "2", "3",
}

# Minimum length for valid node IDs
MIN_NODE_ID_LENGTH = 3

# Valid node and relationship types
VALID_NODE_TYPES = {nt.value for nt in NodeType}
VALID_REL_TYPES = {rt.value for rt in RelationshipType}


# =============================================================================
# System Prompt for LLM
# =============================================================================

EXTRACTION_SYSTEM_PROMPT = """You are an expert crime investigation analyst specializing in extracting structured information from case files and evidence documents.

Your task is to extract entities (nodes) and relationships from the given text to build a knowledge graph for crime investigation.

## CRITICAL RULES FOR ENTITY EXTRACTION:

1. **NEVER create nodes for pronouns**: Do not extract He, She, It, They, Them, etc. as entities.

2. **NEVER create nodes for generic terms**: Do not extract "The Company", "The Driver", "The Victim", "A Man", "The Suspect", etc. Only extract specific, named entities.

3. **Use FULL PROPER NOUNS as IDs**: 
   - CORRECT: "Thomas Vane", "Sarah Mitchell", "Obsidian Industries"
   - WRONG: "Thomas", "Vane", "The Company", "Mitchell"

4. **Handle multiple references**: If someone is referred to as "Detective Sarah Mitchell" and later as "Mitchell" or "Sarah", use "Sarah Mitchell" as the ID and add aliases.

5. **Be specific with locations**: Use "123 Oak Street, Manhattan" not just "the house" or "the location".

6. **Include confidence scores**: Lower scores (0.5-0.7) for inferred relationships, higher scores (0.8-1.0) for explicitly stated facts.

7. **Provide evidence**: For relationships, include the text snippet that supports the connection.

8. **EXTRACT DATES FOR EVENTS AND CRIMES**: This is critical for timeline reconstruction.
   - For Event and Crime nodes, ALWAYS extract the date if mentioned
   - Use ISO format (YYYY-MM-DD) when possible, e.g., "2024-03-15"
   - If only month/year given, use first day: "2024-03-01"
   - If relative (e.g., "last Tuesday", "three days ago"), note the relative description
   - Assign date_order (1, 2, 3...) to sequence events chronologically

## NODE TYPES (use exactly these values):
- Person: Named individuals (victims, suspects, witnesses, detectives)
- Organization: Companies, criminal groups, agencies, institutions
- Location: Specific addresses, buildings, cities, landmarks
- Event: Named events, incidents, meetings with dates/times - MUST include date field
- Crime: Specific criminal acts (murder, theft, fraud) - MUST include date field
- Evidence: Physical evidence items (weapons, documents, forensics)
- Vehicle: Cars, boats, planes with identifying info
- Weapon: Specific weapons used in crimes

## RELATIONSHIP TYPES (use exactly these values):
- KNOWS: Personal acquaintance between people
- INVOLVED_IN: Connection to events or crimes
- LOCATED_AT: Physical presence at a location
- PERPETRATED: Committed a crime
- VICTIM_OF: Was victimized by a crime
- WITNESSED: Saw an event or crime
- OWNS: Ownership of property, vehicles, weapons
- WORKS_FOR: Employment relationship
- RELATED_TO: Family or general connection
- MEMBER_OF: Membership in organization
- CONNECTED_TO: Financial or communication link
- FOUND_AT: Evidence discovered at location
- USED_IN: Item used in crime/event

## TIMELINE EXTRACTION EXAMPLES:
- "The murder occurred on March 15, 2024" → date: "2024-03-15", date_order: 1
- "They met at the bar the night before" → date: "2024-03-14" (inferred), date_order: 1
- "Three weeks earlier, the debt was incurred" → date: "2024-02-22" (calculate), date_order: 1
- "First the meeting, then the argument, finally the shooting" → date_order: 1, 2, 3 respectively

Extract ALL relevant entities and relationships from the text. Be thorough but precise. PAY SPECIAL ATTENTION TO TEMPORAL/DATE INFORMATION FOR TIMELINE RECONSTRUCTION."""


# =============================================================================
# LLM Initialization
# =============================================================================

def get_extraction_llm() -> ChatOpenAI:
    """
    Initialize ChatOpenAI with Grok 4.1 Fast (Free) via OpenRouter.
    Configured for structured output extraction.
    """
    settings = get_settings()
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        model="x-ai/grok-4.1-fast:free",
        temperature=0,
    )


# =============================================================================
# Data Cleaning Functions
# =============================================================================

def normalize_text(text: str) -> str:
    """Convert text to Title Case and clean whitespace."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    # Convert to title case
    return text.title()


def is_valid_node_id(node_id: str) -> bool:
    """
    Check if a node ID is valid (not a blocked term, long enough, etc.)
    
    Args:
        node_id: The node ID to validate
        
    Returns:
        True if valid, False if should be filtered out
    """
    if not node_id:
        return False
    
    # Check minimum length
    if len(node_id.strip()) < MIN_NODE_ID_LENGTH:
        return False
    
    # Check against blocked terms (case-insensitive)
    if node_id.lower().strip() in BLOCKED_TERMS:
        return False
    
    # Check if it's just punctuation or numbers
    if not re.search(r'[a-zA-Z]', node_id):
        return False
    
    # Check for generic patterns
    generic_patterns = [
        r'^the\s+\w+$',  # "the something"
        r'^a\s+\w+$',    # "a something"
        r'^an\s+\w+$',   # "an something"
        r'^\w+\s+#?\d+$', # "something 123" or "something #123"
    ]
    
    for pattern in generic_patterns:
        if re.match(pattern, node_id.lower().strip()):
            return False
    
    return True


def normalize_node_type(node_type: str) -> str:
    """Normalize node type to valid enum value."""
    normalized = node_type.strip().title()
    if normalized in VALID_NODE_TYPES:
        return normalized
    # Default to Person for unknown types
    return "Person"


def normalize_rel_type(rel_type: str) -> str:
    """Normalize relationship type to valid enum value."""
    normalized = rel_type.strip().upper().replace(" ", "_")
    if normalized in VALID_REL_TYPES:
        return normalized
    # Default to RELATED_TO for unknown types
    return "RELATED_TO"


def clean_graph_data(extraction: GraphExtraction) -> GraphExtraction:
    """
    Clean and normalize extracted graph data.
    
    This function:
    1. Filters out invalid nodes (short IDs, pronouns, generic terms)
    2. Normalizes all IDs to Title Case
    3. Removes relationships with invalid source/target
    4. Deduplicates nodes by normalized ID
    
    Args:
        extraction: Raw GraphExtraction from LLM
        
    Returns:
        Cleaned GraphExtraction
    """
    # Track valid node IDs for relationship filtering
    valid_node_ids: Set[str] = set()
    
    # Clean and deduplicate nodes
    seen_ids: Set[str] = set()
    cleaned_nodes: List[ExtractedNode] = []
    
    for node in extraction.nodes:
        # Normalize the ID
        normalized_id = normalize_text(node.id)
        
        # Skip invalid nodes
        if not is_valid_node_id(normalized_id):
            continue
        
        # Skip duplicates
        if normalized_id.lower() in seen_ids:
            continue
        
        seen_ids.add(normalized_id.lower())
        valid_node_ids.add(normalized_id.lower())
        
        # Normalize node type
        normalized_type = normalize_node_type(node.type)
        
        # Clamp confidence score
        confidence = max(0.0, min(1.0, node.confidence_score))
        
        # Create cleaned node
        cleaned_node = ExtractedNode(
            id=normalized_id,
            type=normalized_type,
            description=node.description,
            date=node.date,
            date_order=node.date_order,
            confidence_score=confidence,
            aliases=[normalize_text(a) for a in node.aliases if is_valid_node_id(a)]
        )
        cleaned_nodes.append(cleaned_node)
    
    # Clean relationships - only keep those with valid source and target
    cleaned_relationships: List[ExtractedRelationship] = []
    seen_rels: Set[str] = set()
    
    for rel in extraction.relationships:
        # Normalize source and target
        normalized_source = normalize_text(rel.source)
        normalized_target = normalize_text(rel.target)
        
        # Skip if source or target is invalid
        if not is_valid_node_id(normalized_source) or not is_valid_node_id(normalized_target):
            continue
        
        # Skip self-referential relationships
        if normalized_source.lower() == normalized_target.lower():
            continue
        
        # Normalize relationship type
        normalized_rel_type = normalize_rel_type(rel.type)
        
        # Create unique key for deduplication
        rel_key = f"{normalized_source.lower()}|{normalized_rel_type}|{normalized_target.lower()}"
        if rel_key in seen_rels:
            continue
        seen_rels.add(rel_key)
        
        # Add nodes if they don't exist (from relationship endpoints)
        for node_id in [normalized_source, normalized_target]:
            if node_id.lower() not in valid_node_ids:
                valid_node_ids.add(node_id.lower())
                seen_ids.add(node_id.lower())
                # Infer node type from context
                inferred_type = "Person"  # Default
                cleaned_nodes.append(ExtractedNode(
                    id=node_id,
                    type=inferred_type,
                    description=None,
                    confidence_score=0.7  # Lower confidence for inferred nodes
                ))
        
        # Clamp confidence score
        confidence = max(0.0, min(1.0, rel.confidence_score))
        
        cleaned_rel = ExtractedRelationship(
            source=normalized_source,
            target=normalized_target,
            type=normalized_rel_type,
            evidence=rel.evidence,
            confidence_score=confidence
        )
        cleaned_relationships.append(cleaned_rel)
    
    return GraphExtraction(nodes=cleaned_nodes, relationships=cleaned_relationships)


# =============================================================================
# Neo4j Upload Functions
# =============================================================================

def upload_to_neo4j(
    extraction: GraphExtraction,
    source: Optional[str] = None,
    investigation_id: Optional[str] = None
) -> tuple:
    """
    Upload cleaned graph data to Neo4j using MERGE to prevent duplicates.
    
    Args:
        extraction: Cleaned GraphExtraction
        source: Optional source identifier
        investigation_id: Optional investigation ID for data isolation
        
    Returns:
        Tuple of (nodes_created, relationships_created, node_types, relationship_types)
    """
    graph = get_neo4j_graph()
    
    node_types_found: Set[str] = set()
    rel_types_found: Set[str] = set()
    nodes_created = 0
    relationships_created = 0
    
    # Upload nodes using MERGE
    for node in extraction.nodes:
        node_type = node.type
        node_types_found.add(node_type)
        
        # Build properties
        props = {
            "name": node.id,
            "confidence_score": node.confidence_score
        }
        if node.description:
            props["description"] = node.description
        if node.aliases:
            props["aliases"] = node.aliases
        if node.date:
            props["date"] = node.date
        if node.date_order is not None:
            props["date_order"] = node.date_order
        if source:
            props["source"] = source
        if investigation_id:
            props["investigation_id"] = investigation_id
        
        # Use MERGE with investigation_id for isolation
        if investigation_id:
            query = f"""
            MERGE (n:{node_type} {{name: $name, investigation_id: $investigation_id}})
            ON CREATE SET n += $properties, n.created_at = datetime()
            ON MATCH SET n += $properties, n.updated_at = datetime()
            RETURN n
            """
            params = {
                "name": node.id, 
                "investigation_id": investigation_id, 
                "properties": props
            }
        else:
            query = f"""
            MERGE (n:{node_type} {{name: $name}})
            ON CREATE SET n += $properties, n.created_at = datetime()
            ON MATCH SET n += $properties, n.updated_at = datetime()
            RETURN n
            """
            params = {"name": node.id, "properties": props}
        
        try:
            result = graph.query(query, params)
            if result:
                nodes_created += 1
        except Exception as e:
            print(f"Error creating node {node.id}: {e}")
    
    # Upload relationships using MERGE
    for rel in extraction.relationships:
        rel_type = rel.type
        rel_types_found.add(rel_type)
        
        # Build relationship properties
        rel_props = {
            "confidence_score": rel.confidence_score
        }
        if rel.evidence:
            rel_props["evidence"] = rel.evidence
        if investigation_id:
            rel_props["investigation_id"] = investigation_id
        
        # Use MERGE for relationships with investigation_id isolation
        if investigation_id:
            query = f"""
            MATCH (a {{name: $source, investigation_id: $investigation_id}})
            MATCH (b {{name: $target, investigation_id: $investigation_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET r += $properties, r.created_at = datetime()
            ON MATCH SET r += $properties, r.updated_at = datetime()
            RETURN r
            """
            params = {
                "source": rel.source,
                "target": rel.target,
                "investigation_id": investigation_id,
                "properties": rel_props
            }
        else:
            query = f"""
            MATCH (a {{name: $source}})
            MATCH (b {{name: $target}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET r += $properties, r.updated_at = datetime()
            RETURN r
            """
            params = {
                "source": rel.source,
                "target": rel.target,
                "properties": rel_props
            }
        
        try:
            result = graph.query(query, params)
            if result:
                relationships_created += 1
        except Exception as e:
            print(f"Error creating relationship {rel.source} -[{rel_type}]-> {rel.target}: {e}")
    
    return nodes_created, relationships_created, list(node_types_found), list(rel_types_found)


# =============================================================================
# Main Extraction Function
# =============================================================================

def extract_graph_from_text(text: str) -> GraphExtraction:
    """
    Extract graph data from text using LLM with structured output.
    
    Args:
        text: The text to extract entities and relationships from
        
    Returns:
        GraphExtraction containing nodes and relationships
    """
    llm = get_extraction_llm()
    
    # Use structured output with Pydantic schema
    structured_llm = llm.with_structured_output(GraphExtraction)
    
    # Build the prompt
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract all entities and relationships from the following text:\n\n{text}"}
    ]
    
    # Get structured extraction
    extraction = structured_llm.invoke(messages)
    
    return extraction


# =============================================================================
# Public API Functions
# =============================================================================

async def ingest_document(
    text: str, 
    source: Optional[str] = None, 
    investigation_id: Optional[str] = None
) -> IngestResponse:
    """
    Ingest a text document and convert it to a knowledge graph.
    
    This function:
    1. Uses LLM with structured output to extract entities and relationships
    2. Cleans and normalizes the extracted data
    3. Uploads to Neo4j using MERGE operations
    
    Args:
        text: The text content to process
        source: Optional source identifier for tracking
        investigation_id: Optional investigation ID for data isolation
        
    Returns:
        IngestResponse with details about created nodes and relationships
    """
    try:
        # Step 1: Extract graph data using LLM
        raw_extraction = extract_graph_from_text(text)
        
        # Count raw nodes for reporting
        raw_node_count = len(raw_extraction.nodes)
        
        # Step 2: Clean and normalize the data
        cleaned_extraction = clean_graph_data(raw_extraction)
        
        # Calculate filtered count
        filtered_count = raw_node_count - len(cleaned_extraction.nodes)
        
        if not cleaned_extraction.nodes and not cleaned_extraction.relationships:
            return IngestResponse(
                success=True,
                message="No valid entities or relationships found in the document after filtering.",
                nodes_created=0,
                relationships_created=0,
                nodes_filtered=filtered_count
            )
        
        # Step 3: Upload to Neo4j
        nodes_created, relationships_created, node_types, rel_types = upload_to_neo4j(
            cleaned_extraction, source, investigation_id
        )
        
        # Refresh schema
        graph = get_neo4j_graph()
        graph.refresh_schema()
        
        return IngestResponse(
            success=True,
            message=f"Successfully ingested document. Created {nodes_created} nodes and {relationships_created} relationships. Filtered {filtered_count} invalid entities.",
            nodes_created=nodes_created,
            relationships_created=relationships_created,
            nodes_filtered=filtered_count,
            node_types=node_types,
            relationship_types=rel_types
        )
        
    except Exception as e:
        return IngestResponse(
            success=False,
            message=f"Failed to ingest document: {str(e)}",
            nodes_created=0,
            relationships_created=0
        )


async def ingest_multiple_documents(
    texts: List[str], 
    source: Optional[str] = None,
    investigation_id: Optional[str] = None
) -> IngestResponse:
    """
    Ingest multiple text documents at once.
    
    Args:
        texts: List of text contents to process
        source: Optional source identifier
        investigation_id: Optional investigation ID for data isolation
        
    Returns:
        IngestResponse with aggregated results
    """
    total_nodes = 0
    total_relationships = 0
    total_filtered = 0
    all_node_types: Set[str] = set()
    all_rel_types: Set[str] = set()
    
    for i, text in enumerate(texts):
        doc_source = f"{source}_{i}" if source else f"doc_{i}"
        
        try:
            result = await ingest_document(text, doc_source, investigation_id)
            
            if result.success:
                total_nodes += result.nodes_created
                total_relationships += result.relationships_created
                total_filtered += result.nodes_filtered
                all_node_types.update(result.node_types)
                all_rel_types.update(result.relationship_types)
        except Exception as e:
            print(f"Error processing document {i}: {e}")
    
    return IngestResponse(
        success=True,
        message=f"Successfully ingested {len(texts)} documents. Created {total_nodes} nodes and {total_relationships} relationships. Filtered {total_filtered} invalid entities.",
        nodes_created=total_nodes,
        relationships_created=total_relationships,
        nodes_filtered=total_filtered,
        node_types=list(all_node_types),
        relationship_types=list(all_rel_types)
    )


# =============================================================================
# Entity Resolution Models
# =============================================================================

class RefineGraphRequest(BaseModel):
    """Request model for graph refinement/entity resolution."""
    investigation_id: Optional[str] = Field(None, description="Investigation ID to refine (if None, refines all)")
    similarity_threshold: float = Field(default=0.8, ge=0.5, le=1.0, description="Minimum similarity score for merging (0.5-1.0)")
    remove_orphans: bool = Field(default=True, description="Whether to remove nodes with no relationships")
    dry_run: bool = Field(default=False, description="If True, only report what would be done without making changes")


class MergeCandidate(BaseModel):
    """A pair of nodes that are candidates for merging."""
    primary_node: str
    duplicate_node: str
    similarity_score: float
    match_reason: str


class RefineGraphResponse(BaseModel):
    """Response model for graph refinement."""
    success: bool
    message: str
    nodes_merged: int = 0
    orphans_removed: int = 0
    merge_candidates: List[MergeCandidate] = []
    dry_run: bool = False


# =============================================================================
# Entity Resolution Functions
# =============================================================================

def calculate_similarity(str1: str, str2: str) -> tuple[float, str]:
    """
    Calculate similarity between two strings using multiple methods.
    Returns (similarity_score, match_reason).
    
    Methods used:
    1. Exact match (after normalization)
    2. Containment (one string contains the other)
    3. Token overlap (Jaccard similarity)
    4. Edit distance ratio (Levenshtein-like)
    """
    # Normalize strings
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()
    
    # Exact match
    if s1 == s2:
        return 1.0, "exact_match"
    
    # One contains the other (e.g., "Mr. Vane" contains "Vane")
    if s1 in s2:
        return 0.9, f"'{str1}' contained in '{str2}'"
    if s2 in s1:
        return 0.9, f"'{str2}' contained in '{str1}'"
    
    # Check for title/honorific patterns
    honorifics = ["mr.", "mrs.", "ms.", "dr.", "detective", "officer", "agent", "prof.", "sir", "lady"]
    s1_clean = s1
    s2_clean = s2
    for h in honorifics:
        s1_clean = s1_clean.replace(h, "").strip()
        s2_clean = s2_clean.replace(h, "").strip()
    
    if s1_clean and s2_clean and (s1_clean == s2_clean or s1_clean in s2_clean or s2_clean in s1_clean):
        return 0.85, "honorific_variation"
    
    # Token-based similarity (Jaccard)
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    
    if tokens1 and tokens2:
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        jaccard = len(intersection) / len(union)
        
        if jaccard >= 0.5:
            return jaccard, f"token_overlap ({len(intersection)}/{len(union)} tokens)"
    
    # Character-level similarity (simple ratio)
    # Count matching characters in order
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0, "empty_string"
    
    matches = 0
    j = 0
    for char in s1:
        while j < len2:
            if s2[j] == char:
                matches += 1
                j += 1
                break
            j += 1
    
    ratio = (2.0 * matches) / (len1 + len2)
    if ratio >= 0.7:
        return ratio, "character_similarity"
    
    return 0.0, "no_match"


def find_duplicate_candidates(
    investigation_id: Optional[str] = None,
    similarity_threshold: float = 0.8
) -> List[MergeCandidate]:
    """
    Find pairs of nodes that are likely duplicates based on name similarity.
    
    Args:
        investigation_id: Optional filter for specific investigation
        similarity_threshold: Minimum similarity score to consider as duplicate
        
    Returns:
        List of MergeCandidate objects
    """
    graph = get_neo4j_graph()
    
    # Query to get all nodes grouped by type
    if investigation_id:
        query = """
        MATCH (n)
        WHERE n.investigation_id = $investigation_id
        RETURN n.name AS name, labels(n)[0] AS type, 
               n.confidence_score AS confidence,
               n.description AS description
        ORDER BY type, name
        """
        nodes = graph.query(query, {"investigation_id": investigation_id})
    else:
        query = """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN n.name AS name, labels(n)[0] AS type,
               n.confidence_score AS confidence,
               n.description AS description
        ORDER BY type, name
        """
        nodes = graph.query(query)
    
    # Group nodes by type
    nodes_by_type: dict = {}
    for node in nodes:
        node_type = node.get("type", "Unknown")
        if node_type not in nodes_by_type:
            nodes_by_type[node_type] = []
        nodes_by_type[node_type].append(node)
    
    # Find duplicates within each type
    candidates: List[MergeCandidate] = []
    
    for node_type, type_nodes in nodes_by_type.items():
        # Compare each pair
        for i, node1 in enumerate(type_nodes):
            for node2 in type_nodes[i + 1:]:
                name1 = node1.get("name", "")
                name2 = node2.get("name", "")
                
                if not name1 or not name2:
                    continue
                
                similarity, reason = calculate_similarity(name1, name2)
                
                if similarity >= similarity_threshold:
                    # Determine which is the primary (prefer longer, more complete names)
                    conf1 = node1.get("confidence", 0.5) or 0.5
                    conf2 = node2.get("confidence", 0.5) or 0.5
                    
                    # Score based on name length and confidence
                    score1 = len(name1) * conf1
                    score2 = len(name2) * conf2
                    
                    if score1 >= score2:
                        primary, duplicate = name1, name2
                    else:
                        primary, duplicate = name2, name1
                    
                    candidates.append(MergeCandidate(
                        primary_node=primary,
                        duplicate_node=duplicate,
                        similarity_score=round(similarity, 3),
                        match_reason=reason
                    ))
    
    return candidates


def merge_duplicate_nodes(
    primary_name: str,
    duplicate_name: str,
    investigation_id: Optional[str] = None
) -> bool:
    """
    Merge a duplicate node into the primary node.
    
    This:
    1. Transfers all relationships from duplicate to primary
    2. Merges any useful properties
    3. Deletes the duplicate node
    
    Args:
        primary_name: Name of the node to keep
        duplicate_name: Name of the node to merge and delete
        investigation_id: Optional investigation filter
        
    Returns:
        True if merge was successful
    """
    graph = get_neo4j_graph()
    
    try:
        # Build the filter condition
        if investigation_id:
            filter_condition = "AND n.investigation_id = $investigation_id"
            params = {
                "primary_name": primary_name,
                "duplicate_name": duplicate_name,
                "investigation_id": investigation_id
            }
        else:
            filter_condition = ""
            params = {
                "primary_name": primary_name,
                "duplicate_name": duplicate_name
            }
        
        # Step 1: Transfer incoming relationships from duplicate to primary
        transfer_incoming = f"""
        MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
        MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
        MATCH (other)-[r]->(dup)
        WHERE other <> primary
        WITH primary, dup, other, r, type(r) AS relType, properties(r) AS relProps
        CALL apoc.merge.relationship(other, relType, {{}}, relProps, primary, {{}}) YIELD rel
        DELETE r
        RETURN count(rel) AS transferred
        """
        
        # Step 2: Transfer outgoing relationships from duplicate to primary
        transfer_outgoing = f"""
        MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
        MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
        MATCH (dup)-[r]->(other)
        WHERE other <> primary
        WITH primary, dup, other, r, type(r) AS relType, properties(r) AS relProps
        CALL apoc.merge.relationship(primary, relType, {{}}, relProps, other, {{}}) YIELD rel
        DELETE r
        RETURN count(rel) AS transferred
        """
        
        # Fallback queries without APOC (manual relationship transfer)
        transfer_incoming_simple = f"""
        MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
        MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
        OPTIONAL MATCH (other)-[r]->(dup)
        WHERE other <> primary
        WITH primary, dup, collect({{other: other, r: r, type: type(r)}}) AS rels
        RETURN dup, primary, rels
        """
        
        # Try with APOC first, fall back to simple queries
        try:
            graph.query(transfer_incoming, params)
            graph.query(transfer_outgoing, params)
        except Exception:
            # Fallback: Manual relationship transfer using multiple queries
            # Get incoming relationships
            incoming_query = f"""
            MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
            MATCH (other)-[r]->(dup)
            RETURN other.name AS other_name, type(r) AS rel_type, properties(r) AS rel_props
            """
            incoming_rels = graph.query(incoming_query, params)
            
            for rel in incoming_rels:
                create_query = f"""
                MATCH (other {{name: $other_name}})
                MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
                MERGE (other)-[r:{rel['rel_type']}]->(primary)
                SET r += $rel_props
                """
                graph.query(create_query, {**params, "other_name": rel["other_name"], "rel_props": rel.get("rel_props", {})})
            
            # Get outgoing relationships
            outgoing_query = f"""
            MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
            MATCH (dup)-[r]->(other)
            RETURN other.name AS other_name, type(r) AS rel_type, properties(r) AS rel_props
            """
            outgoing_rels = graph.query(outgoing_query, params)
            
            for rel in outgoing_rels:
                create_query = f"""
                MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
                MATCH (other {{name: $other_name}})
                MERGE (primary)-[r:{rel['rel_type']}]->(other)
                SET r += $rel_props
                """
                graph.query(create_query, {**params, "other_name": rel["other_name"], "rel_props": rel.get("rel_props", {})})
        
        # Step 3: Merge aliases from duplicate into primary
        merge_aliases = f"""
        MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
        MATCH (primary {{name: $primary_name}}) {filter_condition.replace('n.', 'primary.')}
        WITH primary, dup,
             COALESCE(primary.aliases, []) AS existing_aliases,
             COALESCE(dup.aliases, []) + [$duplicate_name] AS new_aliases
        SET primary.aliases = existing_aliases + [x IN new_aliases WHERE NOT x IN existing_aliases]
        RETURN primary
        """
        graph.query(merge_aliases, params)
        
        # Step 4: Delete the duplicate node
        delete_query = f"""
        MATCH (dup {{name: $duplicate_name}}) {filter_condition.replace('n.', 'dup.')}
        DETACH DELETE dup
        RETURN count(dup) AS deleted
        """
        result = graph.query(delete_query, params)
        
        return True
        
    except Exception as e:
        print(f"Error merging nodes {duplicate_name} -> {primary_name}: {e}")
        return False


def remove_orphan_nodes(investigation_id: Optional[str] = None) -> int:
    """
    Remove nodes that have no relationships (orphans).
    
    Args:
        investigation_id: Optional filter for specific investigation
        
    Returns:
        Number of orphan nodes removed
    """
    graph = get_neo4j_graph()
    
    if investigation_id:
        query = """
        MATCH (n)
        WHERE n.investigation_id = $investigation_id
        AND NOT (n)--()
        WITH n, n.name AS name
        DELETE n
        RETURN count(n) AS removed
        """
        result = graph.query(query, {"investigation_id": investigation_id})
    else:
        query = """
        MATCH (n)
        WHERE NOT (n)--()
        AND n.name IS NOT NULL
        WITH n, n.name AS name
        DELETE n
        RETURN count(n) AS removed
        """
        result = graph.query(query)
    
    return result[0]["removed"] if result else 0


async def refine_graph(request: RefineGraphRequest) -> RefineGraphResponse:
    """
    Refine the graph by merging duplicates and removing orphans.
    
    This is the "Entity Resolution" function that cleans up the graph.
    
    Args:
        request: RefineGraphRequest with options
        
    Returns:
        RefineGraphResponse with details of changes made
    """
    try:
        # Step 1: Find duplicate candidates
        candidates = find_duplicate_candidates(
            investigation_id=request.investigation_id,
            similarity_threshold=request.similarity_threshold
        )
        
        if request.dry_run:
            # Just report what would be done
            orphan_count = 0
            if request.remove_orphans:
                graph = get_neo4j_graph()
                if request.investigation_id:
                    orphan_query = """
                    MATCH (n)
                    WHERE n.investigation_id = $investigation_id
                    AND NOT (n)--()
                    RETURN count(n) AS count
                    """
                    result = graph.query(orphan_query, {"investigation_id": request.investigation_id})
                else:
                    orphan_query = """
                    MATCH (n)
                    WHERE NOT (n)--()
                    AND n.name IS NOT NULL
                    RETURN count(n) AS count
                    """
                    result = graph.query(orphan_query)
                orphan_count = result[0]["count"] if result else 0
            
            return RefineGraphResponse(
                success=True,
                message=f"DRY RUN: Would merge {len(candidates)} duplicate pairs and remove {orphan_count} orphan nodes.",
                nodes_merged=0,
                orphans_removed=0,
                merge_candidates=candidates,
                dry_run=True
            )
        
        # Step 2: Merge duplicates
        merged_count = 0
        for candidate in candidates:
            success = merge_duplicate_nodes(
                primary_name=candidate.primary_node,
                duplicate_name=candidate.duplicate_node,
                investigation_id=request.investigation_id
            )
            if success:
                merged_count += 1
        
        # Step 3: Remove orphans if requested
        orphans_removed = 0
        if request.remove_orphans:
            orphans_removed = remove_orphan_nodes(request.investigation_id)
        
        # Refresh schema
        graph = get_neo4j_graph()
        graph.refresh_schema()
        
        return RefineGraphResponse(
            success=True,
            message=f"Graph refinement complete. Merged {merged_count} duplicate pairs and removed {orphans_removed} orphan nodes.",
            nodes_merged=merged_count,
            orphans_removed=orphans_removed,
            merge_candidates=candidates,
            dry_run=False
        )
        
    except Exception as e:
        return RefineGraphResponse(
            success=False,
            message=f"Failed to refine graph: {str(e)}",
            nodes_merged=0,
            orphans_removed=0
        )


# =============================================================================
# Exported Constants (for backward compatibility)
# =============================================================================

ALLOWED_NODES = [nt.value for nt in NodeType]
ALLOWED_RELATIONSHIPS = [rt.value for rt in RelationshipType]
