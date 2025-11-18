# Global Expansion Strategy - Canadian LOD Knowledge Graph

## Current State (November 2025)

### Database Composition
- **Total Nodes:** 556,626 Place nodes
- **Geographic Coverage:** Canada (comprehensive) + Global cities (pop ≥500)
- **Data Sources:**
  - `cities500.txt`: 225,112 global cities (population ≥ 500)
  - `CA.txt`: 315,928 Canadian geographic features (all types)
  - `Wikidata`: 27,163 Canadian places with rich metadata
  - **After deduplication:** 556,626 unique places

### Infrastructure Status
✅ **Spatial indexes optimized** (102ms query performance for 10km radius)
✅ **Point geometry** on all 556,626 places
✅ **Relationship types:** SAME_AS, NEAR, LOCATED_IN, ADMINISTRATIVELY_LOCATED_IN
✅ **Ready for global scale** (10M+ nodes)

## Phase 1: GeoNames Global Expansion

### Objective
Expand from 556K places to 12M+ global coverage using allCountries.txt

### Data Source
- **File:** `allCountries.txt` (from https://download.geonames.org/export/dump/allCountries.zip)
- **Size:** 1.5GB compressed, ~400MB uncompressed
- **Records:** 12,316,360 geographic features
- **Format:** 19-field tab-delimited (geonameId, name, coordinates, feature codes, population, etc.)

### Strategy: Incremental Country-by-Country Loading

#### Priority Tiers

**Tier 1: English-Speaking Core** (Start Here)
- **US** (~2M records) - Major research collaboration partner
- **GB** (~700K records) - Historical colonial connections
- **AU** (~500K records) - Commonwealth, historical ties
- **NZ** (~100K records) - Commonwealth, historical ties

**Tier 2: Major European Countries**
- **FR** (France) - Colonial history, Quebec connections
- **DE** (Germany) - Large immigrant population to Canada
- **IT** (Italy) - Immigrant population
- **ES** (Spain) - Latin American connections
- **NL** (Netherlands) - Historical fur trade connections
- **IE** (Ireland) - Large immigrant population to Canada

**Tier 3: Historical Connection Countries**
- **IN** (India) - Commonwealth, large immigrant population
- **CN** (China) - Large immigrant population
- **PK** (Pakistan) - Commonwealth, immigrant population
- **HK** (Hong Kong) - Commonwealth history
- **SG** (Singapore) - Commonwealth

**Tier 4: Global Coverage** (Load all remaining countries)

### Loading Commands

```bash
# Tier 1: English-speaking core (test with US first)
python3 load_global_geonames.py --countries US --dry-run
python3 load_global_geonames.py --countries US

# Add more Tier 1 countries
python3 load_global_geonames.py --countries GB,AU,NZ

# Tier 2: European
python3 load_global_geonames.py --countries FR,DE,IT,ES,NL,IE

# Tier 3: Historical connections
python3 load_global_geonames.py --countries IN,CN,PK,HK,SG

# Tier 4: All remaining (excluding already loaded)
python3 load_global_geonames.py --exclude-countries CA
```

### Deduplication Strategy
- **Automatic:** Neo4j MERGE on `geonameId` ensures no duplicates
- **cities500.txt overlap:** Already in database, will be updated (not duplicated)
- **CA.txt overlap:** Canadian records already loaded, will be skipped by default

### Expected Database Growth

| After Loading | Total Places | New Records | Countries |
|---------------|--------------|-------------|-----------|
| **Current** | 556,626 | - | CA + global cities |
| + Tier 1 | ~3.8M | ~3.3M | CA, US, GB, AU, NZ |
| + Tier 2 | ~6M | ~2.2M | + FR, DE, IT, ES, NL, IE |
| + Tier 3 | ~8M | ~2M | + IN, CN, PK, HK, SG |
| + All Countries | ~12.3M | ~11.7M | Global |

### Performance Considerations
- **Query Performance:** Spatial indexes will handle 12M+ nodes efficiently
- **Disk Space:** ~2GB for Neo4j database at full scale
- **Loading Time:** ~10,000 records/second = ~20 minutes per million records
- **Memory:** 10GB RAM recommended for full dataset

## Phase 2: Selective Wikidata Integration

### Objective
Add rich metadata to strategically important places from Wikidata

### Why Selective (Not Comprehensive)?
1. **Wikidata Scale:** 100M+ items (too large for comprehensive integration)
2. **Metadata Quality:** Varies significantly by region and topic
3. **Query Performance:** Only add what provides value for NER reconciliation
4. **Maintenance:** Easier to update smaller, curated dataset

### Target Categories

#### Administrative Divisions (High Priority)
- **Countries** - All countries (already covered via GeoNames)
- **Provinces/States** - First-level administrative divisions
- **Counties/Regions** - Second-level divisions where relevant
- **Municipalities** - Cities, towns with official boundaries (P131 relationships)

**Why:** Critical for resolving ambiguous place names (e.g., "Cambridge" - city or county?)

#### Historical Institutions (Canadian Focus)
- **Residential Schools** (P31=Q3914)
- **Historical Churches** (P31=Q16970)
- **Universities/Colleges** (P31=Q3918)
- **Hospitals** (historical, P31=Q16917)
- **Government Buildings** (P31=Q1307)

**Why:** Core to Saskatchewan History Knowledge Graph use case

#### Infrastructure (Selective)
- **Major Railways** (P31=Q22667, historical lines)
- **Ports** (P31=Q44782)
- **Airports** (P31=Q1248784, major only)
- **Bridges** (P31=Q12280, notable only)

**Why:** Transportation networks crucial for historical settlement patterns

### Geographic Priorities

1. **Canada:** Comprehensive (all categories above)
2. **US:** Administrative divisions + major institutions
3. **UK:** Administrative divisions + Commonwealth historical sites
4. **Other Tier 1/2:** Administrative divisions only

### Implementation Approach

**SPARQL Query Pattern:**
```sparql
SELECT ?item ?itemLabel ?instanceLabel ?coord ?p131 WHERE {
  ?item wdt:P31 wd:Q3914 .  # Instance of: Residential School
  ?item wdt:P17 wd:Q16 .     # Country: Canada
  ?item wdt:P625 ?coord .    # Coordinates required
  OPTIONAL { ?item wdt:P131 ?p131 }  # Administrative territory
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Loading Strategy:**
1. **Fetch by category** (one SPARQL query per entity type)
2. **Cache results** as JSON (version control friendly)
3. **Incremental updates** (monthly or quarterly refresh)
4. **Link to GeoNames** via SAME_AS relationships (geographic matching)

### Wikidata Loading Scripts

```bash
# Canadian institutions (comprehensive)
python3 fetch_wikidata_by_type.py --type residential_school --country CA
python3 fetch_wikidata_by_type.py --type university --country CA
python3 fetch_wikidata_by_type.py --type hospital --country CA --historical

# US administrative divisions
python3 fetch_wikidata_by_type.py --type admin_division --country US --levels 1,2

# UK Commonwealth sites
python3 fetch_wikidata_by_type.py --type colonial_office --country GB
```

### Expected Wikidata Node Additions

| Category | CA | US | GB | Other | Total |
|----------|----|----|----|----|-------|
| **Current** | 27,163 | 0 | 0 | 0 | 27,163 |
| Admin Divisions | +5K | +60K | +30K | +100K | +195K |
| Institutions | +10K | +5K | +2K | +1K | +18K |
| Infrastructure | +2K | +3K | +1K | +500 | +6.5K |
| **Total** | ~44K | ~68K | ~33K | ~101K | ~247K |

## Phase 3: Historical Post Office Integration

### Objective
Add 26,000+ historical Canadian post offices for NER reconciliation

### Data Source
- **Library and Archives Canada** post office records
- **Coverage:** 1867-present (many closed/renamed)
- **Value:** Resolves historical place name ambiguities

### Integration Strategy
1. Load post office records as `PostOffice` nodes (separate from `Place`)
2. Link to `Place` nodes via SAME_AS or NEAR relationships
3. Temporal properties: `openYear`, `closeYear`, `nameChanges`
4. Handle multiple post offices at same location (different time periods)

### Use Case Example
**Problem:** Historical document mentions "Admiral, SK" (1912)
- **GeoNames:** Shows "Admiral" (rural municipality, modern boundaries)
- **Post Office Data:** Shows "Admiral Post Office" (1909-1968, specific building location)
- **Resolution:** Both valid, but post office gives precise historical coordinates

## Phase 4: RAG Integration (Future)

### Objective
Enable semantic search over knowledge graph for historical research

### Components
1. **Vector Embeddings:** Generate embeddings for place descriptions
2. **Graph Context:** Use relationships to augment retrieval
3. **LLM Integration:** Connect to GPT-OSS-120B (already downloaded on Nibi cluster)
4. **Query Interface:** Natural language → Cypher translation

### Example Query
**User:** "Which settlements in Saskatchewan received railways before 1900 and had residential schools?"

**System:**
1. **Semantic Search:** Find "Saskatchewan + railways + 1900 + residential schools"
2. **Graph Query:** Execute Cypher with discovered entities
3. **Context Enhancement:** Add related places, institutions, temporal events
4. **LLM Response:** Natural language answer with citations

## Timeline

| Phase | Duration | Outcome |
|-------|----------|---------|
| **Phase 1 (Tier 1)** | 1 week | US, GB, AU, NZ loaded (~3.8M places) |
| **Phase 1 (Tier 2)** | 1 week | European countries loaded (~6M places) |
| **Phase 1 (Complete)** | 2 weeks | Global coverage (~12.3M places) |
| **Phase 2 (Canada)** | 2 weeks | Canadian Wikidata comprehensive (~44K) |
| **Phase 2 (Global)** | 4 weeks | Strategic global Wikidata (~247K) |
| **Phase 3** | 2 weeks | Historical post offices integrated |
| **Phase 4** | 8 weeks | RAG system deployed |
| **TOTAL** | ~5 months | Production-ready global NER system |

## Success Metrics

### Phase 1 Success
- ✅ 12M+ places loaded
- ✅ Query performance <200ms for 10km radius (any country)
- ✅ Country-level statistics accurate
- ✅ Zero duplicate geonameIds

### Phase 2 Success
- ✅ 250K+ Wikidata places with rich metadata
- ✅ Administrative hierarchies complete (P131 relationships)
- ✅ Canadian institutions comprehensive coverage
- ✅ SAME_AS links between GeoNames and Wikidata validated

### Phase 3 Success
- ✅ 26K+ historical post offices loaded
- ✅ Temporal queries working (e.g., "active in 1912")
- ✅ Name change tracking functional
- ✅ Integration with existing Place nodes tested

### Phase 4 Success
- ✅ Vector search returns relevant places
- ✅ Graph-enhanced context improves LLM responses
- ✅ Natural language queries translate to Cypher accurately
- ✅ Response time <5 seconds for complex queries

## Maintenance Strategy

### GeoNames Updates
- **Frequency:** Quarterly
- **Method:** Incremental updates via modification_date field
- **Command:** `python3 update_geonames.py --since 2025-01-01`

### Wikidata Refresh
- **Frequency:** Monthly for Canadian data, Quarterly for global
- **Method:** Re-run SPARQL queries, MERGE updates
- **Command:** `python3 refresh_wikidata.py --country CA`

### Backup Strategy
- **Daily:** Neo4j automatic backups (last 7 days)
- **Weekly:** Full database export to Cypher dump
- **Monthly:** Archive to long-term storage

## Risk Mitigation

### Performance Degradation
- **Risk:** Queries slow down with 12M+ nodes
- **Mitigation:** Spatial indexes, country filtering, query profiling
- **Monitoring:** Track query times, alert if >500ms

### Data Quality Issues
- **Risk:** Duplicate places, incorrect coordinates, broken relationships
- **Mitigation:** Validation scripts, confidence scoring, manual review queues
- **Monitoring:** Weekly data quality reports

### Storage Constraints
- **Risk:** Database exceeds available disk space
- **Mitigation:** Monitor disk usage, cleanup old backups, optimize node properties
- **Monitoring:** Alert if disk usage >80%

## Next Steps (Immediate)

1. ✅ **Spatial indexes optimized** (COMPLETE)
2. ✅ **Global loader script created** (COMPLETE)
3. ⏳ **Download allCountries.txt** (IN PROGRESS - user action required)
4. 🔜 **Test load US data** (dry-run → actual load)
5. 🔜 **Validate query performance** with US data
6. 🔜 **Proceed to Tier 1 completion** (GB, AU, NZ)
