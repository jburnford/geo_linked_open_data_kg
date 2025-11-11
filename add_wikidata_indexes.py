#!/usr/bin/env python3
"""
Add critical indexes to WikidataPlace nodes for spatial linking performance.

Indexes needed:
1. countryQid - for country-based filtering and aggregation
2. latitude - for spatial bounding box queries
3. longitude - for spatial bounding box queries
4. geonamesId - for direct ID matching
"""

from neo4j import GraphDatabase
import time


class WikidataIndexer:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="historicalkg2025"):
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_indexes(self):
        """Create all necessary indexes for WikidataPlace."""
        indexes = [
            ("countryQid", "Index on countryQid for country filtering"),
            ("latitude", "Index on latitude for spatial bounding box"),
            ("longitude", "Index on longitude for spatial bounding box"),
            ("geonamesId", "Index on geonamesId for direct ID matching"),
        ]

        print("\n" + "="*60)
        print("CREATING WIKIDATA INDEXES")
        print("="*60)

        with self.driver.session() as session:
            for prop, description in indexes:
                print(f"\n{description}...")

                try:
                    # Create index
                    session.run(f"""
                        CREATE INDEX wikidata_{prop}_idx IF NOT EXISTS
                        FOR (wp:WikidataPlace)
                        ON (wp.{prop})
                    """)
                    print(f"  ✓ Index created: wikidata_{prop}_idx")

                except Exception as e:
                    if "already exists" in str(e).lower() or "equivalent index" in str(e).lower():
                        print(f"  ✓ Index already exists: wikidata_{prop}_idx")
                    else:
                        print(f"  ✗ Error creating index: {e}")

        print("\n" + "="*60)
        print("Waiting for indexes to come online...")
        print("="*60)

        time.sleep(5)

        # Show all WikidataPlace indexes
        with self.driver.session() as session:
            result = session.run("""
                SHOW INDEXES
                WHERE labelsOrTypes = ['WikidataPlace']
            """)

            print("\nWikidataPlace Indexes:")
            for record in result:
                print(f"  - {record['name']}: {record['labelsOrTypes']} ON {record['properties']}")

    def show_statistics(self):
        """Show statistics for indexed properties."""
        print("\n" + "="*60)
        print("PROPERTY STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total nodes
            result = session.run("MATCH (wp:WikidataPlace) RETURN count(wp) as total")
            total = result.single()['total']
            print(f"\nTotal WikidataPlace nodes: {total:,}")

            # Properties with values
            properties = ['countryQid', 'latitude', 'longitude', 'geonamesId']

            for prop in properties:
                result = session.run(f"""
                    MATCH (wp:WikidataPlace)
                    WHERE wp.{prop} IS NOT NULL
                    RETURN count(wp) as count
                """)
                count = result.single()['count']
                pct = (count / total * 100) if total > 0 else 0
                print(f"  {prop}: {count:,} ({pct:.1f}%)")

            # Already linked
            result = session.run("""
                MATCH (wp:WikidataPlace)
                OPTIONAL MATCH (linked:WikidataPlace)-[:SAME_AS]->()
                RETURN count(DISTINCT linked) as linked
            """)
            linked = result.single()['linked']
            pct = (linked / total * 100) if total > 0 else 0
            print(f"  Already linked (SAME_AS): {linked:,} ({pct:.1f}%)")


def main():
    """Main execution."""
    print("="*60)
    print("WikidataPlace Index Creator")
    print("="*60)

    indexer = WikidataIndexer()

    try:
        # Show current statistics
        indexer.show_statistics()

        # Create indexes
        indexer.create_indexes()

        print("\n✓ Index creation complete!")
        print("\nNote: Large indexes may take several minutes to fully populate.")
        print("Check SHOW INDEXES to verify they are ONLINE before running spatial linking.")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        indexer.close()


if __name__ == '__main__':
    main()
