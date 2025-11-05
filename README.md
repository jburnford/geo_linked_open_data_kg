# GeoNames LOD Knowledge Graph for NER Reconciliation

## Overview
Linked Open Data knowledge graph combining GeoNames and Wikidata for reconciling Named Entity Recognition results in historical research pipelines.

## Data Sources

### GeoNames
- **cities500.txt**: 225,112 global cities with population > 500
- **CA.txt**: 315,928 Canadian geographic features (all types)
- **License**: Creative Commons Attribution 4.0

### Wikidata (Planned)
- Entity linking for populated places meeting threshold
- Additional metadata: Wikipedia links, alternative names, historical data
- Q-numbers for LOD integration

## Neo4j Data Model

### Node Types

#### 1. Place (Primary Entity)
Properties:
- `geonameId`: int (unique identifier)
- `name`: string (primary name)
- `asciiName`: string (ASCII version)
- `alternateNames`: list[string] (for fuzzy matching)
- `latitude`: float
- `longitude`: float
- `featureClass`: string (P, H, T, L, etc.)
- `featureCode`: string (PPL, PPLA, etc.)
- `countryCode`: string (ISO 2-letter)
- `population`: int
- `elevation`: int (meters)
- `timezone`: string
- `modifiedDate`: date
- `wikidataId`: string (Q-number, nullable)
- `wikipediaUrl`: string (nullable)

Indexes:
- `geonameId` (unique)
- `name` (text search)
- `asciiName` (text search)
- `alternateNames` (full-text)
- `wikidataId` (unique when present)

#### 2. Country
Properties:
- `code`: string (ISO 2-letter)
- `name`: string
- `wikidataId`: string

#### 3. AdminDivision (Province/State/County)
Properties:
- `code`: string (admin code)
- `name`: string
- `level`: int (1-4)
- `countryCode`: string
- `wikidataId`: string (nullable)

### Relationships

#### Place Relationships
- `(Place)-[:LOCATED_IN_COUNTRY]->(Country)`
- `(Place)-[:LOCATED_IN_ADMIN1]->(AdminDivision {level: 1})`
- `(Place)-[:LOCATED_IN_ADMIN2]->(AdminDivision {level: 2})`
- `(Place)-[:LOCATED_IN_ADMIN3]->(AdminDivision {level: 3})`
- `(Place)-[:LOCATED_IN_ADMIN4]->(AdminDivision {level: 4})`
- `(Place)-[:NEAR {distance_km}]->(Place)` (spatial proximity, optional)
- `(Place)-[:SAME_AS]->(Place)` (duplicate/alternate records)

#### LOD Relationships
- `(Place)-[:WIKIDATA_LINK {qid}]->(WikidataEntity)` (future)

## NER Reconciliation Strategy

### Matching Approaches

#### 1. Exact Match
```cypher
MATCH (p:Place)
WHERE p.name = $entity_name
  OR $entity_name IN p.alternateNames
RETURN p
```

#### 2. Fuzzy Match (Levenshtein)
```cypher
MATCH (p:Place)
WHERE apoc.text.levenshteinDistance(toLower(p.name), toLower($entity_name)) <= 2
RETURN p, apoc.text.levenshteinDistance(toLower(p.name), toLower($entity_name)) as distance
ORDER BY distance
LIMIT 10
```

#### 3. Geographic Context (with coordinates)
```cypher
MATCH (p:Place)
WHERE point.distance(
  point({latitude: p.latitude, longitude: p.longitude}),
  point({latitude: $lat, longitude: $lon})
) <= 50000  // 50km radius
RETURN p, point.distance(...) as distance_m
ORDER BY distance_m
```

#### 4. Administrative Context (e.g., "Regina, Saskatchewan")
```cypher
MATCH (p:Place)-[:LOCATED_IN_ADMIN1]->(a:AdminDivision)
WHERE p.name = $city_name AND a.name = $admin_name
RETURN p
```

#### 5. Historical Name Resolution
```cypher
MATCH (p:Place)
WHERE p.name = $modern_name
  OR $historical_name IN p.alternateNames
RETURN p
```

