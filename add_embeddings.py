import pandas as pd
from neo4j import GraphDatabase
import google.generativeai as genai
from dotenv import load_dotenv
import os
from tqdm import tqdm
import time

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
print(GEMINI_API_KEY)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

# Initialize
genai.configure(api_key=GEMINI_API_KEY)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_embedding(text, model="models/text-embedding-004"):
    """Generate embedding using Gemini"""
    try:
        result = genai.embed_content(
            model=model,
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def add_entity_embeddings():
    """Add embeddings to entities in Neo4j"""
    
    print("📊 Loading entities from parquet...")
    entities_df = pd.read_parquet("output/entities.parquet")
    print(f"Found {len(entities_df)} entities")
    print(f"Columns: {entities_df.columns.tolist()}\n")
    
    print("🔢 Generating and storing embeddings...")
    
    success_count = 0
    
    with driver.session() as session:
        for idx, row in tqdm(entities_df.iterrows(), total=len(entities_df)):
            try:
                # Use 'title' instead of 'name'
                title = row['title']
                description = row.get('description', '')
                entity_type = row.get('type', '')
                
                # Create rich text for embedding
                text = f"{title} ({entity_type}): {description}"
                
                # Generate embedding
                embedding = get_embedding(text)
                
                if embedding:
                    # Store in Neo4j (match by id)
                    result = session.run("""
                        MATCH (e:Entity {id: $id})
                        SET e.embedding = $embedding,
                            e.embedding_text = $text,
                            e.embedding_dimension = $dimension
                        RETURN e.name as name
                    """, 
                        id=str(row['id']),
                        embedding=embedding,
                        text=text,
                        dimension=len(embedding)
                    )
                    
                    if result.single():
                        success_count += 1
                    else:
                        print(f"\n⚠️  Entity {title} (ID: {row['id']}) not found in Neo4j")
                
                # Rate limiting - avoid hitting Gemini API limits
                time.sleep(0.15)
                
            except Exception as e:
                print(f"\n❌ Error processing {row.get('title', 'unknown')}: {e}")
                continue
    
    print(f"\n✅ Added embeddings to {success_count}/{len(entities_df)} entities!")
    return success_count

def add_relationship_embeddings():
    """Add embeddings to relationships"""
    
    print("\n📊 Loading relationships from parquet...")
    relationships_df = pd.read_parquet("output/relationships.parquet")
    print(f"Found {len(relationships_df)} relationships")
    
    # Show columns
    print(f"Columns: {relationships_df.columns.tolist()}\n")
    
    print("🔢 Generating and storing relationship embeddings...")
    
    success_count = 0
    
    with driver.session() as session:
        for idx, row in tqdm(relationships_df.iterrows(), total=len(relationships_df)):
            try:
                # Get relationship data
                source = row.get('source', '')
                target = row.get('target', '')
                description = row.get('description', '')
                
                # Create text for embedding
                text = f"{source} {description} {target}"
                
                # Generate embedding
                embedding = get_embedding(text)
                
                if embedding:
                    # Store in Neo4j
                    result = session.run("""
                        MATCH ()-[r:RELATES_TO {id: $id}]->()
                        SET r.embedding = $embedding,
                            r.embedding_text = $text,
                            r.embedding_dimension = $dimension
                        RETURN id(r) as rel_id
                    """, 
                        id=str(row['id']),
                        embedding=embedding,
                        text=text,
                        dimension=len(embedding)
                    )
                    
                    if result.single():
                        success_count += 1
                
                time.sleep(0.15)
                
            except Exception as e:
                print(f"\n❌ Error processing relationship {idx}: {e}")
                continue
    
    print(f"\n✅ Added embeddings to {success_count}/{len(relationships_df)} relationships!")
    return success_count

def create_vector_indexes():
    """Create vector indexes for similarity search"""
    
    print("\n📊 Creating vector indexes...")
    
    with driver.session() as session:
        # Check Neo4j version
        try:
            version_result = session.run("CALL dbms.components() YIELD versions RETURN versions[0] as version").single()
            version = version_result['version']
            print(f"Neo4j version: {version}")
            
            # Vector indexes require Neo4j 5.11+
            major_version = int(version.split('.')[0])
            minor_version = int(version.split('.')[1])
            
            if major_version < 5 or (major_version == 5 and minor_version < 11):
                print(f"⚠️  Vector indexes require Neo4j 5.11+. You have {version}")
                print("   Embeddings are stored but vector search won't work optimally")
                return False
                
        except Exception as e:
            print(f"⚠️  Could not check version: {e}")
        
        # Create entity vector index
        try:
            session.run("""
                CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
                FOR (e:Entity)
                ON e.embedding
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }}
            """)
            print("✅ Entity vector index created!")
        except Exception as e:
            print(f"⚠️  Could not create entity vector index: {e}")
            return False
        
        # Create relationship vector index
        try:
            session.run("""
                CREATE VECTOR INDEX relationship_embeddings IF NOT EXISTS
                FOR ()-[r:RELATES_TO]-()
                ON r.embedding
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }}
            """)
            print("✅ Relationship vector index created!")
        except Exception as e:
            print(f"⚠️  Could not create relationship vector index: {e}")
        
        return True

def test_similarity_search():
    """Test similarity search with embeddings"""
    
    print("\n🔍 Testing similarity search...")
    
    # Generate a test query embedding
    query_text = "CEO of Tesla"
    print(f"Query: '{query_text}'")
    
    query_embedding = get_embedding(query_text)
    
    if not query_embedding:
        print("❌ Could not generate query embedding")
        return
    
    with driver.session() as session:
        try:
            # Try vector search
            results = session.run("""
                CALL db.index.vector.queryNodes('entity_embeddings', 3, $embedding)
                YIELD node, score
                RETURN node.name as name, 
                       node.type as type,
                       node.description as description,
                       score
                ORDER BY score DESC
            """, embedding=query_embedding)
            
            print("\n📊 Top 3 similar entities (using vector index):")
            found = False
            for record in results:
                found = True
                print(f"  • {record['name']} ({record['type']}) - Score: {record['score']:.4f}")
                print(f"    {record['description'][:100]}...")
            
            if not found:
                print("  (No results - vector index may not be working)")
                
        except Exception as e:
            print(f"⚠️  Vector search failed: {e}")
            print("   Falling back to cosine similarity calculation...")
            
            # Manual cosine similarity (slower but works without vector index)
            results = session.run("""
                MATCH (e:Entity)
                WHERE e.embedding IS NOT NULL
                WITH e, 
                     reduce(dot = 0.0, i IN range(0, size(e.embedding)-1) | 
                         dot + e.embedding[i] * $embedding[i]) as dot_product,
                     sqrt(reduce(sum = 0.0, x IN e.embedding | sum + x*x)) as norm1,
                     sqrt(reduce(sum = 0.0, x IN $embedding | sum + x*x)) as norm2
                WITH e, dot_product / (norm1 * norm2) as similarity
                RETURN e.name as name, 
                       e.type as type, 
                       e.description as description,
                       similarity
                ORDER BY similarity DESC
                LIMIT 3
            """, embedding=query_embedding)
            
            print("\n📊 Top 3 similar entities (manual calculation):")
            for record in results:
                print(f"  • {record['name']} ({record['type']}) - Similarity: {record['similarity']:.4f}")
                print(f"    {record['description'][:100]}...")

def show_stats():
    """Show embedding statistics"""
    
    print("\n📊 Embedding Statistics:")
    
    with driver.session() as session:
        # Count entities with embeddings
        result = session.run("""
            MATCH (e:Entity)
            WITH count(e) as total,
                 count(e.embedding) as with_embedding
            RETURN total, with_embedding
        """).single()
        
        print(f"  • Entities: {result['with_embedding']}/{result['total']} have embeddings")
        
        # Count relationships with embeddings
        result = session.run("""
            MATCH ()-[r:RELATES_TO]->()
            WITH count(r) as total,
                 count(r.embedding) as with_embedding
            RETURN total, with_embedding
        """).single()
        
        print(f"  • Relationships: {result['with_embedding']}/{result['total']} have embeddings")
        
        # Show sample embedding
        result = session.run("""
            MATCH (e:Entity)
            WHERE e.embedding IS NOT NULL
            RETURN e.name as name, 
                   e.embedding_text as text,
                   e.embedding_dimension as dim
            LIMIT 1
        """).single()
        
        if result:
            print(f"\n  Sample:")
            print(f"    Entity: {result['name']}")
            print(f"    Text: {result['text'][:80]}...")
            print(f"    Dimensions: {result['dim']}")

if __name__ == "__main__":
    print("="*80)
    print("Adding Embeddings to Neo4j Knowledge Graph")
    print("="*80)
    
    try:
        # Add embeddings
        entity_count = add_entity_embeddings()
        rel_count = add_relationship_embeddings()
        
        if entity_count > 0 or rel_count > 0:
            # Create vector indexes
            create_vector_indexes()
            
            # Show stats
            show_stats()
            
            # Test similarity search
            test_similarity_search()
        
        print("\n" + "="*80)
        print("✅ Process complete!")
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        driver.close()