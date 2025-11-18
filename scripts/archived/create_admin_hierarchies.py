#!/usr/bin/env python3
"""
Create administrative hierarchy relationships from GeoNames data.

Uses admin codes to link:
- Places to admin divisions (admin1Code, admin2Code, admin3Code, admin4Code)
- Admin divisions to countries

Examples:
- Seattle -> Washington State -> United States
- Toronto -> Ontario -> Canada
- Mumbai -> Maharashtra -> India
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class AdminHierarchyBuilder:
    """Build administrative hierarchy relationships."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_admin_division_nodes(self):
        """
        Create AdminDivision nodes from GeoNames admin features.

        Feature codes: A.ADM1, A.ADM2, A.ADM3, A.ADM4, A.ADMD
        """
        print("\nCreating AdminDivision nodes from GeoNames admin features...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.featureClass = 'A'
                  AND p.featureCode IN ['ADM1', 'ADM2', 'ADM3', 'ADM4', 'ADMD']
                WITH p
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
                RETURN count(a) AS created
            """)

            created = result.single()['created']
            print(f"✓ Created {created:,} AdminDivision nodes")

    def link_places_to_admin1(self):
        """Link places to their first-level admin division (state/province)."""
        print("\nLinking places to Admin1 divisions (states/provinces)...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin1Code IS NOT NULL
                  AND p.countryCode IS NOT NULL
                  AND p.featureClass <> 'A'  // Don't link admin divisions to themselves

                MATCH (a:AdminDivision)
                WHERE a.featureCode = 'ADM1'
                  AND a.countryCode = p.countryCode
                  AND a.admin1Code = p.admin1Code

                MERGE (p)-[:LOCATED_IN_ADMIN1]->(a)

                RETURN count(*) AS linked
            """)

            linked = result.single()['linked']
            print(f"✓ Created {linked:,} LOCATED_IN_ADMIN1 relationships")

    def link_places_to_admin2(self):
        """Link places to their second-level admin division (county/district)."""
        print("\nLinking places to Admin2 divisions (counties/districts)...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin2Code IS NOT NULL
                  AND p.admin1Code IS NOT NULL
                  AND p.countryCode IS NOT NULL
                  AND p.featureClass <> 'A'

                MATCH (a:AdminDivision)
                WHERE a.featureCode = 'ADM2'
                  AND a.countryCode = p.countryCode
                  AND a.admin1Code = p.admin1Code
                  AND a.admin2Code = p.admin2Code

                MERGE (p)-[:LOCATED_IN_ADMIN2]->(a)

                RETURN count(*) AS linked
            """)

            linked = result.single()['linked']
            print(f"✓ Created {linked:,} LOCATED_IN_ADMIN2 relationships")

    def link_places_to_admin3(self):
        """Link places to their third-level admin division."""
        print("\nLinking places to Admin3 divisions...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.admin3Code IS NOT NULL
                  AND p.admin2Code IS NOT NULL
                  AND p.admin1Code IS NOT NULL
                  AND p.countryCode IS NOT NULL
                  AND p.featureClass <> 'A'

                MATCH (a:AdminDivision)
                WHERE a.featureCode = 'ADM3'
                  AND a.countryCode = p.countryCode
                  AND a.admin1Code = p.admin1Code
                  AND a.admin2Code = p.admin2Code
                  AND a.admin3Code = p.admin3Code

                MERGE (p)-[:LOCATED_IN_ADMIN3]->(a)

                RETURN count(*) AS linked
            """)

            linked = result.single()['linked']
            print(f"✓ Created {linked:,} LOCATED_IN_ADMIN3 relationships")

    def link_admin_divisions_hierarchically(self):
        """Link admin divisions to their parent divisions."""
        print("\nCreating hierarchical links between admin divisions...")

        with self.driver.session() as session:
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
            admin2_to_1 = result.single()['linked']
            print(f"  Admin2 -> Admin1: {admin2_to_1:,} relationships")

            # Admin3 -> Admin2
            result = session.run("""
                MATCH (a3:AdminDivision)
                WHERE a3.featureCode = 'ADM3'
                  AND a3.admin2Code IS NOT NULL
                  AND a3.admin1Code IS NOT NULL

                MATCH (a2:AdminDivision)
                WHERE a2.featureCode = 'ADM2'
                  AND a2.countryCode = a3.countryCode
                  AND a2.admin1Code = a3.admin1Code
                  AND a2.admin2Code = a3.admin2Code

                MERGE (a3)-[:PART_OF]->(a2)

                RETURN count(*) AS linked
            """)
            admin3_to_2 = result.single()['linked']
            print(f"  Admin3 -> Admin2: {admin3_to_2:,} relationships")

            # Admin4 -> Admin3
            result = session.run("""
                MATCH (a4:AdminDivision)
                WHERE a4.featureCode = 'ADM4'
                  AND a4.admin3Code IS NOT NULL
                  AND a4.admin2Code IS NOT NULL
                  AND a4.admin1Code IS NOT NULL

                MATCH (a3:AdminDivision)
                WHERE a3.featureCode = 'ADM3'
                  AND a3.countryCode = a4.countryCode
                  AND a3.admin1Code = a4.admin1Code
                  AND a3.admin2Code = a4.admin2Code
                  AND a3.admin3Code = a4.admin3Code

                MERGE (a4)-[:PART_OF]->(a3)

                RETURN count(*) AS linked
            """)
            admin4_to_3 = result.single()['linked']
            print(f"  Admin4 -> Admin3: {admin4_to_3:,} relationships")

            # Admin1 -> Country
            result = session.run("""
                MATCH (a1:AdminDivision)
                WHERE a1.featureCode = 'ADM1'
                  AND a1.countryCode IS NOT NULL

                MERGE (c:Country {code: a1.countryCode})
                MERGE (a1)-[:PART_OF]->(c)

                RETURN count(*) AS linked
            """)
            admin1_to_country = result.single()['linked']
            print(f"  Admin1 -> Country: {admin1_to_country:,} relationships")

    def print_statistics(self):
        """Print hierarchy statistics."""
        print("\n" + "="*60)
        print("ADMINISTRATIVE HIERARCHY STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Count AdminDivision nodes
            result = session.run("""
                MATCH (a:AdminDivision)
                RETURN a.featureCode AS level, count(a) AS count
                ORDER BY level
            """)
            print("\nAdminDivision nodes:")
            for record in result:
                print(f"  {record['level']}: {record['count']:,}")

            # Count relationships
            result = session.run("""
                MATCH ()-[r:LOCATED_IN_ADMIN1]->()
                RETURN count(r) AS count
            """)
            admin1_links = result.single()['count']

            result = session.run("""
                MATCH ()-[r:LOCATED_IN_ADMIN2]->()
                RETURN count(r) AS count
            """)
            admin2_links = result.single()['count']

            result = session.run("""
                MATCH ()-[r:LOCATED_IN_ADMIN3]->()
                RETURN count(r) AS count
            """)
            admin3_links = result.single()['count']

            result = session.run("""
                MATCH ()-[r:PART_OF]->()
                RETURN count(r) AS count
            """)
            part_of_links = result.single()['count']

            print("\nRelationships:")
            print(f"  Places -> Admin1: {admin1_links:,}")
            print(f"  Places -> Admin2: {admin2_links:,}")
            print(f"  Places -> Admin3: {admin3_links:,}")
            print(f"  Admin divisions hierarchical: {part_of_links:,}")

            # Sample queries
            print("\nSample hierarchies:")
            result = session.run("""
                MATCH path = (p:Place)-[:LOCATED_IN_ADMIN1|LOCATED_IN_ADMIN2|PART_OF*1..3]->(c:Country)
                WHERE p.featureCode = 'PPLA'  // State capitals
                RETURN p.name AS place,
                       [n in nodes(path)[1..-1] | n.name] AS hierarchy
                LIMIT 5
            """)
            for record in result:
                hierarchy_str = " -> ".join(record['hierarchy'])
                print(f"  {record['place']} -> {hierarchy_str}")

        print("="*60)

    def build_all(self):
        """Execute complete hierarchy building process."""
        print("="*60)
        print("BUILDING ADMINISTRATIVE HIERARCHIES")
        print("="*60)

        self.create_admin_division_nodes()
        self.link_places_to_admin1()
        self.link_places_to_admin2()
        self.link_places_to_admin3()
        self.link_admin_divisions_hierarchically()
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
    finally:
        builder.close()


if __name__ == '__main__':
    main()
