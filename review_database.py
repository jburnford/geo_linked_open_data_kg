#!/usr/bin/env python3
"""Review complete database state after admin hierarchy creation."""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
    auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
)

print("="*60)
print("NEO4J DATABASE CURRENT STATE")
print("="*60)

with driver.session() as session:
    # Node counts
    print("\nNODE COUNTS:")
    result = session.run("MATCH (p:Place) RETURN count(p) AS count")
    place_count = result.single()['count']
    print(f"  Place nodes: {place_count:,}")

    result = session.run("MATCH (a:AdminDivision) RETURN count(a) AS count")
    admin_count = result.single()['count']
    print(f"  AdminDivision nodes: {admin_count:,}")

    result = session.run("MATCH (c:Country) RETURN count(c) AS count")
    country_count = result.single()['count']
    print(f"  Country nodes: {country_count:,}")

    print(f"\n  Total nodes: {place_count + admin_count + country_count:,}")

    # AdminDivision breakdown
    if admin_count > 0:
        print("\n  AdminDivision by level:")
        result = session.run("""
            MATCH (a:AdminDivision)
            RETURN a.featureCode AS level, count(a) AS count
            ORDER BY level
        """)
        for record in result:
            print(f"    {record['level']}: {record['count']:,}")

    # Relationship counts
    print("\nRELATIONSHIP COUNTS:")
    result = session.run("MATCH ()-[r:LOCATED_IN_COUNTRY]->() RETURN count(r) AS count")
    country_rels = result.single()['count']
    print(f"  LOCATED_IN_COUNTRY: {country_rels:,}")

    result = session.run("MATCH ()-[r:LOCATED_IN_ADMIN1]->() RETURN count(r) AS count")
    admin1_count = result.single()['count']
    print(f"  LOCATED_IN_ADMIN1: {admin1_count:,}")

    result = session.run("MATCH ()-[r:LOCATED_IN_ADMIN2]->() RETURN count(r) AS count")
    admin2_count = result.single()['count']
    print(f"  LOCATED_IN_ADMIN2: {admin2_count:,}")

    result = session.run("MATCH ()-[r:LOCATED_IN_ADMIN3]->() RETURN count(r) AS count")
    admin3_count = result.single()['count']
    print(f"  LOCATED_IN_ADMIN3: {admin3_count:,}")

    result = session.run("MATCH ()-[r:PART_OF]->() RETURN count(r) AS count")
    part_of_count = result.single()['count']
    print(f"  PART_OF (admin hierarchies): {part_of_count:,}")

    total_rels = country_rels + admin1_count + admin2_count + admin3_count + part_of_count
    print(f"\n  Total relationships: {total_rels:,}")

    # Coverage statistics
    print("\nCOVERAGE STATISTICS:")
    print(f"  Places with Admin1 link: {admin1_count:,} ({admin1_count/place_count*100:.1f}%)")
    print(f"  Places with Admin2 link: {admin2_count:,} ({admin2_count/place_count*100:.1f}%)")
    print(f"  Places with Admin3 link: {admin3_count:,} ({admin3_count/place_count*100:.1f}%)")

    # Check indexes
    print("\nINDEXES:")
    result = session.run("SHOW INDEXES")
    indexes = list(result)
    print(f"  Total indexes: {len(indexes)}")

    for record in indexes:
        index_name = record.get('name', 'unknown')
        index_type = record.get('type', 'unknown')
        labels = record.get('labelsOrTypes', [])
        properties = record.get('properties', [])
        state = record.get('state', 'unknown')

        if state == 'ONLINE':
            status_symbol = '✓'
        elif state == 'POPULATING':
            status_symbol = '⏳'
        else:
            status_symbol = '✗'

        if labels and properties:
            label_str = labels[0] if labels else 'unknown'
            prop_str = ', '.join(properties) if properties else 'unknown'
            print(f"  {status_symbol} {label_str}.{prop_str} ({index_type})")

    # Sample hierarchies
    print("\nSAMPLE HIERARCHIES (Top 10 cities):")
    result = session.run("""
        MATCH (p:Place)
        WHERE p.population > 0 AND p.featureCode STARTS WITH 'PPL'
        OPTIONAL MATCH path = (p)-[:LOCATED_IN_ADMIN1|PART_OF*1..3]->(c:Country)
        WITH p, [n in nodes(path)[1..-1] | coalesce(n.name, n.code)] AS hierarchy
        RETURN p.name AS city,
               p.countryCode AS country,
               p.population AS pop,
               hierarchy
        ORDER BY p.population DESC
        LIMIT 10
    """)
    for record in result:
        hierarchy_str = " -> ".join([str(h) for h in record['hierarchy']]) if record['hierarchy'] else "No hierarchy"
        print(f"  {record['city']}, {record['country']} (pop: {record['pop']:,})")
        print(f"    └─ {hierarchy_str}")

    # Database size estimate
    print("\nDATABASE METRICS:")
    result = session.run("""
        CALL apoc.meta.stats()
        YIELD nodeCount, relCount, labelCount, relTypeCount
        RETURN nodeCount, relCount, labelCount, relTypeCount
    """)
    try:
        stats = result.single()
        if stats:
            print(f"  Total nodes: {stats['nodeCount']:,}")
            print(f"  Total relationships: {stats['relCount']:,}")
            print(f"  Node labels: {stats['labelCount']}")
            print(f"  Relationship types: {stats['relTypeCount']}")
    except:
        print("  (apoc.meta.stats not available)")

print("="*60)

driver.close()
