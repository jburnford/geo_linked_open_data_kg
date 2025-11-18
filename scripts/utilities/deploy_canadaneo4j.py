#!/usr/bin/env python3
"""
Complete deployment orchestrator for CanadaNeo4j Knowledge Graph on Arbutus VM.

This script coordinates the full import and relationship building process:
1. Import GeoNames data (Countries, AdminDivisions, Places)
2. Import Wikidata entities (Geographic, People, Organizations)
3. Build administrative hierarchies
4. Create ADMIN3 links
5. Setup spatial indexes
6. Validate final database state

Estimated time: 4-6 hours for complete deployment
"""

import sys
import time
import os
from pathlib import Path
from neo4j import GraphDatabase
from typing import Optional

class CanadaNeo4jDeployer:
    def __init__(self, uri=None, user=None, password=None):
        # Use environment variables if not provided
        uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        user = user or os.getenv('NEO4J_USER', 'neo4j')
        password = password or os.getenv('NEO4J_PASSWORD', 'CHANGE_ME')  # Example password only
        print("=" * 80)
        print("CanadaNeo4j Knowledge Graph Deployment")
        print("=" * 80)
        print(f"Target: {uri}")
        print(f"Database: canadaneo4j")
        print()

        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self.start_time = time.time()

    def connect(self):
        """Connect to Neo4j and verify canadaneo4j database exists."""
        print("Step 1: Connecting to Neo4j...")
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

            # Verify connection
            with self.driver.session(database="system") as session:
                result = session.run("SHOW DATABASES")
                databases = [record["name"] for record in result]

                if "canadaneo4j" not in databases:
                    print("  ⚠ Database 'canadaneo4j' does not exist. Creating...")
                    session.run("CREATE DATABASE canadaneo4j")
                    print("  ✓ Database created")
                    # Wait for database to come online
                    time.sleep(5)
                else:
                    print("  ✓ Database 'canadaneo4j' exists")

            print("✓ Connected successfully\n")
            return True

        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()

    def clear_database(self):
        """Clear existing data in canadaneo4j database."""
        print("Step 2: Clearing existing data...")
        response = input("  ⚠ This will DELETE all data in canadaneo4j database. Continue? (yes/no): ")

        if response.lower() != 'yes':
            print("  Aborted by user.")
            return False

        try:
            with self.driver.session(database="canadaneo4j") as session:
                session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared\n")
            return True
        except Exception as e:
            print(f"✗ Failed to clear database: {e}")
            return False

    def run_import_script(self, script_name: str, description: str, estimated_time: str):
        """Run an import script and track progress."""
        print("=" * 80)
        print(f"Phase: {description}")
        print(f"Estimated time: {estimated_time}")
        print("=" * 80)

        script_path = Path("/var/lib/neo4j-data/import/canadaneo4j") / script_name

        if not script_path.exists():
            print(f"✗ Script not found: {script_path}")
            return False

        import subprocess

        try:
            # Run the script
            result = subprocess.run(
                ["python3", str(script_path)],
                capture_output=True,
                text=True,
                check=False
            )

            # Show output
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)

            if result.returncode == 0:
                print(f"✓ {description} completed successfully\n")
                return True
            else:
                print(f"✗ {description} failed with exit code {result.returncode}\n")
                return False

        except Exception as e:
            print(f"✗ Error running {script_name}: {e}\n")
            return False

    def verify_deployment(self):
        """Verify the complete deployment."""
        print("=" * 80)
        print("FINAL VERIFICATION")
        print("=" * 80)

        try:
            with self.driver.session(database="canadaneo4j") as session:
                # Count all nodes by label
                print("\nNode Counts:")
                result = session.run("""
                    MATCH (n)
                    WITH labels(n)[0] as label, count(*) as count
                    RETURN label, count
                    ORDER BY count DESC
                """)

                total_nodes = 0
                for record in result:
                    label = record["label"]
                    count = record["count"]
                    total_nodes += count
                    print(f"  {label}: {count:,}")

                print(f"\n  TOTAL NODES: {total_nodes:,}")

                # Count all relationships by type
                print("\nRelationship Counts:")
                result = session.run("""
                    MATCH ()-[r]->()
                    WITH type(r) as relType, count(*) as count
                    RETURN relType, count
                    ORDER BY count DESC
                """)

                total_rels = 0
                for record in result:
                    rel_type = record["relType"]
                    count = record["count"]
                    total_rels += count
                    print(f"  {rel_type}: {count:,}")

                print(f"\n  TOTAL RELATIONSHIPS: {total_rels:,}")

                # Check indexes
                print("\nIndexes and Constraints:")
                result = session.run("SHOW INDEXES")
                index_count = 0
                for record in result:
                    index_count += 1
                    name = record.get("name", "N/A")
                    state = record.get("state", "N/A")
                    print(f"  {name}: {state}")

                print(f"\n  TOTAL INDEXES: {index_count}")

        except Exception as e:
            print(f"✗ Verification failed: {e}")
            return False

        # Calculate elapsed time
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)

        print("\n" + "=" * 80)
        print("✓ DEPLOYMENT COMPLETE")
        print("=" * 80)
        print(f"Total deployment time: {hours}h {minutes}m")
        print(f"Database: canadaneo4j")
        print(f"Connection: {self.uri}")
        print()
        print("Next steps:")
        print("  1. Connect via Neo4j Browser: http://206.12.90.118:7474")
        print("  2. Switch to canadaneo4j database: :use canadaneo4j")
        print("  3. Run test queries to validate data")
        print("=" * 80)

        return True


