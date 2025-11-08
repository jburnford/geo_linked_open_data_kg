# Wikidata Multi-Pass Extraction Plan

## Strategy: Extract All, Delete Dump Last

**Goal**: Get maximum value from the 145GB Wikidata dump before deleting it.

**Approach**: Multiple filtering passes, each extracting different entity types.

## Timeline

### **Pass 1: Geographic Entities (P625)** - FIRST PRIORITY
**When**: As soon as download completes (~5-6 hours from now)
**Filter**: All entities with coordinate location property (P625)
**Output**: `wikidata_geographic.json.gz` (~5-15 GB)
**Processing time**: ~6-10 hours on Nibi
**Load locally**: ~1-3 hours
**Purpose**: Immediate need for place enrichment and NER

### **Pass 2: Historical People** - SECOND PRIORITY
**When**: After Pass 1 completes (~12 hours from now)
**Filter**: P31=Q5 (human) + has place connections (P19, P20, P551, P937)
**Output**: `wikidata_people.json.gz` (~1-3 GB)
**Processing time**: ~6-10 hours on Nibi
**Load locally**: ~30-60 minutes
**Purpose**: Biographical research, colonial administrators, founders

### **Pass 3: Organizations** - THIRD PRIORITY
**When**: After Pass 2 completes (~24 hours from now)
**Filter**: P31=Q43229 (organization) + has place connections (P740, P159, P2541)
**Output**: `wikidata_organizations.json.gz` (~300-600 MB)
**Processing time**: ~6-10 hours on Nibi
**Purpose**: Colonial companies, trading posts, government agencies

### **Pass 4: Historical Events** - FOURTH PRIORITY
**When**: After Pass 3 completes (~36 hours from now)
**Filter**: P31=event types (Q178561, Q625298, etc.) + has location (P276)
**Output**: `wikidata_events.json.gz` (~100-300 MB)
**Processing time**: ~6-10 hours on Nibi
**Purpose**: Battles, treaties, conferences tied to places

### **Pass 5: Works & Documents** - OPTIONAL
**When**: After Pass 4 completes (~48 hours from now)
**Filter**: P31=work types (Q571, Q9372, etc.) + about places (P921)
**Output**: `wikidata_works.json.gz` (~500MB-1GB)
**Processing time**: ~6-10 hours on Nibi
**Purpose**: Historical maps, colonial reports, books about places

## Total Timeline

- **Start**: Download completes (ETA: 5:30 AM Nov 8)
- **Pass 1 done**: ~4:00 PM Nov 8 (geographic entities loaded)
- **Pass 2 done**: ~2:00 AM Nov 9 (people loaded)
- **Pass 3 done**: ~12:00 PM Nov 9 (organizations loaded)
- **Pass 4 done**: ~10:00 PM Nov 9 (events loaded)
- **Pass 5 done**: ~8:00 AM Nov 10 (works loaded - optional)

**Total elapsed**: ~3 days to extract everything

## Disk Space Requirements

### On Nibi (while processing):
- Raw dump: 145 GB (keep until all passes done)
- Pass 1 output: 5-15 GB
- Pass 2 output: 1-3 GB
- Pass 3 output: 300-600 MB
- Pass 4 output: 100-300 MB
- Pass 5 output: 500MB-1GB
- **Total outputs**: ~8-20 GB
- **Peak usage**: 145 GB + 20 GB = **165 GB** (have 251 GB available ✓)

### On Local (after downloads):
- All outputs: ~8-20 GB compressed
- Loaded into Neo4j: ~50-80 GB database
- **Total local**: ~60-100 GB (have 739 GB available ✓)

## Processing Scripts

### Pass 1: Geographic Entities (Already Created)
**Script**: `filter_wikidata_full_dump.py`
**Command**:
```bash
ssh nibi
cd ~/projects/def-jic823/CanadaNeo4j
sbatch nibi_filter_wikidata.sh
```

### Pass 2-5: Need New Scripts
Create filtered versions for each entity type:
- `filter_wikidata_people.py`
- `filter_wikidata_organizations.py`
- `filter_wikidata_events.py`
- `filter_wikidata_works.py`

OR: **Single enhanced script** that does all in one pass (saves time!)

## Alternative: Single-Pass Multi-Category Extraction

**Pros**:
- Only read the 145GB dump **once** (~6-10 hours)
- Save 20-30 hours of processing time
- Get all entity types in one go

