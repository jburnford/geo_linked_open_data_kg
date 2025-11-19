#!/usr/bin/env python3
"""
Explore connections between Canada and Ceylon (Sri Lanka) between 1867-1946.

Historical context:
- 1867: Canadian Confederation
- 1815-1948: Ceylon under British colonial rule
- 1946: End of WWII, Ceylon independence approaching (1948)

This script searches for:
1. People born in one country who died/worked in the other
2. Organizations with presence in both countries
3. Migration patterns and biographical connections
4. Colonial administrative connections
"""

import os
from neo4j import GraphDatabase
from datetime import datetime
from dotenv import load_dotenv

# Load credentials
load_dotenv()

class CanadaCeylonExplorer:
    def __init__(self):
        uri = os.getenv('NEO4J_URI', 'bolt://206.12.90.118:7687')
        user = os.getenv('NEO4J_USER', 'neo4j')
        password = os.getenv('NEO4J_PASSWORD')
        database = os.getenv('NEO4J_DATABASE', 'canadaneo4j')

        if not password:
            print("ERROR: NEO4J_PASSWORD not set in environment")
            print("Please set credentials in .env file")
            raise ValueError("Missing credentials")

        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        """Execute a Cypher query and return results."""
        with self.driver.session(database=self.database) as session:
            result = session.run(query, params or {})
            return list(result)

    def check_ceylon_places(self):
        """Find Ceylon/Sri Lanka places in the database."""
        print("\n" + "="*80)
        print("CEYLON/SRI LANKA PLACES IN DATABASE")
        print("="*80)

        query = """
        MATCH (p:Place)
        WHERE p.countryCode = 'LK'  // Sri Lanka (Ceylon)
        RETURN p.name AS name, p.geonameId AS id, p.population AS pop,
               p.featureClass AS class, p.featureCode AS code
        ORDER BY p.population DESC
        LIMIT 20
        """

        results = self.run_query(query)
        print(f"\nFound {len(results)} top Ceylon/Sri Lanka places:")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r['name']} (pop: {r['pop']:,} | {r['class']}.{r['code']})")

        return results

    def check_canadian_places(self):
        """Sample Canadian places for context."""
        print("\n" + "="*80)
        print("CANADIAN PLACES IN DATABASE (Sample)")
        print("="*80)

        query = """
        MATCH (p:Place)
        WHERE p.countryCode = 'CA'
        RETURN p.name AS name, p.population AS pop
        ORDER BY p.population DESC
        LIMIT 10
        """

        results = self.run_query(query)
        print(f"\nTop 10 Canadian places by population:")
        for i, r in enumerate(results, 1):
            pop = r['pop'] if r['pop'] else 0
            print(f"  {i}. {r['name']} (pop: {pop:,})")

    def find_people_ceylon_to_canada(self):
        """Find people born in Ceylon who died/worked in Canada."""
        print("\n" + "="*80)
        print("PEOPLE: CEYLON → CANADA (1867-1946)")
        print("="*80)

        query = """
        MATCH (person:Person)
        MATCH (birthPlace:WikidataPlace)-[:SAME_AS|LOCATED_IN*0..2]->(ceylonPlace:Place {countryCode: 'LK'})
        MATCH (deathPlace:WikidataPlace)-[:SAME_AS|LOCATED_IN*0..2]->(canadaPlace:Place {countryCode: 'CA'})
        WHERE person.birthPlaceQid = birthPlace.qid
          AND person.deathPlaceQid = deathPlace.qid
          AND person.birthDate >= '1800-01-01'
          AND person.deathDate >= '1867-01-01'
          AND person.deathDate <= '1946-12-31'
        RETURN person.name AS name,
               person.wikidataQid AS qid,
               person.birthDate AS born,
               person.deathDate AS died,
               birthPlace.label AS birthPlace,
               deathPlace.label AS deathPlace,
               person.occupations AS occupations
        ORDER BY person.birthDate
        LIMIT 50
        """

        results = self.run_query(query)

        if results:
            print(f"\nFound {len(results)} people born in Ceylon, died in Canada:")
            for i, r in enumerate(results, 1):
                print(f"\n  {i}. {r['name']}")
                print(f"     Wikidata: https://www.wikidata.org/wiki/{r['qid']}")
                print(f"     Born: {r['born']} in {r['birthPlace']}")
                print(f"     Died: {r['died']} in {r['deathPlace']}")
                if r['occupations']:
                    print(f"     Occupations: {', '.join(r['occupations'][:5])}")
        else:
            print("\n  No direct matches found (may need broader search)")

        return results

    def find_people_canada_to_ceylon(self):
        """Find people born in Canada who died/worked in Ceylon."""
        print("\n" + "="*80)
        print("PEOPLE: CANADA → CEYLON (1867-1946)")
        print("="*80)

        query = """
        MATCH (person:Person)
        MATCH (birthPlace:WikidataPlace)-[:SAME_AS|LOCATED_IN*0..2]->(canadaPlace:Place {countryCode: 'CA'})
        MATCH (deathPlace:WikidataPlace)-[:SAME_AS|LOCATED_IN*0..2]->(ceylonPlace:Place {countryCode: 'LK'})
        WHERE person.birthPlaceQid = birthPlace.qid
          AND person.deathPlaceQid = deathPlace.qid
          AND person.birthDate >= '1800-01-01'
          AND person.deathDate >= '1867-01-01'
          AND person.deathDate <= '1946-12-31'
        RETURN person.name AS name,
               person.wikidataQid AS qid,
               person.birthDate AS born,
               person.deathDate AS died,
               birthPlace.label AS birthPlace,
               deathPlace.label AS deathPlace,
               person.occupations AS occupations
        ORDER BY person.birthDate
        LIMIT 50
        """

        results = self.run_query(query)

        if results:
            print(f"\nFound {len(results)} people born in Canada, died in Ceylon:")
            for i, r in enumerate(results, 1):
                print(f"\n  {i}. {r['name']}")
                print(f"     Wikidata: https://www.wikidata.org/wiki/{r['qid']}")
                print(f"     Born: {r['born']} in {r['birthPlace']}")
                print(f"     Died: {r['died']} in {r['deathPlace']}")
                if r['occupations']:
                    print(f"     Occupations: {', '.join(r['occupations'][:5])}")
        else:
            print("\n  No direct matches found (may need broader search)")

        return results

    def find_colonial_administrators(self):
        """Find British colonial administrators who worked in both regions."""
        print("\n" + "="*80)
        print("BRITISH COLONIAL ADMINISTRATORS (Both Regions)")
        print("="*80)

        query = """
        MATCH (person:Person)
        WHERE ANY(occ IN person.occupations WHERE
                  occ CONTAINS 'politician' OR
                  occ CONTAINS 'administrator' OR
                  occ CONTAINS 'governor' OR
                  occ CONTAINS 'civil servant' OR
                  occ CONTAINS 'military')
          AND person.birthDate >= '1800-01-01'
          AND person.birthDate <= '1900-12-31'
        OPTIONAL MATCH (person)-[:BORN_IN]->(birthPlace:WikidataPlace)
        OPTIONAL MATCH (person)-[:DIED_IN]->(deathPlace:WikidataPlace)
        RETURN person.name AS name,
               person.wikidataQid AS qid,
               person.birthDate AS born,
               person.occupations AS occupations,
               birthPlace.label AS birthPlace,
               deathPlace.label AS deathPlace
        LIMIT 100
        """

        results = self.run_query(query)

        print(f"\nFound {len(results)} potential colonial administrators (1800-1900):")
        print("(Filtering for Ceylon/Canada connections...)")

        # This is a broader search - would need position data to narrow down
        relevant = []
        for r in results:
            if r['birthPlace'] or r['deathPlace']:
                relevant.append(r)

        for i, r in enumerate(relevant[:20], 1):
            print(f"\n  {i}. {r['name']}")
            print(f"     Wikidata: https://www.wikidata.org/wiki/{r['qid']}")
            if r['occupations']:
                print(f"     Occupations: {', '.join(r['occupations'][:3])}")

        return results

    def find_organizations_both_countries(self):
        """Find organizations with presence in both Canada and Ceylon."""
        print("\n" + "="*80)
        print("ORGANIZATIONS WITH CANADA-CEYLON CONNECTIONS")
        print("="*80)

        query = """
        MATCH (org:Organization)
        WHERE org.foundingDate >= '1867-01-01'
          AND org.foundingDate <= '1946-12-31'
        OPTIONAL MATCH (org)-[:LOCATED_IN]->(location:WikidataPlace)
        RETURN org.name AS name,
               org.wikidataQid AS qid,
               org.foundingDate AS founded,
               org.dissolutionDate AS dissolved,
               collect(location.label) AS locations
        LIMIT 100
        """

        results = self.run_query(query)

        print(f"\nFound {len(results)} organizations (1867-1946):")
        print("(Would need location data to identify Canada-Ceylon connections)")

        for i, r in enumerate(results[:10], 1):
            print(f"\n  {i}. {r['name']}")
            print(f"     Wikidata: https://www.wikidata.org/wiki/{r['qid']}")
            print(f"     Founded: {r['founded']}")
            if r['locations']:
                print(f"     Locations: {', '.join(r['locations'][:5])}")

        return results

    def search_by_occupation(self, occupation):
        """Search for people by specific occupation."""
        print(f"\n" + "="*80)
        print(f"PEOPLE BY OCCUPATION: {occupation.upper()}")
        print("="*80)

        query = """
        MATCH (person:Person)
        WHERE ANY(occ IN person.occupations WHERE occ CONTAINS $occupation)
          AND person.birthDate >= '1800-01-01'
          AND person.deathDate <= '1950-12-31'
        OPTIONAL MATCH (birthPlace:WikidataPlace {qid: person.birthPlaceQid})
        OPTIONAL MATCH (deathPlace:WikidataPlace {qid: person.deathPlaceQid})
        RETURN person.name AS name,
               person.wikidataQid AS qid,
               person.birthDate AS born,
               person.deathDate AS died,
               birthPlace.label AS birthPlace,
               deathPlace.label AS deathPlace,
               person.occupations AS occupations
        LIMIT 50
        """

        results = self.run_query(query, {'occupation': occupation})

        print(f"\nFound {len(results)} people with occupation containing '{occupation}':")
        for i, r in enumerate(results[:20], 1):
            print(f"\n  {i}. {r['name']}")
            print(f"     Born: {r['born']} {f'in {r["birthPlace"]}' if r['birthPlace'] else ''}")
            print(f"     Died: {r['died']} {f'in {r["deathPlace"]}' if r['deathPlace'] else ''}")

        return results

    def database_stats(self):
        """Show database statistics."""
        print("\n" + "="*80)
        print("DATABASE STATISTICS")
        print("="*80)

        queries = {
            "Total Places": "MATCH (p:Place) RETURN count(p) AS count",
            "Canadian Places": "MATCH (p:Place {countryCode: 'CA'}) RETURN count(p) AS count",
            "Ceylon/Sri Lanka Places": "MATCH (p:Place {countryCode: 'LK'}) RETURN count(p) AS count",
            "Total People": "MATCH (p:Person) RETURN count(p) AS count",
            "People with birth dates": "MATCH (p:Person) WHERE p.birthDate IS NOT NULL RETURN count(p) AS count",
            "People 1867-1946": "MATCH (p:Person) WHERE p.birthDate >= '1867-01-01' AND p.deathDate <= '1946-12-31' RETURN count(p) AS count",
            "Total Organizations": "MATCH (o:Organization) RETURN count(o) AS count",
            "Total WikidataPlaces": "MATCH (w:WikidataPlace) RETURN count(w) AS count",
        }

        for label, query in queries.items():
            result = self.run_query(query)
            count = result[0]['count'] if result else 0
            print(f"  {label:.<40} {count:>12,}")


