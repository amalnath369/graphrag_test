import os
from fastapi import FastAPI, Query, HTTPException
from neo4j import GraphDatabase
from typing import Optional

app = FastAPI(title="GraphRAG Neo4j API")

# Initialize Neo4j driver at startup
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

try:
    with driver.session() as session:
        session.run("RETURN 1")
    print("✅ Successfully connected to Neo4j")
except Exception as e:
    print("⚠️ Cannot connect to Neo4j:", e)
    raise e


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


def search_full_text(keyword: str, limit: int = 10):
    """Search across entities, communities, and text units"""
    query = """
    // Search entities
    MATCH (e:Entity)
    WHERE toLower(e.name) CONTAINS toLower($keyword)
       OR toLower(e.description) CONTAINS toLower($keyword)
    WITH e LIMIT $limit
    
    OPTIONAL MATCH (e)-[r:RELATES_TO]->(related:Entity)
    OPTIONAL MATCH (e)-[:BELONGS_TO]->(c:Community)
    
    RETURN 
        e.name AS entity_name,
        e.type AS entity_type,
        e.description AS entity_description,
        e.degree AS connections,
        collect(DISTINCT related.name)[..5] AS related_entities,
        collect(DISTINCT c.title)[..3] AS communities
    """
    
    with driver.session() as session:
        result = session.run(query, keyword=keyword, limit=limit)
        data = [record.data() for record in result]
    
    return data


@app.get("/")
def root():
    return {
        "status": "ok", 
        "message": "GraphRAG Neo4j API running",
        "endpoints": {
            "stats": "/stats",
            "search": "/search?q=keyword",
            "entity": "/entity?name=entity_name",
            "communities": "/communities?q=keyword",
            "ask": "/ask?question=your_question (legacy)"
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
    """Search for entities and their context"""
    try:
        results = search_full_text(q, limit)
        return {
            "query": q,
            "count": len(results),
            "results": results
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
            # Get top communities by rank
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


@app.get("/ask")
def ask_graph(
    question: str = Query(..., examples=["What is Elon Musk related to?"])
):
    """Legacy endpoint - use /search instead"""
    try:
        results = fetch_entity_context(question, limit=20)
        return {
            "question": question,
            "count": len(results),
            "results": results,
            "note": "This endpoint is deprecated. Use /search?q=your_query for better results"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
def shutdown_event():
    """Close Neo4j driver on shutdown"""
    driver.close()
    print("✅ Neo4j driver closed")