**Cons**:
- More complex filtering logic
- Larger output file (~20-25 GB vs separate smaller files)
- Need to separate entity types after

**Recommendation**:
- If time is critical: **Single-pass multi-category**
- If disk space is critical: **Multiple passes** (can delete outputs after loading)

## Automation Strategy

### Option A: Sequential (Safe, Slower)
Submit each pass manually after previous completes:
1. Monitor Pass 1 completion
2. Start Pass 2
3. Monitor Pass 2 completion
4. Start Pass 3
... etc

**Advantage**: Can check results after each pass
**Disadvantage**: Requires manual intervention

### Option B: Chained Jobs (Automated, Faster)
Submit all passes with dependencies:
```bash
# Submit Pass 1
JOB1=$(sbatch nibi_filter_geographic.sh | awk '{print $4}')

# Submit Pass 2 (depends on Pass 1)
JOB2=$(sbatch --dependency=afterok:$JOB1 nibi_filter_people.sh | awk '{print $4}')

# Submit Pass 3 (depends on Pass 2)
JOB3=$(sbatch --dependency=afterok:$JOB2 nibi_filter_orgs.sh | awk '{print $4}')

# ... etc
```

**Advantage**: Fully automated, runs overnight
**Disadvantage**: If one fails, rest don't run

### Option C: Hybrid (Recommended)
- Do Pass 1 (geographic) manually - verify it works
- Chain Passes 2-5 together after Pass 1 succeeds
- Balance of safety and automation

## Cleanup Schedule

**DO NOT DELETE until all passes complete!**

### After Pass 1:
- ✗ Don't delete raw dump (need for other passes)
- ✓ Can download `wikidata_geographic.json.gz` locally
- ✓ Can load geographic entities into Neo4j

### After Pass 5 (or last pass you want):
- ✓ Download all output files to local
- ✓ Verify all files downloaded correctly
- ✓ Delete raw dump: `rm wikidata-latest-all.json.gz` (saves 145 GB on Nibi)
- ✓ Keep output files for potential re-loading

## Loading Order into Neo4j

### 1. Geographic Entities (Priority 1)
**Load first** - foundation for everything else
```bash
python3 load_wikidata_from_cache.py --cache wikidata_geographic.json.gz
```

### 2. People (Priority 2)
**Load second** - can link to places loaded in step 1
```bash
python3 load_wikidata_people.py --cache wikidata_people.json.gz
```
Creates:
- Person nodes
- BORN_IN, DIED_IN, RESIDED_IN relationships to Place nodes

### 3. Organizations (Priority 3)
**Load third** - can link to places and people
```bash
python3 load_wikidata_organizations.py --cache wikidata_organizations.json.gz
```
Creates:
- Organization nodes
- FOUNDED_IN, HEADQUARTERED_IN relationships to Place nodes
- WORKED_FOR relationships to Person nodes

### 4. Events (Priority 4)
**Load fourth** - can link to places, people, organizations
```bash
python3 load_wikidata_events.py --cache wikidata_events.json.gz
```
Creates:
- Event nodes
- OCCURRED_AT relationships to Place nodes
- PARTICIPANT relationships to Person/Organization nodes

### 5. Works (Optional)
**Load last** - references everything else
```bash
python3 load_wikidata_works.py --cache wikidata_works.json.gz
```
Creates:
- Work nodes
- ABOUT relationships to Place/Person/Organization nodes
- AUTHOR relationships to Person nodes

## Current Status

- ✓ Download started (Job 4063323, 41% complete)
- ✓ Pass 1 script ready (`filter_wikidata_full_dump.py`)
- ⏳ Pass 2-5 scripts: Need to create
- ⏳ Loader scripts: Need to create for people/orgs/events/works

## Next Steps

1. **Wait for download** (~5 hours remaining)
2. **Submit Pass 1** (geographic entities)
3. **While Pass 1 runs**: Create Pass 2-5 scripts
4. **After Pass 1 completes**: Download and load geographic entities
5. **Chain Passes 2-5** for overnight processing
6. **Load remaining entity types** over next few days
7. **Delete raw dump** only after all passes complete and verified

## Recommendation

**For your use case:**
- **Do Pass 1 immediately** (geographic - your priority)
- **Do Pass 2 next day** (people - high value)
- **Do Passes 3-4 when convenient** (orgs, events - nice to have)
- **Skip Pass 5** (works - can always re-download dump if needed later)

This gives you 80% of the value (places + people + orgs + events) while managing time and complexity.
