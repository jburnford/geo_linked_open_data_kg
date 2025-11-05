#!/usr/bin/env python3
"""
GeoNames Data Loader for Neo4j LOD Knowledge Graph

Loads GeoNames data (cities500.txt and CA.txt) into Neo4j with proper schema,
indexes, and relationships for NER reconciliation.
"""

import os
import csv
from typing import Dict, List, Optional
from datetime import datetime
from neo4j import GraphDatabase
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# GeoNames field mapping (tab-delimited)
GEONAMES_FIELDS = [
    'geonameid', 'name', 'asciiname', 'alternatenames',
    'latitude', 'longitude', 'feature_class', 'feature_code',
    'country_code', 'cc2', 'admin1_code', 'admin2_code',
    'admin3_code', 'admin4_code', 'population', 'elevation',
    'dem', 'timezone', 'modification_date'
]


class GeoNamesLoader:
    """Load GeoNames data into Neo4j for NER reconciliation."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = int(os.getenv('BATCH_SIZE', 10000))

    def close(self):
        self.driver.close()

    def setup_schema(self):
        """Create constraints and indexes for optimal query performance."""
        print("Setting up Neo4j schema...")

        with self.driver.session() as session:
            # Constraints (ensure uniqueness)
            constraints = [
                "CREATE CONSTRAINT place_geonameid IF NOT EXISTS FOR (p:Place) REQUIRE p.geonameId IS UNIQUE",
                "CREATE CONSTRAINT country_code IF NOT EXISTS FOR (c:Country) REQUIRE c.code IS UNIQUE",
                "CREATE CONSTRAINT admin_code IF NOT EXISTS FOR (a:AdminDivision) REQUIRE (a.code, a.countryCode, a.level) IS UNIQUE",
            ]

            # Indexes (speed up lookups)
            indexes = [
                "CREATE INDEX place_name IF NOT EXISTS FOR (p:Place) ON (p.name)",
                "CREATE INDEX place_asciiname IF NOT EXISTS FOR (p:Place) ON (p.asciiName)",
                "CREATE INDEX place_country IF NOT EXISTS FOR (p:Place) ON (p.countryCode)",
                "CREATE INDEX place_featureclass IF NOT EXISTS FOR (p:Place) ON (p.featureClass)",
                "CREATE INDEX place_population IF NOT EXISTS FOR (p:Place) ON (p.population)",
                "CREATE TEXT INDEX place_name_text IF NOT EXISTS FOR (p:Place) ON (p.name)",
                "CREATE TEXT INDEX place_alternatenames_text IF NOT EXISTS FOR (p:Place) ON (p.alternateNames)",
            ]

            for cypher in constraints + indexes:
                try:
                    session.run(cypher)
                    print(f"✓ {cypher.split()[1]}")
                except Exception as e:
                    print(f"⚠ {cypher.split()[1]}: {e}")

    def clear_database(self, confirm: bool = False):
        """Clear all nodes and relationships (USE WITH CAUTION)."""
        if not confirm:
            print("⚠ Skipping database clear (set confirm=True to clear)")
            return

        print("Clearing database...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")

    def parse_geonames_row(self, row: Dict) -> Dict:
        """Parse a GeoNames row into Neo4j-friendly format."""
        # Parse alternate names into list
        alt_names = []
        if row.get('alternatenames'):
            alt_names = [n.strip() for n in row['alternatenames'].split(',') if n.strip()]

        # Convert numeric fields
        try:
            population = int(row.get('population', 0) or 0)
        except ValueError:
            population = 0

        try:
            elevation = int(row.get('elevation', 0) or 0)
        except ValueError:
            elevation = 0

        try:
            latitude = float(row['latitude'])
            longitude = float(row['longitude'])
        except (ValueError, KeyError):
            latitude = None
            longitude = None

        return {
            'geonameId': int(row['geonameid']),
            'name': row['name'],
            'asciiName': row['asciiname'],
            'alternateNames': alt_names,
            'latitude': latitude,
            'longitude': longitude,
            'featureClass': row['feature_class'],
            'featureCode': row['feature_code'],
            'countryCode': row['country_code'],
            'admin1Code': row.get('admin1_code', ''),
            'admin2Code': row.get('admin2_code', ''),
            'admin3Code': row.get('admin3_code', ''),
            'admin4Code': row.get('admin4_code', ''),
            'population': population,
            'elevation': elevation,
            'timezone': row.get('timezone', ''),
            'modifiedDate': row.get('modification_date', ''),
            'wikidataId': None,  # To be populated later
            'wikipediaUrl': None
        }

    def load_places_batch(self, places: List[Dict]):
        """Load a batch of places into Neo4j."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $places AS place
                MERGE (p:Place {geonameId: place.geonameId})
                SET p.name = place.name,
                    p.asciiName = place.asciiName,
                    p.alternateNames = place.alternateNames,
                    p.latitude = place.latitude,
                    p.longitude = place.longitude,
                    p.featureClass = place.featureClass,
                    p.featureCode = place.featureCode,
                    p.countryCode = place.countryCode,
                    p.admin1Code = place.admin1Code,
                    p.admin2Code = place.admin2Code,
                    p.admin3Code = place.admin3Code,
                    p.admin4Code = place.admin4Code,
                    p.population = place.population,
                    p.elevation = place.elevation,
                    p.timezone = place.timezone,
                    p.modifiedDate = place.modifiedDate,
                    p.wikidataId = place.wikidataId,
                    p.wikipediaUrl = place.wikipediaUrl

                // Create or link to country
                MERGE (c:Country {code: place.countryCode})
                MERGE (p)-[:LOCATED_IN_COUNTRY]->(c)
            """, places=places)

    def load_geonames_file(self, filepath: str, description: str = ""):
        """Load a GeoNames file into Neo4j."""
        print(f"\nLoading {description or filepath}...")

        # Count total lines for progress bar
        with open(filepath, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)

        batch = []
        loaded_count = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, fieldnames=GEONAMES_FIELDS, delimiter='\t')

            with tqdm(total=total_lines, desc=description) as pbar:
                for row in reader:
                    try:
                        place = self.parse_geonames_row(row)
                        batch.append(place)

                        if len(batch) >= self.batch_size:
                            self.load_places_batch(batch)
                            loaded_count += len(batch)
                            batch = []

                        pbar.update(1)

                    except Exception as e:
                        print(f"Error parsing row {row.get('geonameid')}: {e}")
                        continue

                # Load remaining batch
                if batch:
                    self.load_places_batch(batch)
                    loaded_count += len(batch)

        print(f"✓ Loaded {loaded_count:,} places from {description}")
        return loaded_count

    def create_admin_divisions(self):
        """Create AdminDivision nodes from Place data."""
        print("\nCreating administrative division nodes...")

        with self.driver.session() as session:
            # Admin level 1 (provinces/states)
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin1Code <> ''
                WITH DISTINCT p.countryCode AS country, p.admin1Code AS code
                MERGE (a:AdminDivision {code: code, countryCode: country, level: 1})
                RETURN count(a) AS count
            """)
            admin1_count = result.single()['count']
            print(f"✓ Created {admin1_count:,} Admin Level 1 divisions")

            # Admin level 2 (counties/municipalities)
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin2Code <> ''
                WITH DISTINCT p.countryCode AS country, p.admin2Code AS code
                MERGE (a:AdminDivision {code: code, countryCode: country, level: 2})
                RETURN count(a) AS count
            """)
            admin2_count = result.single()['count']
            print(f"✓ Created {admin2_count:,} Admin Level 2 divisions")

    def create_admin_relationships(self):
        """Create relationships between places and admin divisions."""
        print("\nCreating administrative relationships...")

        with self.driver.session() as session:
            # Link places to admin1
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin1Code <> ''
                MATCH (a:AdminDivision {code: p.admin1Code, countryCode: p.countryCode, level: 1})
                MERGE (p)-[:LOCATED_IN_ADMIN1]->(a)
                RETURN count(p) AS count
            """)
            admin1_links = result.single()['count']
            print(f"✓ Created {admin1_links:,} LOCATED_IN_ADMIN1 relationships")

            # Link places to admin2
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin2Code <> ''
                MATCH (a:AdminDivision {code: p.admin2Code, countryCode: p.countryCode, level: 2})
                MERGE (p)-[:LOCATED_IN_ADMIN2]->(a)
                RETURN count(p) AS count
            """)
            admin2_links = result.single()['count']
            print(f"✓ Created {admin2_links:,} LOCATED_IN_ADMIN2 relationships")

    def print_statistics(self):
        """Print database statistics."""
        print("\n" + "="*60)
        print("DATABASE STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total places
            result = session.run("MATCH (p:Place) RETURN count(p) AS count")
            total_places = result.single()['count']
            print(f"Total Places: {total_places:,}")

            # Places by feature class
            result = session.run("""
                MATCH (p:Place)
                RETURN p.featureClass AS class, count(p) AS count
                ORDER BY count DESC
            """)
            print("\nPlaces by Feature Class:")
            for record in result:
                print(f"  {record['class']}: {record['count']:,}")

            # Places by country (top 10)
            result = session.run("""
                MATCH (p:Place)
                RETURN p.countryCode AS country, count(p) AS count
                ORDER BY count DESC
                LIMIT 10
            """)
            print("\nTop 10 Countries:")
            for record in result:
                print(f"  {record['country']}: {record['count']:,}")

            # Population statistics
            result = session.run("""
                MATCH (p:Place)
                WHERE p.population > 0
                RETURN count(p) AS count,
                       min(p.population) AS min_pop,
                       max(p.population) AS max_pop,
                       avg(p.population) AS avg_pop
            """)
            stats = result.single()
            print(f"\nPopulation Statistics:")
            print(f"  Places with population data: {stats['count']:,}")
            print(f"  Min: {stats['min_pop']:,}")
            print(f"  Max: {stats['max_pop']:,}")
            print(f"  Average: {int(stats['avg_pop']):,}")

            # Admin divisions
            result = session.run("MATCH (a:AdminDivision) RETURN count(a) AS count")
            admin_count = result.single()['count']
            print(f"\nAdministrative Divisions: {admin_count:,}")

            # Countries
            result = session.run("MATCH (c:Country) RETURN count(c) AS count")
            country_count = result.single()['count']
            print(f"Countries: {country_count:,}")

        print("="*60)


def main():
    """Main execution function."""
    # Configuration
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    CITIES500_FILE = os.path.join(DATA_DIR, 'cities500.txt')
    CA_FILE = os.path.join(DATA_DIR, 'CA', 'CA.txt')

    print("="*60)
    print("GeoNames LOD Knowledge Graph Loader")
    print("="*60)

    # Initialize loader
    loader = GeoNamesLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Setup schema
        loader.setup_schema()

        # Optional: Clear existing data (COMMENTED OUT FOR SAFETY)
        # loader.clear_database(confirm=True)

        # Load cities500 (global coverage)
        if os.path.exists(CITIES500_FILE):
            loader.load_geonames_file(CITIES500_FILE, "Global cities (pop > 500)")
        else:
            print(f"⚠ File not found: {CITIES500_FILE}")

        # Load Canadian data (comprehensive)
        if os.path.exists(CA_FILE):
            loader.load_geonames_file(CA_FILE, "Canadian geographic features")
        else:
            print(f"⚠ File not found: {CA_FILE}")

        # Create admin divisions and relationships
        loader.create_admin_divisions()
        loader.create_admin_relationships()

        # Print statistics
        loader.print_statistics()

        print("\n✓ GeoNames data loaded successfully!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        loader.close()


if __name__ == '__main__':
    main()
