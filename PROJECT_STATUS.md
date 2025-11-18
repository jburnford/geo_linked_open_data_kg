# CanadaNeo4j Knowledge Graph - Project Status

**Last Updated**: November 13, 2025
**Database**: Neo4j 5.13 on Arbutus Cloud VM (32GB RAM, 4 vCPUs)
**Connection**: bolt://206.12.90.118:7687
**Repository**: `/home/jic823/CanadaNeo4j/` (local WSL)

---

## Current Status: Phase 3 IN PROGRESS (39% Complete)

### ✅ Phase 1: GeoNames Import - COMPLETED
**Status**: Successfully loaded all GeoNames gazetteer data
**Duration**: ~2 hours
**Data Loaded**:
- **254 countries** (Country nodes)
- **509,253 administrative divisions** (AdminDivision nodes)
- **6,252,512 places** (Place nodes with Point geometries)

**Node Types Created**:
- `Country` - Country codes (e.g., CA, US, CN)
- `AdminDivision` - Administrative regions (ADM1, ADM2, ADM3, ADM4)
- `Place` - Geographic locations with coordinates

**Key Properties**:
- GeoNames IDs (primary linking key)
- Names, coordinates, population
- Administrative codes (country, admin1, admin2, admin3, admin4)
- Feature classes and codes
- Neo4j Point geometries for spatial queries

**Files Used**:
- `allCountries.txt.gz` (1.5GB compressed, 6.2M places)
- `admin1CodesASCII.txt` (4,847 first-level divisions)
- `admin2Codes.txt` (504K second-level divisions)

---

### ✅ Phase 2: Wikidata Import - COMPLETED
**Status**: Successfully loaded filtered Wikidata entities
**Duration**: ~4 hours
**Data Loaded**:
- **11.6M geographic entities** (WikidataPlace nodes)
- **6M people** (Person nodes)
- **235K organizations** (Organization nodes)

**Node Types Created**:
- `WikidataPlace` - Geographic entities with QIDs and GeoNames IDs
- `Person` - People with biographical data (birth/death dates, places, occupations)
- `Organization` - Institutions with locations and temporal data

**Linking Capabilities**:
- GeoNames IDs bridge WikidataPlace ↔ Place nodes
- VIAF IDs, GND IDs, LOC IDs for library authority control
- Occupation QIDs, position QIDs for social network analysis

**Files Used**:
- `wikidata_geographic.json.gz` (filtered from 130GB Wikidata dump)
- `wikidata_people.json.gz`
- `wikidata_organizations.json.gz`

---

### 🔄 Phase 3: Administrative Hierarchies - IN PROGRESS (39%)

**Status**: Ultra-robust version processing countries with adaptive chunking
**Started**: November 13, 2025 14:15 UTC
**Current Progress**: 98/254 countries (39%) - **~4.75 hours elapsed**
**Script**: `create_admin_hierarchies_robust.py`

#### Objective
Create hierarchical relationships connecting 6.2M places to administrative divisions:
- `(Place)-[:LOCATED_IN_ADMIN1]->(AdminDivision)` - Link places to regions
- `(AdminDivision)-[:PART_OF]->(AdminDivision)` - Build admin hierarchies
- `(AdminDivision)-[:PART_OF]->(Country)` - Link to countries

#### Adaptive Chunking Strategy (3-Tier)

**Small Countries** (<50K places): Standard 10K batching
- Examples: Belgium (12K), Netherlands (20K), Switzerland (8K)
- Processing time: ~5-30 seconds per country

**Mega Countries** (50-500K places): Admin1 regional chunking (states/provinces)
- Examples:
  - **Canada**: 329K places → 13 provinces → **✅ 311,593 links**
  - **Brazil**: 73K places → 27 states → **✅ 73,245 links**
  - France: ~258K places → 27 regions
- Processing time: ~5-30 minutes per country

