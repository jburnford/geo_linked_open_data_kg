#!/usr/bin/env python3
"""
Create administrative hierarchy relationships from GeoNames data.
ULTRA-ROBUST version with resume capability and multi-level chunking.

Strategy:
- Resume from where we left off (tracks completed countries)
- Three-tier chunking:
  * Small countries (<50K places): Normal batching
  * Mega countries (50-500K): Admin1 regional chunking
  * Ultra-mega (>500K): Admin2 district chunking
- Skip problematic countries and continue
- Save progress after each country
"""

import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm
import time

load_dotenv()

# State file to track progress
STATE_FILE = "/home/ubuntu/phase3_progress.json"


class AdminHierarchyBuilder:
    """Build administrative hierarchy relationships with robust error handling."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 10000  # Process 10K at a time
        self.state = self.load_state()

    def close(self):
        self.driver.close()

    def load_state(self):
        """Load progress state from disk."""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {"completed_countries": [], "failed_countries": []}

    def save_state(self):
        """Save progress state to disk."""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)

    def create_indexes(self):
        """Create indexes for fast admin code lookups."""
        print("\nCreating indexes for admin codes...")

        with self.driver.session() as session:
            # Index on admin codes for Places
            session.run("CREATE INDEX place_country_admin1 IF NOT EXISTS FOR (p:Place) ON (p.countryCode, p.admin1Code)")
            session.run("CREATE INDEX place_country_admin2 IF NOT EXISTS FOR (p:Place) ON (p.countryCode, p.admin2Code)")
            session.run("CREATE INDEX place_feature_code IF NOT EXISTS FOR (p:Place) ON (p.featureCode)")

            # Index on geonameId for AdminDivisions
            session.run("CREATE INDEX admin_geonameid IF NOT EXISTS FOR (a:AdminDivision) ON (a.geonameId)")
            session.run("CREATE INDEX admin_country_code IF NOT EXISTS FOR (a:AdminDivision) ON (a.countryCode, a.admin1Code)")
            session.run("CREATE INDEX admin_country_admin2 IF NOT EXISTS FOR (a:AdminDivision) ON (a.countryCode, a.admin2Code)")

            print("✓ Indexes created")
            time.sleep(2)  # Give Neo4j time to build indexes

    def get_country_list(self):
        """Get list of countries in database."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode IS NOT NULL
                RETURN DISTINCT p.countryCode AS code
                ORDER BY code
            """)
            countries = [record['code'] for record in result]

        print(f"Found {len(countries)} countries")

        # Filter out already completed
        completed = set(self.state.get("completed_countries", []))
        remaining = [c for c in countries if c not in completed]

        if completed:
            print(f"Already completed: {len(completed)} countries")
            print(f"Remaining: {len(remaining)} countries")

        return remaining

    def count_places_for_country(self, country_code: str):
        """Count total places for a country."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = $country
                  AND p.featureClass <> 'A'
                RETURN count(p) AS total
            """, country=country_code)
            return result.single()['total']

    def create_admin_divisions_for_country(self, country_code: str):
        """Create AdminDivision nodes for one country."""

        with self.driver.session() as session:
            # Count admin features for this country
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = $country
                  AND p.featureClass = 'A'
                  AND p.featureCode IN ['ADM1', 'ADM2', 'ADM3', 'ADM4', 'ADMD']
                RETURN count(p) AS total
            """, country=country_code)

            total = result.single()['total']

            if total == 0:
                return 0

            # Process in batches
            created = 0
            for skip in range(0, total, self.batch_size):
                result = session.run("""
                    MATCH (p:Place)
                    WHERE p.countryCode = $country
                      AND p.featureClass = 'A'
                      AND p.featureCode IN ['ADM1', 'ADM2', 'ADM3', 'ADM4', 'ADMD']
                    WITH p
                    SKIP $skip LIMIT $limit
                    MERGE (a:AdminDivision {geonameId: p.geonameId})
                    SET a.name = p.name,
                        a.countryCode = p.countryCode,
                        a.admin1Code = p.admin1Code,
                        a.admin2Code = p.admin2Code,
                        a.admin3Code = p.admin3Code,
                        a.admin4Code = p.admin4Code,
                        a.featureCode = p.featureCode,
                        a.latitude = p.latitude,
                        a.longitude = p.longitude,
                        a.location = p.location,
                        a.population = p.population
                    RETURN count(a) AS batch_created
                """, country=country_code, skip=skip, limit=self.batch_size)

                batch_created = result.single()['batch_created']
                created += batch_created

            return created

    def link_places_to_admin1_for_country(self, country_code: str):
        """Link places to Admin1 divisions for one country with adaptive chunking."""

        total = self.count_places_for_country(country_code)

        if total == 0:
            return 0

        # Adaptive strategy based on size
        if total > 500000:
            # Ultra-mega: chunk by admin2 (districts)
            print(f"    → Ultra-mega country ({total:,} places), using admin2 chunking")
            return self._link_ultra_mega_country_by_admin2(country_code)
        elif total > 50000:
            # Mega: chunk by admin1 (states/provinces)
            print(f"    → Mega country ({total:,} places), using admin1 chunking")
            return self._link_mega_country_by_admin1(country_code)
        else:
            # Normal: process all at once with batching
            print(f"    → Normal country ({total:,} places), standard batching")
            return self._link_normal_country(country_code, total)

    def _link_normal_country(self, country_code: str, total: int):
        """Process smaller countries with standard batching."""
        linked = 0

        with self.driver.session() as session:
            for skip in range(0, total, self.batch_size):
                result = session.run("""
                    MATCH (p:Place)
                    WHERE p.countryCode = $country
                      AND p.admin1Code IS NOT NULL
                      AND p.featureClass <> 'A'
                    WITH p
                    SKIP $skip LIMIT $limit

                    MATCH (a:AdminDivision {featureCode: 'ADM1', countryCode: p.countryCode, admin1Code: p.admin1Code})
                    MERGE (p)-[:LOCATED_IN_ADMIN1]->(a)
                    RETURN count(*) AS batch_linked
                """, country=country_code, skip=skip, limit=self.batch_size)

                batch_linked = result.single()['batch_linked']
                linked += batch_linked

        return linked

    def _link_mega_country_by_admin1(self, country_code: str):
        """Process mega-countries by admin1 region (state/province)."""

        with self.driver.session() as session:
            # Get list of admin1 codes in this country
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = $country
                  AND p.admin1Code IS NOT NULL
                  AND p.featureClass <> 'A'
                RETURN DISTINCT p.admin1Code AS admin1
            """, country=country_code)

            admin1_codes = [rec['admin1'] for rec in result]

            total_linked = 0

            # Process each admin1 region separately
            for admin1_code in admin1_codes:
                # Count places in this admin1 region
                result = session.run("""
                    MATCH (p:Place)
                    WHERE p.countryCode = $country
                      AND p.admin1Code = $admin1
                      AND p.featureClass <> 'A'
                    RETURN count(p) AS total
                """, country=country_code, admin1=admin1_code)

                region_total = result.single()['total']

                if region_total == 0:
                    continue

                # Process this admin1 region in batches
                for skip in range(0, region_total, self.batch_size):
                    result = session.run("""
                        MATCH (p:Place)
                        WHERE p.countryCode = $country
                          AND p.admin1Code = $admin1
                          AND p.featureClass <> 'A'
                        WITH p
                        SKIP $skip LIMIT $limit

                        MATCH (a:AdminDivision {featureCode: 'ADM1', countryCode: p.countryCode, admin1Code: p.admin1Code})
                        MERGE (p)-[:LOCATED_IN_ADMIN1]->(a)
                        RETURN count(*) AS batch_linked
                    """, country=country_code, admin1=admin1_code, skip=skip, limit=self.batch_size)

                    batch_linked = result.single()['batch_linked']
                    total_linked += batch_linked

            return total_linked

    def _link_ultra_mega_country_by_admin2(self, country_code: str):
        """Process ultra-mega countries by admin2 district for finest granularity."""

        with self.driver.session() as session:
            # Get list of admin1 regions
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = $country
                  AND p.admin1Code IS NOT NULL
                  AND p.featureClass <> 'A'
                RETURN DISTINCT p.admin1Code AS admin1
            """, country=country_code)

            admin1_codes = [rec['admin1'] for rec in result]

            total_linked = 0

            # For each admin1, get admin2 subdivisions
            for admin1_code in admin1_codes:
                # Get admin2 codes within this admin1
                result = session.run("""
                    MATCH (p:Place)
                    WHERE p.countryCode = $country
                      AND p.admin1Code = $admin1
                      AND p.admin2Code IS NOT NULL
                      AND p.featureClass <> 'A'
                    RETURN DISTINCT p.admin2Code AS admin2
                """, country=country_code, admin1=admin1_code)

                admin2_codes = [rec['admin2'] for rec in result]

                # Process each admin2 district separately (smallest chunks)
                for admin2_code in admin2_codes:
                    # Count places in this admin2 district
                    result = session.run("""
                        MATCH (p:Place)
                        WHERE p.countryCode = $country
                          AND p.admin1Code = $admin1
                          AND p.admin2Code = $admin2
                          AND p.featureClass <> 'A'
                        RETURN count(p) AS total
                    """, country=country_code, admin1=admin1_code, admin2=admin2_code)

                    district_total = result.single()['total']

                    if district_total == 0:
                        continue

                    # Process this admin2 district in batches
                    for skip in range(0, district_total, self.batch_size):
                        result = session.run("""
                            MATCH (p:Place)
                            WHERE p.countryCode = $country
                              AND p.admin1Code = $admin1
                              AND p.admin2Code = $admin2
                              AND p.featureClass <> 'A'
                            WITH p
                            SKIP $skip LIMIT $limit

                            MATCH (a:AdminDivision {featureCode: 'ADM1', countryCode: p.countryCode, admin1Code: p.admin1Code})
                            MERGE (p)-[:LOCATED_IN_ADMIN1]->(a)
                            RETURN count(*) AS batch_linked
                        """, country=country_code, admin1=admin1_code, admin2=admin2_code, skip=skip, limit=self.batch_size)

                        batch_linked = result.single()['batch_linked']
                        total_linked += batch_linked

            return total_linked

    def link_admin_divisions_hierarchically(self):
        """Link admin divisions to parent divisions - done globally since fewer nodes."""
        print("\nLinking admin division hierarchies...")

        with self.driver.session() as session:
            # Admin1 -> Country (small, can do all at once)
            result = session.run("""
                MATCH (a1:AdminDivision)
                WHERE a1.featureCode = 'ADM1'
                  AND a1.countryCode IS NOT NULL
                MERGE (c:Country {code: a1.countryCode})
                MERGE (a1)-[:PART_OF]->(c)
                RETURN count(*) AS linked
            """)
            admin1_country = result.single()['linked']
            print(f"  Admin1 -> Country: {admin1_country:,}")

            # Admin2 -> Admin1
            result = session.run("""
                MATCH (a2:AdminDivision)
                WHERE a2.featureCode = 'ADM2'
                  AND a2.admin1Code IS NOT NULL

                MATCH (a1:AdminDivision)
                WHERE a1.featureCode = 'ADM1'
                  AND a1.countryCode = a2.countryCode
                  AND a1.admin1Code = a2.admin1Code

                MERGE (a2)-[:PART_OF]->(a1)
                RETURN count(*) AS linked
            """)
            admin2_1 = result.single()['linked']
            print(f"  Admin2 -> Admin1: {admin2_1:,}")

            # Admin3 -> Admin2
            result = session.run("""
                MATCH (a3:AdminDivision)
                WHERE a3.featureCode = 'ADM3'
                  AND a3.admin2Code IS NOT NULL

                MATCH (a2:AdminDivision)
                WHERE a2.featureCode = 'ADM2'
                  AND a2.countryCode = a3.countryCode
                  AND a2.admin1Code = a3.admin1Code
                  AND a2.admin2Code = a3.admin2Code

                MERGE (a3)-[:PART_OF]->(a2)
                RETURN count(*) AS linked
            """)
            admin3_2 = result.single()['linked']
            print(f"  Admin3 -> Admin2: {admin3_2:,}")

    def print_statistics(self):
        """Print hierarchy statistics."""
        print("\n" + "="*60)
        print("ADMINISTRATIVE HIERARCHY STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # AdminDivision nodes
            result = session.run("""
                MATCH (a:AdminDivision)
                RETURN a.featureCode AS level, count(a) AS count
                ORDER BY level
            """)
            print("\nAdminDivision nodes:")
            for record in result:
                print(f"  {record['level']}: {record['count']:,}")

            # Relationships
            result = session.run("MATCH ()-[r:LOCATED_IN_ADMIN1]->() RETURN count(r) AS c")
            admin1_rels = result.single()['c']

            result = session.run("MATCH ()-[r:PART_OF]->() RETURN count(r) AS c")
            part_of_rels = result.single()['c']

            print(f"\nRelationships:")
            print(f"  Places -> Admin1: {admin1_rels:,}")
            print(f"  Admin hierarchies: {part_of_rels:,}")

            # Sample paths
            print("\nSample hierarchies:")
            result = session.run("""
                MATCH path = (p:Place)-[:LOCATED_IN_ADMIN1|PART_OF*1..3]->(c:Country)
                WHERE p.population > 100000
                WITH p, [n in nodes(path)[1..-1] | n.name] AS hierarchy
                RETURN p.name AS place, hierarchy
                ORDER BY p.population DESC
                LIMIT 5
            """)
            for record in result:
                hierarchy_str = " -> ".join([str(h) for h in record['hierarchy']])
                print(f"  {record['place']} -> {hierarchy_str}")

        print("="*60)

    def build_all(self):
        """Execute complete hierarchy building with resume capability."""
        print("="*60)
        print("BUILDING ADMINISTRATIVE HIERARCHIES (Ultra-Robust)")
        print("="*60)
        print("Adaptive chunking: <50K normal, 50-500K admin1, >500K admin2")

        # Step 1: Create indexes
        self.create_indexes()

        # Step 2: Get country list (excluding completed)
        countries = self.get_country_list()

        if not countries:
            print("\n✓ All countries already processed!")
            self.link_admin_divisions_hierarchically()
            self.print_statistics()
            return

        # Step 3: Process each country with error handling
        print(f"\nProcessing {len(countries)} countries...")
        total_admin_created = 0
        total_links_created = 0

        for country in tqdm(countries, desc="Countries"):
            try:
                # Create admin divisions
                admin_created = self.create_admin_divisions_for_country(country)
                total_admin_created += admin_created

                # Link places to admin1
                links_created = self.link_places_to_admin1_for_country(country)
                total_links_created += links_created

                if admin_created > 0 or links_created > 0:
                    tqdm.write(f"  {country}: {admin_created:,} admin divs, {links_created:,} links")

                # Mark as completed and save state
                self.state["completed_countries"].append(country)
                self.save_state()

            except Exception as e:
                tqdm.write(f"  ✗ {country}: FAILED - {str(e)[:100]}")
                self.state["failed_countries"].append({"country": country, "error": str(e)})
                self.save_state()
                continue  # Skip to next country

        print(f"\n✓ Created {total_admin_created:,} AdminDivision nodes")
        print(f"✓ Created {total_links_created:,} LOCATED_IN_ADMIN1 relationships")

        if self.state.get("failed_countries"):
            print(f"\n⚠ Failed countries: {len(self.state['failed_countries'])}")
            for failed in self.state["failed_countries"][:5]:
                print(f"    {failed['country']}: {failed['error'][:80]}")

        # Step 4: Link admin divisions hierarchically
        self.link_admin_divisions_hierarchically()

        # Step 5: Print statistics
        self.print_statistics()

        print("\n✓ Administrative hierarchy building complete!")


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    builder = AdminHierarchyBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        builder.build_all()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress is saved.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
    finally:
        builder.close()


if __name__ == '__main__':
    main()
