#!/usr/bin/env python3
"""
Add spatial indexes to the Neo4j database for optimal geographic query performance.

This script:
1. Creates a point property from latitude/longitude coordinates
2. Adds spatial indexes for fast distance queries
3. Adds supporting indexes for country-based filtering

Run this BEFORE scaling to global coverage.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


class SpatialIndexer:
    """Add spatial indexes to Neo4j for geographic queries."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def check_existing_indexes(self):
        """Check what indexes already exist."""
        print("\n" + "="*60)
        print("EXISTING INDEXES")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("SHOW INDEXES")
            indexes = list(result)

            if not indexes:
                print("No indexes found.")
            else:
                for idx in indexes:
                    print(f"  {idx['name']}: {idx['labelsOrTypes']} ON {idx['properties']}")
                    print(f"    Type: {idx['type']}, State: {idx['state']}")

        return indexes

    def create_spatial_index(self):
        """Create spatial point index on Place.location."""
        print("\n" + "="*60)
        print("CREATING SPATIAL INDEX")
        print("="*60)

        with self.driver.session() as session:
            # Check Neo4j version to use correct syntax
            version_result = session.run("CALL dbms.components() YIELD versions RETURN versions[0] AS version")
            version = version_result.single()['version']
            print(f"\nNeo4j version: {version}")

            # Create point index (Neo4j 4.0+ syntax)
            try:
                print("\n1. Creating POINT index on Place.location...")
                session.run("""
                    CREATE POINT INDEX place_location IF NOT EXISTS
                    FOR (p:Place) ON (p.location)
                """)
                print("   ✓ Spatial index created (or already exists)")
            except Exception as e:
                print(f"   ⚠ Could not create spatial index: {e}")
                print("   Note: Point indexes require Neo4j 4.3+")

    def create_supporting_indexes(self):
        """Create indexes to support country-based filtering."""
        print("\n2. Creating supporting indexes...")

        with self.driver.session() as session:
            # Country code index
            try:
                session.run("""
                    CREATE INDEX place_country IF NOT EXISTS
                    FOR (p:Place) ON (p.countryCode)
                """)
                print("   ✓ Country code index created")
            except Exception as e:
                print(f"   ⚠ Error creating country index: {e}")

            # Composite index for latitude (for bounding box queries)
            try:
                session.run("""
                    CREATE INDEX place_latitude IF NOT EXISTS
                    FOR (p:Place) ON (p.latitude)
                """)
                print("   ✓ Latitude index created")
            except Exception as e:
                print(f"   ⚠ Error creating latitude index: {e}")

            # Composite index for longitude (for bounding box queries)
            try:
                session.run("""
                    CREATE INDEX place_longitude IF NOT EXISTS
                    FOR (p:Place) ON (p.longitude)
                """)
                print("   ✓ Longitude index created")
            except Exception as e:
                print(f"   ⚠ Error creating longitude index: {e}")

    def count_places_needing_migration(self):
        """Count how many places need location point added."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.latitude IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND p.location IS NULL
                RETURN count(p) AS count
            """)
            return result.single()['count']

    def migrate_coordinates_to_points(self, batch_size: int = 10000):
        """Convert lat/lon properties to point geometry."""
        print("\n" + "="*60)
        print("MIGRATING COORDINATES TO POINT GEOMETRY")
        print("="*60)

        # Count places needing migration
        total = self.count_places_needing_migration()
        print(f"\nPlaces needing migration: {total:,}")

        if total == 0:
            print("✓ All places already have location points")
            return

        print(f"Processing in batches of {batch_size:,}...")

        with self.driver.session() as session:
            # Process in batches to avoid memory issues
            migrated = 0

            with tqdm(total=total, desc="Migrating to points") as pbar:
                while True:
                    result = session.run(f"""
                        MATCH (p:Place)
                        WHERE p.latitude IS NOT NULL
                          AND p.longitude IS NOT NULL
                          AND p.location IS NULL
                        WITH p LIMIT {batch_size}
                        SET p.location = point({{latitude: p.latitude, longitude: p.longitude}})
                        RETURN count(p) AS updated
                    """)

                    updated = result.single()['updated']
                    if updated == 0:
                        break

                    migrated += updated
                    pbar.update(updated)

        print(f"\n✓ Migrated {migrated:,} places to point geometry")

    def verify_spatial_queries(self):
        """Test that spatial queries work correctly."""
        print("\n" + "="*60)
        print("VERIFYING SPATIAL QUERY PERFORMANCE")
        print("="*60)

        with self.driver.session() as session:
            # Test query: Find places within 10km of Toronto
            toronto_lat, toronto_lon = 43.6532, -79.3832

            print("\nTest query: Places within 10km of Toronto...")
            print("(Using spatial index if available)")

            import time
            start = time.time()

            result = session.run("""
                MATCH (p:Place)
                WHERE p.location IS NOT NULL
                  AND point.distance(
                      p.location,
                      point({latitude: $lat, longitude: $lon})
                  ) <= 10000
                RETURN p.name AS name,
                       p.countryCode AS country,
                       point.distance(
                           p.location,
                           point({latitude: $lat, longitude: $lon})
                       ) / 1000.0 AS distance_km
                ORDER BY distance_km
                LIMIT 10
            """, lat=toronto_lat, lon=toronto_lon)

            places = list(result)
            elapsed = time.time() - start

            print(f"\nFound {len(places)} places in {elapsed:.3f} seconds")
            print("\nNearest places:")
            for place in places:
                print(f"  {place['name']} ({place['country']}): {place['distance_km']:.2f} km")

            # Performance assessment
            if elapsed < 0.1:
                print(f"\n✓ EXCELLENT performance ({elapsed*1000:.0f}ms) - spatial index is working!")
            elif elapsed < 0.5:
                print(f"\n✓ Good performance ({elapsed*1000:.0f}ms) - index may need time to warm up")
            elif elapsed < 2.0:
                print(f"\n⚠ Moderate performance ({elapsed:.2f}s) - index may still be building")
            else:
                print(f"\n⚠ Slow performance ({elapsed:.2f}s) - index may not be active yet")
                print("   Wait a few minutes and try again, or check SHOW INDEXES for state")

    def print_optimization_tips(self):
        """Print tips for optimized queries."""
        print("\n" + "="*60)
        print("QUERY OPTIMIZATION TIPS")
        print("="*60)

        print("""
For best performance, always:

1. Use point geometry with spatial index:
   MATCH (p:Place)
   WHERE point.distance(p.location, $search_point) <= 10000

2. Filter by country first to reduce search space:
   MATCH (p:Place)
   WHERE p.countryCode = 'CA'
     AND point.distance(p.location, $search_point) <= 10000

3. For bounding box queries (even faster):
   MATCH (p:Place)
   WHERE p.countryCode = 'CA'
     AND p.latitude >= $min_lat AND p.latitude <= $max_lat
     AND p.longitude >= $min_lon AND p.longitude <= $max_lon
     AND point.distance(p.location, $search_point) <= 10000

4. Create parametrized queries to benefit from query cache:
   // Good - uses parameters
   WHERE point.distance(p.location, point({latitude: $lat, longitude: $lon})) <= $radius

   // Bad - inline values prevent caching
   WHERE point.distance(p.location, point({latitude: 45.5, longitude: -73.5})) <= 10000
""")

    def print_statistics(self):
        """Print final statistics."""
        print("\n" + "="*60)
        print("DATABASE STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total places with location
            result = session.run("""
                MATCH (p:Place)
                WHERE p.location IS NOT NULL
                RETURN count(p) AS count
            """)
            with_location = result.single()['count']

            # Total places
            result = session.run("""
                MATCH (p:Place)
                RETURN count(p) AS count
            """)
            total = result.single()['count']

            # Places with coordinates but no location point
            result = session.run("""
                MATCH (p:Place)
                WHERE p.latitude IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND p.location IS NULL
                RETURN count(p) AS count
            """)
            missing = result.single()['count']

            print(f"\nTotal Place nodes: {total:,}")
            print(f"Places with location point: {with_location:,} ({with_location/total*100:.1f}%)")
            if missing > 0:
                print(f"⚠ Places missing location point: {missing:,}")
            else:
                print("✓ All places with coordinates have location points")


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    print("="*60)
    print("Neo4j Spatial Index Setup")
    print("="*60)
    print("\nThis will:")
    print("1. Create spatial point index on Place.location")
    print("2. Create supporting indexes (country, lat, lon)")
    print("3. Migrate lat/lon coordinates to point geometry")
    print("4. Verify spatial query performance")

    indexer = SpatialIndexer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Check existing indexes
        indexer.check_existing_indexes()

        # Create spatial index
        indexer.create_spatial_index()

        # Create supporting indexes
        indexer.create_supporting_indexes()

        # Migrate coordinates to point geometry
        indexer.migrate_coordinates_to_points(batch_size=10000)

        # Verify performance
        indexer.verify_spatial_queries()

        # Print optimization tips
        indexer.print_optimization_tips()

        # Print statistics
        indexer.print_statistics()

        print("\n" + "="*60)
        print("✓ Spatial indexing complete!")
        print("="*60)
        print("\nYour database is now optimized for:")
        print("  - Fast geographic distance queries")
        print("  - Global scale (10M+ nodes)")
        print("  - Country-based filtering")
        print("\nNext steps:")
        print("  1. Test NER reconciliation queries")
        print("  2. Add more countries incrementally")
        print("  3. Monitor query performance with PROFILE")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        indexer.close()


if __name__ == '__main__':
    main()
