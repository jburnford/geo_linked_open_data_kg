# Canadian LOD Knowledge Graph - Status Report

**Last Updated**: November 7, 2025 @ 21:45 EST

## Current Database State (Local)

### Nodes
- **Total**: 6,761,089 nodes
  - Place: 6,233,958 (GeoNames global)
  - AdminDivision: 509,913 (countries, states, provinces, districts)
  - Country: 254
  - Other: Saskatchewan history graph nodes (settlements, institutions, etc.)

### Relationships
- **Total**: 11,536,857 relationships
  - LOCATED_IN_COUNTRY: ~6.2M
  - LOCATED_IN_ADMIN1: ~3.5M
  - LOCATED_IN_ADMIN2: ~200K
  - LOCATED_IN_ADMIN3: **1,103,932** ✅ **JUST COMPLETED**
  - Admin hierarchies (PART_OF): ~210K

### Coverage Statistics
- ADMIN1: 56.2%
- ADMIN2: 5.4%
- ADMIN3: **17.7%** ✅ **NEW**

### Indexes
- **Total**: 33 indexes (all ONLINE)
- Spatial index on Place.location ✓
- Text indexes on Place.name ✓
- Admin code indexes ✓

## Infrastructure Progress

### ✅ Completed Today

1. **Global GeoNames Loading**
   - Loaded 6.2M places from 254 countries
   - Filtered to P, A, S.CMTY, S.PO feature codes (81% reduction from raw data)
   - All relationships established

2. **Administrative Hierarchies**
   - ADMIN1: 3.5M relationships (countries → states/provinces)
   - ADMIN2: 200K relationships (states → counties/districts)
   - ADMIN3: **1.1M relationships** (districts → municipalities) ✅ **NEW**
   - Admin4 hierarchies: 110K relationships

3. **Neo4j Container for Nibi** ✅ **NEW**
   - Built: Neo4j 5.13 Community Edition
   - Size: 278MB
   - Location: `~/projects/def-jic823/CanadaNeo4j/neo4j.sif`
   - Build time: 26 seconds

4. **Historical KG Pipeline Infrastructure** ✅ **NEW**
   - Deployment scripts created
   - Documentation complete
   - Ready for data migration to Nibi

### 🔄 In Progress

1. **Wikidata Full Dump Download** (Job 4063323)
   - Progress: **69GB / 146GB (47%)**
   - Runtime: 1 hour 7 minutes
   - ETA: ~3-4 hours remaining
   - Destination: `~/projects/def-jic823/wikidata/`

2. **Pipeline Jobs on Nibi**
   - olmocr-ner (Job 4069020): UniversalNER processing
   - sarah496_fixed: Archive OCR job

### ⏳ Next Steps

1. **Wait for Wikidata download** (~4 hours)
2. **Filter Wikidata entities**:
   - Pass 1: Geographic (P625) - ~5-10M entities
   - Pass 2: People with places - ~2M entities
   - Pass 3: Organizations - ~500K entities
   - Pass 4: Events - ~300K entities
3. **Deploy Historical KG to Nibi**
4. **Load Wikidata into Nibi Neo4j**
5. **Connect to UniversalNER pipeline**

## Pipeline Architecture

```
Historical Documents
    ↓
[OLMoCR] ✅ Running on Nibi
    ↓
OCR Text + Layout
    ↓
[UniversalNER] ✅ Running (Job 4069020)
    ↓
Named Entities (Places, People, Orgs, Events)
    ↓
[Grounding to Neo4j] ⏳ Next Phase
    ↓
Knowledge Graph (6.2M places + Wikidata entities)
    ↓
[Embedding] ⏳ Future
    ↓
[GraphRAG] ⏳ Future
    ↓
Contextual Query Answering
```

## Storage Utilization

### Local (Laptop)
- Database size: ~5-10 GB
- Available: 50-100 GB (Windows drive 95% full)
- Strategy: Keep lean (places only, limited Wikidata)

