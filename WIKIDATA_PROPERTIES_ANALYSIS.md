# Critical Missing Wikidata Properties for Historical NER

## Currently Fetching ✅
- Basic: qid, name, description, coordinates, population, geonamesId
- Temporal: inceptionDate, dissolvedDate, abolishedDate
- Context: wikipediaUrl, instanceOf, country

## CRITICAL MISSING (Must Add) 🚨

### 1. **Alternate Names** - ESSENTIAL FOR NER MATCHING
**Problem:** Historical places have dozens of name variations. Without these, we'll miss most matches.

**Properties to add:**
- `skos:altLabel` - All alternate labels (all languages)
- `P1448` - Official name (with temporal qualifiers)
- `P1705` - Native label
- `P1449` - Nickname
- `rdfs:label` - Labels in ALL languages (not just English)

**Example:** "Bombay" vs "Mumbai", "Calcutta" vs "Kolkata", "Peking" vs "Beijing"

**SPARQL Addition:**
```sparql
OPTIONAL { ?place skos:altLabel ?altLabel . }
OPTIONAL { ?place wdt:P1448 ?officialName . }
OPTIONAL { ?place wdt:P1705 ?nativeLabel . }
OPTIONAL { ?place wdt:P1449 ?nickname . }
```

### 2. **Administrative Hierarchy (P131)** - ALREADY HAVE SEPARATE SCRIPT
We have `fetch_wikidata_p131_relationships.py` but should consider including in main fetch:
- `P131` - located in the administrative territorial entity
- Critical for understanding "Toronto, Ontario, Canada" hierarchy

### 3. **Historical Succession Relationships**
**Problem:** Need to understand what replaced what (colonial to independent states)

**Properties to add:**
- `P1365` - replaces (what came before)
- `P1366` - replaced by (what came after)
- `P155` - follows
- `P156` - followed by

**Example:** "British Raj (Q129286) replaced by India (Q668) + Pakistan (Q843)"

### 4. **Colonial/Founding Context**
**Properties to add:**
- `P112` - founded by (person or organization)
- `P127` - owned by (especially for trading posts, colonies)
- `P1376` - capital of (with temporal qualifiers)
- `P17` - country (with temporal qualifiers - e.g., "British Empire 1858-1947")

**Example:** "Fort Victoria founded by Hudson's Bay Company (Q1232355)"

### 5. **Additional External IDs for Cross-Linking**
**Properties to add:**
- `P227` - GND ID (German National Library)
- `P214` - VIAF ID (Virtual International Authority File)
- `P244` - Library of Congress ID
- `P1667` - Getty TGN ID (Thesaurus of Geographic Names)
- `P402` - OpenStreetMap relation ID
- `P6766` - Who's on First ID

**Why:** These help reconcile with other historical databases and archives

### 6. **Historic County/Traditional Region**
**Properties to add:**
- `P7959` - historic county
- `P1001` - applies to jurisdiction
- Important for pre-modern administrative divisions

### 7. **Temporal Qualifiers on Relationships**
**Currently:** We get single value for many properties
**Need:** Time-qualified values

**Example:**
```sparql
# Capital of British India (with dates)
?place p:P1376 ?capitalStatement .
?capitalStatement ps:P1376 ?capitalOf .
?capitalStatement pq:P580 ?startTime .
?capitalStatement pq:P582 ?endTime .
```

### 8. **Official Website (for modern places)**
**Properties to add:**
- `P856` - official website
- Useful for modern municipal entities

## LESS CRITICAL (Can Skip)

