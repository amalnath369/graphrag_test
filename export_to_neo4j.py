import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
from tqdm import tqdm

class GraphRAGToNeo4j:
    def __init__(self, uri, username, password):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
    
    def close(self):
        self.driver.close()
    
    def clear_database(self):
        """Clear all nodes and relationships"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✅ Database cleared")
    
    def create_constraints(self):
        """Create uniqueness constraints"""
        with self.driver.session() as session:
            try:
                session.run("""
                    CREATE CONSTRAINT entity_id IF NOT EXISTS
                    FOR (e:Entity) REQUIRE e.id IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT community_id IF NOT EXISTS
                    FOR (c:Community) REQUIRE c.id IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT document_id IF NOT EXISTS
                    FOR (d:Document) REQUIRE d.id IS UNIQUE
                """)
                print("✅ Constraints created")
            except Exception as e:
                print(f"Note: {e}")
    
    def import_documents(self, documents_df):
        """Import documents"""
        print("\n📄 Importing documents...")
        with self.driver.session() as session:
            for _, row in tqdm(documents_df.iterrows(), total=len(documents_df)):
                session.run("""
                    MERGE (d:Document {id: $id})
                    SET d.title = $title,
                        d.raw_content = $raw_content
                """, 
                    id=str(row['id']),
                    title=row.get('title', row.get('id', '')),
                    raw_content=str(row.get('raw_content', ''))[:1000]  # Truncate for display
                )
        print(f"✅ Imported {len(documents_df)} documents")
    
    def import_entities(self, entities_df):
        """Import entities as nodes"""
        print("\n🏷️  Importing entities...")
        with self.driver.session() as session:
            for _, row in tqdm(entities_df.iterrows(), total=len(entities_df)):
                session.run("""
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name,
                        e.type = $type,
                        e.description = $description,
                        e.degree = $degree,
                        e.human_readable_id = $human_readable_id
                """, 
                    id=str(row['id']),
                    name=str(row.get('name', row.get('title', ''))),
                    type=str(row.get('type', '')),
                    description=str(row.get('description', '')),
                    degree=int(row.get('degree', 0)),
                    human_readable_id=int(row.get('human_readable_id', 0))
                )
        print(f"✅ Imported {len(entities_df)} entities")
    
    def import_relationships(self, relationships_df):
        """Import relationships as edges"""
        print("\n🔗 Importing relationships...")
        successful = 0
        with self.driver.session() as session:
            for _, row in tqdm(relationships_df.iterrows(), total=len(relationships_df)):
                try:
                    session.run("""
                        MATCH (source:Entity {id: $source})
                        MATCH (target:Entity {id: $target})
                        MERGE (source)-[r:RELATES_TO {id: $id}]->(target)
                        SET r.description = $description,
                            r.weight = $weight,
                            r.human_readable_id = $human_readable_id
                    """,
                        id=str(row['id']),
                        source=str(row['source']),
                        target=str(row['target']),
                        description=str(row.get('description', '')),
                        weight=float(row.get('weight', 1.0)),
                        human_readable_id=int(row.get('human_readable_id', 0))
                    )
                    successful += 1
                except Exception as e:
                    # Skip relationships where entities don't exist
                    pass
        print(f"✅ Imported {successful}/{len(relationships_df)} relationships")
    
    def import_communities(self, communities_df):
        """Import communities"""
        print("\n👥 Importing communities...")
        with self.driver.session() as session:
            for _, row in tqdm(communities_df.iterrows(), total=len(communities_df)):
                session.run("""
                    MERGE (c:Community {id: $id})
                    SET c.title = $title,
                        c.level = $level,
                        c.period = $period
                """,
                    id=str(row['id']),
                    title=str(row.get('title', '')),
                    level=int(row.get('level', 0)),
                    period=str(row.get('period', ''))
                )
        print(f"✅ Imported {len(communities_df)} communities")
    
    def import_community_reports(self, reports_df):
        """Import community reports and link to communities"""
        print("\n📋 Importing community reports...")
        with self.driver.session() as session:
            for _, row in tqdm(reports_df.iterrows(), total=len(reports_df)):
                # Update community with report data
                session.run("""
                    MATCH (c:Community {id: $community_id})
                    SET c.summary = $summary,
                        c.full_content = $full_content,
                        c.rank = $rank,
                        c.rank_explanation = $rank_explanation,
                        c.findings = $findings
                """,
                    community_id=str(row.get('community', row.get('id', ''))),
                    summary=str(row.get('summary', '')),
                    full_content=str(row.get('full_content', ''))[:5000],  # Truncate
                    rank=float(row.get('rank', 0.0)),
                    rank_explanation=str(row.get('rank_explanation', '')),
                    findings=str(row.get('findings', ''))
                )
        print(f"✅ Imported {len(reports_df)} community reports")
    
    def link_entities_to_communities(self, entities_df):
        """Link entities to their communities"""
        print("\n🔗 Linking entities to communities...")
        linked = 0
        with self.driver.session() as session:
            for _, row in tqdm(entities_df.iterrows(), total=len(entities_df)):
                community_ids = row.get('community_ids', None)
                if pd.notna(community_ids):
                    # Handle different formats
                    if isinstance(community_ids, str):
                        try:
                            community_ids = eval(community_ids)
                        except:
                            continue
                    
                    if isinstance(community_ids, (list, tuple)):
                        for comm_id in community_ids:
                            try:
                                session.run("""
                                    MATCH (e:Entity {id: $entity_id})
                                    MATCH (c:Community {id: $community_id})
                                    MERGE (e)-[:BELONGS_TO]->(c)
                                """,
                                    entity_id=str(row['id']),
                                    community_id=str(comm_id)
                                )
                                linked += 1
                            except:
                                pass
        print(f"✅ Created {linked} community links")
    
    def link_text_units_to_entities(self, text_units_df):
        """Link text units to entities"""
        print("\n📝 Linking text units to entities...")
        with self.driver.session() as session:
            for _, row in tqdm(text_units_df.iterrows(), total=len(text_units_df)):
                # Create text unit node
                session.run("""
                    MERGE (t:TextUnit {id: $id})
                    SET t.text = $text,
                        t.n_tokens = $n_tokens
                """,
                    id=str(row['id']),
                    text=str(row.get('text', ''))[:1000],
                    n_tokens=int(row.get('n_tokens', 0))
                )
                
                # Link to entities if available
                entity_ids = row.get('entity_ids', None)
                
                # Fix: Check if it's not None and not NaN properly
                if entity_ids is not None:
                    try:
                        # Handle if it's already a list/array
                        if hasattr(entity_ids, '__iter__') and not isinstance(entity_ids, str):
                            entity_list = list(entity_ids)
                        elif isinstance(entity_ids, str):
                            entity_list = eval(entity_ids)
                        else:
                            continue
                        
                        # Link each entity
                        for entity_id in entity_list:
                            if entity_id and str(entity_id).strip():
                                try:
                                    session.run("""
                                        MATCH (e:Entity {id: $entity_id})
                                        MATCH (t:TextUnit {id: $text_unit_id})
                                        MERGE (t)-[:MENTIONS]->(e)
                                    """,
                                        entity_id=str(entity_id),
                                        text_unit_id=str(row['id'])
                                    )
                                except Exception as e:
                                    pass
                    except Exception as e:
                        # Skip if we can't parse entity_ids
                        pass
        
        print(f"✅ Imported {len(text_units_df)} text units")    

        
    def create_indexes(self):
        """Create indexes for better query performance"""
        print("\n📊 Creating indexes...")
        with self.driver.session() as session:
            try:
                session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
                session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)")
                session.run("CREATE INDEX community_level IF NOT EXISTS FOR (c:Community) ON (c.level)")
                print("✅ Indexes created")
            except Exception as e:
                print(f"Note: {e}")

def main():
    # Configuration
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USERNAME = "neo4j"
    NEO4J_PASSWORD = "password"  # CHANGE THIS IF DIFFERENT!
    
    OUTPUT_DIR = Path("output")  # Changed from output/artifacts
    
    print("="*80)
    print("GraphRAG to Neo4j Exporter")
    print("="*80)
    
    # Initialize Neo4j connection
    print(f"\n🔌 Connecting to Neo4j at {NEO4J_URI}...")
    neo4j = GraphRAGToNeo4j(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)
    
    try:
        # Clear existing data
        clear = input("\n⚠️  Clear existing Neo4j database? (y/n): ").lower()
        if clear == 'y':
            neo4j.clear_database()
        
        # Create constraints
        neo4j.create_constraints()
        
        # Load GraphRAG output files
        print("\n📂 Loading GraphRAG data...")
        
        entities_df = pd.read_parquet(OUTPUT_DIR / "entities.parquet")
        print(f"   ✓ Loaded {len(entities_df)} entities")
        
        relationships_df = pd.read_parquet(OUTPUT_DIR / "relationships.parquet")
        print(f"   ✓ Loaded {len(relationships_df)} relationships")
        
        communities_df = pd.read_parquet(OUTPUT_DIR / "communities.parquet")
        print(f"   ✓ Loaded {len(communities_df)} communities")
        
        community_reports_df = pd.read_parquet(OUTPUT_DIR / "community_reports.parquet")
        print(f"   ✓ Loaded {len(community_reports_df)} community reports")
        
        documents_df = pd.read_parquet(OUTPUT_DIR / "documents.parquet")
        print(f"   ✓ Loaded {len(documents_df)} documents")
        
        text_units_df = pd.read_parquet(OUTPUT_DIR / "text_units.parquet")
        print(f"   ✓ Loaded {len(text_units_df)} text units")
        
        # Import data
        neo4j.import_documents(documents_df)
        neo4j.import_entities(entities_df)
        neo4j.import_relationships(relationships_df)
        neo4j.import_communities(communities_df)
        neo4j.import_community_reports(community_reports_df)
        neo4j.link_entities_to_communities(entities_df)
        # neo4j.link_text_units_to_entities(text_units_df)
        neo4j.create_indexes()
        
        print("\n" + "="*80)
        print("✅ Export complete!")
        print("="*80)
        print(f"\n📊 Summary:")
        print(f"   • Documents: {len(documents_df)}")
        print(f"   • Text Units: {len(text_units_df)}")
        print(f"   • Entities: {len(entities_df)}")
        print(f"   • Relationships: {len(relationships_df)}")
        print(f"   • Communities: {len(communities_df)}")
        print(f"   • Community Reports: {len(community_reports_df)}")
        
        print(f"\n🌐 Open Neo4j Browser: http://localhost:7474")
        print(f"\n💡 Try these queries:")
        print(f"\n   1. View the graph structure:")
        print(f"      MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50")
        print(f"\n   2. Count all nodes by type:")
        print(f"      MATCH (n) RETURN labels(n)[0] as Type, count(n) as Count ORDER BY Count DESC")
        print(f"\n   3. Top entities by connections:")
        print(f"      MATCH (e:Entity) RETURN e.name, e.type, e.degree ORDER BY e.degree DESC LIMIT 10")
        print(f"\n   4. View communities:")
        print(f"      MATCH (c:Community) RETURN c.title, c.level, c.rank ORDER BY c.rank DESC LIMIT 10")
        print(f"\n   5. Entities in top community:")
        print(f"      MATCH (e:Entity)-[:BELONGS_TO]->(c:Community)")
        print(f"      WHERE c.rank > 0")
        print(f"      RETURN e.name, e.type, c.title")
        print(f"      ORDER BY c.rank DESC LIMIT 20")
        
    finally:
        neo4j.close()

if __name__ == "__main__":
    main()