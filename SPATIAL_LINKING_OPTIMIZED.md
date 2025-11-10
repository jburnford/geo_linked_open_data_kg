# Optimized Spatial Linking Strategy

## Problem Analysis

**Previous Attempt Performance:**
- 3.6 seconds per WikidataPlace node
- 1.27M places in US alone → 1,300 hours
- 11.5M total places → months of processing

**Root Causes:**
1. No bounding box pre-filtering → full table scan for every spatial query
2. Large batch sizes (50K) → slow iteration feedback
3. Too many candidates evaluated per place
4. No early termination strategies

## Optimization Strategy

### 1. **Bounding Box Pre-Filtering**

**Before (slow):**
```cypher
MATCH (p:Place)
WITH p, point.distance(p.location, $target) / 1000.0 AS distance_km
WHERE distance_km <= 10.0
```
- Calculates distance for ALL 6.2M Place nodes
- ~6.2M distance calculations per WikidataPlace

**After (fast):**
```cypher
MATCH (p:Place)
WHERE p.latitude >= $min_lat AND p.latitude <= $max_lat
  AND p.longitude >= $min_lon AND p.longitude <= $max_lon
WITH p, point.distance(p.location, $target) / 1000.0 AS distance_km
WHERE distance_km <= 10.0
```
- Filters to ~100-1000 candidates via index range scan
- Only calculates distance for candidates in bounding box
- **Expected speedup: 100-1000x for distance calculations**

### 2. **Limit Candidates Per Place**

**Old:** Evaluate all nearby places within 10km (could be hundreds)

**New:** Return only top 5 nearest places
- Reduces database load
- Reduces Python processing
- Focus on most relevant matches

### 3. **Smaller Batch Sizes**

**Old:** 50,000 places per batch → no progress for hours

**New:** 1,000 places per batch
- Better progress tracking
- Faster iteration
- Lower memory usage
- Can resume more easily

### 4. **Higher Confidence Threshold**

**Old:** min_confidence = 0.5

**New:** min_confidence = 0.7
- Reduces false positives
- Fewer low-quality links created
- Faster processing (skip marginal matches)

### 5. **Skip Already-Linked Nodes**

```cypher
WHERE NOT EXISTS((wp)-[:SAME_AS]->())
```
- Automatically resumes from interruptions
- No duplicate work
- Can run multiple jobs safely

## Expected Performance

### Optimistic Estimate:
- **Target**: 10 places/sec (0.1 sec/place)
- **11.5M places**: 1.15M seconds = **320 hours (~13 days)**
- **Per 24-hour job**: ~864K places = 7.5% progress

### Conservative Estimate:
- **Target**: 2-5 places/sec
- **11.5M places**: **64-160 days** total
- **Per 24-hour job**: ~173K-432K places = 1.5-3.8% progress

### Actual Performance will depend on:
- Geographic clustering (some areas denser than others)
- Country size (US, China, India slower than small countries)
- Match quality (high-quality matches found faster)
- Database cache warmth (faster after initial queries)

## Implementation Details

### Haversine Bounding Box Calculation

```python
def haversine_box(lat, lon, distance_km=10.0):
    """Calculate lat/lon ranges for bounding box."""
    R = 6371.0  # Earth radius in km

    # Latitude: same at all longitudes
    lat_delta = (distance_km / R) * (180 / math.pi)

    # Longitude: varies by latitude
    lon_delta = (distance_km / (R * math.cos(math.radians(lat)))) * (180 / math.pi)

    return (
        max(-90, lat - lat_delta),
        min(90, lat + lat_delta),
        lon - lon_delta,
        lon + lon_delta
    )
```

### Spatial Query with Bounding Box

```python
def find_nearby_with_bbox(lat, lon, distance_km=10.0, limit=5):
    """Find up to 5 nearest places using bounding box pre-filter."""
    min_lat, max_lat, min_lon, max_lon = self.haversine_box(lat, lon, distance_km)

    # Query uses lat/lon range indexes first
    result = session.run("""
        MATCH (p:Place)
        WHERE p.geonameId IS NOT NULL
          AND p.latitude >= $min_lat AND p.latitude <= $max_lat
          AND p.longitude >= $min_lon AND p.longitude <= $max_lon
        WITH p,
             point.distance(p.location, point({latitude: $lat, longitude: $lon})) / 1000.0 AS distance_km
        WHERE distance_km <= $max_distance
        RETURN ... ORDER BY distance_km ASC LIMIT $limit
    """, ...)
```

### Country-Based Processing

```python
def link_all_optimized(batch_size=1000):
    """Process all countries in order of unlinked count."""
    countries = get_countries_with_unlinked_counts()  # Ordered by count DESC

    for country_qid, count in countries:
        while True:
            links, processed = link_country_batch(country_qid, batch_size=1000)
            if processed < batch_size:
                break  # Finished this country
```

## Resumability

The script is designed to be **resumable**:

1. Queries only unlinked WikidataPlace nodes:
   ```cypher
   WHERE NOT EXISTS((wp)-[:SAME_AS]->())
   ```

2. Processes countries in batches of 1000

3. If interrupted, rerun the same job script:
   - Already-linked nodes automatically skipped
   - Picks up where it left off
   - No duplicate work

## Monitoring Progress

**During execution:**
- Progress bar shows countries processed
- Per-country statistics printed
- Overall rate (places/sec) displayed

**After completion:**
```cypher
// Check coverage
MATCH (wp:WikidataPlace)
RETURN
    count(wp) as total,
    count((wp)-[:SAME_AS]->()) as linked_same_as,
    count((wp)-[:NEAR]->()) as linked_near,
    count((wp)-[:LOCATED_IN]->()) as linked_located_in
```

## Running the Optimized Linking

**Submit 24-hour job:**
```bash
cd ~/projects/def-jic823/CanadaNeo4j
sbatch run_spatial_linking_optimized.sh
```

**Monitor progress:**
```bash
tail -f ~/projects/def-jic823/CanadaNeo4j/neo4j_spatial_opt_JOBID.out
```

**Resume after completion:**
```bash
# Script automatically resumes - just resubmit
sbatch run_spatial_linking_optimized.sh
```

## Success Criteria

**Target Coverage:**
- Link >60% of WikidataPlace nodes (7M+)
- Focus on high-confidence matches (≥0.7)
- Achieve >2 places/sec average rate

**Quality Metrics:**
- SAME_AS: confidence ≥0.85, distance <1km
- NEAR: confidence ≥0.7, distance ≤10km
- Manual validation of sample shows >90% correct

## Next Steps After Spatial Linking

Once WikidataPlace → Place linking reaches good coverage:

1. **Phase 2: Person Geographic Links**
   - `Person.birthPlaceQid` → `WikidataPlace` (BORN_IN)
   - `Person.deathPlaceQid` → `WikidataPlace` (DIED_IN)
   - Expected: 15-18M relationships, 2-4 hours

2. **Phase 3: Organization Links**
   - `Organization.headquartersQid` → `WikidataPlace`
   - Expected: 300K relationships, 1 hour

3. **Phase 4: Derived Person → Place Links**
   - Via `Person → WikidataPlace → Place` chains
   - Enables direct geographic queries on people

## Files

- `link_spatial_optimized.py` - Optimized spatial linking script
- `run_spatial_linking_optimized.sh` - SLURM job script (24 hours)
- `SPATIAL_LINKING_OPTIMIZED.md` - This document