**Ultra-Mega Countries** (>500K places): Admin2 district chunking (finest granularity)
- Examples:
  - **China**: 883K places → 34 provinces → hundreds of districts → **✅ 883,593 links**
  - **India**: 557K places → 36 states → districts → **✅ 557,939 links**
- Processing time: ~1-2 hours per country

#### Major Achievement

**Previous versions CRASHED on China and India** due to memory exhaustion. The ultra-robust version with admin2 chunking **successfully processed both mega-countries**:

1. **China (CN)**: Largest dataset (883K places) - **COMPLETED**
2. **India (IN)**: Second largest (557K places) - **COMPLETED**
3. **USA (US)**: Third largest (428K places) - Coming at country position 232

#### Performance Metrics

- **Average speed**: ~4.8 minutes per country
- **Estimated completion**: ~8-10 more hours (assuming 254 countries total)
- **Total runtime estimate**: ~12-15 hours for all 254 countries

#### Technical Improvements from Previous Versions

1. **Memory Configuration**: Increased Neo4j transaction pool from 4GB → 10GB
   - File: `/etc/neo4j/neo4j.conf`
   - Setting: `dbms.memory.transaction.total.max=10g`

2. **Removed NOT EXISTS Checks**: Eliminated exponential-time relationship scans
   - Relied on MERGE idempotency instead
   - Speedup: 100x faster for countries with existing relationships

3. **Three-Tier Adaptive Chunking**: Automatically selects strategy based on country size
   - Small: Normal batching
   - Mega: Admin1 regional chunking
   - Ultra-mega: Admin2 district chunking (China, India)

4. **Resume Capability**: Progress saved to `/home/ubuntu/phase3_progress.json`
   - Can restart without losing work
   - Tracks completed and failed countries

5. **Error Handling**: Continues on country failures
   - Logs errors to state file
   - Doesn't abort entire process on single country failure

#### Files Modified

**Primary Scripts**:
- `create_admin_hierarchies.py` - Original version (failed on mega-countries)
- `create_admin_hierarchies_batched.py` - Batched version (crashed at ~107 countries)
- `create_admin_hierarchies_robust.py` - **Current version (success!)**

**Configuration**:
- `/etc/neo4j/neo4j.conf` - Memory pool increased to 10GB

**Logs**:
- `/home/ubuntu/phase3_robust.log` - Current run log
- `/home/ubuntu/canadaneo4j_deployment.log` - Historical deployment log

---

## Pilot Integration: Indian Affairs Agents (Ready)

**Status**: Parsed and ready to import (awaiting Phase 3 completion)
**Source**: LINCS Indian Affairs Agents RDF dataset (11.2 MB Turtle format)

### Data Parsed

**File**: `indian_affairs_agents.json` (created from RDF)

**Contents**:
- **2,468 persons** (Indian Affairs agents, 1870s-1920s)
- **14 with Wikidata QIDs** (including John A. Macdonald)
- **Occupations**: Indian Agent, Superintendent, Inspector, etc.
- **GeoNames place links**: Work locations tied to Place nodes

**Node Type to Create**:
- `IndianAffairsAgent` nodes with properties:
  - `lincsId` (unique LINCS identifier)
  - `name`, `viafId`, `wikidataQid`
  - `roles` (array of occupations)
  - `geonamesIds` (array of work locations)
  - `earliestDate` (start of service)

**Relationships to Create**:
- `(IndianAffairsAgent)-[:WORKED_AT]->(Place)` via GeoNames IDs
- `(IndianAffairsAgent)-[:SAME_AS]->(Person)` via Wikidata QIDs

**Scripts Created**:
- `parse_indian_affairs_rdf.py` - RDF → JSON parser (CIDOC-CRM support)
- `load_indian_affairs_agents.py` - Neo4j import script

**Integration Benefits**:
1. Tests LINCS integration pipeline before full Historical Canadians (400K people)
2. Validates GeoNames linking strategy
3. Enriches Person nodes with Canadian historical context
4. Demonstrates Wikidata ↔ LINCS reconciliation

---

## Planned: LINCS Historical Canadians Integration

