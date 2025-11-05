# Loading Order for Canadian LOD Knowledge Graph

## Complete Loading Sequence

Execute in this order to build the complete knowledge graph:

### 1. Load GeoNames Data (ALREADY DONE ✓)
```bash
python3 load_geonames.py
```
**Result:**
- 225K global cities (pop > 500)
- 315K Canadian geographic features
- All feature types, including places with population = 0

### 2. Load Wikidata Enrichment
```bash
python3 load_wikidata_from_cache.py
```
**What it loads:**
- 27,423 Wikidata entries
- 24,895 populated places (cities, towns, villages, historical sites)
- 2,528 administrative divisions (townships, counties, RMs)
- 10,491 Wikipedia links
- Historical dates (founded, dissolved)

**Matches by:**
- GeoNames ID (when available)
- Creates new nodes for Wikidata-only entries

**Expected time:** 5-10 minutes

### 3. Load Post Office Data
```bash
python3 load_post_offices.py
```
**What it loads:**
- 26,272 Canadian post offices
- Established dates (1840s-2000s)
- Closing dates for historical offices
- 10,291 still-open post offices

**Conservative matching:**
- Only links when name + province is unique
- Flags ambiguous cases (multiple Maitlands, etc.)
- Creates separate PostOffice nodes

**Expected time:** 3-5 minutes

### 4. Test NER Reconciliation
```bash
python3 reconcile.py
```
**Tests:**
- Maitland, NS (historical shipbuilding center)
- Admiral, SK (small village)
- Westmeath Township, ON (founded 1832)
- Various matching strategies

## Final Knowledge Graph Statistics

**Expected totals:**
- ~342K Place nodes (GeoNames + Wikidata-only)
- ~26K PostOffice nodes
- ~10K Wikipedia links
- ~15K historical/dissolved entities
- ~2,500 townships/counties/administrative divisions

## Data Sources

1. **GeoNames** - Comprehensive geographic coverage
2. **Wikidata** - Rich metadata, Wikipedia links, historical context
3. **Post Offices** - Temporal data, settlement indicators

## Known Limitations

### Coordinate Accuracy
- Some GeoNames coordinates incorrect (e.g., Maitland, NS)
- Wikidata coordinates generally more accurate
- Post offices lack coordinates entirely

### Name Matching Challenges
- Multiple places with same name (Maitland x3 in NS, x2 in ON)
- Historical name changes not fully captured
- French accent variations

### Coverage Gaps
- Maitland, NS: In GeoNames + Wikidata, but wrong GeoNames coords
- Some historically important places lack Wikidata entries
- Not all GeoNames places have post office data

## Usage for NER Reconciliation

### Query Strategies Available

1. **Exact name match** - Fast, high confidence
2. **Fuzzy match** - Handles typos (requires APOC)
3. **Geographic context** - Uses coordinates + radius
4. **Administrative context** - "Regina, Saskatchewan"
5. **Historical names** - Checks alternate names, dissolved places
6. **Post office validation** - Cross-reference founding dates

### Example Workflow

```python
from reconcile import NERReconciler

reconciler = NERReconciler(uri, user, password)

# Smart reconciliation with context
results = reconciler.reconcile_smart(
    'Maitland',
    context={
        'country': 'CA',
        'admin1': 'Nova Scotia',
        'historical': True
    }
)

# Returns ranked matches with confidence scores
# Falls back to multiple strategies automatically
```

## Next Steps After Loading

1. **Test reconciliation** - Verify matching strategies work
2. **Tune confidence thresholds** - Based on your historical research needs
3. **Add custom enrichments** - Manual additions for critical places
4. **Connect to NER pipeline** - Integrate with your OCR/NER workflow
5. **Monitor and improve** - Track mismatches, add corrections

## Maintenance

### Updating Data

- **GeoNames**: Download monthly dumps, reload
- **Wikidata**: Re-run fetch scripts to get new entries
- **Post Offices**: Static historical dataset (unless new source found)

### Manual Corrections

To fix incorrect matches or add missing data:

```cypher
// Add Wikipedia URL to Maitland
MATCH (p:Place {geonameId: 6064484})
SET p.wikipediaUrl = 'https://en.wikipedia.org/wiki/Maitland,_Nova_Scotia',
    p.wikidataId = 'Q6737132'
```

## Backup

Before major operations:

```bash
# Export current database
neo4j-admin dump --database=neo4j --to=/backup/neo4j-$(date +%Y%m%d).dump
```