### Nibi (Cluster)
- Database target: 100-150 GB
- Wikidata raw: 146 GB (will delete after filtering)
- Container: 278 MB
- Available: ~200-250 GB in project space
- Strategy: Full historical knowledge graph

## Performance Metrics

### Data Loading
- GeoNames: ~6.2M places in batches of 10K
- Admin hierarchies: Country-by-country batching
- ADMIN3: 34 minutes for 138 countries (1.1M relationships)
- Memory: 32GB RAM (laptop), stable performance

### Database Queries
- Simple lookups: <100ms
- Complex hierarchies: <500ms
- Spatial queries: Fast (using point geometry index)

## Expected Final State

### After Wikidata Loading

**Nodes** (estimated):
- Places: 12-16M (6.2M GeoNames + 5-10M Wikidata)
- People: ~2M
- Organizations: ~500K
- Events: ~300K
- Documents: TBD (based on OCR corpus)
- Entity Mentions: TBD (based on NER output)
- **Total: 15-20M nodes**

**Relationships** (estimated):
- Administrative: ~11.5M (current)
- Biographical: ~6M (birth/death/residence places)
- Organizational: ~1.5M (founding, headquarters)
- Event locations: ~1M
- Document mentions: TBD
- Grounding: TBD
- **Total: 80-100M relationships**

**Database Size**: 100-150 GB on Nibi

## Git Repository

- **Local**: `/home/jic823/CanadaNeo4j`
- **Remote**: `github.com:jburnford/geo_linked_open_data_kg.git`
- **Last commit**: "Add Historical Knowledge Graph pipeline infrastructure for Nibi"
- **Files committed**:
  - `build_neo4j_container.sh`
  - `deploy_historical_kg_nibi.sh`
  - `HISTORICAL_KG_PIPELINE.md`
  - `STORAGE_CONSTRAINED_PLAN.md`

## Key Documentation

- `EXPANSION_STRATEGY.md` - 4-phase expansion plan
- `WIKIDATA_MULTI_PASS_PLAN.md` - Multi-pass extraction strategy
- `NEO4J_SCALING_LIMITS.md` - Hardware capacity analysis
- `STORAGE_CONSTRAINED_PLAN.md` - Two-database approach
- `HISTORICAL_KG_PIPELINE.md` - Complete pipeline architecture ✅ **NEW**
- `DATABASE_INFO.md` - Current database state

## Integration Points

### OLMoCR
- Container: `~/projects/def-jic823/olmocr/olmocr.sif`
- Performance: ~1.39 pages/sec on H100
- Output: Structured OCR with layout

### UniversalNER
- Status: Running (Job 4069020)
- Output: Named entities from OCR text
- Integration: Ready for grounding pipeline

### GPT-OSS-120B
- Location: `~/projects/def-jic823/models/gpt-oss-120b/`
- Size: ~240-500 GB
- Purpose: Graph-RAG query interface

## Timeline

- **Today (Nov 7)**: Global expansion complete, infrastructure built
- **Tonight**: Wikidata download completes
- **Tomorrow (Nov 8)**: Filter Wikidata entities
- **Nov 9-10**: Load entities into Nibi Neo4j
- **Week of Nov 11**: Grounding pipeline implementation
- **Future**: Embedding + GraphRAG integration

## Success Metrics

✅ **Infrastructure**: Neo4j container built, deployment ready
✅ **Data Scale**: 6.2M places loaded globally
✅ **Relationships**: 11.5M admin hierarchies complete
✅ **Coverage**: 17.7% ADMIN3 coverage (1.1M links)
🔄 **Wikidata**: Download 47% complete
⏳ **Historical Entities**: Pending Wikidata filtering
⏳ **Pipeline Integration**: NER → KG grounding next phase

---

**Project Vision**: Build a comprehensive historical knowledge graph linking places, people, organizations, and events from global sources (GeoNames, Wikidata) with historical documents (OLMoCR) and entity recognition (UniversalNER) for Graph-RAG question answering.
