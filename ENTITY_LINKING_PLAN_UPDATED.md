# Entity Linking Plan - Global Scale (Updated)

## Current Database State

**Total Nodes**: 24,568,022
- **WikidataPlace**: 11,555,027 (geographic entities from Wikidata)
- **Place**: 6,233,958 (GeoNames places)
- **Person**: 6,033,891 (Wikidata people)
- **AdminDivision**: 509,913 (GeoNames admin divisions)
- **Organization**: 234,979 (Wikidata organizations)
- **Country**: 254 (GeoNames countries)

**Existing Relationships**: ~11.5M (Admin hierarchies from previous work)

## Leveraging Existing Spatial Linking Code

We already have sophisticated geographic linking code from the Canadian LOD project:
- `link_by_geography.py`: NEAR/LOCATED_IN/SAME_AS with confidence scoring
- `add_spatial_indexes.py`: Optimized spatial queries
- `add_admin3_links.py`: Administrative hierarchies

**Key insight**: These scripts need adaptation for:
1. WikidataPlace as separate node type (not merged into Place)
2. Global scale (24.5M nodes vs 556K)
3. Person/Organization geographic connections

## Phase 1: WikidataPlace ↔ Place Spatial Linking (PRIORITY)

### 1.1 Direct geonamesId Links (Fast)
**Expected**: 2-3M matches

```cypher
CALL {
    MATCH (wp:WikidataPlace)
    WHERE wp.geonamesId IS NOT NULL
      AND NOT EXISTS((wp)-[:SAME_AS]->())
    WITH wp LIMIT 50000
    MATCH (p:Place {geonameId: wp.geonamesId})
    MERGE (wp)-[:SAME_AS]->(p)
    SET r.evidence = 'geonames_id_match'
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
RETURN sum(batch_count) as total_count
```

### 1.2 Geographic Proximity Linking (Adapt from link_by_geography.py)

**Adaptation needed**: Modify `link_by_geography.py` to:
1. Change source query from `Place WHERE wikidataId IS NOT NULL AND geonameId IS NULL`
   to `WikidataPlace WHERE NOT EXISTS((wp)-[:SAME_AS]->())`
2. Change target query from `Place WHERE geonameId IS NOT NULL`
   to `Place` (all GeoNames places)
3. Keep confidence scoring formula (already excellent)
4. Keep relationship types (NEAR, LOCATED_IN, SAME_AS)

**Expected**:
- SAME_AS (high confidence): ~2-3M
- NEAR (medium confidence): ~3-4M
- LOCATED_IN (POI containment): ~2-3M

**Key parameters** (from existing code):
- Distance threshold: 10km
- SAME_AS: confidence ≥0.85, distance <1km
- NEAR: confidence ≥0.5
- Name similarity weight: 50% (critical for precision)

### 1.3 Batch Processing for Scale

**Modification**: Process by country to avoid memory issues

```python
# Pseudocode adaptation
def link_wikidata_places_to_geonames_by_country():
    """Process one country at a time for memory efficiency"""
    countries = get_all_country_codes()

    for country_code in countries:
        print(f"Linking {country_code}...")

        # Get WikidataPlace nodes for this country
        wikidata_places = get_wikidata_places(country_code, unlinked_only=True)

        # Find nearby GeoNames places
        for wp in wikidata_places:
            nearby = find_nearby_places_within_country(
                lat=wp.latitude,
                lon=wp.longitude,
                country=country_code,
                max_distance_km=10.0
            )

            # Use existing confidence scoring
            create_links_with_confidence(wp, nearby)
```

**Estimated time**: 4-6 hours for 11.5M WikidataPlace nodes

## Phase 2: Person Geographic Links (HIGH PRIORITY)

### 2.1 Birth Place Links
**Property**: `Person.birthPlaceQid` → `WikidataPlace.qid`
**Relationship**: `(Person)-[:BORN_IN]->(WikidataPlace)`
**Expected**: ~4-5M

```python
def link_person_birth_places(batch_size=50000):
    """Link Person to WikidataPlace via birthPlaceQid"""
    with driver.session() as session:
        result = session.run("""
            CALL {
                MATCH (p:Person)
                WHERE p.birthPlaceQid IS NOT NULL
                  AND NOT EXISTS((p)-[:BORN_IN]->())
                WITH p LIMIT $batch_size
                MATCH (wp:WikidataPlace {qid: p.birthPlaceQid})
                CREATE (p)-[:BORN_IN]->(wp)
                RETURN count(*) as batch_count
            } IN TRANSACTIONS OF $batch_size ROWS
            RETURN sum(batch_count) as total_count
        """, batch_size=batch_size)
```

**Estimated time**: 1-2 hours

### 2.2 Death Place Links
**Property**: `Person.deathPlaceQid` → `WikidataPlace.qid`
**Relationship**: `(Person)-[:DIED_IN]->(WikidataPlace)`
**Expected**: ~3-4M
**Estimated time**: 1-2 hours

