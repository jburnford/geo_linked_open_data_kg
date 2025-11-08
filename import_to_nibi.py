#!/usr/bin/env python3
"""
Import exported database into Neo4j on Nibi.
Loads places, admin divisions, and countries from JSON export.
"""

import json
import gzip
from neo4j import GraphDatabase
from tqdm import tqdm
import sys

class Neo4jImporter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="historicalkg2025"):
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 10000

    def close(self):
        self.driver.close()

    def clear_database(self):
        """Clear existing data."""
        print("\nClearing existing data...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("✓ Database cleared")

    def create_constraints_and_indexes(self):
        """Create constraints and indexes before loading data."""
        print("\nCreating constraints and indexes...")

        with self.driver.session() as session:
            # Constraints
            constraints = [
                "CREATE CONSTRAINT place_geoname_id IF NOT EXISTS FOR (p:Place) REQUIRE p.geonameId IS UNIQUE",
                "CREATE CONSTRAINT admin_geoname_id IF NOT EXISTS FOR (a:AdminDivision) REQUIRE a.geonameId IS UNIQUE",
                "CREATE CONSTRAINT country_code IF NOT EXISTS FOR (c:Country) REQUIRE c.code IS UNIQUE",
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                    print(f"  ✓ {constraint.split('CONSTRAINT ')[1].split(' IF')[0]}")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:100]}")

            # Indexes
            indexes = [
                "CREATE INDEX place_country_code IF NOT EXISTS FOR (p:Place) ON (p.countryCode)",
                "CREATE INDEX place_admin1_code IF NOT EXISTS FOR (p:Place) ON (p.admin1Code)",
                "CREATE INDEX place_admin2_code IF NOT EXISTS FOR (p:Place) ON (p.admin2Code)",
                "CREATE INDEX place_admin3_code IF NOT EXISTS FOR (p:Place) ON (p.admin3Code)",
                "CREATE INDEX place_name IF NOT EXISTS FOR (p:Place) ON (p.name)",
                "CREATE INDEX admin_country_code IF NOT EXISTS FOR (a:AdminDivision) ON (a.countryCode)",
                "CREATE INDEX admin_admin1_code IF NOT EXISTS FOR (a:AdminDivision) ON (a.admin1Code)",
                "CREATE INDEX admin_admin2_code IF NOT EXISTS FOR (a:AdminDivision) ON (a.admin2Code)",
                "CREATE INDEX admin_feature_code IF NOT EXISTS FOR (a:AdminDivision) ON (a.featureCode)",
                "CREATE POINT INDEX place_location IF NOT EXISTS FOR (p:Place) ON (p.location)",
            ]

            for index in indexes:
                try:
                    session.run(index)
                    print(f"  ✓ {index.split('INDEX ')[1].split(' IF')[0]}")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:100]}")

        print("✓ Constraints and indexes created")

    def load_countries(self, filepath):
        """Load Country nodes."""
        print(f"\nLoading countries from {filepath}...")

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            countries = json.load(f)

        with self.driver.session() as session:
            session.run("""
                UNWIND $countries AS country
                CREATE (c:Country {
                    code: country.code,
                    name: country.name
                })
            """, countries=countries)

        print(f"✓ Loaded {len(countries)} countries")

    def load_admin_divisions(self, filepath):
        """Load AdminDivision nodes in batches."""
        print(f"\nLoading admin divisions from {filepath}...")

        # Count lines
        print("  Counting admin divisions...")
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            total = sum(1 for _ in f)

        batch = []
        loaded = 0

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            pbar = tqdm(total=total, desc="Admin divisions", unit="nodes")

            for line in f:
                data = json.loads(line)
                batch.append(data)

                if len(batch) >= self.batch_size:
                    self._load_admin_batch(batch)
                    loaded += len(batch)
                    pbar.update(len(batch))
                    batch = []

            # Load remaining
            if batch:
                self._load_admin_batch(batch)
                loaded += len(batch)
                pbar.update(len(batch))

            pbar.close()

        print(f"✓ Loaded {loaded:,} admin divisions")

    def _load_admin_batch(self, batch):
        """Load a batch of admin divisions."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $batch AS admin
                CREATE (a:AdminDivision {
                    geonameId: admin.geonameId,
                    name: admin.name,
                    countryCode: admin.countryCode,
                    admin1Code: admin.admin1Code,
                    admin2Code: admin.admin2Code,
                    admin3Code: admin.admin3Code,
                    featureCode: admin.featureCode
                })
            """, batch=batch)

    def load_places(self, filepath):
        """Load Place nodes in batches."""
        print(f"\nLoading places from {filepath}...")

        # Count lines
        print("  Counting places...")
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            total = sum(1 for _ in f)

        batch = []
        loaded = 0

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            pbar = tqdm(total=total, desc="Places", unit="nodes")

            for line in f:
                data = json.loads(line)
                batch.append(data)

                if len(batch) >= self.batch_size:
                    self._load_place_batch(batch)
                    loaded += len(batch)
                    pbar.update(len(batch))
                    batch = []

            # Load remaining
            if batch:
                self._load_place_batch(batch)
                loaded += len(batch)
                pbar.update(len(batch))

            pbar.close()

        print(f"✓ Loaded {loaded:,} places")

    def _load_place_batch(self, batch):
        """Load a batch of places."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $batch AS place
                CREATE (p:Place {
                    geonameId: place.geonameId,
                    name: place.name,
                    latitude: place.latitude,
                    longitude: place.longitude,
                    location: point({latitude: place.latitude, longitude: place.longitude}),
                    countryCode: place.countryCode,
                    admin1Code: place.admin1Code,
                    admin2Code: place.admin2Code,
                    admin3Code: place.admin3Code,
                    admin4Code: place.admin4Code,
                    featureClass: place.featureClass,
                    featureCode: place.featureCode,
                    population: place.population,
                    elevation: place.elevation,
                    timezone: place.timezone
                })
            """, batch=batch)

    def create_country_relationships(self):
        """Create Place -> Country relationships."""
        print("\nCreating Place -> Country relationships...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place), (c:Country)
                WHERE p.countryCode = c.code
                  AND NOT EXISTS((p)-[:LOCATED_IN_COUNTRY]->())
                CREATE (p)-[:LOCATED_IN_COUNTRY]->(c)
                RETURN count(*) as count
            """)

            count = result.single()["count"]
            print(f"✓ Created {count:,} LOCATED_IN_COUNTRY relationships")

    def verify_import(self):
        """Verify the import completed successfully."""
        print("\n" + "="*60)
        print("IMPORT VERIFICATION")
        print("="*60)

        with self.driver.session() as session:
            # Count nodes
            result = session.run("MATCH (p:Place) RETURN count(p) as count")
            place_count = result.single()["count"]
            print(f"Places: {place_count:,}")

            result = session.run("MATCH (a:AdminDivision) RETURN count(a) as count")
            admin_count = result.single()["count"]
            print(f"Admin divisions: {admin_count:,}")

            result = session.run("MATCH (c:Country) RETURN count(c) as count")
            country_count = result.single()["count"]
            print(f"Countries: {country_count:,}")

            # Count relationships
            result = session.run("MATCH ()-[r:LOCATED_IN_COUNTRY]->() RETURN count(r) as count")
            country_rel_count = result.single()["count"]
            print(f"Country relationships: {country_rel_count:,}")

        print("="*60)
        print("✓ Import complete!")
        print("\nNext steps:")
        print("1. Run create_admin_hierarchies_batched.py to build admin hierarchies")
        print("2. Run add_admin3_links.py to add ADMIN3 relationships")
        print("3. Load Wikidata entities when filtered files are ready")

if __name__ == "__main__":
    import_dir = "neo4j_export"

    if len(sys.argv) > 1:
        import_dir = sys.argv[1]

    importer = Neo4jImporter()

    try:
        # Clear and prepare
        response = input("\n⚠ This will clear the database. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

        importer.clear_database()
        importer.create_constraints_and_indexes()

        # Load data
        importer.load_countries(f"{import_dir}/countries.json.gz")
        importer.load_admin_divisions(f"{import_dir}/admin_divisions.json.gz")
        importer.load_places(f"{import_dir}/places.json.gz")

        # Create basic relationships
        importer.create_country_relationships()

        # Verify
        importer.verify_import()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
    finally:
        importer.close()