def main():
    print("\n" + "="*80)
    print("CANADA-CEYLON CONNECTIONS (1867-1946)")
    print("Exploring historical links during the British colonial period")
    print("="*80)

    explorer = CanadaCeylonExplorer()

    try:
        # 1. Database overview
        explorer.database_stats()

        # 2. Check what places we have
        explorer.check_ceylon_places()
        explorer.check_canadian_places()

        # 3. Search for people connections
        explorer.find_people_ceylon_to_canada()
        explorer.find_people_canada_to_ceylon()

        # 4. Colonial administrators
        explorer.find_colonial_administrators()

        # 5. Organizations
        explorer.find_organizations_both_countries()

        # 6. Specific occupation searches
        print("\n" + "="*80)
        print("OCCUPATION-BASED SEARCHES")
        print("="*80)
        print("\nSearching for key occupations that might connect the regions...")

        occupations = ['missionary', 'merchant', 'soldier', 'diplomat', 'tea']
        for occ in occupations:
            explorer.search_by_occupation(occ)

        print("\n" + "="*80)
        print("EXPLORATION COMPLETE")
        print("="*80)
        print("\nNext steps:")
        print("1. Refine searches based on results")
        print("2. Explore specific individuals in Wikidata")
        print("3. Add LINCS Historical Canadians data for deeper connections")
        print("4. Query for specific occupations or organizations")

    finally:
        explorer.close()


if __name__ == "__main__":
    main()