### 2.3 Residence Links (Array Property)
**Property**: `Person.residenceQids[]` → `WikidataPlace.qid`
**Relationship**: `(Person)-[:RESIDED_IN]->(WikidataPlace)`
**Expected**: ~2-3M

```cypher
CALL {
    MATCH (person:Person)
    WHERE size(person.residenceQids) > 0
      AND NOT EXISTS((person)-[:RESIDED_IN]->())
    WITH person LIMIT 50000
    UNWIND person.residenceQids AS residenceQid
    MATCH (place:WikidataPlace {qid: residenceQid})
    CREATE (person)-[:RESIDED_IN]->(place)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
RETURN sum(batch_count) as total_count
```

**Estimated time**: 1 hour

### 2.4 Citizenship Links
**Property**: `Person.citizenshipQid` → `WikidataPlace.qid` (typically country)
**Relationship**: `(Person)-[:CITIZEN_OF]->(WikidataPlace)`
**Expected**: ~5M
**Estimated time**: 1-2 hours

## Phase 3: Organization Geographic Links (MEDIUM PRIORITY)

### 3.1 Headquarters
```cypher
CALL {
    MATCH (org:Organization)
    WHERE org.headquartersQid IS NOT NULL
      AND NOT EXISTS((org)-[:HEADQUARTERED_IN]->())
    WITH org LIMIT 50000
    MATCH (place:WikidataPlace {qid: org.headquartersQid})
    CREATE (org)-[:HEADQUARTERED_IN]->(place)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
```

**Expected**: ~150-200K
**Estimated time**: 30 minutes

### 3.2 Founded In
**Property**: `Organization.foundedInQid` → `WikidataPlace.qid`
**Expected**: ~100-150K
**Estimated time**: 30 minutes

## Phase 4: Organization-Person Links (MEDIUM PRIORITY)

### 4.1 Founder Relationships
**Property**: `Organization.founderQids[]` → `Person.qid`
**Relationship**: `(Person)-[:FOUNDED]->(Organization)`

```cypher
CALL {
    MATCH (org:Organization)
    WHERE size(org.founderQids) > 0
      AND NOT EXISTS(()-[:FOUNDED]->(org))
    WITH org LIMIT 50000
    UNWIND org.founderQids AS founderQid
    MATCH (person:Person {qid: founderQid})
    CREATE (person)-[:FOUNDED]->(org)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
```

**Expected**: ~200-300K
**Estimated time**: 30 minutes

## Phase 5: Derived Geographic Chains (LOW PRIORITY)

### 5.1 Person → Place (via WikidataPlace → Place links)

Create convenience relationships for common query patterns:

```cypher
// Person born in GeoNames Place (via WikidataPlace)
CALL {
    MATCH (p:Person)-[:BORN_IN]->(wp:WikidataPlace)-[:SAME_AS]->(place:Place)
    WHERE NOT EXISTS((p)-[:BORN_IN_PLACE]->(place))
    WITH p, place LIMIT 50000
    CREATE (p)-[:BORN_IN_PLACE]->(place)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
```

**Expected**: ~8-10M derived relationships
**Estimated time**: 2-3 hours
**Priority**: LOW (can be generated on-demand via queries)

## Implementation Scripts

### Script 1: `link_wikidata_places_global.py`

Adaptation of `link_by_geography.py` for WikidataPlace → Place at global scale:

```python
#!/usr/bin/env python3
"""
Link WikidataPlace to Place using geographic proximity.
Adapted from link_by_geography.py for global scale.
"""

class WikidataPlaceLinker:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def link_by_geonames_id(self):
        """Fast direct linking via geonamesId"""
        with self.driver.session() as session:
            result = session.run("""
                CALL {
                    MATCH (wp:WikidataPlace)
                    WHERE wp.geonamesId IS NOT NULL
                      AND NOT EXISTS((wp)-[:SAME_AS]->())
                    WITH wp LIMIT 50000
                    MATCH (p:Place {geonameId: wp.geonamesId})
                    MERGE (wp)-[r:SAME_AS]->(p)
                    SET r.evidence = 'geonames_id_match',
                        r.confidence = 1.0
                    RETURN count(*) as batch_count
                } IN TRANSACTIONS OF 50000 ROWS
                RETURN sum(batch_count) as total_count
            """)
            return result.single()['total_count']

    def get_countries_with_unlinked_places(self):
        """Get countries that still have unlinked WikidataPlace nodes"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.countryQid IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS|NEAR|LOCATED_IN]->())
                RETURN DISTINCT wp.countryQid AS country, count(*) AS count
                ORDER BY count DESC
            """)
            return [(r['country'], r['count']) for r in result]

    def link_by_geography_for_country(self, country_qid,
                                     distance_threshold=10.0,
                                     min_confidence=0.5):
        """Link WikidataPlace to Place for one country using geographic proximity"""
        # Reuse logic from link_by_geography.py
        # Modified to work with WikidataPlace → Place instead of Place → Place
        pass  # Implementation adapts existing code

# Usage:
# linker = WikidataPlaceLinker(uri, user, password)
# linker.link_by_geonames_id()  # Fast direct links
# for country, count in linker.get_countries_with_unlinked_places():
#     linker.link_by_geography_for_country(country)
```

