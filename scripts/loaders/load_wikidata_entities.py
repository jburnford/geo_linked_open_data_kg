#!/usr/bin/env python3
"""
Load filtered Wikidata entities (people, organizations, geographic) into Neo4j.
Reads newline-delimited JSON from filter_wikidata_*.py output.
"""

import json
import gzip
import os
from neo4j import GraphDatabase
from tqdm import tqdm
import sys
from typing import Dict, Any


class WikidataLoader:
    def __init__(self, uri=None, user=None, password=None):
        # Use environment variables if not provided
        uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        user = user or os.getenv('NEO4J_USER', 'neo4j')
        password = password or os.getenv('NEO4J_PASSWORD', 'historicalkg2025')

        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 1000

    def close(self):
        self.driver.close()

    def load_people(self, filepath: str):
        """Load Person nodes from wikidata_people.json.gz"""
        print(f"\nLoading people from {filepath}...")

        count = 0
        batch = []

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            # Count lines for progress bar (skip metadata line)
            print("  Counting entities...")
            total = sum(1 for _ in f) - 1  # Skip metadata line
            f.seek(0)

            pbar = tqdm(total=total, desc="People", unit="entities")

            # Skip first line (metadata)
            next(f)

            for line in f:
                entity = json.loads(line)

                # Skip if no ID
                if not entity.get('wikidataId'):
                    continue

                person_data = {
                    'qid': entity['wikidataId'],
                    'name': entity.get('name', 'Unknown'),
                    'description': entity.get('description'),

                    # Birth
                    'birthPlaceQid': entity.get('birthPlaceQid'),
                    'birthDate': entity.get('dateOfBirth'),

                    # Death
                    'deathPlaceQid': entity.get('deathPlaceQid'),
                    'deathDate': entity.get('dateOfDeath'),

                    # Other places
                    'residencePlaceQids': entity.get('residenceQids', []),
                    'workPlaceQids': entity.get('workLocationQids', []),
                    'citizenshipQid': entity.get('citizenshipQid'),

                    # Attributes
                    'occupationQids': entity.get('occupationQids', []),
                    'positionQids': entity.get('positionQids', []),

                    # External IDs
                    'viafId': entity.get('viafId'),
                    'gndId': entity.get('gndId'),
                    'locId': entity.get('locId'),
                }

                batch.append(person_data)

                if len(batch) >= self.batch_size:
                    count += self._load_people_batch(batch)
                    pbar.update(len(batch))
                    batch = []

            if batch:
                count += self._load_people_batch(batch)
                pbar.update(len(batch))

            pbar.close()

        print(f"✓ Loaded {count:,} people")
        return count

    def _load_people_batch(self, batch):
        """Load a batch of people."""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS person
                MERGE (p:Person {qid: person.qid})
                SET p.name = person.name,
                    p.description = person.description,
                    p.birthPlaceQid = person.birthPlaceQid,
                    p.birthDate = person.birthDate,
                    p.deathPlaceQid = person.deathPlaceQid,
                    p.deathDate = person.deathDate,
                    p.residencePlaceQids = person.residencePlaceQids,
                    p.workPlaceQids = person.workPlaceQids,
                    p.citizenshipQid = person.citizenshipQid,
                    p.occupationQids = person.occupationQids,
                    p.positionQids = person.positionQids,
                    p.viafId = person.viafId,
                    p.gndId = person.gndId,
                    p.locId = person.locId
                RETURN count(p) as count
            """, batch=batch)
            return result.single()['count']

    def load_organizations(self, filepath: str):
        """Load Organization nodes from wikidata_organizations.json.gz"""
        print(f"\nLoading organizations from {filepath}...")

        count = 0
        batch = []

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            print("  Counting entities...")
            # Check if first line is metadata
            first_line = f.readline()
            if b'metadata' in first_line:
                total = sum(1 for _ in f)
                # Don't seek back, we'll skip metadata
            else:
                f.seek(0)
                total = sum(1 for _ in f) + 1
                f.seek(0)

            pbar = tqdm(total=total, desc="Organizations", unit="entities")

            for line in f:
                entity = json.loads(line)

                # Skip metadata line
                if 'metadata' in entity:
                    continue

                org_data = {
                    'qid': entity.get('qid') or entity.get('id'),
                    'name': entity.get('label', 'Unknown'),
                    'description': entity.get('description'),

                    # Location
                    'headquartersQid': entity.get('headquarters'),
                    'locationQids': entity.get('location', []),

                    # Temporal
                    'inceptionDate': entity.get('inception'),
                    'dissolvedDate': entity.get('dissolved'),

                    # Type
                    'instanceOf': entity.get('instance_of'),
                    'organizationType': entity.get('organization_type'),

                    # External IDs
                    'viafId': entity.get('viaf'),
                    'gndId': entity.get('gnd'),
                    'locId': entity.get('loc'),
                }

                batch.append(org_data)

                if len(batch) >= self.batch_size:
                    count += self._load_orgs_batch(batch)
                    pbar.update(len(batch))
                    batch = []

            if batch:
                count += self._load_orgs_batch(batch)
                pbar.update(len(batch))

            pbar.close()

        print(f"✓ Loaded {count:,} organizations")
        return count

    def _load_orgs_batch(self, batch):
        """Load a batch of organizations."""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS org
                MERGE (o:Organization {qid: org.qid})
                SET o.name = org.name,
                    o.description = org.description,
                    o.headquartersQid = org.headquartersQid,
                    o.locationQids = org.locationQids,
                    o.inceptionDate = org.inceptionDate,
                    o.dissolvedDate = org.dissolvedDate,
                    o.instanceOf = org.instanceOf,
                    o.organizationType = org.organizationType,
                    o.viafId = org.viafId,
                    o.gndId = org.gndId,
                    o.locId = org.locId
                RETURN count(o) as count
            """, batch=batch)
            return result.single()['count']

    def load_geographic_entities(self, filepath: str):
        """Load geographic WikidataPlace nodes from wikidata_geographic.json.gz"""
        print(f"\nLoading geographic entities from {filepath}...")

        count = 0
        batch = []

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            print("  Counting entities...")
            total = sum(1 for _ in f) - 1  # Skip metadata line
            f.seek(0)

            pbar = tqdm(total=total, desc="Geographic entities", unit="entities")

            # Skip first line (metadata)
            next(f)

            for line in f:
                entity = json.loads(line)

                geo_data = {
                    'qid': entity.get('qid') or entity.get('id'),
                    'name': entity.get('label', 'Unknown'),
                    'description': entity.get('description'),

                    # Coordinates
                    'latitude': entity.get('latitude'),
                    'longitude': entity.get('longitude'),

                    # Administrative
                    'countryQid': entity.get('country'),
                    'admin1Qid': entity.get('admin1'),
                    'admin2Qid': entity.get('admin2'),

                    # Type
                    'instanceOf': entity.get('instance_of'),

                    # External IDs
                    'geonamesId': entity.get('geonames_id'),
                    'osmId': entity.get('osm_id'),
                }

                batch.append(geo_data)

                if len(batch) >= self.batch_size:
                    count += self._load_geo_batch(batch)
                    pbar.update(len(batch))
                    batch = []

            if batch:
                count += self._load_geo_batch(batch)
                pbar.update(len(batch))

            pbar.close()

        print(f"✓ Loaded {count:,} geographic entities")
        return count

    def _load_geo_batch(self, batch):
        """Load a batch of geographic entities."""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS geo
                MERGE (g:WikidataPlace {qid: geo.qid})
                SET g.name = geo.name,
                    g.description = geo.description,
                    g.latitude = geo.latitude,
                    g.longitude = geo.longitude,
                    g.countryQid = geo.countryQid,
                    g.admin1Qid = geo.admin1Qid,
                    g.admin2Qid = geo.admin2Qid,
                    g.instanceOf = geo.instanceOf,
                    g.geonamesId = geo.geonamesId,
                    g.osmId = geo.osmId,
                    g.location = CASE WHEN geo.latitude IS NOT NULL AND geo.longitude IS NOT NULL
                                      THEN point({latitude: geo.latitude, longitude: geo.longitude})
                                      ELSE null END
                RETURN count(g) as count
            """, batch=batch)
            return result.single()['count']

    def create_indexes(self):
        """Create indexes for new node types."""
        print("\nCreating indexes...")

        with self.driver.session() as session:
            indexes = [
                "CREATE CONSTRAINT person_qid IF NOT EXISTS FOR (p:Person) REQUIRE p.qid IS UNIQUE",
                "CREATE CONSTRAINT org_qid IF NOT EXISTS FOR (o:Organization) REQUIRE o.qid IS UNIQUE",
                "CREATE CONSTRAINT wikiplace_qid IF NOT EXISTS FOR (w:WikidataPlace) REQUIRE w.qid IS UNIQUE",
                "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name)",
                "CREATE INDEX org_name IF NOT EXISTS FOR (o:Organization) ON (o.name)",
                "CREATE INDEX wikiplace_name IF NOT EXISTS FOR (w:WikidataPlace) ON (w.name)",
                "CREATE POINT INDEX wikiplace_location IF NOT EXISTS FOR (w:WikidataPlace) ON (w.location)",
            ]

            for index in indexes:
                try:
                    session.run(index)
                    print(f"  ✓ {index.split('INDEX')[0].split('CONSTRAINT')[1].split('IF')[0].strip()}")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:100]}")

        print("✓ Indexes created")

    def verify_import(self):
        """Verify the import and show statistics."""
        print("\n" + "="*60)
        print("WIKIDATA IMPORT VERIFICATION")
        print("="*60)

        with self.driver.session() as session:
            # Count nodes
            for label in ['Person', 'Organization', 'WikidataPlace', 'Place', 'AdminDivision', 'Country']:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) as count")
                count = result.single()['count']
                if count > 0:
                    print(f"{label}: {count:,}")

        print("="*60)


if __name__ == "__main__":
    import os

    # Paths
    filtered_dir = os.getenv('FILTERED_DIR', '/home/jic823/projects/def-jic823/wikidata/filtered')

    loader = WikidataLoader()

    try:
        # Create indexes first
        loader.create_indexes()

        # Load entities
        print("\n" + "="*60)
        print("LOADING WIKIDATA ENTITIES")
        print("="*60)

        # Load geographic entities
        geo_file = f"{filtered_dir}/wikidata_geographic.json.gz"
        if os.path.exists(geo_file):
            loader.load_geographic_entities(geo_file)

        # Load people
        people_file = f"{filtered_dir}/wikidata_people.json.gz"
        if os.path.exists(people_file):
            loader.load_people(people_file)

        # Load organizations
        org_file = f"{filtered_dir}/wikidata_organizations.json.gz"
        if os.path.exists(org_file):
            loader.load_organizations(org_file)

        # Verify
        loader.verify_import()

        print("\n✓ Wikidata import complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
    finally:
        loader.close()
