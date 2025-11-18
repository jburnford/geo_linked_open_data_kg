# Additional Wikidata Entities to Extract

## Current Plan: P625 (Geographic Entities)
We're extracting ~5-10M entities with coordinates.

## Additional Valuable Categories

### 1. **Historical People** (CRITICAL for NER and research)

**Why extract:**
- Link people to places (birthplace, death place, residence)
- Track colonial administrators, explorers, founders
- Enable biographical research queries

**Filter criteria:**
- P31 (instance of) = Q5 (human)
- With at least one place connection:
  - P19 (place of birth)
  - P20 (place of death)
  - P551 (residence)
  - P937 (work location)
  - P27 (country of citizenship)

**Properties to capture:**
- P569: date of birth
- P570: date of death
- P19: place of birth (QID)
- P20: place of death (QID)
- P551: residence (QID)
- P106: occupation (important for colonial administrators, etc.)
- P39: position held (governor, etc.)
- P108: employer (Hudson's Bay Company, etc.)
- P27: country of citizenship
- Cross-database IDs: VIAF, GND, LOC (for linking to archives)

**Estimated count:** ~1-2M people with place connections

### 2. **Organizations & Companies**

**Why extract:**
- Colonial companies (Hudson's Bay, East India Company)
- Trading companies
- Government agencies
- Religious organizations

**Filter criteria:**
- P31 (instance of) = Q43229 (organization) or subclasses:
  - Q4830453 (business)
  - Q783794 (company)
  - Q7210356 (government agency)
  - Q16917 (religious organization)
- With place connections:
  - P740 (location of formation)
  - P159 (headquarters location)
  - P2541 (operating area)

**Properties to capture:**
- P571: inception
- P576: dissolved
- P740: location of formation (QID)
- P159: headquarters (QID)
- P112: founded by (person QID)
- P749: parent organization
- P2541: operating area (QID)
- P452: industry
- P1448: official name

**Estimated count:** ~200K-500K organizations

### 3. **Historical Events**

**Why extract:**
- Battles, treaties, conferences
- Colonial transitions
- Historical milestones tied to places

**Filter criteria:**
- P31 (instance of) = event types:
  - Q178561 (battle)
  - Q625298 (treaty)
  - Q1656682 (event)
  - Q8465 (civil war)
- With location: P276 (location)

**Properties to capture:**
- P585: point in time
- P580: start time
- P582: end time
- P276: location (QID)
- P710: participant (person/org QIDs)
- P793: significant event (for places)
- P17: country

**Estimated count:** ~100K-300K events

### 4. **Infrastructure & Buildings**

**Why extract:**
- Historical forts, trading posts
- Government buildings
- Religious buildings
- Railways, ports

**Filter criteria:**
- P31 (instance of) = infrastructure types:
  - Q57821 (fortification)
  - Q16560 (palace)
  - Q16970 (church building)
  - Q1006904 (railway station)
  - Q44782 (port)
  - Q41176 (building)
- Many will already have P625, but extract richer metadata

**Properties to capture:**
- P571: inception
- P576: dissolved/demolished
- P84: architect
- P149: architectural style
- P127: owned by (org QID)
- P466: occupant

**Estimated count:** Already in P625 set, just richer metadata

### 5. **Works & Documents**

**Why extract:**
- Historical maps
- Colonial reports
- Books about places
- Treaties

**Filter criteria:**
- P31 (instance of) = work types:
  - Q571 (book)
  - Q9372 (map)
  - Q49848 (document)
  - Q1172284 (report)
- With subject about places: P921 (main subject)

**Properties to capture:**
- P577: publication date
- P50: author (person QID)
- P921: main subject (place QID)
- P123: publisher
- P407: language
- P1476: title

**Estimated count:** ~500K-1M works

## Recommended Extraction Strategy

### Option A: Multi-Pass Filtering (RECOMMENDED)
Process the dump multiple times, extracting different entity types:

1. **Pass 1: Geographic entities** (P625) - What we're doing now
   - ~5-10M entities
   - ~5-15 GB output

2. **Pass 2: Historical people** (P31=Q5 + place connections)
   - ~1-2M entities
   - ~1-3 GB output

3. **Pass 3: Organizations** (P31=Q43229 + place connections)
   - ~200K-500K entities
   - ~200MB-500MB output

4. **Pass 4: Events** (P31=event types + P276)
   - ~100K-300K entities
   - ~100MB-300MB output

**Total additional data:** ~2-4 GB
**Total processing time:** ~6 hours per pass on Nibi

### Option B: Single-Pass Multi-Category (EFFICIENT)
Modify the filter script to extract ALL useful categories in one pass:

```python
def should_extract_entity(entity):
    """Determine if entity is useful for historical research."""

    qid = entity.get('id')
    claims = entity.get('claims', {})

    # Category 1: Has coordinates (geographic)
    if 'P625' in claims:
        return 'geographic'

    # Category 2: Human with place connections
    if is_human(claims):
        if has_place_connection(claims):
            return 'person'

    # Category 3: Organization with place connections
    if is_organization(claims):
        if has_place_connection(claims):
            return 'organization'

    # Category 4: Event with location
    if is_event(claims):
        if 'P276' in claims:  # has location
            return 'event'

    return None
```

**Advantages:**
- Only read the dump once (~6-10 hours)
- Extract everything in single pass
- Smaller combined output than separate passes

**Disadvantages:**
- More complex filtering logic
- Need to track multiple entity types

## Graph Schema Extensions

### Nodes
- **Place** (existing - ~10M)
- **Person** (new - ~1-2M)
- **Organization** (new - ~200K-500K)
- **Event** (new - ~100K-300K)
- **Work** (new - ~500K-1M)

### New Relationships
- `(Person)-[:BORN_IN]->(Place)`
- `(Person)-[:DIED_IN]->(Place)`
- `(Person)-[:RESIDED_IN]->(Place)`
- `(Person)-[:WORKED_FOR]->(Organization)`
- `(Organization)-[:FOUNDED_IN]->(Place)`
- `(Organization)-[:HEADQUARTERED_IN]->(Place)`
- `(Event)-[:OCCURRED_AT]->(Place)`
- `(Event)-[:PARTICIPANT]->(Person|Organization)`
- `(Work)-[:ABOUT]->(Place)`
- `(Work)-[:AUTHOR]->(Person)`

### Use Cases Enabled

**Historical Biography:**
```cypher
// Find all governors of British India
MATCH (p:Person)-[:POSITION_HELD]->(:Position {name: "Governor-General of India"})
MATCH (p)-[:BORN_IN]->(birthplace:Place)
RETURN p.name, birthplace.name, p.dateOfBirth
ORDER BY p.dateOfBirth
```

**Organizational History:**
```cypher
// Trading posts founded by Hudson's Bay Company
MATCH (hbc:Organization {name: "Hudson's Bay Company"})-[:FOUNDED]->(place:Place)
RETURN place.name, place.inceptionDate, place.latitude, place.longitude
ORDER BY place.inceptionDate
```

**Event Networks:**
```cypher
// Battles in a specific region
MATCH (event:Event)-[:OCCURRED_AT]->(place:Place)
WHERE place.countryCode = 'IN'
  AND event.instanceOfLabel CONTAINS 'battle'
RETURN event.name, place.name, event.date
ORDER BY event.date
```

## Recommendation

**START WITH:** Geographic entities (P625) - already planned

**THEN ADD** (in order of value):
1. **People** with place connections (huge value for NER and research)
2. **Organizations** (colonial companies, governments)
3. **Events** (battles, treaties, conferences)

**Implementation:**
- Use **single-pass multi-category** approach
- Modify `filter_wikidata_full_dump.py` to detect and extract all types
- Output to separate sections in same file OR separate files by type

**Estimated total:**
- Geographic: ~5-10M entities (~10-15 GB)
- People: ~1-2M entities (~2-3 GB)
- Organizations: ~300K entities (~500 MB)
- Events: ~200K entities (~300 MB)
- **Total: ~15-20 GB filtered output** from ~145 GB dump

This gives you a comprehensive historical knowledge graph covering places, people, organizations, and events!