### Script 2: `link_person_places.py`

```python
#!/usr/bin/env python3
"""Link Person nodes to WikidataPlace nodes"""

class PersonPlaceLinker:
    def link_birth_places(self):
        """Link Person → WikidataPlace via birthPlaceQid"""
        with self.driver.session() as session:
            result = session.run("""
                CALL {
                    MATCH (p:Person)
                    WHERE p.birthPlaceQid IS NOT NULL
                      AND NOT EXISTS((p)-[:BORN_IN]->())
                    WITH p LIMIT 50000
                    MATCH (wp:WikidataPlace {qid: p.birthPlaceQid})
                    CREATE (p)-[:BORN_IN]->(wp)
                    RETURN count(*) as batch_count
                } IN TRANSACTIONS OF 50000 ROWS
                RETURN sum(batch_count) as total_count
            """)
            return result.single()['total_count']

    # Similar methods for death places, residences, citizenship
```

### Script 3: `link_organizations.py`

Similar structure for Organization geographic links and founder links.

## Execution Timeline

### Week 1: WikidataPlace Spatial Linking
- Day 1: Direct geonamesId links (fast, ~2-3M links)
- Day 2-3: Adapt link_by_geography.py for WikidataPlace → Place
- Day 4-5: Run geographic linking by country (4-6 hours processing)
- **Deliverable**: ~7-10M WikidataPlace ↔ Place relationships

### Week 2: Person Geographic Links
- Day 1: Birth and death places (~8-10M links, 2-4 hours)
- Day 2: Residences and citizenship (~7-8M links, 2-3 hours)
- **Deliverable**: ~15-18M Person → WikidataPlace relationships

### Week 3: Organizations & Founders
- Day 1: Organization geographic links (~300K, 1 hour)
- Day 2: Founder relationships (~300K, 1 hour)
- Day 3: Testing and validation queries
- **Deliverable**: ~600K Organization relationships

### Week 4: Optimization & Derived Links (Optional)
- Day 1-2: Create derived Person → Place links via chains
- Day 3: Performance tuning and index optimization
- Day 4-5: Documentation and example queries

## Expected Final State

**Nodes**: 24.5M (unchanged)

**Relationships**: ~45-50M total
- Admin hierarchies: 11.5M (existing)
- WikidataPlace ↔ Place: 7-10M (Phase 1)
- Person → WikidataPlace: 15-18M (Phase 2)
- Organization relationships: 600K (Phase 3-4)
- Derived links: 8-10M (Phase 5, optional)

## Key Success Metrics

1. **Coverage**: >80% of WikidataPlace nodes linked to Place
2. **Precision**: >95% of SAME_AS links are correct (validate manually)
3. **Query Performance**: Geographic queries <500ms on global dataset
4. **Person Coverage**: >70% of people have at least one place link

## Validation Queries

```cypher
// Check WikidataPlace linking coverage
MATCH (wp:WikidataPlace)
RETURN
    count(wp) as total,
    count((wp)-[:SAME_AS]->()) as direct_match,
    count((wp)-[:NEAR]->()) as proximity_match,
    count((wp)-[:LOCATED_IN]->()) as contained,
    count(*) - count((wp)--()) as unlinked

// Sample high-confidence links
MATCH (wp:WikidataPlace)-[r:SAME_AS]->(p:Place)
WHERE r.confidence > 0.9
RETURN wp.name, p.name, r.confidence, r.distance_km
LIMIT 20

// Check Person geographic coverage
MATCH (person:Person)
RETURN
    count(person) as total_people,
    count((person)-[:BORN_IN]->()) as with_birth_place,
    count((person)-[:DIED_IN]->()) as with_death_place,
    count((person)-[:RESIDED_IN]->()) as with_residence
```

## Spatial Query Performance

With 11.5M WikidataPlace nodes, spatial queries need optimization:

1. **Country filtering first**: Always filter by country before spatial search
2. **Bounding box pre-filter**: Use lat/lon ranges before point.distance()
3. **Batch by region**: Process linking regionally to fit in memory

```cypher
// Optimized spatial query pattern
MATCH (wp:WikidataPlace)
WHERE wp.countryQid = $country
  AND wp.latitude >= $min_lat AND wp.latitude <= $max_lat
  AND wp.longitude >= $min_lon AND wp.longitude <= $max_lon
WITH wp
MATCH (p:Place)
WHERE p.countryCode = $country_code
  AND point.distance(wp.location, p.location) <= 10000
RETURN wp, p, point.distance(wp.location, p.location) as distance
```

## Next Immediate Steps

1. ✅ Test query session working (Job 4151801)
2. 🔜 Create `link_wikidata_places_global.py` adapted from `link_by_geography.py`
3. 🔜 Run Phase 1.1: Direct geonamesId links (fast, ~30 minutes)
4. 🔜 Run Phase 1.2: Geographic proximity linking (4-6 hours)
5. 🔜 Validate linking quality with sample queries
6. 🔜 Proceed to Person geographic links
