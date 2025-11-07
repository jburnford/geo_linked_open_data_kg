# Canadian LOD Knowledge Graph - Database Information

## Neo4j Connection Details

- **URI:** `bolt://localhost:7687`
- **Username:** `neo4j`
- **Password:** See `.env` file (NEO4J_PASSWORD)
- **Database:** Default (`neo4j`)

## Database Statistics

**Total Nodes:** 556,626 Place nodes

**Node Breakdown:**
- Places with GeoNames ID: 539,053
- Places with Wikidata ID: 27,163
- Places with both: 9,590
- GeoNames-only: 529,463
- Wikidata-only: 17,573

## Relationships

### 1. ADMINISTRATIVELY_LOCATED_IN (13,950)
From Wikidata P131 (located in administrative territory)
- Source: Official Wikidata administrative boundaries
- Properties: `source`, `fetchedDate`
- Example: High Park → Toronto

### 2. NEAR (7,566)
Spatial proximity between distinct entities
- Confidence: ≥0.5
- Distance: Within 10km
- Properties: `distance_km`, `confidence`, `matchMethod`, `linkedDate`
- Example: Port Maitland NEAR Maitland (3km apart, different places)

### 3. LOCATED_IN (12,643)
Geographic containment (inferred from coordinates)
- POI/building contained in settlement/admin division
- Distance: <5km
- Entity hierarchy: building (priority 10) < settlement (70) < admin (85)
- Properties: `distance_km`, `confidence`, `matchMethod`, `linkedDate`
- Example: St. Mary's Church LOCATED_IN Montreal

### 4. SAME_AS (3,424)
High-confidence identity (same entity in different databases)
- Confidence: ≥0.85
- Distance: <1km
- Name match: Required (50% weight in scoring)
- Properties: `confidence`, `distance_km`, `evidence`
- Example: Wikidata "Toronto" SAME_AS GeoNames "Toronto"

## Schema

### Place Node Properties

#### Core Identifiers
- `geonameId`: int (unique, indexed)
- `wikidataId`: string (Q-number, indexed when present)

#### Names
- `name`: string (primary name, indexed)
- `asciiName`: string (ASCII version, indexed)
- `alternateNames`: list[string] (full-text indexed)

#### Geographic
- `latitude`: float
- `longitude`: float
- `countryCode`: string (ISO 2-letter)
- `featureClass`: string (P, H, T, L, etc.)
- `featureCode`: string (PPL, PPLA, ADM1, etc.)

#### Metadata
- `population`: int
- `elevation`: int (meters)
- `timezone`: string
- `modifiedDate`: date
- `instanceOfLabel`: string (Wikidata entity type)

## Data Sources

### GeoNames
- **cities500.txt:** 225,112 global cities (population ≥ 500)
- **CA.txt:** 315,928 Canadian geographic features (all types)
- **License:** Creative Commons Attribution 4.0

### Wikidata
- **Canadian Places:** 27,163 entities with coordinates
- **P131 Relationships:** 28,710 cached administrative relationships
- **Coverage:** All Canadian places from Wikidata SPARQL query
- **License:** CC0 (Public Domain)

## Linking Strategy - Precision First

**Philosophy:** Zero tolerance for false identity (SAME_AS) links

**Confidence Scoring:**
- **Name similarity:** 50% weight (CRITICAL)
- **Distance:** 30% weight
- **Entity type compatibility:** 20% weight

**Thresholds:**
- SAME_AS: confidence ≥0.85, distance <1km, name match required
- NEAR: confidence ≥0.5, distance ≤10km
- LOCATED_IN: POI priority <60, settlement priority ≥60, distance ≤5km

## File Locations

### Scripts
- `load_geonames.py` - Load GeoNames data
- `load_wikidata_from_cache.py` - Load cached Wikidata entities
- `fetch_wikidata_p131_relationships.py` - Fetch P131 admin relationships
- `link_by_geography.py` - Geographic linking (NEAR/LOCATED_IN/SAME_AS)

### Data Files
- `cities500.txt` - Global cities data (ignored in git)
- `CA/CA.txt` - Canadian GeoNames data (ignored in git)
- `wikidata_canada_*.json` - Cached Wikidata entities (ignored in git)
- `wikidata_p131_relationships.json` - Cached P131 data (ignored in git, 976KB)

### Logs
- `geographic_linking.log` - Latest geographic linking run

## Cypher Query Examples

