# Global LOD Knowledge Graph for NER Reconciliation

## Overview
Linked Open Data knowledge graph combining GeoNames and Wikidata for reconciling Named Entity Recognition results in historical research pipelines.

**Current Scale:** 556,626 places (Canada comprehensive + global cities)
**Target Scale:** 12M+ places (global coverage)
**Status:** ✅ Spatial indexes optimized, 🚀 Ready for global expansion

## Data Sources

### GeoNames (✅ Loaded)
- **cities500.txt**: 225,112 global cities with population > 500 ✅
- **CA.txt**: 315,928 Canadian geographic features (all types) ✅
- **allCountries.txt**: 12.3M global features (⏳ In Progress - see Phase 1)
- **License**: Creative Commons Attribution 4.0

### Wikidata (27,163 Canadian places ✅, Global expansion planned)
- Entity linking with P131 administrative relationships
- Additional metadata: Wikipedia links, alternative names, historical data
- Q-numbers for LOD integration
- **Phase 2 Target**: ~247K strategically selected global places

**After deduplication:** 556,626 unique Place nodes currently loaded

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

#### Geographic and Administrative Relationships

**Precision-First Philosophy**: We maintain high precision by using three distinct relationship types:

1. **`SAME_AS`** - Identity (same entity in different databases)
   - Confidence >= 0.85
   - Distance < 1km
   - Name match required (50% weight in scoring)
   - Example: Wikidata "Toronto" → GeoNames "Toronto"

2. **`NEAR`** - Spatial proximity (nearby but distinct entities)
   - Confidence >= 0.5
   - Within 10km radius
   - May have different names
   - Example: "Port Maitland" NEAR "Maitland" (3km apart)

3. **`LOCATED_IN`** - Geographic containment (inferred from coordinates)
   - POI/building entity contained in settlement/admin division
   - Distance < 5km
   - Entity hierarchy: building (priority 10) < settlement (70) < admin (85)
   - Example: "St. Mary's Church" LOCATED_IN "Montreal"

4. **`ADMINISTRATIVELY_LOCATED_IN`** - Wikidata P131 relationships
   - Direct from Wikidata (located in administrative territory)
   - Official administrative boundaries
   - Example: "High Park" ADMINISTRATIVELY_LOCATED_IN "Toronto"

#### Core Relationships
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

### Phase 1: GeoNames Global Expansion (⏳ In Progress)
**Status:** Infrastructure ready, loading global data country-by-country

1. ✅ Load cities500.txt (225K global cities)
2. ✅ Load CA.txt (316K Canadian features)
3. ✅ Create spatial indexes (102ms query performance)
4. ✅ Add point geometry to all places
5. ⏳ Load allCountries.txt by tiers:
   - **Tier 1:** US, GB, AU, NZ (~3.3M new records)
   - **Tier 2:** FR, DE, IT, ES, NL, IE (~2.2M)
   - **Tier 3:** IN, CN, PK, HK, SG (~2M)
   - **Tier 4:** All remaining (~4M)

**Timeline:** 2-4 weeks
**See:** `EXPANSION_STRATEGY.md` for detailed plan

### Phase 2: Selective Wikidata Integration (Planned)
**Target:** Add rich metadata to ~247K strategically important places

1. ✅ Canadian places loaded (27K with P131 relationships)
2. 🔜 Global administrative divisions (all countries)
3. 🔜 Canadian institutions comprehensive (residential schools, universities, hospitals)
4. 🔜 Infrastructure (major railways, ports, historical sites)

**Timeline:** 4-6 weeks after Phase 1
**See:** `EXPANSION_STRATEGY.md` Phase 2 details

### Phase 3: Historical Post Office Data (Planned)
1. Load 26K+ Canadian post offices
2. Temporal property handling (open/close dates)
3. Link to existing Place nodes
4. Test NER disambiguation cases

**Timeline:** 2 weeks

### Phase 4: RAG Integration (Planned)
1. Vector embeddings for place descriptions
2. Connect to GPT-OSS-120B (already downloaded on Nibi cluster)
3. Natural language → Cypher query translation
4. Graph-enhanced LLM responses

**Timeline:** 8 weeks

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
├── README.md                        # Quick start guide (this file)
├── DATABASE_INFO.md                 # Database schema and statistics
├── EXPANSION_STRATEGY.md            # Detailed expansion plan and timelines
├── requirements.txt                 # Python dependencies
├── .env                            # Neo4j credentials (not in git)
│
├── load_geonames.py                # Original GeoNames loader (CA + cities500)
├── load_global_geonames.py         # Global loader with country filtering ✨
├── add_spatial_indexes.py          # Spatial index setup ✨
├── link_by_geography.py            # Geographic relationship builder
├── load_wikidata_from_cache.py     # Wikidata loader
├── fetch_wikidata_p131_relationships.py  # P131 admin relationships
│
├── data/
│   ├── cities500.txt               # Global cities (225K) ✅
│   ├── allCountries.txt            # Global features (12.3M) ⏳
│   ├── CA/
│   │   └── CA.txt                  # Canadian data (316K) ✅
│   ├── wikidata_canada_*.json      # Cached Wikidata entities
│   └── wikidata_p131_relationships.json  # Cached P131 data
│
├── geographic_linking.log          # Latest geographic linking run
└── spatial_index_setup.log         # Spatial index creation log
```

✨ = New scripts for global expansion

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

## Quick Start

### Prerequisites
- Neo4j running on `bolt://localhost:7687`
- Python 3.x with dependencies: `pip install -r requirements.txt`
- `.env` file with Neo4j credentials

### Current Status Verification
```bash
# Check database statistics
python3 -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'your-password')); print(driver.session().run('MATCH (p:Place) RETURN count(p)').single())"
```

### Global Expansion - Next Steps

**Step 1: Download correct allCountries.txt**
```bash
cd /home/jic823/CanadaNeo4j

# Rename wrong file (postal codes)
mv allCountries.txt allCountries_postalcodes_WRONG.txt

# Download correct GeoNames dump (~1.5GB compressed)
wget https://download.geonames.org/export/dump/allCountries.zip
unzip allCountries.zip

# Verify format (should show "19 fields")
head -1 allCountries.txt | awk -F'\t' '{print NF " fields"}'
```

**Step 2: Test with US data (dry-run)**
```bash
python3 load_global_geonames.py --countries US --dry-run
```

**Step 3: Load Tier 1 countries**
```bash
python3 load_global_geonames.py --countries US,GB,AU,NZ
```

**Step 4: Verify and continue**
- Check query performance
- Review statistics
- Proceed to Tier 2 countries

## Documentation

- **README.md** (this file): Quick start and overview
- **DATABASE_INFO.md**: Schema, statistics, relationship types, query examples
- **EXPANSION_STRATEGY.md**: Detailed expansion plan, timelines, priorities
- **spatial_index_setup.log**: Spatial optimization results
- **geographic_linking.log**: Relationship creation results

## Support

For detailed expansion strategy, see `EXPANSION_STRATEGY.md`
For database schema and queries, see `DATABASE_INFO.md`
