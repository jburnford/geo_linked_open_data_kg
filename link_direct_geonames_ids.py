#!/usr/bin/env python3
"""
Create SAME_AS links between WikidataPlace and Place via direct geonamesId matching.

Fix: Converts WikidataPlace.geonamesId (STRING) to Place.geonameId (INTEGER).
"""

from neo4j import GraphDatabase
import time


class DirectIDLinker:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="historicalkg2025"):
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def count_linkable(self):
        """Count WikidataPlace nodes with geonamesId property."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                RETURN count(wp) as total
            """)
            return result.single()['total']

    def link_by_direct_id_match(self, batch_size=50000):
        """
        Create SAME_AS relationships via geonamesId match.

        Uses toInteger() to convert WikidataPlace.geonamesId (string)
        to match Place.geonameId (integer).
        """
        print("\n" + "="*60)
        print("DIRECT GEONAMES ID LINKING")
        print("="*60)

        total = self.count_linkable()
        print(f"\nWikidataPlace nodes with geonamesId: {total:,}")

        if total == 0:
            print("All nodes already linked!")
            return 0

        print(f"Creating SAME_AS links with type conversion...")
        print(f"Batch size: {batch_size:,}\n")

        start_time = time.time()

        with self.driver.session() as session:
            result = session.run(f"""
                CALL {{
                    MATCH (wp:WikidataPlace)
                    WHERE wp.geonamesId IS NOT NULL
                      AND NOT EXISTS((wp)-[:SAME_AS]->())
                    WITH wp LIMIT {batch_size}
                    MATCH (p:Place)
                    WHERE p.geonameId = toInteger(wp.geonamesId)
                    MERGE (wp)-[r:SAME_AS]->(p)
                    SET r.evidence = 'geonames_id_match',
                        r.confidence = 1.0,
                        r.distance_km = 0.0,
                        r.linkedDate = datetime()
                    RETURN count(r) as batch_count
                }} IN TRANSACTIONS OF {batch_size} ROWS
                RETURN sum(batch_count) as total_count
            """)

            count = result.single()['total_count']

        elapsed = time.time() - start_time

        print(f"\n✓ Created {count:,} SAME_AS relationships")
        print(f"  Time: {elapsed:.1f} seconds ({count/elapsed:.0f} links/sec)")
        print(f"  Coverage: {(count/total)*100:.1f}% of linkable nodes")

        return count

    def print_statistics(self):
        """Print linking statistics."""
        print("\n" + "="*60)
        print("LINKING STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total WikidataPlace nodes
            result = session.run("MATCH (wp:WikidataPlace) RETURN count(wp) as total")
            total_wp = result.single()['total']

            # Linked via SAME_AS
            result = session.run("""
                MATCH (wp:WikidataPlace)-[:SAME_AS]->()
                RETURN count(DISTINCT wp) as count
            """)
            same_as_count = result.single()['count']

            # Total SAME_AS relationships
            result = session.run("MATCH ()-[r:SAME_AS]->() RETURN count(r) as count")
            same_as_rels = result.single()['count']

            print(f"\nWikidataPlace nodes: {total_wp:,}")
            print(f"  With SAME_AS links: {same_as_count:,} ({(same_as_count/total_wp)*100:.1f}%)")
            print(f"  Unlinked: {total_wp - same_as_count:,}")

            print(f"\nSAME_AS relationships: {same_as_rels:,}")

            # Sample high-confidence links
            result = session.run("""
                MATCH (wp:WikidataPlace)-[r:SAME_AS]->(p:Place)
                RETURN wp.name AS wikidata_name,
                       p.name AS geonames_name,
                       wp.geonamesId AS wikidata_id,
                       p.geonameId AS geonames_id
                LIMIT 10
            """)

            print(f"\nSample SAME_AS Links:")
            for record in result:
                print(f"  {record['wikidata_name']} (GN:{record['wikidata_id']}) → {record['geonames_name']} (GN:{record['geonames_id']})")

        print("="*60)


def main():
    """Main execution."""
    print("="*60)
    print("Direct GeoNames ID Linker")
    print("="*60)

    linker = DirectIDLinker()

    try:
        # Create direct ID links
        linker.link_by_direct_id_match()

        # Print statistics
        linker.print_statistics()

        print("\n✓ Direct ID linking complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        linker.close()


if __name__ == '__main__':
    main()
