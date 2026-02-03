# GraphRAG with Neo4j API

A GraphRAG (Graph Retrieval-Augmented Generation) implementation that extracts entities and relationships from documents and stores them in a Neo4j graph database, accessible via FastAPI endpoints.

## 📋 Overview

This project uses GraphRAG to extract knowledge graphs from documents and provides a REST API to query the graph data stored in Neo4j.

## ⚠️ Known Limitations

- **OpenAI API**: Hit rate limits during entity extraction
- **Gemini API**: Similar quota limitations encountered
- **Embeddings**: Manual embedding generation attempted but didn't work as expected
- Due to these limitations, the project focuses on the graph structure (entities and relationships) without embeddings

## 🏗️ Architecture

```
Documents → GraphRAG Extraction → Neo4j Database → FastAPI → REST API
```

- **GraphRAG**: Extracts entities, relationships, and communities from documents
- **Neo4j**: Graph database storing the knowledge graph
- **FastAPI**: REST API for querying the graph data

## 🚀 Setup

### Prerequisites

- Python 3.8+
- Neo4j (running in Docker)
- Virtual environment (recommended)

### 1. Start Neo4j Database

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

Access Neo4j Browser at: http://localhost:7474

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn neo4j pandas pyarrow tqdm
```

### 3. Load GraphRAG Data into Neo4j

```bash
python export_to_neo4j.py
```

This script loads entities, relationships, communities, and documents from GraphRAG output into Neo4j.

### 4. Start the API Server

```bash
uvicorn graph_api:app --reload
```

The API will be available at: http://localhost:8000

## 📚 API Documentation

Interactive API documentation (Swagger UI) is available at:

**http://localhost:8000/docs**

### Available Endpoints

#### Main Endpoints

- **GET `/`** - API information and available endpoints
- **GET `/stats`** - Get graph statistics (total entities, relationships, communities, documents)
- **GET `/search?q={keyword}`** - Search entities by name, description, or type
- **GET `/entity?name={entity_name}`** - Get detailed information about a specific entity
- **GET `/communities?q={keyword}`** - Search and browse communities
- **GET `/entities/types`** - Get all available entity types
- **GET `/entities/by-type?entity_type={type}`** - Filter entities by type


#### Legacy Endpoint

- **GET `/ask?question={question}`** - Legacy search endpoint (deprecated, use `/search` instead)

## 🧪 Testing the API

### Using Swagger UI (Recommended)

1. Open http://localhost:8000/docs
2. Start with debug endpoints to see what data exists:
   - Try `/debug/entities` to see all entities
   - Try `/debug/sample-search` to get test data
3. Use the sample entity names to test other endpoints

### Using cURL

```bash
# Get statistics
curl http://localhost:8000/stats

# Search for entities
curl "http://localhost:8000/search?q=technology&limit=10"

# Get entity types
curl http://localhost:8000/entities/types

# Filter by entity type
curl "http://localhost:8000/entities/by-type?entity_type=PERSON&limit=10"

# Get specific entity details
curl "http://localhost:8000/entity?name=Elon%20Musk"

# Browse communities
curl http://localhost:8000/communities
```

### Example Queries

```bash
# Find all PERSON entities
GET /entities/by-type?entity_type=PERSON

# Search for AI-related content
GET /search?q=artificial intelligence

# Get top communities
GET /communities?limit=10

# Get detailed entity information
GET /entity?name=OpenAI&depth=2
```

## 📁 Project Structure

```
GraphRag/
├── output/                      # GraphRAG output files
│   ├── entities.parquet
│   ├── relationships.parquet
│   ├── communities.parquet
│   ├── community_reports.parquet
│   ├── documents.parquet
│   └── text_units.parquet
├── export_to_neo4j.py          # Script to load data into Neo4j
├── graph_api.py                # FastAPI application
├── load_test_data.py           # Test data loader (optional)
└── README.md
```

## 🔧 Configuration

### Environment Variables

You can configure the following via environment variables:

```bash
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
```

### Windows Example

```cmd
set NEO4J_URI=bolt://localhost:7687
set NEO4J_USERNAME=neo4j
set NEO4J_PASSWORD=your_password
uvicorn graph_api:app --reload
```

### Linux/Mac Example

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password
uvicorn graph_api:app --reload
```

## 🐳 Note on Containerization

**This API is NOT containerized.** Both Neo4j and the FastAPI application run separately:
- Neo4j runs in Docker
- FastAPI runs locally on the host machine

To access the API, use: **http://localhost:8000**

## 📊 Data Model

### Entities
- Properties: `id`, `name`, `type`, `description`, `degree`, `human_readable_id`
- Types: PERSON, ORGANIZATION, TECHNOLOGY, etc.

### Relationships
- Type: `RELATES_TO`
- Properties: `id`, `description`, `weight`, `human_readable_id`

### Communities
- Properties: `id`, `title`, `summary`, `level`, `rank`, `period`

### Documents
- Properties: `id`, `title`, `raw_content`

## 🛠️ Troubleshooting

### API returns empty results
1. Check if data is loaded: `GET /debug/entities`
2. Verify Neo4j is running: `docker ps`
3. Check Neo4j Browser: http://localhost:7474

### Cannot connect to Neo4j
```bash
# Check if Neo4j container is running
docker ps

# Check Neo4j logs
docker logs neo4j

# Restart Neo4j
docker restart neo4j
```

### Port already in use
```bash
# Kill process on port 8000
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac:
lsof -ti:8000 | xargs kill -9
```

### Syntax Error in graph_api.py
If you see `SyntaxError: invalid syntax` at startup, check that all variable assignments are complete and there are no incomplete lines.

### DNS Resolution Failed
If you see `Failed to DNS resolve address neo4j:7687`, change the Neo4j URI from `bolt://neo4j:7687` to `bolt://localhost:7687` in your configuration.

## 🔍 Key Features

✅ Entity extraction and storage
✅ Relationship mapping
✅ Community detection
✅ REST API with Swagger documentation
✅ Graph database querying
✅ Debug endpoints for troubleshooting
✅ Type-based filtering
✅ Full-text search across entities

## 📖 Usage Examples

### Python Client Example

```python
import requests

# Get all entity types
response = requests.get("http://localhost:8000/entities/types")
print(response.json())

# Search for entities
response = requests.get("http://localhost:8000/search", params={"q": "AI", "limit": 5})
print(response.json())

# Get specific entity
response = requests.get("http://localhost:8000/entity", params={"name": "OpenAI"})
print(response.json())
```


**Built using GraphRAG, Neo4j, and FastAPI**