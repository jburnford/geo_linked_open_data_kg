#!/usr/bin/env python3
"""
Analyze why some places appear unlinked in the visualization.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

print("\n" + "="*80)
print("ANALYZING UNLINKED PLACES IN VISUALIZATION")
print("="*80)

with driver.session(database='neo4j') as session:

    # Get all people with both birth and death locations
    print("\nQuerying database...")

    query = """
    MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place)
    MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    WHERE birthPlace.latitude IS NOT NULL
      AND birthPlace.longitude IS NOT NULL
      AND deathPlace.latitude IS NOT NULL
      AND deathPlace.longitude IS NOT NULL
    RETURN person.name AS name,
           birthPlace.name AS birthName,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathName,
           deathPlace.countryCode AS deathCountry
    """

    result = session.run(query)
    migrations = list(result)

    print(f"Total people with complete data: {len(migrations)}")

    # Analyze city-to-city flows
    city_flows = defaultdict(list)

    for m in migrations:
        flow_key = (m['birthName'], m['birthCountry'], m['deathName'], m['deathCountry'])
        city_flows[flow_key].append(m['name'])

    # Count how many unique routes each place participates in
    birth_place_routes = defaultdict(set)
    death_place_routes = defaultdict(set)

    for (birth_name, birth_country, death_name, death_country), people in city_flows.items():
        birth_key = (birth_name, birth_country)
        death_key = (death_name, death_country)

        birth_place_routes[birth_key].add((death_name, death_country))
        death_place_routes[death_key].add((birth_name, birth_country))

    # Find places with only 1 person
    single_person_births = {}
    single_person_deaths = {}

    for (birth_name, birth_country, death_name, death_country), people in city_flows.items():
        if len(people) == 1:
            birth_key = (birth_name, birth_country)
            death_key = (death_name, death_country)

            if birth_key not in single_person_births:
                single_person_births[birth_key] = []
            if death_key not in single_person_deaths:
                single_person_deaths[death_key] = []

            single_person_births[birth_key].append({
                'person': people[0],
                'to': f"{death_name}, {death_country}"
            })
            single_person_deaths[death_key].append({
                'person': people[0],
                'from': f"{birth_name}, {birth_country}"
            })

    # Count flows by size
    flow_sizes = defaultdict(int)
    for people in city_flows.values():
        flow_sizes[len(people)] += 1

    print("\n" + "="*80)
    print("FLOW SIZE DISTRIBUTION")
    print("="*80)
    print("\nNumber of people per route:")
    for size in sorted(flow_sizes.keys(), reverse=True)[:20]:
        print(f"  {size:3d} people: {flow_sizes[size]:4d} routes")

    # The visualization only shows flows with 2+ people
    threshold = 2
    flows_below_threshold = sum(count for size, count in flow_sizes.items() if size < threshold)
    flows_above_threshold = sum(count for size, count in flow_sizes.items() if size >= threshold)

    print(f"\nVisualization threshold: {threshold}+ people per route")
    print(f"  Routes shown (≥{threshold} people): {flows_above_threshold}")
    print(f"  Routes hidden (<{threshold} people): {flows_below_threshold}")

    # Find places that ONLY participate in single-person routes
    birth_places_unlinked = {}
    death_places_unlinked = {}

    for birth_key, routes in birth_place_routes.items():
        # Check if ALL routes from this birth place have only 1 person
        all_single = True
        for death_place in routes:
            flow_key = (birth_key[0], birth_key[1], death_place[0], death_place[1])
            if len(city_flows[flow_key]) >= threshold:
                all_single = False
                break

        if all_single:
            birth_places_unlinked[birth_key] = len(routes)

    for death_key, routes in death_place_routes.items():
        # Check if ALL routes to this death place have only 1 person
        all_single = True
        for birth_place in routes:
            flow_key = (birth_place[0], birth_place[1], death_key[0], death_key[1])
            if len(city_flows[flow_key]) >= threshold:
                all_single = False
                break

        if all_single:
            death_places_unlinked[death_key] = len(routes)

    print("\n" + "="*80)
    print("UNLINKED PLACES (All routes below threshold)")
    print("="*80)

    print(f"\nBirth places with NO visible lines: {len(birth_places_unlinked)}")
    print("  (All their outgoing routes have only 1 person)")

    print(f"\nDeath places with NO visible lines: {len(death_places_unlinked)}")
    print("  (All their incoming routes have only 1 person)")

    # Show examples
    print("\n" + "="*80)
    print("EXAMPLES OF UNLINKED BIRTH PLACES")
    print("="*80)

    sorted_births = sorted(birth_places_unlinked.items(), key=lambda x: x[1], reverse=True)

    for i, ((place_name, country), route_count) in enumerate(sorted_births[:10], 1):
        print(f"\n{i}. {place_name}, {country}")
        print(f"   {route_count} unique destinations (all single-person routes)")

        # Show where people from here went
        destinations = birth_place_routes[(place_name, country)]
        print(f"   People went to:")
        for dest_name, dest_country in list(destinations)[:3]:
            flow_key = (place_name, country, dest_name, dest_country)
            people = city_flows[flow_key]
            for person in people[:2]:
                print(f"     - {person} → {dest_name}, {dest_country}")

    print("\n" + "="*80)
    print("EXAMPLES OF UNLINKED DEATH PLACES")
    print("="*80)

    sorted_deaths = sorted(death_places_unlinked.items(), key=lambda x: x[1], reverse=True)

    for i, ((place_name, country), route_count) in enumerate(sorted_deaths[:10], 1):
        print(f"\n{i}. {place_name}, {country}")
        print(f"   {route_count} unique origins (all single-person routes)")

        # Show where people here came from
        origins = death_place_routes[(place_name, country)]
        print(f"   People came from:")
        for origin_name, origin_country in list(origins)[:3]:
            flow_key = (origin_name, origin_country, place_name, country)
            people = city_flows[flow_key]
            for person in people[:2]:
                print(f"     - {person} from {origin_name}, {origin_country}")

    # Check for same-place births and deaths
    print("\n" + "="*80)
    print("PEOPLE BORN AND DIED IN SAME PLACE")
    print("="*80)

    same_place_count = 0
    for m in migrations:
        if m['birthName'] == m['deathName'] and m['birthCountry'] == m['deathCountry']:
            same_place_count += 1

    print(f"\nPeople who died where they were born: {same_place_count}")
    print(f"  These have markers but no connecting line (0 distance)")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    print(f"""
Unlinked markers appear because:

1. THRESHOLD FILTERING ({flows_below_threshold} routes hidden)
   - Visualization only shows routes with 2+ people
   - Single-person migrations don't get lines drawn
   - This reduces visual clutter on the map

2. DISPERSED MIGRATION PATTERNS
   - {len(birth_places_unlinked)} birth places only have single-person routes
   - {len(death_places_unlinked)} death places only have single-person routes
   - These places have markers but no visible lines

3. SAME-PLACE BIRTHS/DEATHS ({same_place_count} people)
   - People who died where they were born
   - Markers overlap, no line drawn (0 distance)

Total routes in data: {len(city_flows)}
Routes shown on map (2+ people): {flows_above_threshold} ({flows_above_threshold/len(city_flows)*100:.1f}%)
Routes hidden (<2 people): {flows_below_threshold} ({flows_below_threshold/len(city_flows)*100:.1f}%)

Recommendation: The current 2-person threshold provides a good balance
between showing patterns and avoiding clutter. Most unlinked places
represent unique individual migrations rather than systematic patterns.
""")

driver.close()
