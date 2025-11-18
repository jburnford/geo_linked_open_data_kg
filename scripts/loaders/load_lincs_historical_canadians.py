#!/usr/bin/env python3
"""
Load LINCS Historical Canadians into Neo4j and link to existing Place and Person nodes.

Creates:
- HistoricalPerson nodes (25,596 total, 14,049 with biographical data)
- BORN_IN relationships → Place nodes (via GeoNames IDs)
- DIED_IN relationships → Place nodes (via GeoNames IDs)
- SAME_AS relationships → Person nodes (via Wikidata QIDs)
- PARENT_OF / CHILD_OF relationships (family connections)
- SPOUSE_OF relationships (marriages)

Integration with existing CanadaNeo4j:
- Links to Place nodes (6.2M from GeoNames) via birth/death locations
- Links to Person nodes (6M from Wikidata) via owl:sameAs QIDs
- Enriches existing Person nodes with Canadian biographical detail
"""

import json
import os
from neo4j import GraphDatabase
from tqdm import tqdm
from typing import Dict, List


class LINCSHistoricalCanadiansLoader:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.batch_size = 500

    def close(self):
        self.driver.close()

    def create_indexes(self):
        """Create indexes for HistoricalPerson nodes."""
        print("\nCreating indexes...")

        with self.driver.session(database=self.database) as session:
            indexes = [
                "CREATE CONSTRAINT historical_person_id IF NOT EXISTS FOR (h:HistoricalPerson) REQUIRE h.personId IS UNIQUE",
                "CREATE INDEX historical_person_name IF NOT EXISTS FOR (h:HistoricalPerson) ON (h.name)",
                "CREATE INDEX historical_person_wikidata IF NOT EXISTS FOR (h:HistoricalPerson) ON (h.wikidataQid)",
                "CREATE INDEX historical_person_viaf IF NOT EXISTS FOR (h:HistoricalPerson) ON (h.viafId)",
            ]

            for idx in indexes:
                try:
                    session.run(idx)
                    print(f"  ✓ {idx.split('IF')[0].strip()[:60]}...")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:100]}")

    def load_persons(self, json_file: str):
        """
        Load historical persons from parsed JSON.

        Creates HistoricalPerson nodes and links them to Place/Person nodes.
        """
        print(f"\nLoading persons from {json_file}...")

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            metadata = data.get('metadata', {})
            persons = data['persons']

        print(f"Found {len(persons):,} persons with biographical data")
        print(f"Metadata: {metadata.get('totalPersons', 0):,} total persons in source")

        # Process in batches
        total_persons = 0
        total_birth_links = 0
        total_death_links = 0

        with self.driver.session(database=self.database) as session:
            for i in tqdm(range(0, len(persons), self.batch_size), desc="Loading persons"):
                batch = persons[i:i + self.batch_size]

                # Prepare batch data
                person_batch = []
                for person in batch:
                    # Extract birth/death dates and places
                    birth_date = None
                    birth_geonames_ids = []
                    if person.get('birthEvent'):
                        birth_date = person['birthEvent'].get('date')
                        if 'places' in person['birthEvent']:
                            birth_geonames_ids = [
                                p['id'] for p in person['birthEvent']['places']
                                if p.get('type') == 'geonames'
                            ]

                    death_date = None
                    death_geonames_ids = []
                    if person.get('deathEvent'):
                        death_date = person['deathEvent'].get('date')
                        if 'places' in person['deathEvent']:
                            death_geonames_ids = [
                                p['id'] for p in person['deathEvent']['places']
                                if p.get('type') == 'geonames'
                            ]

                    # Store parent/spouse IDs for relationship creation
                    mother_id = None
                    father_id = None
                    if person.get('birthEvent'):
                        mother_id = person['birthEvent'].get('motherId')
                        father_id = person['birthEvent'].get('fatherId')

                    spouse_ids = [
                        rel['personId'] for rel in person.get('relationships', [])
                        if rel['type'] == 'spouse'
                    ]

                    person_batch.append({
                        'personId': person['personId'],
                        'idType': person.get('idType', 'Unknown'),
                        'name': person['name'],
                        'alternateNames': person.get('alternateNames', []),
                        'wikidataQid': person.get('wikidataQid'),
                        'viafId': person.get('viafId'),
                        'birthDate': birth_date,
                        'birthGeonamesIds': birth_geonames_ids,
                        'deathDate': death_date,
                        'deathGeonamesIds': death_geonames_ids,
                        'motherId': mother_id,
                        'fatherId': father_id,
                        'spouseIds': spouse_ids
                    })

                # Create person nodes
                result = session.run("""
                    UNWIND $batch AS person
                    MERGE (h:HistoricalPerson {personId: person.personId})
                    SET h.name = person.name,
                        h.alternateNames = person.alternateNames,
                        h.wikidataQid = person.wikidataQid,
                        h.viafId = person.viafId,
                        h.idType = person.idType,
                        h.birthDate = person.birthDate,
                        h.deathDate = person.deathDate
                    RETURN count(h) as count
                """, batch=person_batch)

                batch_count = result.single()['count']
                total_persons += batch_count

                # Create birth place relationships
                result = session.run("""
                    UNWIND $batch AS person
                    MATCH (h:HistoricalPerson {personId: person.personId})
                    UNWIND person.birthGeonamesIds AS geonamesId
                    MATCH (p:Place {geonameId: geonamesId})
                    MERGE (h)-[:BORN_IN]->(p)
                    RETURN count(*) as linkedCount
                """, batch=person_batch)

                batch_birth = result.single()['linkedCount']
                total_birth_links += batch_birth

                # Create death place relationships
                result = session.run("""
                    UNWIND $batch AS person
                    MATCH (h:HistoricalPerson {personId: person.personId})
                    UNWIND person.deathGeonamesIds AS geonamesId
                    MATCH (p:Place {geonameId: geonamesId})
                    MERGE (h)-[:DIED_IN]->(p)
                    RETURN count(*) as linkedCount
                """, batch=person_batch)

                batch_death = result.single()['linkedCount']
                total_death_links += batch_death

        print(f"\n✓ Created {total_persons:,} HistoricalPerson nodes")
        print(f"✓ Created {total_birth_links:,} BORN_IN relationships to Place nodes")
        print(f"✓ Created {total_death_links:,} DIED_IN relationships to Place nodes")

        return total_persons, total_birth_links, total_death_links

    def link_to_wikidata_persons(self):
        """Link HistoricalPerson nodes to existing Person nodes via Wikidata QIDs."""
        print("\nLinking to Wikidata Person nodes...")

        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (h:HistoricalPerson)
                WHERE h.wikidataQid IS NOT NULL
                MATCH (p:Person {qid: h.wikidataQid})
                MERGE (h)-[:SAME_AS]->(p)
                RETURN count(*) as count
            """)
            person_links = result.single()['count']

            print(f"  ✓ Linked {person_links:,} HistoricalPerson → Person nodes")

            return person_links

    def create_family_relationships(self, json_file: str):
        """Create parent-child and spouse relationships between HistoricalPerson nodes."""
        print("\nCreating family relationships...")

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            persons = data['persons']

        # Collect all parent-child and spouse relationships
        parent_child_rels = []
        spouse_rels = set()  # Use set to avoid duplicates

        for person in persons:
            person_id = person['personId']

            # Parent relationships
            if person.get('birthEvent'):
                mother_id = person['birthEvent'].get('motherId')
                father_id = person['birthEvent'].get('fatherId')

                if mother_id:
                    parent_child_rels.append({
                        'parentId': mother_id,
                        'childId': person_id,
                        'parentType': 'mother'
                    })

                if father_id:
                    parent_child_rels.append({
                        'parentId': father_id,
                        'childId': person_id,
                        'parentType': 'father'
                    })

            # Spouse relationships (ensure we only create each once)
            for rel in person.get('relationships', []):
                if rel['type'] == 'spouse':
                    # Sort IDs to create canonical ordering
                    spouse_pair = tuple(sorted([person_id, rel['personId']]))
                    spouse_rels.add((spouse_pair[0], spouse_pair[1], rel.get('date')))

        print(f"Found {len(parent_child_rels):,} parent-child relationships")
        print(f"Found {len(spouse_rels):,} spouse relationships")

        with self.driver.session(database=self.database) as session:
            # Create parent-child relationships
            parent_count = 0
            for i in tqdm(range(0, len(parent_child_rels), self.batch_size), desc="Parent-child"):
                batch = parent_child_rels[i:i + self.batch_size]

                result = session.run("""
                    UNWIND $batch AS rel
                    MATCH (parent:HistoricalPerson {personId: rel.parentId})
                    MATCH (child:HistoricalPerson {personId: rel.childId})
                    MERGE (parent)-[:PARENT_OF {relationship: rel.parentType}]->(child)
                    MERGE (child)-[:CHILD_OF {relationship: rel.parentType}]->(parent)
                    RETURN count(*) as count
                """, batch=batch)

                parent_count += result.single()['count']

            # Create spouse relationships
            spouse_list = [{'spouse1': s[0], 'spouse2': s[1], 'date': s[2]} for s in spouse_rels]
            spouse_count = 0

            for i in tqdm(range(0, len(spouse_list), self.batch_size), desc="Spouses"):
                batch = spouse_list[i:i + self.batch_size]

                result = session.run("""
                    UNWIND $batch AS rel
                    MATCH (s1:HistoricalPerson {personId: rel.spouse1})
                    MATCH (s2:HistoricalPerson {personId: rel.spouse2})
                    MERGE (s1)-[r:SPOUSE_OF]-(s2)
                    SET r.marriageDate = rel.date
                    RETURN count(*) as count
                """, batch=batch)

                spouse_count += result.single()['count']

        print(f"  ✓ Created {parent_count:,} parent-child relationships")
        print(f"  ✓ Created {spouse_count:,} spouse relationships")

        return parent_count, spouse_count

    def print_statistics(self):
        """Print statistics about the import."""
        print("\n" + "="*60)
        print("LINCS HISTORICAL CANADIANS - IMPORT STATISTICS")
        print("="*60)

        with self.driver.session(database=self.database) as session:
            # Count nodes
            result = session.run("MATCH (h:HistoricalPerson) RETURN count(h) as count")
            person_count = result.single()['count']

            # Count relationships
            result = session.run("MATCH (:HistoricalPerson)-[r:BORN_IN]->() RETURN count(r) as count")
            born_in_count = result.single()['count']

            result = session.run("MATCH (:HistoricalPerson)-[r:DIED_IN]->() RETURN count(r) as count")
            died_in_count = result.single()['count']

            result = session.run("MATCH (:HistoricalPerson)-[r:SAME_AS]->() RETURN count(r) as count")
            same_as_count = result.single()['count']

            result = session.run("MATCH ()-[r:PARENT_OF]->() RETURN count(r) as count")
            parent_count = result.single()['count']

            result = session.run("MATCH ()-[r:SPOUSE_OF]-() RETURN count(r) as count")
            spouse_count = result.single()['count']

            print(f"\nHistoricalPerson nodes: {person_count:,}")
            print(f"\nRelationships:")
            print(f"  BORN_IN (→ Place): {born_in_count:,}")
            print(f"  DIED_IN (→ Place): {died_in_count:,}")
            print(f"  SAME_AS (→ Person): {same_as_count:,}")
            print(f"  PARENT_OF: {parent_count:,}")
            print(f"  SPOUSE_OF: {spouse_count:,}")

            # Sample queries
            print("\n" + "="*60)
            print("SAMPLE HISTORICAL CANADIANS")
            print("="*60)

            result = session.run("""
                MATCH (h:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place)
                WHERE h.wikidataQid IS NOT NULL
                  AND h.deathDate IS NOT NULL
                WITH h, birthPlace
                LIMIT 5
                RETURN h.name AS name,
                       h.birthDate AS birth,
                       birthPlace.name AS birthPlace,
                       h.deathDate AS death,
                       h.wikidataQid AS wikidata
                ORDER BY h.birthDate
            """)

            for record in result:
                print(f"\n{record['name']}")
                print(f"  Born: {record['birth']} in {record['birthPlace']}")
                print(f"  Died: {record['death']}")
                print(f"  Wikidata: {record['wikidata']}")

            # Family network example
            print("\n" + "="*60)
            print("SAMPLE FAMILY NETWORK")
            print("="*60)

            result = session.run("""
                MATCH (parent:HistoricalPerson)-[:PARENT_OF]->(child:HistoricalPerson)
                WHERE parent.name IS NOT NULL AND child.name IS NOT NULL
                WITH parent, collect(child.name) AS children
                WHERE size(children) > 1
                RETURN parent.name AS parent, children
                LIMIT 3
            """)

            for record in result:
                children_str = ", ".join(record['children'][:5])
                if len(record['children']) > 5:
                    children_str += f" (and {len(record['children']) - 5} more)"
                print(f"  {record['parent']} → {children_str}")

        print("\n" + "="*60)

    def run_import(self, json_file: str):
        """Execute complete import process."""
        print("="*60)
        print("IMPORTING LINCS HISTORICAL CANADIANS")
        print("="*60)

        self.create_indexes()
        person_count, birth_links, death_links = self.load_persons(json_file)
        wikidata_links = self.link_to_wikidata_persons()
        parent_count, spouse_count = self.create_family_relationships(json_file)
        self.print_statistics()

        print("\n✓ LINCS Historical Canadians import complete!")


def main():
    import sys

    # Get connection details from environment or arguments
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    json_file = sys.argv[1] if len(sys.argv) > 1 else "lincs_historical_canadians.json"

    loader = LINCSHistoricalCanadiansLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        loader.run_import(json_file)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()