### Find a place by name
```cypher
MATCH (p:Place)
WHERE p.name = 'Toronto'
   OR 'Toronto' IN p.alternateNames
RETURN p
LIMIT 10
```

### Find places SAME_AS linked
```cypher
MATCH (wd:Place)-[r:SAME_AS]->(gn:Place)
WHERE wd.wikidataId IS NOT NULL AND gn.geonameId IS NOT NULL
RETURN wd.name, gn.name, r.confidence, r.distance_km
ORDER BY r.confidence DESC
LIMIT 20
```

### Find POIs LOCATED_IN a settlement
```cypher
MATCH (poi:Place)-[r:LOCATED_IN]->(settlement:Place)
WHERE settlement.name = 'Montreal'
RETURN poi.name, poi.wikidataId, r.distance_km, r.confidence
ORDER BY r.confidence DESC
LIMIT 20
```

### Find administrative hierarchy
```cypher
MATCH (child:Place)-[r:ADMINISTRATIVELY_LOCATED_IN]->(parent:Place)
WHERE child.name = 'High Park'
RETURN child.name, parent.name, child.wikidataId, parent.wikidataId
```

### Find nearby places
```cypher
MATCH (p1:Place)-[r:NEAR]->(p2:Place)
WHERE p1.name =~ '(?i).*maitland.*'
RETURN p1.name, p2.name, r.distance_km, r.confidence
ORDER BY r.confidence DESC
```

## Global Expansion Roadmap

### Current Status: Ready for Global Scale ✅
- ✅ Spatial indexes optimized (102ms query performance)
- ✅ Point geometry on all 556,626 places
- ✅ Infrastructure tested for 10M+ nodes
- ✅ Global loader script ready (`load_global_geonames.py`)

### Phase 1: GeoNames Global Expansion (In Progress)

**Objective:** Expand from 556K → 12.3M places worldwide

**Data Source:** `allCountries.txt` from https://download.geonames.org/export/dump/allCountries.zip
- Size: 1.5GB compressed
- Records: 12,316,360 geographic features
- Format: 19-field GeoNames standard

**Loading Strategy:** Country-by-country incremental approach

**Tier 1 (Priority):** US, GB, AU, NZ (~3.3M new records)
```bash
python3 load_global_geonames.py --countries US,GB,AU,NZ
```

**Tier 2:** FR, DE, IT, ES, NL, IE (~2.2M new records)
```bash
python3 load_global_geonames.py --countries FR,DE,IT,ES,NL,IE
```

**Tier 3:** IN, CN, PK, HK, SG (~2M new records)

**Tier 4:** All remaining countries (~4M new records)
```bash
python3 load_global_geonames.py --exclude-countries CA
```

**Expected Timeline:** 2-4 weeks (country-by-country testing and validation)

### Phase 2: Selective Wikidata Integration

**Objective:** Add rich metadata for strategically important places

**Target Coverage:**
- **Canadian Institutions:** Comprehensive (residential schools, universities, hospitals)
- **Global Admin Divisions:** All first and second-level administrative boundaries
- **Infrastructure:** Major railways, ports, historical sites

**Expected Additions:** ~247K Wikidata nodes with rich metadata

**Timeline:** 4-6 weeks after Phase 1 completion

### Phase 3: Historical Post Office Data

**Objective:** Integrate 26K+ Canadian post offices for NER reconciliation

**Test Cases:**
- Maitland, NS (wrong coords in GeoNames)
- Admiral, SK (settlement vs rural municipality)
- Westmeath, ON (multiple entities)

**Timeline:** 2 weeks

### Phase 4: RAG Integration

**Objective:** Connect to GPT-OSS-120B for semantic search over knowledge graph

**Components:**
- Vector embeddings for place descriptions
- Natural language → Cypher query translation
- Graph-enhanced context for LLM responses

**Timeline:** 8 weeks

## Documentation

- **EXPANSION_STRATEGY.md:** Detailed expansion plan, priorities, and timelines
- **DATABASE_INFO.md:** Current database statistics and schema (this file)
- **README.md:** Project overview and quick start guide

## Next Immediate Steps

1. ⏳ Download correct `allCountries.txt` (12.3M records, not postal codes)
2. 🔜 Test load US data (dry-run → actual load)
3. 🔜 Validate query performance with multi-country dataset
4. 🔜 Load Tier 1 countries (US, GB, AU, NZ)
5. 🔜 Begin Wikidata integration planning
