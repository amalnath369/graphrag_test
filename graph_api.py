from dotenv import load_dotenv
import os
from fastapi import FastAPI, Query, HTTPException
from neo4j import GraphDatabase
from typing import Optional
import google.generativeai as genai

load_dotenv()

app = FastAPI(title="GraphRAG Neo4j API with Semantic Search")

# Initialize Neo4j driver
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GRAPHRAG_API_KEY")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Initialize Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    SEMANTIC_SEARCH_ENABLED = True
    print("✅ Semantic search enabled with Gemini embeddings")
else:
    SEMANTIC_SEARCH_ENABLED = False
    print("⚠️ No API key found - semantic search disabled")

try:
    with driver.session() as session:
        session.run("RETURN 1")
    print("✅ Successfully connected to Neo4j")
except Exception as e:
    print("⚠️ Cannot connect to Neo4j:", e)
    raise e


def get_embedding(text: str):
    """Generate embedding for semantic search"""
    if not SEMANTIC_SEARCH_ENABLED:
        return None
    
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None


def semantic_search_entities(query: str, limit: int = 5):
    """Search entities using vector similarity"""
    embedding = get_embedding(query)
    
    if not embedding:
        # Fallback to keyword search
        return keyword_search_entities(query, limit)
    
    with driver.session() as session:
        try:
            # Use vector index for semantic search
            result = session.run("""
                CALL db.index.vector.queryNodes('entity_embeddings', $limit, $embedding)
                YIELD node, score
                
                OPTIONAL MATCH (node)-[r:RELATES_TO]-(related:Entity)
                OPTIONAL MATCH (node)-[:BELONGS_TO]->(c:Community)
                
                RETURN 
                    node.name AS entity_name,
                    node.type AS entity_type,
                    node.description AS entity_description,
                    node.degree AS connections,
                    score AS relevance_score,
                    collect(DISTINCT {
                        name: related.name,
                        type: related.type,
                        relationship: r.description
                    })[..5] AS related_entities,
                    collect(DISTINCT c.title)[..3] AS communities
                ORDER BY score DESC
            """, embedding=embedding, limit=limit)
            
            return [dict(record) for record in result]
            
        except Exception as e:
            print(f"Vector search failed: {e}")
            # Fallback to keyword search
            return keyword_search_entities(query, limit)


def keyword_search_entities(query: str, limit: int = 10):
    """Fallback keyword search"""
    with driver.session() as session:
        result = session.run("""
            MATCH (e:Entity)
            WHERE toLower(e.name) CONTAINS toLower($query)
               OR toLower(e.description) CONTAINS toLower($query)
            
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(related:Entity)
            OPTIONAL MATCH (e)-[:BELONGS_TO]->(c:Community)
            
            RETURN 
                e.name AS entity_name,
                e.type AS entity_type,
                e.description AS entity_description,
                e.degree AS connections,
                1.0 AS relevance_score,
                collect(DISTINCT {
                    name: related.name,
                    type: related.type,
                    relationship: r.description
                })[..5] AS related_entities,
                collect(DISTINCT c.title)[..3] AS communities
            LIMIT $limit
        """, query=query, limit=limit)
        
        return [dict(record) for record in result]


def extract_keywords(question: str):
    """Extract important keywords from natural language questions"""
    # Remove common question words
    stop_words = ['who', 'what', 'where', 'when', 'why', 'how', 'is', 'are', 'was', 'were', 'the', 'a', 'an']
    words = question.lower().split()
    keywords = [w for w in words if w not in stop_words]
    return ' '.join(keywords)


def fetch_entity_context(keyword: str, limit: int = 10):
    """Fetch entities and their relationships"""
    query = """
    MATCH (e:Entity)
    WHERE toLower(e.name) CONTAINS toLower($keyword)
    OPTIONAL MATCH (e)-[r:RELATES_TO]->(related:Entity)
    RETURN e.name AS entity, 
           e.type AS entity_type,
           e.description AS description,
           type(r) AS relation, 
           related.name AS related_entity,
           related.type AS related_type,
           r.description AS relation_description
    LIMIT $limit
    """

    with driver.session() as session:
        result = session.run(query, keyword=keyword, limit=limit)
        data = [record.data() for record in result]
    
    return data


def fetch_community_context(keyword: str, limit: int = 5):
    """Fetch communities related to keyword"""
    query = """
    MATCH (e:Entity)-[:BELONGS_TO]->(c:Community)
    WHERE toLower(e.name) CONTAINS toLower($keyword)
    RETURN DISTINCT c.title AS community_title,
           c.summary AS summary,
           c.level AS level,
           c.rank AS rank,
           collect(e.name)[..10] AS members
    ORDER BY c.rank DESC
    LIMIT $limit
    """
    
    with driver.session() as session:
        result = session.run(query, keyword=keyword, limit=limit)
        data = [record.data() for record in result]
    
    return data


def fetch_graph_stats():
    """Get overall graph statistics"""
    query = """
    MATCH (e:Entity)
    OPTIONAL MATCH (e)-[r:RELATES_TO]->()
    OPTIONAL MATCH (c:Community)
    OPTIONAL MATCH (d:Document)
    RETURN 
        count(DISTINCT e) AS total_entities,
        count(DISTINCT r) AS total_relationships,
        count(DISTINCT c) AS total_communities,
        count(DISTINCT d) AS total_documents
    """
    
    with driver.session() as session:
        result = session.run(query)
        data = result.single()
    
    return dict(data) if data else {}


