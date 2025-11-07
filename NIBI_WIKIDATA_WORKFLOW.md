# Wikidata Processing on Nibi - Complete Workflow

## Space Check ✓

**Status**: Ready to proceed
- **Available**: 251 GB
- **Required**: ~120-150 GB (compressed dump) + ~5-15 GB (filtered output)
- **Margin**: ~100 GB safety buffer

## Workflow Overview

1. **Download full Wikidata dump to Nibi** (~2-4 hours)
2. **Filter for P625 entities on Nibi** (~6-10 hours)
3. **Download filtered data to local** (~30 minutes)
4. **Load into Neo4j locally** (~1-3 hours)

## Step 1: Upload Scripts to Nibi

```bash
# From local machine
cd /home/jic823/CanadaNeo4j

# Upload files to Nibi
scp nibi_download_wikidata.sh nibi:~/projects/def-jic823/CanadaNeo4j/
scp nibi_filter_wikidata.sh nibi:~/projects/def-jic823/CanadaNeo4j/
scp filter_wikidata_full_dump.py nibi:~/projects/def-jic823/CanadaNeo4j/
```

## Step 2: Download Full Wikidata Dump

```bash
# SSH to Nibi
ssh nibi

# Create directories
mkdir -p ~/projects/def-jic823/wikidata
mkdir -p ~/projects/def-jic823/CanadaNeo4j

# Submit download job
cd ~/projects/def-jic823/CanadaNeo4j
sbatch nibi_download_wikidata.sh
```

**Expected output:**
- File: `~/projects/def-jic823/wikidata/wikidata-latest-all.json.gz`
- Size: ~120-150 GB (compressed)
- Time: ~2-4 hours

**Monitor progress:**
```bash
# Check job status
squeue -u jic823

# Watch output (once job starts)
tail -f wikidata_download-*.out

# Check download progress
ls -lh ~/projects/def-jic823/wikidata/
```

## Step 3: Filter for Geographic Entities (P625)

```bash
# Once download completes, submit filter job
cd ~/projects/def-jic823/CanadaNeo4j
sbatch nibi_filter_wikidata.sh
```

**What this does:**
- Reads: `wikidata-latest-all.json.gz` (full dump)
- Filters: Only entities with P625 (coordinate location)
- Extracts: All properties we identified in `WIKIDATA_PROPERTIES_ANALYSIS.md`
  - Alternate names (all languages)
  - Historical succession (replaces, replacedBy, follows, followedBy)
  - Colonial context (foundedBy, ownedBy, capitalOf)
  - Cross-database IDs (GND, VIAF, LOC, Getty TGN, OSM, WOF)
  - Temporal data (inception, dissolved)
  - Instance types (colony, trading post, fort, etc.)
- Writes: `wikidata_p625_filtered.json.gz` (compressed, newline-delimited JSON)

**Expected output:**
- File: `~/projects/def-jic823/wikidata/wikidata_p625_filtered.json.gz`
- Size: ~5-15 GB (compressed, estimated)
- Entities: ~5-10 million with coordinates
- Time: ~6-10 hours

**Monitor progress:**
```bash
# Check job status
squeue -u jic823

# Watch filtering progress
tail -f wikidata_filter-*.out

# Look for progress reports every 100K entities
# Example output:
#   Processed 100,000 entities... Found 4,523 with coordinates (4.52%)
#   Processed 200,000 entities... Found 9,187 with coordinates (4.59%)
```

## Step 4: Download Filtered Data to Local

```bash
# From local machine (once filtering completes)
cd /home/jic823/CanadaNeo4j

# Download filtered data
scp nibi:~/projects/def-jic823/wikidata/wikidata_p625_filtered.json.gz .

# Check file size
ls -lh wikidata_p625_filtered.json.gz
```

**Expected:**
- Size: ~5-15 GB
- Download time: ~30 minutes (depends on network)

## Step 5: Load into Neo4j

```bash
# Load from filtered cache
python3 load_wikidata_from_cache.py --cache wikidata_p625_filtered.json.gz
```

**What this does:**
1. Reads filtered Wikidata entities
2. Matches to existing GeoNames places by `geonamesId`
3. Enriches matched places with Wikidata properties
4. Creates new Place nodes for Wikidata-only entities
5. Creates Country relationships
6. Prints statistics

**Expected results:**
- **Matched places**: 500K-2M (enriched with Wikidata)
- **New places**: 3-8M (Wikidata-only, not in GeoNames)
- **Total database**: 10-15M Place nodes
- **Processing time**: 1-3 hours

## Statistics to Expect

