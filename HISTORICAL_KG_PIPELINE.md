# Historical Knowledge Graph Pipeline on Nibi

## Vision: OLMoCR → UniversalNER → Neo4j → Embedding → GraphRAG

Complete pipeline for processing historical documents into a queryable knowledge graph with RAG capabilities.

## Architecture

```
Historical PDFs
    ↓
[OLMoCR] - Optical Character Recognition
    ↓
Plain Text + Structure
    ↓
[UniversalNER] - Named Entity Recognition
    ↓
Entities: Places, People, Organizations, Events
    ↓
[Grounding to Neo4j] - Entity Linking & Knowledge Graph
    ↓
Graph Database: Nodes + Relationships
    ↓
[Embedding] - Vector representations of entities/relationships
    ↓
[GraphRAG] - Graph-enhanced Retrieval Augmented Generation
    ↓
Contextual Query Answering
```

## Components Status

### 1. OLMoCR ✓ Running
- **Location**: `~/projects/def-jic823/olmocr/olmocr.sif`
- **Status**: Processing Canadiana PDFs
- **Output**: Structured OCR with text + layout
- **Performance**: ~1.39 pages/sec on H100

### 2. UniversalNER ✓ Running
- **Status**: User reports "UniversalNER running on Nibi"
- **Input**: OCR text
- **Output**: Named entities (PERSON, ORG, GPE, EVENT, etc.)
- **Next**: Extract entities from OCR output

### 3. Neo4j Knowledge Graph 🔄 Building
- **Container**: `~/projects/def-jic823/CanadaNeo4j/neo4j.sif`
- **Data**: `~/projects/def-jic823/CanadaNeo4j/neo4j_data`
- **Status**: Building infrastructure now

### 4. Grounding Pipeline ⏳ Pending
- **Task**: Link NER entities to Neo4j nodes
- **Strategy**:
  - Places → Match against 6.2M GeoNames + Wikidata places
  - People → Match against Wikidata people (birth/death places)
  - Organizations → Colonial companies, government agencies
  - Events → Historical events with locations

### 5. Embedding ⏳ Pending
- Vector representations for semantic search
- Graph embeddings for relationship-aware retrieval

### 6. GraphRAG ⏳ Pending
- Query interface combining graph structure + document content
- LLM integration (GPT-OSS-120B available on Nibi)

## Knowledge Graph Schema

### Node Types

**Place** (6.2M nodes - already loaded locally)
- Properties: name, coordinates, geonameId, wikidataId, countryCode, featureClass
- Alternate names for NER matching
- Administrative hierarchy relationships

**Person** (to be loaded from Wikidata)
- Properties: name, wikidataId, dateOfBirth, dateOfDeath, occupation
- Relationships: BORN_IN, DIED_IN, RESIDED_IN (→ Place)

**Organization** (to be loaded from Wikidata)
- Properties: name, wikidataId, founded, dissolved
- Relationships: FOUNDED_IN, HEADQUARTERED_IN (→ Place)
- Examples: Hudson's Bay Company, colonial governments

**Event** (to be loaded from Wikidata)
- Properties: name, wikidataId, date, eventType
- Relationships: OCCURRED_AT (→ Place), PARTICIPANT (→ Person/Organization)
- Examples: battles, treaties, conferences

**Document** (from OLMoCR)
- Properties: documentId, title, date, archiveUrl
- Relationships: MENTIONS (→ Place/Person/Organization/Event)

**Entity Mention** (from UniversalNER)
- Properties: text, entityType, confidence, context
- Relationships: GROUNDS_TO (→ Place/Person/Organization/Event)

### Relationship Types

**Administrative Hierarchy:**
- (Place)-[:LOCATED_IN_COUNTRY]->(Country)
- (Place)-[:LOCATED_IN_ADMIN1]->(AdminDivision)
- (Place)-[:LOCATED_IN_ADMIN2]->(AdminDivision)
- (Place)-[:LOCATED_IN_ADMIN3]->(AdminDivision)

**Historical Context:**
- (Person)-[:BORN_IN]->(Place)
- (Person)-[:DIED_IN]->(Place)
- (Person)-[:RESIDED_IN]->(Place)
- (Person)-[:WORKED_FOR]->(Organization)
- (Organization)-[:FOUNDED_IN]->(Place)
- (Organization)-[:HEADQUARTERED_IN]->(Place)
- (Event)-[:OCCURRED_AT]->(Place)
- (Event)-[:PARTICIPANT]->(Person|Organization)

**Document Grounding:**
- (Document)-[:MENTIONS {offset, context}]->(Entity)
- (EntityMention)-[:GROUNDS_TO {confidence}]->(KnownEntity)

## Data Sources

### Currently Loaded (Local)
- **GeoNames**: 6.2M places globally
- **Admin Divisions**: 510K administrative units
- **Relationships**: 10.3M admin hierarchy links

### In Progress
- **Wikidata Download**: 66GB/146GB (45% complete)
  - Geographic entities (P625): ~5-10M
  - People with place connections: ~2M
  - Organizations: ~500K
  - Events: ~300K

### Planned
- **OCR Documents**: Canadiana collection
- **NER Extractions**: UniversalNER output
- **Cross-references**: GND, VIAF, LOC identifiers

## Grounding Strategy

### Phase 1: Fuzzy Name Matching
```python
# Match NER entity to Place nodes
MATCH (p:Place)
WHERE p.name =~ "(?i).*Toronto.*"
   OR ANY(alt IN p.alternateNames WHERE alt =~ "(?i).*Toronto.*")
RETURN p
ORDER BY similarity(p.name, "Toronto") DESC
LIMIT 5
```

