#!/usr/bin/env python3
"""
Diagnose why Phase 1.1 (direct geonamesId linking) created 0 links.

Possible issues:
1. Property name mismatch (geonamesId vs geonameId)
2. Data type mismatch (string vs integer)
3. No matching Place nodes
"""

from neo4j import GraphDatabase
import os


def diagnose(uri=None, user=None, password=None):
    # Use environment variables if not provided
    uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = user or os.getenv('NEO4J_USER', 'neo4j')
    password = password or os.getenv('NEO4J_PASSWORD')
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            print("="*60)
            print("DIAGNOSING GEONAMES ID PROPERTY MISMATCH")
            print("="*60)

            # 1. Check WikidataPlace properties
            print("\n1. WikidataPlace geonamesId property:")
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                RETURN wp.geonamesId as id, wp.name, wp.qid
                LIMIT 5
            """)
            for record in result:
                print(f"   {record['name']} (Q{record['qid']}): geonamesId={record['id']} (type: {type(record['id']).__name__})")

            # 2. Check Place properties
            print("\n2. Place geonameId property:")
            result = session.run("""
                MATCH (p:Place)
                WHERE p.geonameId IS NOT NULL
                RETURN p.geonameId as id, p.name
                LIMIT 5
            """)
            for record in result:
                print(f"   {record['name']}: geonameId={record['id']} (type: {type(record['id']).__name__})")

            # 3. Try manual match with one example
            print("\n3. Testing manual match:")
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                WITH wp LIMIT 1
                OPTIONAL MATCH (p:Place {geonameId: wp.geonamesId})
                RETURN wp.name as wp_name, wp.geonamesId as wp_id, p.name as p_name
            """)
            record = result.single()
            print(f"   WikidataPlace: {record['wp_name']} (geonamesId={record['wp_id']})")
            print(f"   Matched Place: {record['p_name'] if record['p_name'] else 'NO MATCH'}")

            # 4. Try string conversion match
            print("\n4. Testing with string conversion:")
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                WITH wp LIMIT 1
                OPTIONAL MATCH (p:Place)
                WHERE toString(p.geonameId) = toString(wp.geonamesId)
                RETURN wp.name as wp_name, wp.geonamesId as wp_id, p.name as p_name
            """)
            record = result.single()
            print(f"   WikidataPlace: {record['wp_name']} (geonamesId={record['wp_id']})")
            print(f"   Matched Place: {record['p_name'] if record['p_name'] else 'NO MATCH'}")

            # 5. Check if ANY Place nodes have matching IDs
            print("\n5. Checking for ANY matching IDs:")
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                WITH collect(DISTINCT wp.geonamesId)[0..100] as wpIds
                MATCH (p:Place)
                WHERE p.geonameId IN wpIds
                RETURN count(p) as matches
            """)
            matches = result.single()['matches']
            print(f"   Matches in first 100 WikidataPlace geonamesIds: {matches}")

            print("\n" + "="*60)

    finally:
        driver.close()


if __name__ == "__main__":
    diagnose()