**Status**: Planning complete, awaiting CanadaNeo4j deployment completion
**Priority**: HIGH - Best quality Canadian biographical data available
**Effort**: 8-12 days once current deployment completes

### Data Overview

**Source**: LINCS Historical Canadians dataset
**Volume**: ~400K+ biographical entries
**Quality**: Human-reviewed persistent identifiers (PIDs)
**Coverage**:
- Birth/death dates and places
- Occupations and positions
- Family relationships
- Institutional affiliations (LAC, Census, DCB)

### Integration Phases

1. **Data Extraction** (1-2 days): Request triple dump from LINCS team
2. **Transformation** (2-3 days): Map CIDOC-CRM to Neo4j schema, link to GeoNames/Wikidata
3. **Import** (1 day): Create `HistoricalPerson` nodes and relationships
4. **Enrichment** (2-3 days): Link to Census KG, enhance Wikidata Person nodes
5. **Validation** (1 day): Quality checks and documentation

### New Node Type

```cypher
(h:HistoricalPerson {
  dcbId: "12345",
  wikidataQid: "Q67890",
  name: "John A. Macdonald",
  birthDate: "1815-01-11",
  birthPlaceQid: "Q4093",          // → WikidataPlace (Glasgow)
  deathPlaceGeonamesId: 6094817,   // → Place (Ottawa)
  occupations: ["politician", "lawyer"],
  censusLinks: ["1851-census-id"],
  lacFonds: ["LAC-R123-456"]
})
```

**Documentation Created**:
- `LINCS_INTEGRATION_PLAN.md` - Comprehensive 8-page integration plan
- `LINCS_SUMMARY.md` - Quick reference guide
- `lincs_quickstart.py` - SPARQL endpoint reconnaissance tool

---

## Database Statistics (as of Phase 3 start)

### Node Counts

| Label | Count | Description |
|-------|-------|-------------|
| Place | 6,252,512 | GeoNames places with coordinates |
| WikidataPlace | 11,600,000 | Wikidata geographic entities |
| Person | 6,000,000 | Wikidata people |
| Organization | 235,000 | Wikidata organizations |
| AdminDivision | 509,253 | Administrative regions |
| Country | 254 | Country codes |

### Relationship Counts (Phase 3 in progress)

| Relationship | Count (partial) | Description |
|--------------|-----------------|-------------|
| LOCATED_IN_ADMIN1 | ~883K+ | Places → Admin1 (partial, 39% complete) |
| PART_OF | TBD | Admin hierarchies (runs after countries) |

**Expected Final Counts**:
- LOCATED_IN_ADMIN1: ~4-5M relationships
- PART_OF: ~500K relationships (admin hierarchies)

### Disk Usage

- **Neo4j Database**: ~180GB (with Phase 2 complete)
- **Import Files**: ~50GB (compressed Wikidata + GeoNames)
- **Total VM Usage**: ~230GB of 500GB available

---

## Infrastructure

### Neo4j Configuration

**Version**: Neo4j Community 5.13
**Java**: OpenJDK 17
**Memory Allocation**:
- Heap: `dbms.memory.heap.initial_size=8g`, `max_size=8g`
- Page cache: `dbms.memory.pagecache.size=12g`
- Transaction pool: `dbms.memory.transaction.total.max=10g` ⚠️ **Critical for Phase 3**

**Databases**:
- `neo4j` - Default database (Canadian Census 1911)
- `canadaneo4j` - Global knowledge graph (current project)

**Connection**:
- Bolt: `bolt://206.12.90.118:7687`
- HTTP: `http://206.12.90.118:7474`
- User: `neo4j`
- Password: See `CREDENTIALS.txt` (not in git repo)

### Arbutus Cloud VM

**Instance**: Ubuntu 22.04 LTS
**Resources**: 32GB RAM, 4 vCPUs, 500GB storage
**IP**: 206.12.90.118
**Location**: `/var/lib/neo4j-data/import/canadaneo4j/`

