#!/usr/bin/env python3
"""
Add ADMIN3 links that were missed in the initial batch run.
Memory-safe, processes country-by-country in 10K batches.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


class Admin3Linker:
    """Add LOCATED_IN_ADMIN3 relationships."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 10000

    def close(self):
        self.driver.close()

    def get_countries_needing_admin3(self):
        """Get countries that have ADMIN3 divisions."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:AdminDivision)
                WHERE a.featureCode = 'ADM3'
                RETURN DISTINCT a.countryCode AS code
                ORDER BY code
            """)
            countries = [record['code'] for record in result]

        print(f"Found {len(countries)} countries with ADMIN3 divisions")
        return countries

    def link_places_to_admin3_for_country(self, country_code: str):
        """Link places to Admin3 divisions for one country."""

        with self.driver.session() as session:
            # Count places needing links
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = $country
                  AND p.admin3Code IS NOT NULL
                  AND p.admin2Code IS NOT NULL
                  AND p.admin1Code IS NOT NULL
                  AND p.featureClass <> 'A'
                  AND NOT EXISTS((p)-[:LOCATED_IN_ADMIN3]->())
                RETURN count(p) AS total
            """, country=country_code)

            total = result.single()['total']

            if total == 0:
                return 0

            # Process in batches
            linked = 0
            for skip in range(0, total, self.batch_size):
                result = session.run("""
                    MATCH (p:Place)
                    WHERE p.countryCode = $country
                      AND p.admin3Code IS NOT NULL
                      AND p.admin2Code IS NOT NULL
                      AND p.admin1Code IS NOT NULL
                      AND p.featureClass <> 'A'
                      AND NOT EXISTS((p)-[:LOCATED_IN_ADMIN3]->())
                    WITH p
                    SKIP $skip LIMIT $limit

                    MATCH (a:AdminDivision)
                    WHERE a.featureCode = 'ADM3'
                      AND a.countryCode = p.countryCode
                      AND a.admin1Code = p.admin1Code
                      AND a.admin2Code = p.admin2Code
                      AND a.admin3Code = p.admin3Code

                    MERGE (p)-[:LOCATED_IN_ADMIN3]->(a)
                    RETURN count(*) AS batch_linked
                """, country=country_code, skip=skip, limit=self.batch_size)

                batch_linked = result.single()['batch_linked']
                linked += batch_linked

            return linked

    def link_admin4_to_admin3(self):
        """Link ADMIN4 divisions to ADMIN3 (parent hierarchies)."""
        print("\nLinking Admin4 -> Admin3...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (a4:AdminDivision)
                WHERE a4.featureCode = 'ADM4'
                  AND a4.admin3Code IS NOT NULL
                  AND a4.admin2Code IS NOT NULL
                  AND a4.admin1Code IS NOT NULL
                  AND NOT EXISTS((a4)-[:PART_OF]->(:AdminDivision {featureCode: 'ADM3'}))

                MATCH (a3:AdminDivision)
                WHERE a3.featureCode = 'ADM3'
                  AND a3.countryCode = a4.countryCode
                  AND a3.admin1Code = a4.admin1Code
                  AND a3.admin2Code = a4.admin2Code
                  AND a3.admin3Code = a4.admin3Code

                MERGE (a4)-[:PART_OF]->(a3)
                RETURN count(*) AS linked
            """)

            linked = result.single()['linked']
            print(f"✓ Created {linked:,} Admin4 -> Admin3 relationships")

    def run(self):
        """Execute ADMIN3 linking."""
        print("="*60)
        print("ADDING ADMIN3 LINKS")
        print("="*60)

        # Get countries with ADMIN3 divisions
        countries = self.get_countries_needing_admin3()

        # Process each country
        print(f"\nProcessing {len(countries)} countries...")
        total_links = 0

        for country in tqdm(countries, desc="Countries"):
            links_created = self.link_places_to_admin3_for_country(country)
            total_links += links_created

            if links_created > 0:
                tqdm.write(f"  {country}: {links_created:,} ADMIN3 links")

        print(f"\n✓ Created {total_links:,} LOCATED_IN_ADMIN3 relationships")

        # Link ADMIN4 -> ADMIN3
        self.link_admin4_to_admin3()

        # Print summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("MATCH ()-[r:LOCATED_IN_ADMIN3]->() RETURN count(r) AS count")
            admin3_total = result.single()['count']
            print(f"Total LOCATED_IN_ADMIN3 relationships: {admin3_total:,}")

            result = session.run("MATCH (p:Place) RETURN count(p) AS count")
            place_total = result.single()['count']
            print(f"Coverage: {admin3_total/place_total*100:.1f}%")

        print("="*60)


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    linker = Admin3Linker(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        linker.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress is saved.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
    finally:
        linker.close()


if __name__ == '__main__':
    main()
