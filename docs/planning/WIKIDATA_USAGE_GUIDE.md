# Enhanced Wikidata Fetcher - Usage Guide

## What's Been Added

Your Wikidata fetcher now captures **comprehensive historical and colonial context** in addition to basic place data.

## New Properties Captured

### 1. Alternate Names (Critical for NER!)
```json
{
  "alternateNames": ["Bombay", "Mumbai Presidency", "Bombai"],
  "officialNames": ["Mumbai", "Brihanmumbai"],
  "nativeLabel": "मुंबई",
  "nickname": "City of Dreams"
}
```

**Use case:** Match historical documents that use "Bombay" to modern "Mumbai"

### 2. Historical Succession
```json
{
  "replacesQid": "Q129286",     // British Raj
  "replacedByQid": "Q668",      // Republic of India
  "followsQid": "Q1396",        // Bengal Presidency
  "followedByQid": "Q1499"      // West Bengal
}
```

**Use case:** Understand colonial → independent state transitions

### 3. Colonial/Founding Context
```json
{
  "foundedByQid": "Q1232355",      // Hudson's Bay Company
  "foundedByLabel": "Hudson's Bay Company",
  "ownedByQid": "Q1151405",        // British East India Company
  "ownedByLabel": "British East India Company",
  "capitalOfQid": "Q129286",       // British Raj
  "capitalOfLabel": "British Raj (1858-1947)"
}
```

**Use case:** Track trading posts, forts, colonial capitals

### 4. Cross-Database Identifiers
```json
{
  "gndId": "4026722-4",           // German National Library
  "viafId": "134114058",          // Virtual International Authority File
  "locId": "n79081752",           // Library of Congress
  "tgnId": "7001535",             // Getty Thesaurus of Geographic Names
  "osmId": "16173",               // OpenStreetMap
  "wofId": "85632469"             // Who's on First
}
```

**Use case:** Link to archives, historical databases, other LOD sources

### 5. Historic Administrative Context
```json
{
  "historicCountyQid": "Q23169",
  "historicCountyLabel": "Lancashire",
  "instanceOfQid": "Q1750636",
  "instanceOfLabel": "colonial trading post"
}
```

**Use case:** Pre-modern administrative divisions, entity classification

### 6. Temporal Data (Enhanced)
```json
{
  "inceptionDate": "1858-11-01",
  "dissolvedDate": "1947-08-15",
  "abolishedDate": "1947-08-15"
}
```

**Use case:** Track when entities existed, colonial periods

## How to Use

### Step 1: Fetch Global Historical Data

```bash
cd /home/jic823/CanadaNeo4j

# Fetch all 50 colonial priority countries (~3-4 hours)
python3 fetch_wikidata_global_historical.py

# This creates:
# - wikidata_global_cache/wikidata_US.json
# - wikidata_global_cache/wikidata_IN.json
# - ... (one per country)
# - wikidata_global_historical.json (consolidated)
```

### Step 2: Load into Neo4j

```bash
# Load from consolidated file
python3 load_wikidata_from_cache.py

# Or specify specific cache file
python3 load_wikidata_from_cache.py --cache wikidata_global_historical.json
```

### Step 3: Query Historical Context

#### Find places by historical names:
```cypher
// Find "Bombay" (historical name for Mumbai)
MATCH (p:Place)
WHERE "Bombay" IN p.alternateNames
   OR p.nickname = "Bombay"
   OR "Bombay" IN p.officialNames
RETURN p.name, p.alternateNames, p.wikidataId
```

#### Track colonial succession:
```cypher
// What replaced the British Raj?
MATCH (old:Place {wikidataId: "Q129286"})  // British Raj
MATCH (new:Place {wikidataId: old.replacedByQid})
RETURN old.name AS colonial, new.name AS independent,
       old.dissolvedDate, new.inceptionDate
```

#### Find places founded by colonial companies:
```cypher
// Hudson's Bay Company trading posts
MATCH (p:Place)
WHERE p.foundedByLabel CONTAINS "Hudson's Bay"
RETURN p.name, p.inceptionDate, p.foundedByLabel,
       p.latitude, p.longitude
ORDER BY p.inceptionDate
```

#### Link to external archives:
```cypher
// Places with Library of Congress IDs
MATCH (p:Place)
WHERE p.locId IS NOT NULL
RETURN p.name, p.locId, p.viafId, p.gndId
```

## Example Historical Entities Captured

### British Colonial Entities
- British Raj (Q129286)
- Bengal Presidency (Q1396)
- Madras Presidency (Q1048380)
- East India Company territories
- Fort Victoria, Fort William, etc.

### French Colonial Entities
- French India (Q403174)
- Pondicherry (historical)
- French West Africa entities

### Trading Posts
- Hudson's Bay Company posts
- Dutch East India Company settlements
- Portuguese trading posts

### Indigenous Territories
- Indian reserves
- Historical Indigenous territories
- Traditional regions

## What This Enables

### For NER (Named Entity Recognition):
1. **Match historical names** to modern entities
2. **Resolve ambiguities** using temporal context
3. **Link mentions** across different naming conventions

### For Historical Research:
1. **Track colonial transitions** (who owned what when)
2. **Map trading networks** (company → posts)
3. **Understand administrative hierarchies** (historical counties)

### For LOD Integration:
1. **Link to archives** (via LOC, VIAF, GND IDs)
2. **Connect to other knowledge graphs** (via OSM, WOF)
3. **Cross-reference databases** (Getty TGN, etc.)

## Performance Notes

- **Country-by-country caching** prevents timeouts
- **Resume-friendly** - skip already-cached countries
- **10,000 record limit** per country query
- **3 second delay** between queries (Wikidata politeness)

## Estimated Results

For 50 colonial priority countries:
- **~200K-500K historical entities** (depends on Wikidata completeness)
- **~50-80% with alternate names** (critical for NER)
- **~30-40% with succession data** (colonial transitions)
- **~20-30% with founding context** (companies, owners)
- **~40-60% with cross-database IDs** (LOD linking)

## Next Steps After Loading

1. **Create succession relationships** in Neo4j:
```cypher
MATCH (old:Place), (new:Place)
WHERE old.replacedByQid = new.wikidataId
MERGE (old)-[:REPLACED_BY]->(new)
MERGE (new)-[:REPLACES]->(old)
```

2. **Create founding relationships**:
```cypher
MATCH (place:Place)
WHERE place.foundedByQid IS NOT NULL
MERGE (org:Organization {wikidataId: place.foundedByQid})
SET org.name = place.foundedByLabel
MERGE (org)-[:FOUNDED]->(place)
```

3. **Index alternate names** for fast NER lookup:
```cypher
CREATE INDEX alternate_names_idx FOR (p:Place) ON (p.alternateNames)
CREATE FULLTEXT INDEX alternate_names_fulltext
  FOR (p:Place) ON EACH [p.alternateNames, p.officialNames, p.nickname]
```

## Troubleshooting

**Query timeouts?**
- Already limited to 10K per country
- Countries are cached individually - resume will skip completed ones

**Missing data for some countries?**
- Wikidata completeness varies
- British colonies tend to have better coverage
- Can re-run specific countries later

**Large cache files?**
- Compressed files are ~10% of original size
- Use `.json.gz` files for long-term storage
- Consolidate into single file for loading

## Future Enhancements

Consider adding later (would require separate queries):
- **Temporal qualifiers** on relationships (when was X capital of Y?)
- **Multiple languages** for alternate names (currently English only)
- **Detailed population time series** (historical populations)
