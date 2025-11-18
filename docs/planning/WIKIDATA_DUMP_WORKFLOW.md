# Wikidata Dump Processing Workflow

## Overview

Instead of querying Wikidata's SPARQL endpoint (which times out on complex queries), we use **Wikidata Dumps** (wdumps.toolforge.org) to download a complete dataset of all geographic entities.

## Advantages Over SPARQL Queries

| Aspect | SPARQL Endpoint | Dump Approach |
|--------|-----------------|---------------|
| Timeouts | ✗ Frequent 504 errors | ✓ No timeouts |
| Completeness | ✗ Must limit results | ✓ Complete dataset |
| Speed | ✗ Slow, many queries | ✓ Download once, process locally |
| Flexibility | ✗ Fixed when fetched | ✓ Can re-parse anytime |
| Languages | ✗ Must specify in query | ✓ All languages included |

## Workflow

### Step 1: Create Custom Dump

**Done**: Created dump 5175 at https://wdumps.toolforge.org/dump/5175

**Configuration:**
- **Filter**: All items with P625 (coordinate location)
- **Scope**: Global (all countries)
- **Data**: Full statements, qualifiers, references, labels, descriptions, aliases
- **Languages**: All languages
- **Ranks**: All ranks (including non-deprecated)

**What this gets us:**
- All geographic entities with coordinates (~5-10M entities)
- All historical colonies, trading posts, forts, settlements
- Complete alternate names in all languages
- All historical succession relationships
- All colonial context (founded by, owned by, capital of)
- All cross-database identifiers (GND, VIAF, LOC, Getty TGN, OSM, WOF)

### Step 2: Monitor Dump Generation

**Check status:**
```bash
python3 check_wikidata_dump.py --dump-id 5175
```

**Status indicators:**
- `pending` - In queue, not started
- `processing` - Currently generating
- `completed` - Ready to download
- `failed` - Generation failed (rare)

**Typical generation time:**
- Small dumps (100K entities): Minutes
- Medium dumps (1M entities): Hours
- Large dumps (5-10M entities): Hours to days

### Step 3: Download Dump

**When ready (status = completed):**
```bash
python3 check_wikidata_dump.py --dump-id 5175 --download --output wikidata_p625_dump.json.gz
```

**Expected file size:**
- Compressed: 2-5 GB (estimated)
- Uncompressed: 20-50 GB (estimated)

**Download time:**
- ~10-30 minutes (depends on network speed)

### Step 4: Parse Dump Locally

**Process the dump:**
```bash
python3 parse_wikidata_dump.py wikidata_p625_dump.json.gz wikidata_global_complete.json.gz
```

**What the parser does:**
1. Reads newline-delimited JSON format
2. Extracts all geographic entities with coordinates
3. Parses all properties we identified in `WIKIDATA_PROPERTIES_ANALYSIS.md`:
   - Alternate names (all languages, all aliases)
   - Official names (P1448)
   - Native labels (P1705)
   - Nicknames (P1449)
   - Historical succession (P1365, P1366, P155, P156)
   - Colonial context (P112, P127, P1376)
   - Temporal data (P571, P576)
   - Cross-database IDs (P227, P214, P244, P1667, P402, P6766)
   - Historic counties (P7959)
   - Instance of (P31) - to identify historical entity types
   - Country (P17)
   - GeoNames ID (P1566)
   - Population (P1082)
   - Wikipedia links (from sitelinks)
4. Outputs to compressed JSON in our cache format
5. Prints statistics

**Expected output:**
- ~5-10M entities with coordinates
- ~50-80% with alternate names
- ~20-30% with GeoNames IDs (can match to our existing data)
- ~5-10% colonial/historical entities
- ~40-60% with cross-database IDs

**Processing time:**
- ~30-60 minutes (depends on file size and system)

### Step 5: Load into Neo4j

**Use existing loader:**
```bash
python3 load_wikidata_from_cache.py --cache wikidata_global_complete.json.gz
```

**What happens:**
1. Loads cache file
2. Matches to existing GeoNames places by `geonamesId`
3. Enriches matched places with Wikidata properties
4. Creates new `Place` nodes for Wikidata-only entities (no GeoNames match)
5. Creates `Country` relationships
6. Prints statistics

**Expected results:**
- 500K-2M places matched to GeoNames (enriched)
- 3-8M new Wikidata-only places created
- Total database: 10-15M Place nodes

## Properties Captured

### Essential for NER (Named Entity Recognition)

```json
{
  "qid": "Q1156",
  "name": "Mumbai",
  "alternateNames": ["Bombay", "Mumbai Presidency", "Bombai", "मुंबई", "ムンバイ"],
  "officialNames": ["Brihanmumbai"],
  "nativeLabel": "मुंबई",
  "nickname": "City of Dreams"
}
```

### Historical Succession

```json
{
  "replacesQid": "Q129286",      // British Raj
  "replacedByQid": "Q668",       // India
  "followsQid": "Q1396",         // Bengal Presidency
  "followedByQid": "Q1499"       // West Bengal
}
```

### Colonial Context

```json
{
  "foundedByQid": "Q1232355",    // Hudson's Bay Company
  "ownedByQid": "Q1151405",      // British East India Company
  "capitalOfQid": "Q129286",     // British Raj
  "instanceOfQid": "Q1750636"    // colonial trading post
}
```

