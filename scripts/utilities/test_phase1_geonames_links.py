#!/usr/bin/env python3
"""
Quick test of Phase 1.1: Direct geonamesId linking.

This tests the fast ID-based matching before running the full 8-hour job.
"""

import os
from neo4j import GraphDatabase


def test_phase1(uri=None, user=None, password=None):
    """Test Phase 1.1 direct geonamesId links."""
    # Use environment variables if not provided
    uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = user or os.getenv('NEO4J_USER', 'neo4j')
    password = password or os.getenv('NEO4J_PASSWORD')

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # 1. Check current state
            print("="*60)
            print("CURRENT DATABASE STATE")
            print("="*60)

            result = session.run("""
                MATCH ()-[r]->()
                WITH type(r) as relType, count(r) as count
                RETURN relType, count
                ORDER BY count DESC
                LIMIT 10
            """)

            print("\nTop 10 Relationship Types:")
            for record in result:
                print(f"  {record['relType']}: {record['count']:,}")

            # 2. Count linkable WikidataPlace nodes
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                RETURN count(wp) as total
            """)
            linkable = result.single()['total']

            print(f"\nWikidataPlace nodes with geonamesId: {linkable:,}")
            print(f"Ready for Phase 1.1 direct linking")

            # 3. Show sample that could be linked
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                WITH wp LIMIT 5
                MATCH (p:Place {geonameId: wp.geonamesId})
                RETURN wp.qid, wp.name, wp.geonamesId, p.name
            """)

            print("\nSample Linkable Entities:")
            for record in result:
                print(f"  {record['wp.name']} (Q{record['wp.qid']}) → {record['p.name']} (GN:{record['wp.geonamesId']})")

            print("\n" + "="*60)
            print("Ready to run Phase 1.1!")
            print("="*60)

    finally:
        driver.close()


if __name__ == "__main__":
    test_phase1()