### Skip - Don't Need:
- `P18` - image (explicitly don't want)
- `P373` - Commons category (image-related)
- `P94` - coat of arms image (image)
- `P41` - flag image (image)
- `P242` - locator map image (image)
- `P158` - seal image (image)

### Skip - Too detailed for initial load:
- Detailed population time series (can query later if needed)
- Detailed geographic coordinate changes over time
- Minor identifiers (social media accounts, etc.)

## Recommended Enhanced Query Structure

```sparql
SELECT DISTINCT
  ?place ?placeLabel
  ?coords ?population ?geonamesId
  ?inception ?dissolved ?abolished
  ?wikipedia ?description
  ?instanceOf ?instanceOfLabel
  ?country

  # NEW: All alternate names
  (GROUP_CONCAT(DISTINCT ?altLabel; separator="|") AS ?altNames)
  (GROUP_CONCAT(DISTINCT ?officialName; separator="|") AS ?officialNames)
  ?nativeLabel ?nickname

  # NEW: Historical succession
  ?replaces ?replacedBy ?follows ?followedBy

  # NEW: Colonial context
  ?foundedBy ?ownedBy ?capitalOf

  # NEW: Additional identifiers
  ?gndId ?viafId ?locId ?tgnId ?osmId ?wofId

  # NEW: Historic county
  ?historicCounty

WHERE {
  # [Country filter and instance types as before]

  # Basic data (existing)
  OPTIONAL { ?place wdt:P625 ?coords . }
  OPTIONAL { ?place wdt:P1082 ?population . }
  OPTIONAL { ?place wdt:P1566 ?geonamesId . }
  OPTIONAL { ?place wdt:P571 ?inception . }
  OPTIONAL { ?place wdt:P576 ?dissolved . }
  OPTIONAL { ?place wdt:P576 ?abolished . }

  # NEW: Alternate names
  OPTIONAL { ?place skos:altLabel ?altLabel . }
  OPTIONAL { ?place wdt:P1448 ?officialName . }
  OPTIONAL { ?place wdt:P1705 ?nativeLabel . }
  OPTIONAL { ?place wdt:P1449 ?nickname . }

  # NEW: Historical succession
  OPTIONAL { ?place wdt:P1365 ?replaces . }
  OPTIONAL { ?place wdt:P1366 ?replacedBy . }
  OPTIONAL { ?place wdt:P155 ?follows . }
  OPTIONAL { ?place wdt:P156 ?followedBy . }

  # NEW: Colonial context
  OPTIONAL { ?place wdt:P112 ?foundedBy . }
  OPTIONAL { ?place wdt:P127 ?ownedBy . }
  OPTIONAL { ?place wdt:P1376 ?capitalOf . }

  # NEW: Additional identifiers
  OPTIONAL { ?place wdt:P227 ?gndId . }
  OPTIONAL { ?place wdt:P214 ?viafId . }
  OPTIONAL { ?place wdt:P244 ?locId . }
  OPTIONAL { ?place wdt:P1667 ?tgnId . }
  OPTIONAL { ?place wdt:P402 ?osmId . }
  OPTIONAL { ?place wdt:P6766 ?wofId . }

  # NEW: Historic county
  OPTIONAL { ?place wdt:P7959 ?historicCounty . }

  # [Wikipedia, description, labels as before]
}
GROUP BY ?place ?placeLabel ?coords ... # [all non-aggregated variables]
```

## Priority Order for Implementation

1. **CRITICAL (Do First):**
   - Alternate names (altLabel, officialName, nativeLabel, nickname)
   - Historical succession (replaces, replacedBy)
   - Colonial context (foundedBy, ownedBy, capitalOf)

2. **HIGH PRIORITY:**
   - Additional identifiers (GND, VIAF, LOC, Getty TGN)
   - Historic county

3. **MEDIUM PRIORITY:**
   - Temporal qualifiers on relationships (more complex SPARQL)
   - Official website

## Query Size Considerations

**Problem:** Adding all these properties might make queries timeout

**Solutions:**
1. **Fetch in two passes:**
   - Pass 1: Basic data + alternate names
   - Pass 2: Relationships + identifiers (for places found in Pass 1)

2. **Keep country-by-country approach** (already doing this)

3. **Use GROUP_CONCAT** for multi-valued properties (alternate names)

4. **Keep 10,000 LIMIT** per country query
