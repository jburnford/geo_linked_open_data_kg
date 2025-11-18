#!/usr/bin/env python3
"""Check Neo4j database statistics after loading US data."""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("="*60)
print("NEO4J DATABASE STATISTICS")
print("="*60)

with driver.session() as session:
    # Total places
    result = session.run("MATCH (p:Place) RETURN count(p) AS count")
    total = result.single()['count']
    print(f"\nTotal Place nodes: {total:,}")

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

    # US breakdown by feature class
    result = session.run("""
        MATCH (p:Place)
        WHERE p.countryCode = 'US'
        RETURN p.featureClass AS class, count(p) AS count
        ORDER BY count DESC
    """)
    print("\nUS Places by Feature Class:")
    for record in result:
        print(f"  {record['class']}: {record['count']:,}")

    # US breakdown by specific feature codes (top 15)
    result = session.run("""
        MATCH (p:Place)
        WHERE p.countryCode = 'US'
        RETURN p.featureClass + '.' + p.featureCode AS code, count(p) AS count
        ORDER BY count DESC
        LIMIT 15
    """)
    print("\nUS Places by Feature Code (Top 15):")
    for record in result:
        print(f"  {record['code']}: {record['count']:,}")

    # Places with location points (spatial index ready)
    result = session.run("""
        MATCH (p:Place)
        WHERE p.location IS NOT NULL
        RETURN count(p) AS count
    """)
    with_location = result.single()['count']
    print(f"\nPlaces with spatial index: {with_location:,} ({with_location/total*100:.1f}%)")

    # Check for duplicates (should be 0)
    result = session.run("""
        MATCH (p:Place)
        WITH p.geonameId AS gid, count(p) AS cnt
        WHERE cnt > 1
        RETURN sum(cnt) AS duplicates
    """)
    duplicates = result.single()['duplicates']
    if duplicates:
        print(f"\n⚠️  WARNING: {duplicates} duplicate geonameIds found!")
    else:
        print(f"\n✓ No duplicates (geonameId is unique)")

print("="*60)

driver.close()
