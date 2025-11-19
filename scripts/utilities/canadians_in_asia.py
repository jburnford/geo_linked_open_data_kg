#!/usr/bin/env python3
"""
Find Canadian people born or died in Asia before 1900.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

# Asian country codes
ASIA_COUNTRIES = [
    'CN', 'IN', 'JP', 'ID', 'TH', 'VN', 'PH', 'MM', 'MY', 'SG',
    'BD', 'PK', 'LK', 'KH', 'LA', 'NP', 'KR', 'TW', 'HK', 'MO',
    'AF', 'IR', 'IQ', 'SA', 'AE', 'TR', 'IL', 'JO', 'LB', 'SY',
    'KZ', 'UZ', 'TM', 'TJ', 'KG', 'MN', 'BT', 'MV', 'BN'
]

print("\n" + "="*80)
print("CANADIANS BORN OR DIED IN ASIA (Before 1900)")
print("="*80)

with driver.session(database='neo4j') as session:

    # 1. Canadians born in Asia
    print("\n" + "="*80)
    print("CANADIANS BORN IN ASIA")
    print("="*80)

    query = f"""
    MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place)
    WHERE birthPlace.countryCode IN {ASIA_COUNTRIES}
    OPTIONAL MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    RETURN person.name AS name,
           person.personId AS id,
           birthPlace.name AS birthPlace,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathPlace,
           deathPlace.countryCode AS deathCountry
    ORDER BY birthPlace.countryCode, person.name
    """

    result = session.run(query)
    born_in_asia = list(result)

    if born_in_asia:
        print(f"\nFound {len(born_in_asia)} people born in Asia:")

        by_country = {}
        for r in born_in_asia:
            country = r['birthCountry']
            if country not in by_country:
                by_country[country] = []
            by_country[country].append(r)

        for country, people in sorted(by_country.items()):
            country_names = {
                'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'LK': 'Sri Lanka/Ceylon',
                'HK': 'Hong Kong', 'MY': 'Malaysia', 'SG': 'Singapore', 'ID': 'Indonesia',
                'PH': 'Philippines', 'TH': 'Thailand', 'MM': 'Myanmar/Burma'
            }
            country_name = country_names.get(country, country)

            print(f"\n{country_name} ({country}) - {len(people)} people:")
            for i, p in enumerate(people, 1):
                print(f"  {i}. {p['name']}")
                print(f"     Born: {p['birthPlace']}, {country_name}")
                if p['deathPlace']:
                    print(f"     Died: {p['deathPlace']}, {p['deathCountry']}")
                print(f"     ID: {p['id']}")
    else:
        print("\n  No people born in Asia found")

    # 2. Canadians died in Asia
    print("\n" + "="*80)
    print("CANADIANS DIED IN ASIA")
    print("="*80)

    query = f"""
    MATCH (person:HistoricalPerson)-[:DIED_IN]->(deathPlace:Place)
    WHERE deathPlace.countryCode IN {ASIA_COUNTRIES}
    OPTIONAL MATCH (person)-[:BORN_IN]->(birthPlace:Place)
    RETURN person.name AS name,
           person.personId AS id,
           birthPlace.name AS birthPlace,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathPlace,
           deathPlace.countryCode AS deathCountry
    ORDER BY deathPlace.countryCode, person.name
    """

    result = session.run(query)
    died_in_asia = list(result)

    if died_in_asia:
        print(f"\nFound {len(died_in_asia)} people who died in Asia:")

        by_country = {}
        for r in died_in_asia:
            country = r['deathCountry']
            if country not in by_country:
                by_country[country] = []
            by_country[country].append(r)

        for country, people in sorted(by_country.items()):
            country_names = {
                'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'LK': 'Sri Lanka/Ceylon',
                'HK': 'Hong Kong', 'MY': 'Malaysia', 'SG': 'Singapore', 'ID': 'Indonesia',
                'PH': 'Philippines', 'TH': 'Thailand', 'MM': 'Myanmar/Burma'
            }
            country_name = country_names.get(country, country)

            print(f"\n{country_name} ({country}) - {len(people)} people:")
            for i, p in enumerate(people, 1):
                print(f"  {i}. {p['name']}")
                if p['birthPlace']:
                    print(f"     Born: {p['birthPlace']}, {p['birthCountry']}")
                print(f"     Died: {p['deathPlace']}, {country_name}")
                print(f"     ID: {p['id']}")
    else:
        print("\n  No people who died in Asia found")

    # 3. Asian migration patterns
    print("\n" + "="*80)
    print("CANADIAN-ASIAN MIGRATION PATTERNS")
    print("="*80)

    query = f"""
    MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place)
    MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    WHERE (birthPlace.countryCode IN {ASIA_COUNTRIES} AND deathPlace.countryCode = 'CA')
       OR (birthPlace.countryCode = 'CA' AND deathPlace.countryCode IN {ASIA_COUNTRIES})
    RETURN person.name AS name,
           birthPlace.name AS birthPlace,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathPlace,
           deathPlace.countryCode AS deathCountry
    ORDER BY birthPlace.countryCode
    """

    result = session.run(query)
    migrations = list(result)

    if migrations:
        print(f"\nFound {len(migrations)} people with Asia-Canada migration:")

        asia_to_canada = [m for m in migrations if m['deathCountry'] == 'CA']
        canada_to_asia = [m for m in migrations if m['birthCountry'] == 'CA']

        if asia_to_canada:
            print(f"\nAsia → Canada ({len(asia_to_canada)} people):")
            for i, m in enumerate(asia_to_canada, 1):
                print(f"  {i}. {m['name']}")
                print(f"     Born: {m['birthPlace']}, {m['birthCountry']}")
                print(f"     Died: {m['deathPlace']}, Canada")

        if canada_to_asia:
            print(f"\nCanada → Asia ({len(canada_to_asia)} people):")
            for i, m in enumerate(canada_to_asia, 1):
                print(f"  {i}. {m['name']}")
                print(f"     Born: {m['birthPlace']}, Canada")
                print(f"     Died: {m['deathPlace']}, {m['deathCountry']}")
    else:
        print("\n  No Asia-Canada migrations found")

    # 4. Check what Asian places exist
    print("\n" + "="*80)
    print("ASIAN PLACES IN DATABASE")
    print("="*80)

    query = f"""
    MATCH (p:Place)
    WHERE p.countryCode IN {ASIA_COUNTRIES}
    WITH p.countryCode AS country, count(*) AS count
    RETURN country, count
    ORDER BY count DESC
    """

    result = session.run(query)
    asian_places = list(result)

    if asian_places:
        print(f"\nAsian countries represented in database:")
        country_names = {
            'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'LK': 'Sri Lanka/Ceylon',
            'HK': 'Hong Kong', 'MY': 'Malaysia', 'SG': 'Singapore', 'ID': 'Indonesia',
            'PH': 'Philippines', 'TH': 'Thailand', 'MM': 'Myanmar/Burma', 'PK': 'Pakistan',
            'BD': 'Bangladesh', 'VN': 'Vietnam', 'KH': 'Cambodia', 'NP': 'Nepal',
            'KR': 'Korea', 'TW': 'Taiwan', 'MN': 'Mongolia', 'AF': 'Afghanistan',
            'IR': 'Iran', 'IQ': 'Iraq', 'TR': 'Turkey', 'SA': 'Saudi Arabia'
        }

        for r in asian_places:
            country_name = country_names.get(r['country'], r['country'])
            print(f"  {country_name} ({r['country']}): {r['count']:,} places")

    # 5. Sample queries for context
    print("\n" + "="*80)
    print("DATABASE CONTEXT")
    print("="*80)

    stats_queries = {
        "Total HistoricalPersons": "MATCH (p:HistoricalPerson) RETURN count(p)",
        "People with birth data": "MATCH (p:HistoricalPerson)-[:BORN_IN]->() RETURN count(DISTINCT p)",
        "People with death data": "MATCH (p:HistoricalPerson)-[:DIED_IN]->() RETURN count(DISTINCT p)",
        "People with both birth & death": """
            MATCH (p:HistoricalPerson)-[:BORN_IN]->()
            MATCH (p)-[:DIED_IN]->()
            RETURN count(DISTINCT p)
        """
    }

    for label, query in stats_queries.items():
        result = session.run(query)
        count = result.single()[0]
        print(f"  {label:.<45} {count:>10,}")

print("\n" + "="*80)
print("SEARCH COMPLETE")
print("="*80)

driver.close()
