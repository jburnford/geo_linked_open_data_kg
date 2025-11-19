#!/usr/bin/env python3
"""Inspect the actual database schema."""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

print("\n" + "="*80)
print("DATABASE SCHEMA INSPECTION")
print("="*80)

with driver.session(database='neo4j') as session:
    # Check node labels
    print("\nNODE LABELS:")
    result = session.run("CALL db.labels()")
    labels = [r['label'] for r in result]
    for label in sorted(labels):
        result = session.run(f"MATCH (n:{label}) RETURN count(n) AS count")
        count = result.single()['count']
        print(f"  {label}: {count:,}")

    # Check relationship types
    print("\nRELATIONSHIP TYPES:")
    result = session.run("CALL db.relationshipTypes()")
    rel_types = [r['relationshipType'] for r in result]
    for rel_type in sorted(rel_types)[:30]:
        result = session.run(f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS count LIMIT 1")
        rec = result.single()
        count = rec['count'] if rec else 0
        print(f"  {rel_type}: {count:,}")

    # Sample Person properties
    print("\nSAMPLE PERSON NODE:")
    result = session.run("MATCH (p:Person) RETURN properties(p) AS props LIMIT 1")
    rec = result.single()
    if rec:
        print(f"  Properties: {list(rec['props'].keys())}")
        print(f"  Sample: {rec['props']}")

    # Sample HistoricalPerson properties
    print("\nSAMPLE HISTORICALPERSON NODE:")
    result = session.run("MATCH (p:HistoricalPerson) RETURN properties(p) AS props LIMIT 1")
    rec = result.single()
    if rec:
        print(f"  Properties: {list(rec['props'].keys())}")
        print(f"  Sample: {rec['props']}")

driver.close()
