# Ready to Link: WikidataPlace → Place

## Status: ✅ Scripts Created and Tested

The adapted spatial linking code is ready to run on the Nibi cluster.

## What's Ready

### 1. Main Linking Script: `link_wikidata_places_global.py`

Adapted from proven `link_by_geography.py` (Canadian LOD project) for global scale:

**Phase 1.1: Direct geonamesId Links**
- Fast direct matching via `WikidataPlace.geonamesId` → `Place.geonameId`
- Expected: ~2-3M SAME_AS relationships
- Time: ~30 minutes
- Confidence: 1.0 (exact ID match)

**Phase 1.2: Geographic Proximity Links**
- Country-by-country spatial linking for memory efficiency
- Expected: ~7-10M relationships (SAME_AS, NEAR, LOCATED_IN)
- Time: 4-6 hours
- Uses proven confidence scoring formula

**Confidence Scoring (from Canadian LOD):**
```python
confidence = (distance_score * 0.30) + (name_similarity * 0.50) + (entity_type * 0.20)
```

**Relationship Types:**
- `SAME_AS`: High confidence (≥0.85), close distance (<1km), name similarity
- `NEAR`: Spatial proximity (≥0.5 confidence, ≤10km distance)
- `LOCATED_IN`: POI/building contained within settlement (<5km, low priority entity)

### 2. SLURM Job Script: `run_wikidata_linking.sh`

Complete job submission script:
- Allocates: 8 CPUs, 64GB RAM, 8 hours
- Starts Neo4j server
- Runs both Phase 1.1 and 1.2
- Prints statistics and sample links
- Shuts down cleanly

## Database State

**Current (from Job 4149050):**
```
Total Nodes: 24,568,022
- WikidataPlace: 11,555,027 (to be linked)
- Place: 6,233,958 (GeoNames targets)
- Person: 6,033,891
- AdminDivision: 509,913
- Organization: 234,979
- Country: 254

Relationships: ~11.5M (admin hierarchies)
```

**Expected After Phase 1:**
```
New Relationships: ~9-13M
- SAME_AS: ~2-3M (direct ID + high confidence spatial)
- NEAR: ~3-4M (spatial proximity)
- LOCATED_IN: ~2-3M (POI containment)

Total Relationships: ~21-25M
```

## How to Run

### Option 1: Run Complete Linking Job (Recommended)

```bash
# On Nibi cluster
cd ~/projects/def-jic823/CanadaNeo4j
sbatch run_wikidata_linking.sh
```

This will:
1. Start Neo4j
2. Run Phase 1.1 (direct geonamesId links)
3. Run Phase 1.2 (geographic proximity, country-by-country)
4. Print statistics
5. Shutdown cleanly

**Expected runtime**: 4-8 hours total

### Option 2: Test Phase 1.1 Only (Quick Test)

```bash
# Start a query session first
sbatch neo4j_query_session.sh

# Once running, from local machine:
ssh -L 7687:NODE:7687 nibi
python3 link_wikidata_places_global.py
# (Ctrl+C after Phase 1.1 completes to stop early)
```

**Expected runtime**: ~30 minutes for Phase 1.1

## Monitoring

**Check job status:**
```bash
squeue -u jic823
```

**Watch progress:**
```bash
tail -f ~/projects/def-jic823/CanadaNeo4j/neo4j_wikidata_linking_JOBID.out
```

**Key progress indicators:**
- Phase 1.1: "Created X SAME_AS relationships via geonamesId match"
- Phase 1.2: Progress bar per country (tqdm)
- Final: "WikidataPlace linking complete!"

## Validation Queries

Once complete, verify linking quality:

```cypher
// Check WikidataPlace linking coverage
MATCH (wp:WikidataPlace)
RETURN
    count(wp) as total,
    count((wp)-[:SAME_AS]->()) as direct_match,
    count((wp)-[:NEAR]->()) as proximity_match,
    count((wp)-[:LOCATED_IN]->()) as contained

// Sample high-confidence links
MATCH (wp:WikidataPlace)-[r:SAME_AS]->(p:Place)
WHERE r.confidence > 0.9
RETURN wp.name, p.name, r.confidence, r.distance_km
LIMIT 20

// Check relationship distribution
MATCH ()-[r]->()
WITH type(r) as relType, count(r) as count
RETURN relType, count
ORDER BY count DESC
```

## Next Steps After Phase 1

Once WikidataPlace → Place linking is complete, proceed to:

**Phase 2: Person Geographic Links**
- `Person.birthPlaceQid` → `WikidataPlace.qid` (BORN_IN)
- `Person.deathPlaceQid` → `WikidataPlace.qid` (DIED_IN)
- `Person.residenceQids[]` → `WikidataPlace.qid` (RESIDED_IN)
- `Person.citizenshipQid` → `WikidataPlace.qid` (CITIZEN_OF)
- Expected: ~15-18M relationships, ~2-4 hours

**Phase 3: Organization Geographic Links**
- `Organization.headquartersQid` → `WikidataPlace.qid` (HEADQUARTERED_IN)
- `Organization.foundedInQid` → `WikidataPlace.qid` (FOUNDED_IN)
- Expected: ~300K relationships, ~1 hour

**Phase 4: Organization-Person Links**
- `Organization.founderQids[]` → `Person.qid` (FOUNDED)
- Expected: ~300K relationships, ~1 hour

See `ENTITY_LINKING_PLAN_UPDATED.md` for complete details.

## Key Differences from Canadian LOD Project

| Aspect | Canadian LOD (2024) | Global Scale (2025) |
|--------|-------------------|-------------------|
| **Nodes** | 556K total | 24.5M total |
| **WikidataPlace** | Merged into Place | Separate node type |
| **Processing** | Single batch | Country-by-country |
| **Runtime** | ~1 hour | ~4-8 hours |
| **Code** | `link_by_geography.py` | `link_wikidata_places_global.py` |

## Technical Details

**Memory Management:**
- 50,000 rows per transaction (Neo4j `IN TRANSACTIONS OF`)
- Country-by-country to avoid loading 11.5M nodes at once
- 64GB RAM allocation sufficient for per-country batches

**Spatial Queries:**
- Uses `point.distance()` with WGS84 coordinates
- 10km search radius (proven optimal from Canadian LOD)
- Filters by country when possible to reduce search space

**Confidence Thresholds:**
- Minimum: 0.5 (creates NEAR relationship)
- SAME_AS: 0.85 (prevents false positives)
- 50% name weight critical for precision

## Success Metrics

Phase 1 is successful if:
1. **Coverage**: >80% of WikidataPlace nodes have at least one link
2. **Precision**: >95% of sampled SAME_AS links are correct (manual validation)
3. **Performance**: Completes within 8 hours
4. **No crashes**: Processes all countries without memory errors

## Files Created

- `link_wikidata_places_global.py` - Main linking script (571 lines)
- `run_wikidata_linking.sh` - SLURM job script (92 lines)
- `ENTITY_LINKING_PLAN_UPDATED.md` - Complete 5-phase strategy
- `READY_TO_LINK.md` - This file

All committed to repository: commit `88377bb`
