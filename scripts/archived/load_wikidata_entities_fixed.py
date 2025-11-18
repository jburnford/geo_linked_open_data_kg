#!/usr/bin/env python3
"""
Load filtered Wikidata entities (people, organizations, geographic) into Neo4j.
Reads newline-delimited JSON from filter_wikidata_*.py output.
FIXED VERSION - matches actual filter output format.
"""

import json
import gzip
from neo4j import GraphDatabase
from tqdm import tqdm
import sys
from typing import Dict, Any


class WikidataLoader:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="historicalkg2025"):
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 1000

        # Track coordinate issues
        self.coord_stats = {
            'skipped_invalid': 0,
            'fixed_swapped': 0,
            'skipped_missing': 0
        }

    def close(self):
        self.driver.close()

    def load_people(self, filepath: str):
        """Load Person nodes from wikidata_people.json.gz"""
        print(f"\nLoading people from {filepath}...")

        count = 0
        batch = []

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            # Skip metadata line
            next(f)

            pbar = tqdm(desc="People", unit="entities")

            for line in f:
                entity = json.loads(line)

                # Skip if no ID
                if not entity.get('wikidataId'):
                    continue

                person_data = {
                    'qid': entity['wikidataId'],
                    'name': entity.get('name', 'Unknown'),

                    # Birth/Death
                    'birthPlaceQid': entity.get('birthPlaceQid'),
                    'dateOfBirth': entity.get('dateOfBirth'),
                    'deathPlaceQid': entity.get('deathPlaceQid'),
                    'dateOfDeath': entity.get('dateOfDeath'),

                    # Places
                    'residenceQids': entity.get('residenceQids', []),
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
                pbar.update(1)

                if len(batch) >= self.batch_size:
                    count += self._load_people_batch(batch)
                    batch = []

            if batch:
                count += self._load_people_batch(batch)

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
                    p.birthPlaceQid = person.birthPlaceQid,
                    p.dateOfBirth = person.dateOfBirth,
                    p.deathPlaceQid = person.deathPlaceQid,
                    p.dateOfDeath = person.dateOfDeath,
                    p.residenceQids = person.residenceQids,
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
            # Skip metadata line
            next(f)

            pbar = tqdm(desc="Organizations", unit="entities")

            for line in f:
                entity = json.loads(line)

                # Skip if no ID
                if not entity.get('wikidataId'):
                    continue

                org_data = {
                    'qid': entity['wikidataId'],
                    'name': entity.get('name', 'Unknown'),

                    # Location
                    'headquartersQid': entity.get('headquartersQid'),
                    'foundedInQid': entity.get('foundedInQid'),

                    # Temporal
                    'founded': entity.get('founded'),

                    # Relations
                    'founderQids': entity.get('founderQids', []),
                }

                batch.append(org_data)
                pbar.update(1)

                if len(batch) >= self.batch_size:
                    count += self._load_orgs_batch(batch)
                    batch = []

            if batch:
                count += self._load_orgs_batch(batch)

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
                    o.headquartersQid = org.headquartersQid,
                    o.foundedInQid = org.foundedInQid,
                    o.founded = org.founded,
                    o.founderQids = org.founderQids
                RETURN count(o) as count
            """, batch=batch)
            return result.single()['count']

    def load_geographic_entities(self, filepath: str):
        """Load geographic WikidataPlace nodes from wikidata_geographic.json.gz"""
        print(f"\nLoading geographic entities from {filepath}...")

        count = 0
        batch = []

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            # Skip metadata line
            next(f)

            pbar = tqdm(desc="Geographic entities", unit="entities")

            for line in f:
                entity = json.loads(line)

                # Skip if no ID or coordinates
                if not entity.get('qid') or not entity.get('latitude'):
                    continue

                geo_data = {
                    'qid': entity['qid'],
                    'name': entity.get('name', 'Unknown'),
                    'description': entity.get('description'),

                    # Coordinates
                    'latitude': entity.get('latitude'),
                    'longitude': entity.get('longitude'),

                    # Administrative
                    'countryQid': entity.get('countryQid'),
                    'instanceOfQid': entity.get('instanceOfQid'),

                    # External IDs
                    'geonamesId': entity.get('geonamesId'),
                    'osmId': entity.get('osmId'),
                    'wofId': entity.get('wofId'),
                    'tgnId': entity.get('tgnId'),

                    # Other
                    'population': entity.get('population'),
                    'inceptionDate': entity.get('inceptionDate'),
                    'wikipediaUrl': entity.get('wikipediaUrl'),
                    'alternateNames': entity.get('alternateNames', []),
                }

                batch.append(geo_data)
                pbar.update(1)

                if len(batch) >= self.batch_size:
                    count += self._load_geo_batch(batch)
                    batch = []

            if batch:
                count += self._load_geo_batch(batch)

            pbar.close()

        print(f"✓ Loaded {count:,} geographic entities")

        # Report coordinate issues
        if any(self.coord_stats.values()):
            print(f"  Coordinate validation:")
            if self.coord_stats['fixed_swapped'] > 0:
                print(f"    Fixed swapped lat/lon: {self.coord_stats['fixed_swapped']:,}")
            if self.coord_stats['skipped_invalid'] > 0:
                print(f"    Skipped invalid: {self.coord_stats['skipped_invalid']:,}")
            if self.coord_stats['skipped_missing'] > 0:
                print(f"    Skipped missing: {self.coord_stats['skipped_missing']:,}")

        return count

    def _load_geo_batch(self, batch):
        """Load a batch of geographic entities with coordinate validation."""
        # Validate and fix coordinates before loading
        valid_batch = []

        for geo in batch:
            lat = geo.get('latitude')
            lon = geo.get('longitude')

            # Skip if coordinates are missing
            if lat is None or lon is None:
                self.coord_stats['skipped_missing'] += 1
                continue

            # Check if coordinates are in valid range
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                # Valid coordinates
                valid_batch.append(geo)
            elif -90 <= lon <= 90 and -180 <= lat <= 180:
                # Coordinates appear swapped - fix them
                geo['latitude'] = lon
                geo['longitude'] = lat
                valid_batch.append(geo)
                self.coord_stats['fixed_swapped'] += 1
            else:
                # Invalid coordinates that can't be fixed
                self.coord_stats['skipped_invalid'] += 1
                continue

        # Load valid batch
        if not valid_batch:
            return 0

        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS geo
                MERGE (g:WikidataPlace {qid: geo.qid})
                SET g.name = geo.name,
                    g.description = geo.description,
                    g.latitude = geo.latitude,
                    g.longitude = geo.longitude,
                    g.location = point({latitude: geo.latitude, longitude: geo.longitude}),
                    g.countryQid = geo.countryQid,
                    g.instanceOfQid = geo.instanceOfQid,
                    g.geonamesId = geo.geonamesId,
                    g.osmId = geo.osmId,
                    g.wofId = geo.wofId,
                    g.tgnId = geo.tgnId,
                    g.population = geo.population,
                    g.inceptionDate = geo.inceptionDate,
                    g.wikipediaUrl = geo.wikipediaUrl,
                    g.alternateNames = geo.alternateNames
                RETURN count(g) as count
            """, batch=valid_batch)
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
                    # Extract name from index command
                    if 'CONSTRAINT' in index:
                        name = index.split('CONSTRAINT')[1].split('IF')[0].strip()
                    else:
                        name = index.split('INDEX')[1].split('IF')[0].strip()
                    print(f"  ✓ {name}")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:80]}")

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
        import traceback
        traceback.print_exc()
        raise
    finally:
        loader.close()
