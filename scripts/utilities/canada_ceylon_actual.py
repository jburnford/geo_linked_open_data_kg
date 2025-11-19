#!/usr/bin/env python3
"""
Find connections between Canada and Ceylon (Sri Lanka) 1867-1946.
Uses the actual database schema with Place and HistoricalPerson nodes.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

print("\n" + "="*80)
print("CANADA-CEYLON CONNECTIONS (1867-1946)")
print("="*80)

with driver.session(database='neo4j') as session:

    # 1. Check Ceylon places
    print("\n" + "="*80)
    print("CEYLON/SRI LANKA PLACES")
    print("="*80)

    result = session.run("""
        MATCH (p:Place {countryCode: 'LK'})
        RETURN p.name AS name, p.geonameId AS id, p.population AS pop,
               p.latitude AS lat, p.longitude AS lon
        ORDER BY p.population DESC
        LIMIT 20
    """)

    ceylon_places = list(result)
    print(f"\nFound {len(ceylon_places)} top places in Ceylon/Sri Lanka:")
    for i, r in enumerate(ceylon_places, 1):
        pop = r['pop'] if r['pop'] else 0
        print(f"  {i}. {r['name']} (pop: {pop:,}, geonameId: {r['id']})")

    # 2. People born in Ceylon
    print("\n" + "="*80)
    print("PEOPLE BORN IN CEYLON (in our database)")
    print("="*80)

    result = session.run("""
        MATCH (person:HistoricalPerson)-[:BORN_IN]->(place:Place {countryCode: 'LK'})
        RETURN person.name AS name, person.personId AS id,
               place.name AS birthPlace
        LIMIT 50
    """)

    ceylon_born = list(result)
    if ceylon_born:
        print(f"\nFound {len(ceylon_born)} people born in Ceylon:")
        for i, r in enumerate(ceylon_born, 1):
            print(f"  {i}. {r['name']} (born in {r['birthPlace']})")
    else:
        print("\n  No people born in Ceylon found in database")

    # 3. People who died in Ceylon
    print("\n" + "="*80)
    print("PEOPLE WHO DIED IN CEYLON")
    print("="*80)

    result = session.run("""
        MATCH (person:HistoricalPerson)-[:DIED_IN]->(place:Place {countryCode: 'LK'})
        RETURN person.name AS name, person.personId AS id,
               place.name AS deathPlace
        LIMIT 50
    """)

    ceylon_died = list(result)
    if ceylon_died:
        print(f"\nFound {len(ceylon_died)} people who died in Ceylon:")
        for i, r in enumerate(ceylon_died, 1):
            print(f"  {i}. {r['name']} (died in {r['deathPlace']})")
    else:
        print("\n  No people who died in Ceylon found in database")

    # 4. Cross-connections: Ceylon birth → Canada death
    print("\n" + "="*80)
    print("CEYLON → CANADA MIGRATION")
    print("="*80)

    result = session.run("""
        MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place {countryCode: 'LK'})
        MATCH (person)-[:DIED_IN]->(deathPlace:Place {countryCode: 'CA'})
        RETURN person.name AS name,
               birthPlace.name AS birthPlace,
               deathPlace.name AS deathPlace,
               person.personId AS id
        LIMIT 50
    """)

    ceylon_to_canada = list(result)
    if ceylon_to_canada:
        print(f"\nFound {len(ceylon_to_canada)} people born in Ceylon, died in Canada:")
        for i, r in enumerate(ceylon_to_canada, 1):
            print(f"\n  {i}. {r['name']}")
            print(f"     Born: {r['birthPlace']}, Ceylon")
            print(f"     Died: {r['deathPlace']}, Canada")
            print(f"     ID: {r['id']}")
    else:
        print("\n  No Ceylon → Canada migrations found")

    # 5. Cross-connections: Canada birth → Ceylon death
    print("\n" + "="*80)
    print("CANADA → CEYLON MIGRATION")
    print("="*80)

    result = session.run("""
        MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place {countryCode: 'CA'})
        MATCH (person)-[:DIED_IN]->(deathPlace:Place {countryCode: 'LK'})
        RETURN person.name AS name,
               birthPlace.name AS birthPlace,
               deathPlace.name AS deathPlace,
               person.personId AS id
        LIMIT 50
    """)

    canada_to_ceylon = list(result)
    if canada_to_ceylon:
        print(f"\nFound {len(canada_to_ceylon)} people born in Canada, died in Ceylon:")
        for i, r in enumerate(canada_to_ceylon, 1):
            print(f"\n  {i}. {r['name']}")
            print(f"     Born: {r['birthPlace']}, Canada")
            print(f"     Died: {r['deathPlace']}, Ceylon")
            print(f"     ID: {r['id']}")
    else:
        print("\n  No Canada → Ceylon migrations found")

    # 6. Sample of Canadian HistoricalPersons
    print("\n" + "="*80)
    print("SAMPLE CANADIAN HISTORICAL PERSONS")
    print("="*80)

    result = session.run("""
        MATCH (person:HistoricalPerson)-[:BORN_IN]->(place:Place {countryCode: 'CA'})
        RETURN person.name AS name, place.name AS birthPlace
        LIMIT 20
    """)

    canadian_people = list(result)
    if canadian_people:
        print(f"\nSample of {len(canadian_people)} Canadians in database:")
        for i, r in enumerate(canadian_people, 1):
            print(f"  {i}. {r['name']} (born in {r['birthPlace']})")

    # 7. Database statistics
    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)

    stats = {
        "Ceylon/Sri Lanka places": "MATCH (p:Place {countryCode: 'LK'}) RETURN count(p)",
        "Canadian places": "MATCH (p:Place {countryCode: 'CA'}) RETURN count(p)",
        "Total HistoricalPersons": "MATCH (p:HistoricalPerson) RETURN count(p)",
        "People with birth locations": "MATCH (p:HistoricalPerson)-[:BORN_IN]->() RETURN count(p)",
        "People with death locations": "MATCH (p:HistoricalPerson)-[:DIED_IN]->() RETURN count(p)",
    }

    for label, query in stats.items():
        result = session.run(query)
        count = result.single()[0]
        print(f"  {label:.<45} {count:>10,}")

print("\n" + "="*80)
print("ANALYSIS COMPLETE")
print("="*80)

print("\nNEXT STEPS:")
print("1. The LINCS HistoricalPerson data (14K people) is loaded")
print("2. To find more connections, we need to:")
print("   - Load full Wikidata Person nodes (6M+ people)")
print("   - Load LINCS Historical Canadians (400K+ people)")
print("   - Add occupation and career data")
print("3. Current database has limited biographical connections")

driver.close()