## Population Thresholds

### Global Coverage (cities500.txt)
- Threshold: population >= 500
- Total: 225,112 places
- Focus: Major settlements worldwide

### Canadian Enhanced Coverage (CA.txt)
- Include all Canadian places regardless of population
- Total: 315,928 features
- Rationale: Historical research needs comprehensive Canadian coverage

### Wikidata Integration Threshold
- **Option A**: population >= 500 (matches cities500)
- **Option B**: population >= 1000 (reduces API calls)
- **Option C**: population >= 5000 (major places only)
- **Recommendation**: Start with 1000, expand later

## Implementation Phases

### Phase 1: GeoNames Loading (Current)
1. Load cities500.txt (global coverage)
2. Load CA.txt (comprehensive Canadian data)
3. Create Place nodes with all properties
4. Create Country and AdminDivision nodes
5. Establish geographic relationships
6. Build text search indexes

### Phase 2: Wikidata Integration
1. Query Wikidata SPARQL for places above threshold
2. Match GeoNames IDs to Wikidata Q-numbers
3. Enrich Place nodes with Wikidata properties
4. Add Wikipedia URLs and additional alternate names
5. Create WIKIDATA_LINK relationships

### Phase 3: NER Reconciliation API
1. Build reconciliation query functions
2. Implement ranking/scoring system
3. Add confidence metrics
4. Create disambiguation logic
5. Test with historical NER results

### Phase 4: Optimization
1. Spatial indexing for geographic queries
2. Full-text search optimization
3. Caching frequent queries
4. Performance tuning

## Technology Stack

- **Neo4j**: Graph database (Community or Enterprise)
- **Python 3.x**: ETL and integration scripts
- **Libraries**:
  - `neo4j`: Python driver
  - `pandas`: Data processing
  - `requests`: Wikidata API calls
  - `SPARQLWrapper`: Wikidata SPARQL queries (optional)

## File Structure

```
/home/jic823/CanadaNeo4j/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── load_geonames.py           # GeoNames ETL script
├── enrich_wikidata.py         # Wikidata integration
├── reconcile.py               # NER reconciliation queries
├── schema/
│   └── constraints.cypher     # Neo4j schema setup
├── data/
│   ├── cities500.txt          # Global cities (225K)
│   └── CA/
│       └── CA.txt             # Canadian data (316K)
└── queries/
    ├── reconciliation.cypher  # Sample queries
    └── statistics.cypher      # Data analysis
```

## Neo4j Configuration

### Connection Details
- **URI**: `bolt://localhost:7687`
- **User**: `neo4j`
- **Password**: TBD

### Required APOC Procedures
- `apoc.text.levenshteinDistance` (fuzzy matching)
- `apoc.spatial.*` (geographic queries)
- `apoc.periodic.iterate` (batch loading)

## Usage Example

### NER Entity: "Regina"
```python
from reconcile import reconcile_place

results = reconcile_place(
    name="Regina",
    context={"admin1": "Saskatchewan", "country": "CA"},
    threshold=0.8
)

# Returns ranked matches with confidence scores
[
    {
        "geonameId": 6141256,
        "name": "Regina",
        "confidence": 0.98,
        "population": 193443,
        "coordinates": (50.45008, -104.61780),
        "wikidataId": "Q2135"
    }
]
```

## Data Quality Considerations

### GeoNames Strengths
- Comprehensive global coverage
- Stable identifiers
- Regular updates
- Rich alternate names

### GeoNames Limitations
- Historical name coverage varies
- Some duplicate entries
- Population data may be outdated
- Administrative boundaries can be complex

### Wikidata Enhancements
- Better historical name coverage
- Structured temporal data
- Cross-references to other LOD sources
- Community-maintained accuracy

## Next Steps

1. Set up Neo4j instance
2. Create schema and constraints
3. Load GeoNames data
4. Test reconciliation queries
5. Integrate Wikidata
6. Connect to NER pipeline
