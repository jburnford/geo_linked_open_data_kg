# Entity Linking Plan

## Current Database State

**Total Nodes**: 24,568,022
- **WikidataPlace**: 11,555,027 (geographic entities from Wikidata)
- **Place**: 6,233,958 (GeoNames places)
- **Person**: 6,033,891 (Wikidata people)
- **AdminDivision**: 509,913 (GeoNames admin divisions)
- **Organization**: 234,979 (Wikidata organizations)
- **Country**: 254 (GeoNames countries)

**Existing Relationships**:
- Place → Country (LOCATED_IN_COUNTRY): 6.2M
- Place → AdminDivision (ADMIN1/ADMIN2/ADMIN3 hierarchies): 11.5M
- AdminDivision → AdminDivision (hierarchies)

## Proposed Entity Linking Strategy

### Phase 1: Geographic Entity Alignment (HIGH PRIORITY)

**Goal**: Link WikidataPlace to Place nodes via shared identifiers

#### 1.1 WikidataPlace → Place (via geonamesId)
- **Property**: `WikidataPlace.geonamesId` → `Place.geonameId`
- **Relationship**: `(WikidataPlace)-[:SAME_AS]->(Place)`
- **Expected**: ~2-3M matches (WikidataPlace nodes with geonamesId)
- **Priority**: HIGH - Enables cross-reference between Wikidata and GeoNames

**Implementation**:
```cypher
CALL {
    MATCH (wp:WikidataPlace)
    WHERE wp.geonamesId IS NOT NULL
      AND NOT EXISTS((wp)-[:SAME_AS]->())
    WITH wp LIMIT 50000
    MATCH (p:Place {geonameId: wp.geonamesId})
    CREATE (wp)-[:SAME_AS]->(p)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
RETURN sum(batch_count) as total_count
```

#### 1.2 WikidataPlace → AdminDivision (for administrative entities)
- **Property**: WikidataPlace with `instanceOfQid` indicating administrative division
- **Relationship**: `(WikidataPlace)-[:CORRESPONDS_TO]->(AdminDivision)`
- **Expected**: ~100-200K matches
- **Priority**: MEDIUM

### Phase 2: Person Geographic Links (HIGH PRIORITY)

**Goal**: Connect people to places they're associated with

#### 2.1 Person Birth Place Links
- **Property**: `Person.birthPlaceQid` → `WikidataPlace.qid`
- **Relationship**: `(Person)-[:BORN_IN]->(WikidataPlace)`
- **Expected**: ~4-5M relationships
- **Priority**: HIGH

**Implementation**:
```cypher
CALL {
    MATCH (person:Person)
    WHERE person.birthPlaceQid IS NOT NULL
      AND NOT EXISTS((person)-[:BORN_IN]->())
    WITH person LIMIT 50000
    MATCH (place:WikidataPlace {qid: person.birthPlaceQid})
    CREATE (person)-[:BORN_IN]->(place)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
RETURN sum(batch_count) as total_count
```

#### 2.2 Person Death Place Links
- **Property**: `Person.deathPlaceQid` → `WikidataPlace.qid`
- **Relationship**: `(Person)-[:DIED_IN]->(WikidataPlace)`
- **Expected**: ~3-4M relationships
- **Priority**: HIGH

#### 2.3 Person Residence Links
- **Property**: `Person.residenceQids[]` → `WikidataPlace.qid`
- **Relationship**: `(Person)-[:RESIDED_IN]->(WikidataPlace)`
- **Expected**: ~2-3M relationships (many people have multiple residences)
- **Priority**: MEDIUM

#### 2.4 Person Citizenship Links
- **Property**: `Person.citizenshipQid` → `WikidataPlace.qid`
- **Relationship**: `(Person)-[:CITIZEN_OF]->(WikidataPlace)`
- **Expected**: ~5M relationships
- **Priority**: MEDIUM

### Phase 3: Organization Geographic Links (MEDIUM PRIORITY)

#### 3.1 Organization Headquarters
- **Property**: `Organization.headquartersQid` → `WikidataPlace.qid`
- **Relationship**: `(Organization)-[:HEADQUARTERED_IN]->(WikidataPlace)`
- **Expected**: ~150-200K relationships
- **Priority**: MEDIUM

#### 3.2 Organization Founded In
- **Property**: `Organization.foundedInQid` → `WikidataPlace.qid`
- **Relationship**: `(Organization)-[:FOUNDED_IN]->(WikidataPlace)`
- **Expected**: ~100-150K relationships
- **Priority**: MEDIUM

### Phase 4: Organization-Person Links (MEDIUM PRIORITY)

#### 4.1 Founder Links
- **Property**: `Organization.founderQids[]` → `Person.qid`
- **Relationship**: `(Person)-[:FOUNDED]->(Organization)`
- **Expected**: ~200-300K relationships (many orgs have multiple founders)
- **Priority**: MEDIUM

### Phase 5: Indirect Geographic Links (LOW PRIORITY)

**Goal**: Create "chains" that allow geographic queries through multiple hops