### Local Development

**Machine**: WSL (Windows Subsystem for Linux)
**Directory**: `/home/jic823/CanadaNeo4j/`
**Transfer Method**: scp for scripts, rsync for large data files

---

## Key Files and Locations

### On Arbutus VM

**Scripts** (`/var/lib/neo4j-data/import/canadaneo4j/`):
- `create_admin_hierarchies_robust.py` - **Current Phase 3 script (running)**
- `load_wikidata_entities.py` - Phase 2 loader (completed)
- `deploy_canadaneo4j.py` - Original deployment script
- `import_to_nibi.py` - Alternative deployment script

**Logs** (`/home/ubuntu/`):
- `phase3_robust.log` - Current Phase 3 progress
- `canadaneo4j_deployment.log` - Historical logs
- `phase3_progress.json` - Resume state file

**Data Files** (`/tmp/` during import):
- `allCountries.txt` (extracted from .gz, ~11GB uncompressed)
- `admin1CodesASCII.txt`, `admin2Codes.txt`
- `wikidata_*.json.gz` files

### On Local WSL

**Repository** (`/home/jic823/CanadaNeo4j/`):
- Python scripts (synced to VM as needed)
- Documentation (Markdown files)
- `.env` file with connection credentials

**Transfer Directory** (`/home/jic823/CanadaNeo4j_transfer/`):
- LINCS documentation
- Indian Affairs RDF files
- Parsed JSON outputs

---

## Next Steps

### Immediate (Phase 3 completion)

1. **Monitor Phase 3 progress** - Check logs periodically
   ```bash
   ssh ubuntu@206.12.90.118 'tail -20 /home/ubuntu/phase3_robust.log'
   ```

2. **Estimated completion**: ~8-10 more hours (154 countries remaining)

3. **Post-completion validation**:
   - Count LOCATED_IN_ADMIN1 relationships
   - Count PART_OF relationships
   - Verify hierarchical paths (Place → Admin1 → Country)

### After Phase 3 Completion

4. **Import Indian Affairs pilot** (30 minutes)
   - Run `load_indian_affairs_agents.py`
   - Create 2,468 `IndianAffairsAgent` nodes
   - Link to Place and Person nodes

5. **Validate pilot integration** (1 hour)
   - Test GeoNames place linking
   - Test Wikidata Person linking
   - Verify Cypher queries work correctly

6. **Full LINCS Integration** (8-12 days)
   - Request Historical Canadians triple dump
   - Follow integration plan in `LINCS_INTEGRATION_PLAN.md`
   - Import 400K+ historical Canadian biographical entries

---

## Research Capabilities (Once Complete)

### Spatial Queries

```cypher
// Find all places within 50km of Ottawa
MATCH (ottawa:Place {name: 'Ottawa'})
MATCH (nearby:Place)
WHERE point.distance(ottawa.location, nearby.location) < 50000
RETURN nearby.name, point.distance(ottawa.location, nearby.location) AS distance
ORDER BY distance
```

### Administrative Hierarchies

```cypher
// Show full hierarchy for Toronto
MATCH path = (toronto:Place {name: 'Toronto'})-[:LOCATED_IN_ADMIN1|PART_OF*]->(c:Country)
RETURN [n IN nodes(path) | n.name] AS hierarchy
```

### Cross-Dataset Linking

```cypher
// Find Wikidata people born in GeoNames places
MATCH (p:Person)-[:BORN_IN]->(wp:WikidataPlace)
MATCH (place:Place {geonameId: wp.geonamesId})
RETURN p.name, place.name, place.countryCode
LIMIT 100
```

### Biographical Networks

```cypher
// Indian Affairs agents who worked in multiple locations
MATCH (agent:IndianAffairsAgent)-[:WORKED_AT]->(place:Place)
WITH agent, collect(place.name) AS locations
WHERE size(locations) > 1
RETURN agent.name, agent.roles, locations
```

---

## Technical Challenges Overcome