@app.get("/")
def root():
    return {
        "status": "ok", 
        "message": "GraphRAG Neo4j API running",
        "semantic_search": SEMANTIC_SEARCH_ENABLED,
        "endpoints": {
            "stats": "/stats - Get graph statistics",
            "search": "/search?q=keyword - Keyword search",
            "semantic": "/semantic?q=question - AI-powered semantic search (requires embeddings)",
            "entity": "/entity?name=entity_name - Get entity details",
            "communities": "/communities?q=keyword - Search communities",
            "ask": "/ask?question=query - Natural language Q&A (NEW!)"
        }
    }


@app.get("/stats")
def get_stats():
    """Get graph statistics"""
    try:
        stats = fetch_graph_stats()
        return {"status": "success", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
def search(
    q: str = Query(..., description="Search keyword", min_length=1),
    limit: int = Query(10, ge=1, le=100)
):
    """Keyword-based search"""
    try:
        results = keyword_search_entities(q, limit)
        return {
            "query": q,
            "search_type": "keyword",
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/semantic")
def semantic_search(
    q: str = Query(..., description="Natural language question", min_length=1),
    limit: int = Query(5, ge=1, le=20)
):
    """AI-powered semantic search using embeddings"""
    if not SEMANTIC_SEARCH_ENABLED:
        raise HTTPException(
            status_code=503, 
            detail="Semantic search is not enabled. Please set GOOGLE_API_KEY environment variable."
        )
    
    try:
        results = semantic_search_entities(q, limit)
        return {
            "query": q,
            "search_type": "semantic",
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ask")
def ask_graph(
    question: str = Query(..., description="Natural language question",
                         examples=["Who is Elon Musk?", "What companies does Elon Musk run?"])
):
    """
    Natural language Q&A endpoint
    - Uses semantic search if available
    - Falls back to keyword extraction + search
    """
    try:
        # Try semantic search first if available
        if SEMANTIC_SEARCH_ENABLED:
            results = semantic_search_entities(question, limit=5)
            search_method = "semantic"
        else:
            # Extract keywords and search
            keywords = extract_keywords(question)
            results = keyword_search_entities(keywords, limit=5)
            search_method = "keyword_extraction"
        
        # Format response with more context
        formatted_results = []
        for r in results:
            formatted_results.append({
                "entity": r['entity_name'],
                "type": r['entity_type'],
                "description": r['entity_description'],
                "relevance": round(r['relevance_score'], 4),
                "connections": r.get('connections', 0),
                "related_entities": r.get('related_entities', []),
                "communities": r.get('communities', [])
            })
        
        return {
            "question": question,
            "search_method": search_method,
            "count": len(formatted_results),
            "results": formatted_results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/entity")
def get_entity(
    name: str = Query(..., description="Entity name"),
    depth: int = Query(1, ge=1, le=3, description="Relationship depth")
):
    """Get detailed information about a specific entity"""
    query = """
    MATCH (e:Entity {name: $name})
    OPTIONAL MATCH path = (e)-[r:RELATES_TO*1..$$depth]-(connected:Entity)
    OPTIONAL MATCH (e)-[:BELONGS_TO]->(c:Community)
    
    RETURN 
        e.name AS name,
        e.type AS type,
        e.description AS description,
        e.degree AS degree,
        collect(DISTINCT c.title) AS communities,
        collect(DISTINCT {
            entity: connected.name,
            type: connected.type,
            path_length: length(path)
        })[..20] AS connected_entities
    """.replace("$$depth", str(depth))
    
    try:
        with driver.session() as session:
            result = session.run(query, name=name)
            data = result.single()
            
            if not data:
                raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
            
            return {"status": "success", "data": dict(data)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/communities")
def get_communities(
    q: Optional[str] = Query(None, description="Search keyword"),
    limit: int = Query(10, ge=1, le=50)
):
    """Get community information"""
    try:
        if q:
            results = fetch_community_context(q, limit)
        else:
            query = """
            MATCH (c:Community)
            OPTIONAL MATCH (e:Entity)-[:BELONGS_TO]->(c)
            RETURN 
                c.title AS community_title,
                c.summary AS summary,
                c.level AS level,
                c.rank AS rank,
                count(e) AS member_count
            ORDER BY c.rank DESC
            LIMIT $limit
            """
            with driver.session() as session:
                result = session.run(query, limit=limit)
                results = [record.data() for record in result]
        
        return {
            "query": q,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/entities")
def get_all_entities():
    """Get all entities in the graph"""
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (e:Entity)
                RETURN e.name as name,
                       e.type as type,
                       e.description as description,
                       e.degree as degree
                ORDER BY e.degree DESC
            """)
            
            entities = [dict(record) for record in result]
            
            return {
                "count": len(entities),
                "entities": entities
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.on_event("shutdown")
def shutdown_event():
    """Close Neo4j driver on shutdown"""
    driver.close()
    print("✅ Neo4j driver closed")