#!/usr/bin/env python3
"""
Load Indian Affairs Agents into Neo4j and link to existing Place nodes.

Creates:
- IndianAffairsAgent nodes (2,468 persons)
- WORKED_AT relationships → Place nodes (via GeoNames IDs)
- HAS_OCCUPATION relationships → Occupation nodes

Integration with existing CanadaNeo4j:
- Links to Place nodes (6.2M from GeoNames)
- Links to WikidataPlace nodes if Wikidata QIDs present
- Can extend to link Person nodes later if name matching added
"""

import json
import os
from neo4j import GraphDatabase
from tqdm import tqdm


class IndianAffairsLoader:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = 500

    def close(self):
        self.driver.close()

    def create_indexes(self):
        """Create indexes for IndianAffairsAgent nodes."""
        print("\\nCreating indexes...")

        with self.driver.session(database="canadaneo4j") as session:
            indexes = [
                "CREATE CONSTRAINT agent_lincs_id IF NOT EXISTS FOR (a:IndianAffairsAgent) REQUIRE a.lincsId IS UNIQUE",
                "CREATE INDEX agent_name IF NOT EXISTS FOR (a:IndianAffairsAgent) ON (a.name)",
                "CREATE INDEX agent_role IF NOT EXISTS FOR (a:IndianAffairsAgent) ON (a.roles)",
            ]

            for idx in indexes:
                try:
                    session.run(idx)
                    print(f"  ✓ {idx.split('IF')[0].strip()}")
                except Exception as e:
                    print(f"  ⚠ {str(e)[:100]}")

    def load_agents(self, json_file: str):
        """
        Load Indian Affairs agents from parsed JSON.

        Creates agent nodes and links them to Place nodes via GeoNames IDs.
        """
        print(f"\\nLoading agents from {json_file}...")

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            persons = data["persons"]

        print(f"Found {len(persons):,} persons with occupation data")

        # Process in batches
        total_agents = 0
        total_links = 0

        with self.driver.session(database="canadaneo4j") as session:
            for i in tqdm(range(0, len(persons), self.batch_size), desc="Loading agents"):
                batch = persons[i:i + self.batch_size]

                # Prepare batch data
                agent_batch = []
                for person in batch:
                    # Collect unique roles
                    roles = list(set([occ['role'] for occ in person['occupations'] if occ['role']]))

                    # Collect unique GeoNames IDs
                    geonames_ids = list(set([occ['geonamesId'] for occ in person['occupations'] if occ['geonamesId']]))

                    # Collect date ranges
                    start_dates = [occ['startDate'] for occ in person['occupations'] if occ['startDate']]
                    earliest_date = min(start_dates) if start_dates else None

                    agent_batch.append({
                        'lincsId': person['lincsId'],
                        'name': person['name'],
                        'wikidataQid': person['wikidataQid'],
                        'viafId': person['viafId'],
                        'roles': roles,
                        'geonamesIds': geonames_ids,
                        'earliestDate': earliest_date,
                        'occupationCount': len(person['occupations'])
                    })

                # Create agent nodes
                result = session.run("""
                    UNWIND $batch AS agent
                    MERGE (a:IndianAffairsAgent {lincsId: agent.lincsId})
                    SET a.name = agent.name,
                        a.wikidataQid = agent.wikidataQid,
                        a.viafId = agent.viafId,
                        a.roles = agent.roles,
                        a.geonamesIds = agent.geonamesIds,
                        a.earliestDate = agent.earliestDate,
                        a.occupationCount = agent.occupationCount
                    RETURN count(a) as count
                """, batch=agent_batch)

                batch_count = result.single()['count']
                total_agents += batch_count

                # Create relationships to Place nodes
                result = session.run("""
                    UNWIND $batch AS agent
                    MATCH (a:IndianAffairsAgent {lincsId: agent.lincsId})
                    UNWIND agent.geonamesIds AS geonamesId
                    MATCH (p:Place {geonameId: geonamesId})
                    MERGE (a)-[:WORKED_AT]->(p)
                    RETURN count(*) as linkedCount
                """, batch=agent_batch)

                batch_links = result.single()['linkedCount']
                total_links += batch_links

        print(f"\\n✓ Created {total_agents:,} IndianAffairsAgent nodes")
        print(f"✓ Created {total_links:,} WORKED_AT relationships to Place nodes")

        return total_agents, total_links

    def link_to_wikidata(self):
        """Link agents with Wikidata QIDs to existing Person/WikidataPlace nodes."""
        print("\\nLinking agents to Wikidata entities...")

        with self.driver.session(database="canadaneo4j") as session:
            # Link to Person nodes
            result = session.run("""
                MATCH (a:IndianAffairsAgent)
                WHERE a.wikidataQid IS NOT NULL
                MATCH (p:Person {qid: a.wikidataQid})
                MERGE (a)-[:SAME_AS]->(p)
                RETURN count(*) as count
            """)
            person_links = result.single()['count']

            # Link to WikidataPlace nodes (for places of work)
            result = session.run("""
                MATCH (a:IndianAffairsAgent)-[:WORKED_AT]->(place:Place)
                WHERE place.geonameId IN a.geonamesIds
                MATCH (w:WikidataPlace {geonamesId: place.geonameId})
                MERGE (a)-[:WORKED_AT_WIKIDATA]->(w)
                RETURN count(*) as count
            """)
            wikiplace_links = result.single()['count']

            print(f"  Person links: {person_links:,}")
            print(f"  WikidataPlace links: {wikiplace_links:,}")

            return person_links, wikiplace_links

    def print_statistics(self):
        """Print statistics about the import."""
        print("\\n" + "="*60)
        print("INDIAN AFFAIRS AGENTS IMPORT STATISTICS")
        print("="*60)

        with self.driver.session(database="canadaneo4j") as session:
            # Count agents
            result = session.run("MATCH (a:IndianAffairsAgent) RETURN count(a) as count")
            agent_count = result.single()['count']

            # Count relationships
            result = session.run("MATCH (:IndianAffairsAgent)-[r:WORKED_AT]->() RETURN count(r) as count")
            worked_at_count = result.single()['count']

            result = session.run("MATCH (:IndianAffairsAgent)-[r:SAME_AS]->() RETURN count(r) as count")
            same_as_count = result.single()['count']

            # Top roles
            result = session.run("""
                MATCH (a:IndianAffairsAgent)
                UNWIND a.roles AS role
                RETURN role, count(*) as count
                ORDER BY count DESC
                LIMIT 10
            """)
            top_roles = list(result)

            # Top locations
            result = session.run("""
                MATCH (a:IndianAffairsAgent)-[:WORKED_AT]->(p:Place)
                RETURN p.name AS place, p.geonameId AS geonameId, count(a) AS agentCount
                ORDER BY agentCount DESC
                LIMIT 10
            """)
            top_locations = list(result)

            print(f"\\nAgent nodes: {agent_count:,}")
            print(f"WORKED_AT relationships: {worked_at_count:,}")
            print(f"SAME_AS relationships (to Wikidata): {same_as_count:,}")

            print("\\nTop 10 roles:")
            for rec in top_roles:
                print(f"  {rec['role']}: {rec['count']:,}")

            print("\\nTop 10 work locations:")
            for rec in top_locations:
                print(f"  {rec['place']} (GeoNames {rec['geonameId']}): {rec['agentCount']:,} agents")

        print("="*60)

    def run_import(self, json_file: str):
        """Execute complete import process."""
        print("="*60)
        print("IMPORTING INDIAN AFFAIRS AGENTS")
        print("="*60)

        self.create_indexes()
        self.load_agents(json_file)
        self.link_to_wikidata()
        self.print_statistics()

        print("\\n✓ Indian Affairs Agents import complete!")


def main():
    import sys

    # Get connection details from environment or arguments
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'historicalkg2025')

    json_file = sys.argv[1] if len(sys.argv) > 1 else "indian_affairs_agents.json"

    loader = IndianAffairsLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        loader.run_import(json_file)
    except Exception as e:
        print(f"\\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()