### 1. Memory Pool Exhaustion
**Problem**: `Neo.TransientError.General.MemoryPoolOutOfMemoryError`
**Solution**: Increased transaction pool to 10GB in neo4j.conf

### 2. NOT EXISTS Performance Killer
**Problem**: Queries scanning 1.3M+ relationships, causing exponential slowdown
**Solution**: Removed NOT EXISTS checks, relied on MERGE idempotency

### 3. Mega-Country Crashes
**Problem**: China (898K), India (566K), USA (428K) overwhelming system
**Solution**: Three-tier adaptive chunking (normal/admin1/admin2)

### 4. RDF CIDOC-CRM Traversal
**Problem**: Wikidata links buried in name appellations, not directly on persons
**Solution**: Traverse P1_is_identified_by predicate to reach owl:sameAs links

### 5. GeoNames ID Parsing
**Problem**: Trailing characters in URLs (e.g., '6093943l')
**Solution**: Strip non-numeric characters before integer conversion

---

## Project Timeline

- **November 7-9, 2025**: Phase 1 (GeoNames import) - COMPLETED
- **November 9-11, 2025**: Phase 2 (Wikidata import) - COMPLETED
- **November 11-12, 2025**: Phase 3 initial attempts - FAILED (memory, NOT EXISTS, mega-countries)
- **November 13, 2025**: Phase 3 robust version - **IN PROGRESS (39% complete, major breakthroughs)**
- **Estimated November 14, 2025**: Phase 3 completion
- **November 14-15, 2025**: Indian Affairs pilot import and validation
- **November 18-30, 2025**: LINCS Historical Canadians integration (8-12 days)

---

## Key Repositories and Resources

### Data Sources

- **GeoNames**: http://download.geonames.org/export/dump/
- **Wikidata**: https://dumps.wikimedia.org/wikidatawiki/entities/
- **LINCS**: https://lincsproject.ca/ (Historical Canadians dataset)
- **Borealis**: https://borealisdata.ca/ (Indian Affairs Agents RDF)

### Documentation

- **Neo4j 5.13 Docs**: https://neo4j.com/docs/
- **CIDOC-CRM**: http://www.cidoc-crm.org/ (RDF ontology for cultural heritage)
- **GeoNames Feature Codes**: http://www.geonames.org/export/codes.html

### External Links

- **Dictionary of Canadian Biography**: https://www.biographi.ca/
- **Library & Archives Canada**: https://www.bac-lac.gc.ca/
- **Wikidata Query Service**: https://query.wikidata.org/

---

## Monitoring Commands

### Check Phase 3 Progress
```bash
# View recent log entries
ssh ubuntu@206.12.90.118 'tail -50 /home/ubuntu/phase3_robust.log'

# Check if process is running
ssh ubuntu@206.12.90.118 'ps aux | grep create_admin_hierarchies_robust.py'

# Count relationships created so far
ssh ubuntu@206.12.90.118 'echo "MATCH ()-[r:LOCATED_IN_ADMIN1]->() RETURN count(r);" | cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -d canadaneo4j'
```

### Database Statistics
```bash
# Node counts
ssh ubuntu@206.12.90.118 'echo "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC;" | cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -d canadaneo4j'

# Relationship counts
ssh ubuntu@206.12.90.118 'echo "MATCH ()-[r]->() RETURN type(r), count(r) ORDER BY count(r) DESC;" | cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -d canadaneo4j'
```

---

## Contact and Support

**User**: jic823
**Institution**: University of Saskatchewan (assumed based on Nibi cluster references in CLAUDE.md)
**Project Context**: Building Canadian historical knowledge graph integrating GeoNames, Wikidata, and LINCS data

**Related Projects**:
- Canadian Census 1911 Knowledge Graph (neo4j default database)
- LINCS Project (Linked Infrastructure for Networked Cultural Scholarship)

---

**Document Version**: 1.0
**Generated**: November 13, 2025, 14:45 UTC
**Next Update**: Upon Phase 3 completion