#### 5.1 Person → Place (via WikidataPlace)
- **Relationship**: `(Person)-[:ASSOCIATED_WITH_PLACE]->(Place)`
- **Condition**: Person connected to WikidataPlace, WikidataPlace connected to Place
- **Expected**: ~8-10M relationships
- **Priority**: LOW (derived from existing links)

**Implementation** (example):
```cypher
// Create Person → Place links via BORN_IN → SAME_AS
CALL {
    MATCH (p:Person)-[:BORN_IN]->(wp:WikidataPlace)-[:SAME_AS]->(place:Place)
    WHERE NOT EXISTS((p)-[:BORN_IN_PLACE]->(place))
    WITH p, place LIMIT 50000
    CREATE (p)-[:BORN_IN_PLACE]->(place)
    RETURN count(*) as batch_count
} IN TRANSACTIONS OF 50000 ROWS
RETURN sum(batch_count) as total_count
```

## Implementation Order

### Recommended Sequence:

1. **WikidataPlace ↔ Place alignment** (Phase 1.1)
   - Essential foundation for all geographic queries
   - Enables cross-validation between data sources

2. **Person → WikidataPlace links** (Phase 2.1, 2.2)
   - Birth and death places are most reliable
   - High impact for historical research

3. **Organization → WikidataPlace links** (Phase 3.1, 3.2)
   - Establishes organizational geography
   - Required for institutional queries

4. **Person residence/citizenship** (Phase 2.3, 2.4)
   - More complex (arrays of QIDs)
   - Lower priority but valuable for migration studies

5. **Organization-Person links** (Phase 4.1)
   - Enables institutional network analysis
   - Depends on having Person and Organization nodes properly linked

6. **Indirect links** (Phase 5)
   - Optimization for common query patterns
   - Can be generated on-demand

## Batch Processing Scripts

### Template Script Structure:

```python
#!/usr/bin/env python3
"""
Create [RELATIONSHIP_TYPE] relationships between [NODE_TYPE1] and [NODE_TYPE2]
"""

from neo4j import GraphDatabase
from tqdm import tqdm
import time

class EntityLinker:
    def __init__(self, uri="bolt://localhost:7687",
                 user="neo4j", password="historicalkg2025"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def count_linkable_entities(self):
        """Count how many entities can be linked"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (source:SourceType)
                WHERE source.linkProperty IS NOT NULL
                  AND NOT EXISTS((source)-[:RELATIONSHIP_TYPE]->())
                RETURN count(source) as total
            """)
            return result.single()['total']

    def create_links_batched(self, batch_size=50000):
        """Create relationships in batches"""
        total = self.count_linkable_entities()
        print(f"Creating links for {total:,} entities...")

        with self.driver.session() as session:
            result = session.run("""
                CALL {
                    MATCH (source:SourceType)
                    WHERE source.linkProperty IS NOT NULL
                      AND NOT EXISTS((source)-[:RELATIONSHIP_TYPE]->())
                    WITH source LIMIT $batch_size
                    MATCH (target:TargetType {property: source.linkProperty})
                    CREATE (source)-[:RELATIONSHIP_TYPE]->(target)
                    RETURN count(*) as batch_count
                } IN TRANSACTIONS OF $batch_size ROWS
                RETURN sum(batch_count) as total_count
            """, batch_size=batch_size)

            count = result.single()['total_count']
            print(f"✓ Created {count:,} relationships")
            return count

if __name__ == "__main__":
    linker = EntityLinker()
    try:
        linker.create_links_batched()
    finally:
        linker.close()
```

## Validation Queries

### Check Link Coverage:

```cypher
// Person geographic link coverage
MATCH (p:Person)
RETURN
    count(p) as total_people,
    count(p.birthPlaceQid) as have_birth_place,
    count(p.deathPlaceQid) as have_death_place,
    count((p)-[:BORN_IN]->()) as birth_linked,
    count((p)-[:DIED_IN]->()) as death_linked
```

```cypher
// WikidataPlace → Place alignment coverage
MATCH (wp:WikidataPlace)
RETURN
    count(wp) as total_wikidata_places,
    count(wp.geonamesId) as have_geonames_id,
    count((wp)-[:SAME_AS]->()) as linked_to_place
```

### Sample Geographic Chains:

```cypher
// Find people born in places also in GeoNames
MATCH (p:Person)-[:BORN_IN]->(wp:WikidataPlace)-[:SAME_AS]->(place:Place)
RETURN p.name, wp.name, place.name
LIMIT 10
```

## Expected Timeline

- **Phase 1** (WikidataPlace alignment): 30-60 minutes
- **Phase 2** (Person links): 2-3 hours (large volume)
- **Phase 3** (Organization links): 30 minutes
- **Phase 4** (Org-Person links): 30 minutes
- **Phase 5** (Indirect links): 1-2 hours

**Total estimated time**: 5-7 hours of processing

## Memory Considerations

- **Batch size**: 50,000 nodes per transaction (safe for 64GB RAM)
- **Transaction memory limit**: 11.2 GB (Neo4j default)
- **Strategy**: Use `IN TRANSACTIONS OF` to avoid memory overflow

## Next Steps

1. Start with WikidataPlace → Place alignment script
2. Validate with sample queries
3. Proceed with Person geographic links
4. Monitor database size growth
5. Create indexes on new relationship types if needed