### Phase 2: Contextual Disambiguation
Use surrounding entities and document metadata:
- Date constraints (e.g., "Toronto" in 1850s → likely York)
- Geographic constraints (nearby places mentioned)
- Administrative context (province/state mentioned)

### Phase 3: Confidence Scoring
```cypher
CREATE (m:EntityMention {text: "Toronto", context: "..."})
CREATE (m)-[:GROUNDS_TO {confidence: 0.95, method: "name+context"}]->(p:Place)
```

## Neo4j Deployment on Nibi

### Build Container (Step 1)
```bash
cd ~/projects/def-jic823/CanadaNeo4j
sbatch build_neo4j_container.sh
```

### Deploy Database (Step 2)
```bash
sbatch deploy_historical_kg_nibi.sh
```

### Connection Details
- **URL**: `bolt://localhost:7687`
- **Username**: `neo4j`
- **Password**: `historicalkg2025`
- **Access**: SSH tunnel from laptop:
  ```bash
  ssh -L 7687:localhost:7687 -L 7474:localhost:7474 nibi
  ```
  Then connect Neo4j Browser to `http://localhost:7474`

### Loading Data

**Transfer from Local to Nibi:**
```bash
# Export from local Neo4j
python3 export_database.py --output neo4j_export.cypher

# Copy to Nibi
scp neo4j_export.cypher nibi:~/projects/def-jic823/CanadaNeo4j/neo4j_import/

# Load on Nibi via cypher-shell
apptainer exec --bind ~/projects/def-jic823/CanadaNeo4j/neo4j_data:/data \
    neo4j.sif \
    cypher-shell -u neo4j -p historicalkg2025 -f neo4j_import/neo4j_export.cypher
```

**Load Wikidata Entities:**
```bash
# After filtering Wikidata dump
python3 load_wikidata_people.py --cache wikidata_people.json.gz
python3 load_wikidata_organizations.py --cache wikidata_organizations.json.gz
python3 load_wikidata_events.py --cache wikidata_events.json.gz
```

## Expected Database Size

### Current (Local)
- 6.74M nodes, 10.3M relationships
- ~5-10 GB database size

### After Wikidata (Nibi)
- **Places**: 6.2M (GeoNames) + 5-10M (Wikidata) = ~12-16M nodes
- **People**: ~2M nodes
- **Organizations**: ~500K nodes
- **Events**: ~300K nodes
- **Total**: ~15-20M nodes
- **Relationships**: ~80-100M
- **Database size**: ~100-150 GB

### After Document Grounding
- **Documents**: Depends on OCR corpus size
- **Entity Mentions**: Could be 10-100M
- **Additional relationships**: MENTIONS, GROUNDS_TO
- **Total size**: 150-250 GB (well within Nibi capacity)

## Hardware Requirements

### Nibi Allocation
- **CPU**: 8 cores (for batch operations)
- **Memory**: 64 GB RAM
  - Heap: 16 GB
  - Page cache: 32 GB
  - OS: 16 GB
- **Storage**: ~200-250 GB in project space
- **Time**: 48-hour jobs for long-running database

### Benefits on Nibi
- Always accessible (no laptop sleep)
- Better hardware than laptop (64GB vs 32GB RAM)
- Can run concurrent jobs (NER + KG queries)
- Integration with OLMoCR/UniversalNER pipelines

## Query Examples

### Place Lookup for Grounding
```cypher
// Find all "Toronto" variants
MATCH (p:Place)
WHERE p.name = "Toronto"
   OR "Toronto" IN p.alternateNames
RETURN p.geonameId, p.name, p.wikidataId,
       p.latitude, p.longitude, p.countryCode
```

### Historical Entity Resolution
```cypher
// Find person born in Toronto area
MATCH (person:Person)-[:BORN_IN]->(place:Place)
WHERE place.name =~ ".*Toronto.*"
  AND person.dateOfBirth >= "1850"
  AND person.dateOfBirth <= "1900"
RETURN person.name, person.dateOfBirth, place.name
ORDER BY person.dateOfBirth
```

### Document Mention Analysis
```cypher
// Find all documents mentioning Hudson's Bay Company
MATCH (doc:Document)-[:MENTIONS]->(org:Organization)
WHERE org.name CONTAINS "Hudson"
RETURN doc.title, doc.date,
       count(DISTINCT org) as mentioned_orgs
ORDER BY doc.date
```

### Graph-RAG Query
```cypher
// Find context for "fur trade in 1850s"
MATCH (org:Organization)-[:FOUNDED_IN]->(place:Place)
WHERE org.name CONTAINS "fur" OR org.name CONTAINS "trade"
  AND org.founded >= "1850" AND org.founded < "1860"
MATCH (org)-[:MENTIONED_IN]->(doc:Document)
RETURN org.name, place.name,
       collect(doc.title) as source_documents
```

## Next Steps

1. ✓ Build Neo4j container
2. ✓ Create deployment infrastructure
3. ⏳ Wait for Wikidata download
4. ⏳ Filter Wikidata for entities
5. ⏳ Load data into Nibi Neo4j
6. ⏳ Connect UniversalNER output to grounding pipeline
7. ⏳ Build embedding layer
8. ⏳ Implement GraphRAG queries

## Timeline

- **Today**: Build Neo4j container (~30 min)
- **Today**: Wikidata download completes (~4-5 hours)
- **Tomorrow**: Filter Wikidata entities (~6-10 hours per pass)
- **Day 3-4**: Load all entities into Neo4j
- **Week 2**: Grounding pipeline implementation
- **Week 3+**: Embedding + GraphRAG integration

## References

- **GeoNames**: https://www.geonames.org/
- **Wikidata**: https://www.wikidata.org/
- **Neo4j Documentation**: https://neo4j.com/docs/
- **OLMoCR**: Historical document OCR on H100
- **UniversalNER**: Universal named entity recognition