### From Filtering (on Nibi)
```
Total entities processed: ~110,000,000
  With coordinates (P625): ~5,000,000-10,000,000 (4-9%)

Of entities with coordinates:
  With GeoNames ID: ~1,500,000-3,000,000 (30-50%)
  With alternate names: ~3,500,000-7,000,000 (70-80%)
  Historical entities: ~250,000-500,000 (5-10%)
  Colonial context: ~100,000-300,000 (2-5%)
  With cross-DB IDs: ~2,000,000-5,000,000 (40-60%)
```

### From Loading (local Neo4j)
```
Total Wikidata entities: ~5-10M
  Matched to GeoNames: ~1.5-3M (enriched)
  New Wikidata-only places: ~3-8M (created)

Final database:
  Total Place nodes: ~10-15M
  With alternate names: ~8-12M (80%+)
  Historical entities: ~250K-500K
  With Wikipedia links: ~3-5M
```

## Cleanup (Optional)

After successful loading, you can delete the full dump to save space:

```bash
# On Nibi (saves ~120-150 GB)
ssh nibi
rm ~/projects/def-jic823/wikidata/wikidata-latest-all.json.gz

# Keep the filtered version for potential re-loading
# Keep: ~/projects/def-jic823/wikidata/wikidata_p625_filtered.json.gz
```

## Post-Load: Create Relationships

After loading, create historical succession and colonial relationships:

```cypher
// Connect historical succession
MATCH (old:Place), (new:Place)
WHERE old.replacedByQid = new.wikidataId
MERGE (old)-[:REPLACED_BY]->(new)
MERGE (new)-[:REPLACES]->(old)

MATCH (earlier:Place), (later:Place)
WHERE earlier.followedByQid = later.wikidataId
MERGE (earlier)-[:FOLLOWED_BY]->(later)
MERGE (later)-[:FOLLOWS]->(earlier)

// Create Organization nodes for colonial entities
MATCH (place:Place)
WHERE place.foundedByQid IS NOT NULL
MERGE (org:Organization {wikidataId: place.foundedByQid})
MERGE (org)-[:FOUNDED]->(place)

MATCH (place:Place)
WHERE place.ownedByQid IS NOT NULL
MERGE (owner:Organization {wikidataId: place.ownedByQid})
MERGE (owner)-[:OWNED]->(place)

// Create indexes for NER
CREATE INDEX alternate_names_idx IF NOT EXISTS
FOR (p:Place) ON (p.alternateNames)

CREATE FULLTEXT INDEX ner_search_idx IF NOT EXISTS
FOR (p:Place) ON EACH [p.name, p.alternateNames, p.officialNames, p.nickname, p.nativeLabel]

CREATE INDEX wikidata_id_idx IF NOT EXISTS
FOR (p:Place) ON (p.wikidataId)
```

## Troubleshooting

### Download Fails
- Script uses `wget -c` for resume capability
- Re-run `sbatch nibi_download_wikidata.sh` to continue

### Filtering Runs Out of Memory
- Current allocation: 32 GB
- If needed, increase in `nibi_filter_wikidata.sh`: `#SBATCH --mem=64G`

### Filtering Takes Too Long
- Normal for full dump (6-10 hours)
- Check progress reports in output file
- If stalled, check job status: `squeue -u jic823`

### Download to Local Fails
- Use `scp -C` for compression during transfer
- Or use `rsync -avz --progress` for resumable transfer

### Neo4j Loading Fails
- Check available disk space locally (need ~20-30 GB for temp files)
- Increase batch size if too slow (edit `load_wikidata_from_cache.py`)

## Timeline

| Step | Duration | Critical Path |
|------|----------|---------------|
| Upload scripts | 5 minutes | No |
| Download dump | 2-4 hours | Yes |
| Filter dump | 6-10 hours | Yes |
| Download filtered | 30 mins | No (can parallelize) |
| Load to Neo4j | 1-3 hours | No (can do locally while other work continues) |
| **Total** | **~10-18 hours** | Mostly waiting |

**Recommendation**: Start download before end of day, let it run overnight.

## Advantages Over SPARQL Approach

| Aspect | SPARQL Endpoint | Full Dump Approach |
|--------|-----------------|-------------------|
| Timeouts | ✗ Frequent 504 errors | ✓ None |
| Completeness | ✗ Must limit results | ✓ Complete dataset |
| Entity count | ~10K per query | ~5-10M total |
| Queries needed | ~5000+ | 1 download + 1 filter |
| Time | ~weeks (with delays) | ~10-18 hours |
| Languages | ✗ Must specify | ✓ All included |
| Future updates | ✗ Re-query everything | ✓ Download new dump |
