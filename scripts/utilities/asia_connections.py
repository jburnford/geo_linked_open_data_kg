#!/usr/bin/env python3
"""
Explore how Canadians with Asian connections relate to each other.
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
print("CONNECTIONS AMONG CANADIANS WITH ASIAN TIES")
print("="*80)

with driver.session(database='neo4j') as session:

    # First, get our Asia-connected people
    query = f"""
    MATCH (person:HistoricalPerson)
    WHERE EXISTS {{
        MATCH (person)-[:BORN_IN|DIED_IN]->(place:Place)
        WHERE place.countryCode IN {ASIA_COUNTRIES}
    }}
    RETURN person.name AS name, person.personId AS id
    ORDER BY person.name
    """

    result = session.run(query)
    asia_people = list(result)
    asia_ids = [p['id'] for p in asia_people]

    print(f"\nIdentified {len(asia_people)} people with Asian connections")

    # 1. Direct family relationships
    print("\n" + "="*80)
    print("FAMILY RELATIONSHIPS")
    print("="*80)

    query = f"""
    MATCH (p1:HistoricalPerson)-[:BORN_IN|DIED_IN]->(place1:Place)
    WHERE place1.countryCode IN {ASIA_COUNTRIES}
    MATCH (p1)-[r:SPOUSE_OF|PARENT_OF|CHILD_OF]-(p2:HistoricalPerson)
    MATCH (p2)-[:BORN_IN|DIED_IN]->(place2:Place)
    WHERE place2.countryCode IN {ASIA_COUNTRIES}
    RETURN p1.name AS person1,
           type(r) AS relationship,
           p2.name AS person2,
           p1.personId AS id1,
           p2.personId AS id2
    """

    result = session.run(query)
    family_links = list(result)

    if family_links:
        print(f"\nFound {len(family_links)} family connections:")
        for link in family_links:
            print(f"\n  {link['person1']}")
            print(f"    {link['relationship']} → {link['person2']}")
    else:
        print("\n  No direct family relationships found among Asia-connected people")

    # 2. Shared birthplaces
    print("\n" + "="*80)
    print("SHARED BIRTHPLACES IN ASIA")
    print("="*80)

    query = f"""
    MATCH (p1:HistoricalPerson)-[:BORN_IN]->(place:Place)
    WHERE place.countryCode IN {ASIA_COUNTRIES}
    MATCH (p2:HistoricalPerson)-[:BORN_IN]->(place)
    WHERE p1.personId < p2.personId
    RETURN place.name AS birthPlace,
           place.countryCode AS country,
           collect(p1.name) + collect(p2.name) AS people,
           count(*) AS connections
    ORDER BY connections DESC, birthPlace
    """

    result = session.run(query)
    shared_births = list(result)

    if shared_births:
        print(f"\nFound {len(shared_births)} places with multiple births:")
        for place in shared_births:
            country_names = {
                'CN': 'China', 'IN': 'India', 'JP': 'Japan'
            }
            country = country_names.get(place['country'], place['country'])
            print(f"\n  {place['birthPlace']}, {country}:")
            # Get unique people
            people_set = set(place['people'])
            for person in sorted(people_set):
                print(f"    - {person}")
    else:
        print("\n  No shared birthplaces found")

    # 3. Shared death places
    print("\n" + "="*80)
    print("SHARED DEATH PLACES IN ASIA")
    print("="*80)

    query = f"""
    MATCH (p1:HistoricalPerson)-[:DIED_IN]->(place:Place)
    WHERE place.countryCode IN {ASIA_COUNTRIES}
    MATCH (p2:HistoricalPerson)-[:DIED_IN]->(place)
    WHERE p1.personId < p2.personId
    RETURN place.name AS deathPlace,
           place.countryCode AS country,
           collect({{name: p1.name, id: p1.personId}}) + collect({{name: p2.name, id: p2.personId}}) AS people
    ORDER BY deathPlace
    """

    result = session.run(query)
    shared_deaths = list(result)

    if shared_deaths:
        print(f"\nFound {len(shared_deaths)} places where multiple people died:")
        for place in shared_deaths:
            country_names = {
                'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'TW': 'Taiwan'
            }
            country = country_names.get(place['country'], place['country'])
            print(f"\n  {place['deathPlace']}, {country}:")
            # Get unique people
            people_dict = {p['id']: p['name'] for p in place['people']}
            for person_id, person_name in sorted(people_dict.items(), key=lambda x: x[1]):
                print(f"    - {person_name}")
    else:
        print("\n  No shared death places found")

    # 4. Same birthplace and death place combinations
    print("\n" + "="*80)
    print("SHARED ASIAN CITIES (Both Birth and Death)")
    print("="*80)

    query = f"""
    MATCH (place:Place)
    WHERE place.countryCode IN {ASIA_COUNTRIES}
    MATCH (p1:HistoricalPerson)-[:BORN_IN]->(place)
    WITH place, collect(DISTINCT p1.name) AS born_here
    MATCH (p2:HistoricalPerson)-[:DIED_IN]->(place)
    WITH place, born_here, collect(DISTINCT p2.name) AS died_here
    WHERE size(born_here) > 0 AND size(died_here) > 0
    RETURN place.name AS placeName,
           place.countryCode AS country,
           born_here,
           died_here
    ORDER BY size(born_here) + size(died_here) DESC
    LIMIT 10
    """

    result = session.run(query)
    hub_cities = list(result)

    if hub_cities:
        print(f"\nAsian cities as biographical hubs:")
        for city in hub_cities:
            country_names = {
                'CN': 'China', 'IN': 'India', 'JP': 'Japan'
            }
            country = country_names.get(city['country'], city['country'])
            print(f"\n  {city['placeName']}, {country}:")
            if city['born_here']:
                print(f"    Born here ({len(city['born_here'])}):")
                for person in sorted(city['born_here'])[:5]:
                    print(f"      - {person}")
            if city['died_here']:
                print(f"    Died here ({len(city['died_here'])}):")
                for person in sorted(city['died_here'])[:5]:
                    print(f"      - {person}")
    else:
        print("\n  No hub cities found")

    # 5. Colonial India connections - people connected through British India
    print("\n" + "="*80)
    print("BRITISH INDIA NETWORK")
    print("="*80)

    query = """
    MATCH (person:HistoricalPerson)
    WHERE EXISTS {
        MATCH (person)-[:BORN_IN|DIED_IN]->(place:Place {countryCode: 'IN'})
    }
    OPTIONAL MATCH (person)-[:BORN_IN]->(birthPlace:Place)
    OPTIONAL MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    RETURN person.name AS name,
           birthPlace.name AS birthPlace,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathPlace,
           deathPlace.countryCode AS deathCountry
    ORDER BY birthPlace.countryCode, name
    """

    result = session.run(query)
    india_people = list(result)

    if india_people:
        print(f"\nBritish India network ({len(india_people)} people):")

        # Group by pattern
        born_in_india = [p for p in india_people if p['birthCountry'] == 'IN']
        died_in_india = [p for p in india_people if p['deathCountry'] == 'IN']

        print(f"\n  Born in India ({len(born_in_india)} people):")
        for p in born_in_india[:10]:
            dest = f"→ {p['deathPlace']}, {p['deathCountry']}" if p['deathPlace'] else ""
            print(f"    - {p['name']} (from {p['birthPlace']}) {dest}")

        print(f"\n  Died in India ({len(died_in_india)} people):")
        for p in died_in_india[:10]:
            origin = f"{p['birthPlace']}, {p['birthCountry']} →" if p['birthPlace'] else ""
            print(f"    - {p['name']} {origin} {p['deathPlace']}")

    # 6. Chinese-Canadian network
    print("\n" + "="*80)
    print("CHINESE-CANADIAN NETWORK")
    print("="*80)

    query = """
    MATCH (person:HistoricalPerson)
    WHERE EXISTS {
        MATCH (person)-[:BORN_IN|DIED_IN]->(place:Place {countryCode: 'CN'})
    }
    OPTIONAL MATCH (person)-[:BORN_IN]->(birthPlace:Place)
    OPTIONAL MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    RETURN person.name AS name,
           birthPlace.name AS birthPlace,
           deathPlace.name AS deathPlace,
           deathPlace.countryCode AS deathCountry
    ORDER BY name
    """

    result = session.run(query)
    china_people = list(result)

    if china_people:
        print(f"\nChinese-Canadian network ({len(china_people)} people):")

        immigrants = [p for p in china_people if p['deathCountry'] == 'CA']

        if immigrants:
            print(f"\n  Chinese immigrants to Canada ({len(immigrants)} people):")
            # Group by destination
            by_dest = {}
            for p in immigrants:
                dest = p['deathPlace'] or 'Unknown'
                if dest not in by_dest:
                    by_dest[dest] = []
                by_dest[dest].append(p['name'])

            for dest, names in sorted(by_dest.items()):
                print(f"\n    → {dest}:")
                for name in sorted(names):
                    print(f"      - {name}")

    # 7. Any other relationship types?
    print("\n" + "="*80)
    print("RELATIONSHIP TYPES IN DATABASE")
    print("="*80)

    query = """
    CALL db.relationshipTypes() YIELD relationshipType
    RETURN relationshipType
    ORDER BY relationshipType
    """

    result = session.run(query)
    rel_types = [r['relationshipType'] for r in result]

    print("\nAll relationship types:")
    for rel in rel_types:
        print(f"  - {rel}")

print("\n" + "="*80)
print("ANALYSIS COMPLETE")
print("="*80)

driver.close()