### Cross-Database Linking

```json
{
  "gndId": "4026722-4",          // German National Library
  "viafId": "134114058",         // Virtual International Authority File
  "locId": "n79081752",          // Library of Congress
  "tgnId": "7001535",            // Getty TGN
  "osmId": "16173",              // OpenStreetMap
  "wofId": "85632469"            // Who's on First
}
```

### Temporal Context

```json
{
  "inceptionDate": "1858-11-01",
  "dissolvedDate": "1947-08-15",
  "abolishedDate": "1947-08-15"
}
```

## Historical Entity Types Captured

The parser identifies these historical entity types (via P31 - instance of):

- **Q133156** - colony
- **Q1750636** - colonial trading post
- **Q57821** - fortification
- **Q16748868** - historical country
- **Q3024240** - historical country
- **Q28171280** - ancient city
- **Q839954** - archaeological site
- **Q1266818** - historical region
- **Q1620908** - historical geographic location
- **Q15632617** - former administrative territorial entity
- **Q19953632** - former municipality
- **Q19730508** - historical administrative division

## Statistics Tracked

During parsing, the script tracks:

- Total entities processed
- Entities with coordinates (should be 100% since that's our filter)
- Entities with GeoNames IDs (can match to our database)
- Entities with alternate names (critical for NER)
- Historical entities (by instance type)
- Colonial entities (with foundedBy/ownedBy)
- Entities with cross-database IDs

## Post-Load Queries

### Create Historical Succession Relationships

```cypher
// Connect places via REPLACES/REPLACED_BY relationships
MATCH (old:Place), (new:Place)
WHERE old.replacedByQid = new.wikidataId
MERGE (old)-[:REPLACED_BY]->(new)
MERGE (new)-[:REPLACES]->(old)

// Connect via FOLLOWS relationships
MATCH (earlier:Place), (later:Place)
WHERE earlier.followedByQid = later.wikidataId
MERGE (earlier)-[:FOLLOWED_BY]->(later)
MERGE (later)-[:FOLLOWS]->(earlier)
```

### Create Founding/Ownership Relationships

```cypher
// Create Organization nodes for colonial companies
MATCH (place:Place)
WHERE place.foundedByQid IS NOT NULL
MERGE (org:Organization {wikidataId: place.foundedByQid})
MERGE (org)-[:FOUNDED]->(place)

// Create ownership relationships
MATCH (place:Place)
WHERE place.ownedByQid IS NOT NULL
MERGE (owner:Organization {wikidataId: place.ownedByQid})
MERGE (owner)-[:OWNED]->(place)
```

### Create Indexes for Fast NER Lookup

```cypher
// Index on alternate names for fast lookup
CREATE INDEX alternate_names_idx IF NOT EXISTS
FOR (p:Place) ON (p.alternateNames)

// Full-text index for NER matching
CREATE FULLTEXT INDEX ner_search_idx IF NOT EXISTS
FOR (p:Place) ON EACH [p.name, p.alternateNames, p.officialNames, p.nickname, p.nativeLabel]

// Index on Wikidata ID for relationship creation
CREATE INDEX wikidata_id_idx IF NOT EXISTS
FOR (p:Place) ON (p.wikidataId)
```

## Troubleshooting

### Dump Generation Takes Too Long
- Normal for large dumps (5-10M entities)
- Check status every few hours
- If >48 hours, may need to contact Wikidata Dumps support

### Dump Download Fails
- Resume download with `wget -c <download_link>`
- Or use browser download manager with resume capability

### Parser Runs Out of Memory
- Increase system swap space
- Process in chunks (modify script to skip already-processed entities)
- Use a machine with more RAM

### Missing Properties in Output
- Check that dump includes "full statements" (not just "truthy statements")
- Verify dump includes qualifiers and references
- Some entities may genuinely not have those properties

## Next Steps After Loading

1. **Verify statistics** - Check how many places were matched vs created
2. **Create relationships** - Run the Cypher queries above
3. **Test NER queries** - Search for historical names
4. **Export sample data** - Verify data quality
5. **Integrate with RAG** - Connect to GPT-OSS-120B for historical research

## Comparison to Previous Approach

### Old: SPARQL Endpoint
- ✗ Timed out on complex queries
- ✗ Had to limit to 1000 results per query
- ✗ Would need ~5000 queries for complete coverage
- ✗ Risk of rate limiting
- ✗ Incomplete data due to limits

### New: Dump Approach
- ✓ No timeouts
- ✓ Complete dataset (all entities)
- ✓ Download once, process locally
- ✓ Can re-parse with different filters
- ✓ All languages included automatically
- ✓ Future-proof (can update by downloading new dump)

## File Locations

- **Dump ID**: 5175
- **Dump URL**: https://wdumps.toolforge.org/dump/5175
- **Raw dump**: `wikidata_p625_dump.json.gz` (2-5 GB)
- **Parsed cache**: `wikidata_global_complete.json.gz` (~500MB-2GB)
- **Cache directory**: `wikidata_global_cache/` (if using multiple dumps)

## Estimated Timeline

1. **Dump generation**: 6-48 hours (variable)
2. **Dump download**: 10-30 minutes
3. **Dump parsing**: 30-60 minutes
4. **Neo4j loading**: 1-3 hours (for 5-10M entities)

**Total**: ~1-2 days from dump creation to fully loaded database