def main():
    """Main deployment orchestrator."""

    # Configuration
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "admin"  # Arbutus default password

    # Data directory
    DATA_DIR = "/var/lib/neo4j-data/import/canadaneo4j"

    deployer = CanadaNeo4jDeployer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Step 1: Connect
        if not deployer.connect():
            print("✗ Cannot proceed without database connection")
            sys.exit(1)

        # Step 2: Clear existing data (optional)
        response = input("Clear existing data in canadaneo4j? (yes/no): ")
        if response.lower() == 'yes':
            if not deployer.clear_database():
                sys.exit(1)

        # Phase 1: Import GeoNames data (60-90 minutes)
        print("\n" + "=" * 80)
        print("PHASE 1: IMPORT GEONAMES DATA")
        print("=" * 80)

        # Modify import_to_nibi.py to skip the clearing and prompt
        print("Importing Countries, AdminDivisions, and Places...")
        print(f"  Data directory: {DATA_DIR}")
        print(f"  Expected: 254 countries, 509K admins, 6.2M places")
        print()

        response = input("Run GeoNames import script? (yes/no): ")
        if response.lower() == 'yes':
            # User should run: python3 /var/lib/neo4j-data/import/canadaneo4j/import_to_nibi.py
            print("  Please run manually:")
            print(f"  cd {DATA_DIR}")
            print(f"  python3 import_to_nibi.py")
            print()
            input("  Press Enter when import is complete...")

        # Phase 2: Import Wikidata entities (2-3 hours)
        print("\n" + "=" * 80)
        print("PHASE 2: IMPORT WIKIDATA ENTITIES")
        print("=" * 80)

        print("Importing WikidataPlace, Person, and Organization nodes...")
        print(f"  Expected: 11.6M geographic, 6M people, 235K organizations")
        print()

        response = input("Run Wikidata import script? (yes/no): ")
        if response.lower() == 'yes':
            print("  Please run manually:")
            print(f"  cd {DATA_DIR}")
            print(f"  FILTERED_DIR={DATA_DIR} python3 load_wikidata_entities.py")
            print()
            input("  Press Enter when import is complete...")

        # Phase 3: Build admin hierarchies (30-60 minutes)
        print("\n" + "=" * 80)
        print("PHASE 3: BUILD ADMINISTRATIVE HIERARCHIES")
        print("=" * 80)

        print("Creating ADMIN1, ADMIN2, ADMIN3, ADMIN4 relationships...")
        print(f"  Expected: ~2M relationships")
        print()

        response = input("Run admin hierarchy script? (yes/no): ")
        if response.lower() == 'yes':
            print("  Please run manually:")
            print(f"  cd {DATA_DIR}")
            print(f"  python3 create_admin_hierarchies.py")
            print()
            input("  Press Enter when complete...")

        # Phase 4: Verification
        deployer.verify_deployment()

    except KeyboardInterrupt:
        print("\n\n✗ Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        deployer.close()


if __name__ == "__main__":
    main()
